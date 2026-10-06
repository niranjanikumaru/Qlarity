"""Post-freeze external examples. Run from the repository root."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from qiskit import QuantumCircuit, qasm3
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retryguard.analysis import analyze, retry_cap
from retryguard.compiler import native, compile_source_retry, save_qasm
from retryguard.fixtures import load_manifest
from retryguard.verifier import verify_source_retry, execute, choi_input, reduce, compare_branches
from retryguard.independent import branch_maps


def frozen_check(root=ROOT):
    baseline = json.loads((root/'evaluation/baseline_freeze.json').read_text())
    changed = [p for p, digest in {**baseline['sha256'], **baseline['frozen_contracts']}.items()
               if hashlib.sha256((root/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest() != digest]
    if changed:
        raise ValueError('FROZEN_BASELINE_CHANGED: ' + ', '.join(changed))
    return {'core_files_unchanged': len(baseline['sha256']), 'contracts_unchanged': len(baseline['frozen_contracts'])}


def build_adqc():
    """Source equations only; no analyzer feedback or generated repair here."""
    folder = ROOT/'evaluation/new_family'
    spec = json.loads((folder/'contract.json').read_text())
    beta = spec['beta']
    h = np.array([[1,1],[1,-1]])/np.sqrt(2)
    target = h @ np.diag([np.exp(1j*beta/2), np.exp(-1j*beta/2)])
    q = QuantumCircuit(2)
    q.h(0); q.cz(0,1); q.h(0); q.h(1); q.rz(-beta,0); q.h(0)
    save_qasm(native(q), folder/'trial.qasm')
    manifest = [{'name':spec['name'], 'qasm':'trial.qasm', 'target_real':target.real.tolist(),
                 'target_imag':target.imag.tolist(), 'source':spec['source'], 'lineage':spec['family'],
                 'note':spec['authorship']}]
    (folder/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return next(load_manifest(folder/'manifest.json')), spec


def evaluate(routine, spec, out):
    out.mkdir(parents=True, exist_ok=True)
    target = np.array(spec.get('target_real', routine.target.real))+1j*np.array(spec.get('target_imag', routine.target.imag))
    if np.linalg.norm(routine.target-target)>1e-9:
        raise ValueError('TASK_TARGET_MISMATCH')
    if routine.trial.num_qubits != 2:
        raise ValueError('TASK_LAYOUT_MISMATCH')
    result = analyze(routine)
    if abs(result['p']-spec['expected_probability'])>1e-9:
        raise ValueError('TASK_PROBABILITY_MISMATCH')
    checks=[]
    for cap in spec['caps']:
        path=out/f'cap_{cap}.qasm'
        save_qasm(compile_source_retry(routine,cap),path)
        timeout=(1-spec['expected_probability'])**cap
        check=verify_source_retry(path,target,1-timeout,timeout_probability=timeout)
        checks.append({'cap':cap,'expected_timeout':timeout, 'verification':check})
    return {'name':routine.name,'probability':result['p'], 'caps':checks,
            'selected_cap':retry_cap(result['p'],spec.get('timeout_limit',spec.get('max_timeout')),spec['max_attempts']),
            'semantic_pass':all(c['verification']['verified'] for c in checks)}


def natural_comparator(routine,out):
    q=QuantumCircuit(2,1);q.compose(routine.trial,inplace=True);q.measure(0,0)
    with q.if_test((q.clbits[0],1)): q.x(1)
    path=out/'natural_feedforward.qasm';save_qasm(native(q),path)
    q=qasm3.loads(path.read_text())
    primary=sum((reduce(rho,[1,2]) for rho in execute(q,choi_input(2,[1])).values()), np.zeros((4,4),complex))
    secondary=sum(branch_maps(q,[1],source=True))
    zero=np.zeros((4,4),complex)
    return {'output_contract':'Both recorded outcomes are successful after conditional X; no timeout flag.',
            'verification':compare_branches([zero,primary],[zero,secondary],routine.target,1.,0.)}


def teammate(manifest, authorship, out):
    if manifest is None and authorship is None:
        return {'status':'awaiting_independent_submission','semantic_pass':None,'independence_verified':False}
    if manifest is None or authorship is None:
        raise ValueError('Provide both --teammate-manifest and --authorship')
    spec=json.loads((ROOT/'evaluation/teammate/task.json').read_text())
    attestation=json.loads(Path(authorship).read_text())
    if any(field not in attestation for field in spec['required_authorship_fields']):
        raise ValueError('AUTHORSHIP_FIELDS_MISSING')
    if not isinstance(attestation['author'],str) or not attestation['author'].strip():
        raise ValueError('AUTHORSHIP_AUTHOR_MISSING')
    if attestation['written_independently_of_retryguard_core'] is not True or attestation['core_author_involved'] is not False:
        raise ValueError('AUTHORSHIP_NOT_INDEPENDENT')
    for field in ('ai_assistance_disclosed','source_url','notes'):
        if not isinstance(attestation[field],str) or not attestation[field].strip():
            raise ValueError('AUTHORSHIP_DISCLOSURE_MISSING: '+field)
    routines=list(load_manifest(Path(manifest)))
    if len(routines)!=1:raise ValueError('TASK_REQUIRES_ONE_ADAPTER')
    r=routines[0];a=analyze(r)
    failure=r.target.conj().T
    k=a['kraus'][1]; coeff=np.trace(failure.conj().T@k)/2
    if np.linalg.norm(k-coeff*failure)>1e-9:raise ValueError('TASK_FAILURE_BRANCH_MISMATCH')
    report=evaluate(r,spec,out)
    report.update(status='self_attested_pending_human_review',independence_verified=False,authorship=attestation)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'results/external_evaluation')
    parser.add_argument('--teammate-manifest',type=Path)
    parser.add_argument('--authorship',type=Path)
    args=parser.parse_args()
    freeze=frozen_check()
    r,spec=build_adqc();out=args.out;out.mkdir(parents=True,exist_ok=True)
    report={'evaluation_type':'Post-freeze new-family evaluation; not blinded or independently authored',
            'baseline':freeze,'new_family':evaluate(r,spec,out/'adqc'),
            'natural_comparator':natural_comparator(r,out/'adqc'),
            'teammate':teammate(args.teammate_manifest,args.authorship,out/'teammate')}
    report['baseline_after']=frozen_check()
    report['requested_acceptance_complete']=False # human authorship review is outside this harness
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'new_family_pass':report['new_family']['semantic_pass'],
                      'natural_comparator_pass':report['natural_comparator']['verification']['verified'],
                      'teammate_status':report['teammate']['status'],'baseline':freeze},indent=2))
    return 0 if report['new_family']['semantic_pass'] and report['natural_comparator']['verification']['verified'] and report['teammate'].get('semantic_pass') is not False else 1

if __name__=='__main__':sys.exit(main())
