"""Reproducible adversarial QASM corpus; broken artifacts are intentional."""
import argparse
import json
from pathlib import Path
from qiskit import QuantumCircuit
from .fixtures import fixtures
from .analysis import analyze
from .compiler import compile_early_measure, compile_deterministic, corrected_source, save_qasm
from .verifier import verify, verify_source_retry


def cases():
    r=next(fixtures());p=.9;n=32
    yield 'valid_rare_timeout',compile_early_measure(r.target,p,n),r.target,p,n,False,None
    q=compile_early_measure(r.target,p,n)
    with q.if_test((q.clbits[0],False)):q.reset(1)
    yield 'rare_timeout_reset',q,r.target,p,n,False,('CONDITIONAL_STATE_MISMATCH','timeout')
    q=compile_early_measure(r.target,p,n)
    with q.if_test((q.clbits[0],False)):
        q.x(2);q.measure(2,0)
    yield 'rare_timeout_erased',q,r.target,p,n,False,('MISSING_BRANCH','timeout')
    yield 'wrong_retry_cap',compile_early_measure(r.target,.625,1),r.target,.625,2,False,('BRANCH_PROBABILITY_MISMATCH','timeout')
    yield 'controlled_phase_error',compile_deterministic(-r.target),r.target,1.,1,False,('CONDITIONAL_STATE_MISMATCH','success')
    q=compile_early_measure(r.target,.625,1);q.x(2);q.measure(2,0)
    yield 'wrong_success_flag',q,r.target,.625,1,False,('BRANCH_PROBABILITY_MISMATCH','success')
    analysis=analyze(r);a=r.trial.num_qubits-1
    q=corrected_source(r,analysis)
    retry=QuantumCircuit(a+1,a);retry.reset(range(a));retry.compose(corrected_source(r,analysis,False),inplace=True)
    q.if_else((q.cregs[0],0),QuantumCircuit(a+1,a),retry,q.qubits,q.clbits)
    yield 'source_missing_final_recovery',q,r.target,analysis['p'],2,True,('CONDITIONAL_STATE_MISMATCH','timeout')


def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);rows=[]
    for name,q,target,p,n,source,expected in cases():
        path=out/(name+'.qasm');save_qasm(q,path)
        timeout=(1-p)**n
        result=(verify_source_retry if source else verify)(path,target,1-timeout,timeout_probability=timeout)
        reasons={(x['code'],x['branch'],x['engine']) for x in result['failures']}
        met=result['verified'] if expected is None else not result['verified'] and all((expected[0],expected[1],engine) in reasons for engine in ('primary','independent'))
        rows.append({'case':name,'intentional_mutation':expected is not None,'qasm_file':path.name,
                     'expected_failure':None if expected is None else {'code':expected[0],'branch':expected[1]},
                     'expectation_met':met,'verification':result})
    report={'scope':'Ideal numerical adversarial checks; QASM parser and NumPy shared between engines.',
            'all_expectations_met':all(row['expectation_met'] for row in rows),'cases':rows}
    (out/'adversarial_report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    lines=['# Adversarial verification results','',
        'These QASM files deliberately include broken programs. They are test artifacts, not accepted repairs.','',
        '| Case | Intended behavior | Observed | Expected reason matched in both engines |',
        '|---|---|---|---|']
    for row in rows:
        expected=row['expected_failure']
        lines.append(f"| {row['case']} | {'Reject: '+expected['branch']+' '+expected['code'] if expected else 'Accept correct rare-timeout program'} | {'Accepted' if row['verification']['verified'] else 'Rejected'} | {'Yes' if row['expectation_met'] else 'NO'} |")
    rare=next(row for row in rows if row['case']=='rare_timeout_reset')['verification']
    lines += ['',f"Rare timeout reset: timeout probability {rare['timeout_probability']:.4e}; absolute timeout residual {rare['timeout_residual']:.4e}; primary conditional timeout residual {rare['primary_timeout_conditional_residual']:.4f}.",
              '', 'The absolute 1e-9 threshold alone misses this state corruption. Conditioning on the rare timeout exposes it. See JSON for both engines, relative probabilities, and all failure reasons.']
    (out/'ADVERSARIAL_RESULTS.md').write_text('\n'.join(lines)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',default='results/adversarial')
    report=run(parser.parse_args().out)
    print(json.dumps({'cases':len(report['cases']),'all_expectations_met':report['all_expectations_met']}))
    return 0 if report['all_expectations_met'] else 1


if __name__=='__main__':
    raise SystemExit(main())
