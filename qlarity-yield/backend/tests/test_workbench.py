import io, json, sys, time, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend.app.workbench import Scenario, analyze, domain, variants, decision, continuous_reference, identity
from backend.app.classical.monte_carlo import clopper_pearson

@pytest.mark.parametrize('ci,target,expected',[([.1,.2],.2,'meets modeled target'),([.21,.3],.2,'misses modeled target'),([.1,.3],.2,'unresolved'),([.2,.3],.2,'unresolved')])
def test_decision_boundary(ci,target,expected): assert decision(ci,target)==expected

def test_known_encoding_disagreement():
    r=analyze(Scenario(quantum=False,compare=False))
    assert r['reference']['discrete_float']==.3125
    assert r['reference']['encoded']==.25
    assert r['approximation']['disagreement_mass']==.0625
    assert all(x['target_id']==r['target_id']+':encoded' for x in r['results'])
    assert r['results'][0]['decision']=='unresolved'
    assert r['approximation']['score_error_observed']<=r['approximation']['score_error_bound']

def test_interventions_only_change_declared_sigmas():
    s=Scenario(); rows=variants(s)
    assert rows[1].sigma_L_nm==2.25 and rows[1].sigma_vth_mV==15
    assert rows[2].sigma_L_nm==3 and rows[2].sigma_vth_mV==11.25
    for row in rows:
        for k in ['I_limit_A','temperature_K','sigma_tox_nm','scale','alpha','max_failure_probability']:
            assert getattr(row,k)==getattr(s,k)

def test_zero_failures_have_uncertainty():
    assert clopper_pearson(0,100)[1]>0
    r=analyze(Scenario(quantum=False,I_limit_A=1e-6))
    for x in r['results'][2:]: assert x['ci'][1]>0

@pytest.mark.parametrize('bins',[2,4,8,16])
def test_conditional_cdf_and_rounding(bins):
    r=analyze(Scenario(quantum=False,bins=bins,scale=16,samples=256))
    assert abs(r['results'][0]['p_fail']-r['results'][1]['p_fail'])<1e-12
    assert sum(x['weight'] for x in r['population'])==pytest.approx(1)
    a=r['approximation'];assert a['float_probability_bracket'][0]<=r['reference']['discrete_float']<=a['float_probability_bracket'][1]

def test_quantum_limits():
    with pytest.raises(ValueError): Scenario(bins=8)
    with pytest.raises(ValueError): Scenario(scale=500)
    with pytest.raises(ValueError): Scenario(sigma_L_nm=float('nan'))

def test_target_identity():
    a=Scenario();assert identity(a)==identity(a.model_copy(update={'seed':1,'samples':1024}))
    assert identity(a)!=identity(a.model_copy(update={'scale':16}))

def test_continuous_resolution():
    s=Scenario(quantum=False,bins=16)
    c=continuous_reference(s)['p_fail'];r=analyze(s)
    assert abs(c-r['reference']['discrete_float'])<.03

def test_quantum_ledger_and_nontrivial_oracle():
    from backend.app.quantum.oracle import build_oracle,validate_grover_power_identity
    from backend.app.quantum.iqae import run_iqae
    s=Scenario(compare=False);d,op,j,q=domain(s)
    oracle=build_oracle(j,q,validate=True)
    assert oracle.validation_passed,oracle.validation_notes
    notes=validate_grover_power_identity(oracle,.25,max_k=2)
    assert not any('FAIL' in x for x in notes)
    r=run_iqae(oracle,epsilon_target=.05,default_shots=256,seed=42,exact_p_fail=.25)
    assert len(r.powers)==len(r.executed_rounds)
    assert r.NA_our_count==sum(x['shots']*(2*x['k']+1) for x in r.executed_rounds)
    assert r.num_oracle_queries==sum(x['shots']*x['k'] for x in r.executed_rounds)
    assert all(sum(x['counts'].values())==x['shots'] for x in r.executed_rounds)
    assert r.p_fail_ci_lower<=.25<=r.p_fail_ci_upper
    assert all('OPENQASM 3' in x for x in r.circuits.values())

def test_live_api_and_exports():
    from backend.serve import app,JOBS
    JOBS.clear()
    with TestClient(app) as c:
        assert c.get('/').status_code==200
        assert c.get('/api/model').json()['default_scenario']['I_limit_A']==1.25e-10
        payload={'quantum':False,'compare':False,'samples':256}
        headers={'Idempotency-Key':'test-once'}
        r=c.post('/api/runs',json=payload,headers=headers);assert r.status_code==202,r.text
        jid=r.json()['id']
        assert c.post('/api/runs',json=payload,headers=headers).json()['id']==jid
        assert c.post('/api/runs',json={**payload,'seed':9},headers=headers).status_code==409
        for _ in range(200):
            job=c.get('/api/runs/'+jid).json()
            if job['status'] in ['completed','failed']:break
            time.sleep(.1)
        assert job['status']=='completed',job
        exported=c.get(f'/api/runs/{jid}/export/json').json()
        assert exported==job['result']
        z=zipfile.ZipFile(io.BytesIO(c.get(f'/api/runs/{jid}/export/zip').content))
        assert json.loads(z.read('result.json'))==exported
        assert 'results.csv' in z.namelist()
        assert c.post('/api/runs',json={'bins':8}).status_code==422
        assert c.post('/api/runs',json=payload,headers={'Origin':'https://other.example'}).status_code==403
        r=c.post('/api/runs',json={'adaptive':True}).json()
        stopped=c.delete('/api/runs/'+r['id']).json();assert stopped['status']=='cancelled'
        time.sleep(.2);assert c.get('/api/runs/'+r['id']).json()['status']=='cancelled'
        assert c.get(f"/api/runs/{r['id']}/export/json").status_code==409

def test_recorded_qasm_roundtrip():
    from pathlib import Path
    from qiskit import qasm3
    from qiskit.quantum_info import Statevector
    path=Path(__file__).parents[2]/'evidence/example.json'
    recorded=json.loads(path.read_text())
    for scenario in recorded['scenarios']:
        q=next(x['quantum'] for x in scenario['results'] if x['method']=='IQAE')
        circuit=qasm3.loads(q['circuits']['A'])
        p=Statevector(circuit).probabilities([6])[1]
        assert p==pytest.approx(scenario['reference']['encoded'],abs=1e-9)
        for round in q['executed_rounds']:
            c=qasm3.loads(q['circuits'][round['circuit_id']])
            assert c.num_qubits==round['qubits']

def test_benchmark_accuracy_and_coverage_are_separate():
    from backend.app.benchmark_report import summarize
    data={'runs':[{'scenario':{'epsilon':.05},'result':{'reference':{'encoded':.25},'results':[{'method':'example','p_fail':.3,'ci':[.28,.32],'elapsed_s':1.}]}}]}
    r=summarize(data)['rows'][0]
    assert r['within_accuracy_target']==1
    assert r['covered']==0
    assert r['coverage_binomial_interval'][1]>0

def test_adaptive_export_includes_intermediate_circuits():
    from backend.serve import bundle
    from pathlib import Path
    data=json.loads((Path(__file__).parents[2]/'evidence/example.json').read_text())
    first=data['scenarios'][0]
    first['adaptive']={'attempts':[{'step':1,'result':{'results':first['results']}}]}
    z=zipfile.ZipFile(io.BytesIO(bundle(data)))
    assert 'circuits/scenario_0/adaptive_step_1/A.qasm' in z.namelist()
    assert 'benchmark/benchmark-summary.json' in z.namelist()


def test_quantum_resource_estimator_and_comparison():
    from backend.app.benchmark_report import estimate_quantum_resources, estimate_and_compare_resources
    from backend.app.physics.leakage import NominalDevice, OperatingPoint
    from backend.app.physics.variations import default_joint_distribution
    from backend.app.physics.discretize import build_quantised_score
    from backend.app.quantum.oracle import build_oracle

    joint = default_joint_distribution()
    qmodel = build_quantised_score(joint, 1.25e-10, OperatingPoint(), NominalDevice(), scale=4.0)
    oracle_res = build_oracle(joint, qmodel, validate=False)
    A_qc = oracle_res.A_circuit

    q_res = estimate_quantum_resources(A_qc, n_input_qubits=6)
    assert q_res['total_qubits'] == 10
    assert q_res['ancilla_count'] == 4
    assert q_res['cnot_count'] > 0
    assert q_res['circuit_depth'] > 0

    comparison = estimate_and_compare_resources(
        A_qc,
        classical_evaluations=100000,
        total_oracle_calls=5000,
        n_input_qubits=6
    )
    assert comparison['Classical Evaluations'] == 100000
    assert comparison['Total Oracle Calls'] == 5000
    assert comparison['Estimated Circuit Depth'] == q_res['circuit_depth']
    assert comparison['Ancilla Count'] == 4
    assert comparison['2-Qubit Gate Count (CNOTs)'] == q_res['cnot_count']
    assert 'Comparative Analysis' in comparison
