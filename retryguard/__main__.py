"""Batch CLI: input failures are isolated and every item receives a status."""
import argparse, json, platform, hashlib, csv, sys, uuid, shutil
from pathlib import Path
import numpy as np
import qiskit
from .fixtures import fixtures, manifest_entries
from .validation import InputError, validate_budget
from .diagnosis import diagnose_routine, input_diagnosis, attach_evidence, render_html
from .analysis import analyze, retry_cap, expected_attempts, audit_naive_control
from .compiler import (compile_retry, compile_early_measure, compile_deterministic,
    controlled_target, attempt, static_counts, save_qasm, corrected_source, native,
    compile_source_retry)
from .verifier import verify, verify_source, verify_source_retry


def require_verified(check):
    residuals = [value for key, value in check.items() if key.endswith('residual')]
    if check.get('verified') is False or not residuals or not all(np.isfinite(v) and 0 <= v < 1e-9 for v in residuals):
        raise InputError('VERIFICATION_FAILED', 'Emitted circuit failed verification; no artifacts accepted. ' + '; '.join(f"{x['branch']}: {x['code']} ({x['engine']})" for x in check.get('failures', [])), 'verification', details=check.get('failures', []))


def generate(routine, args, out, gen):
    rows, source_rows, provenance, unavailable = [], [], [], []
    a = analyze(routine)
    p = a['p']
    def select_cap(probability, policies):
        try:
            return retry_cap(probability, args.timeout, args.max_attempts)
        except InputError as exc:
            if exc.code != 'INFEASIBLE_BUDGET':
                raise
            unavailable.extend({'policy': policy, **exc.as_dict()} for policy in policies)
            return None
    n = select_cap(p, ['source_selected', 'selected_early_measure'])
    fixed_policies = ['source_fixed', 'fixed_early_measure', 'fixed_coherent_coin']
    if p < .5:
        fixed = None
        unavailable.extend({'policy': policy, 'code': 'BASELINE_DOMAIN', 'field': 'probability',
            'message': 'Fixed baseline requires per-attempt success probability at least 0.5.'} for policy in fixed_policies)
    else:
        fixed = select_cap(.5, fixed_policies)
    raw=verify_source(corrected_source(routine,a,False),routine.target,p)
    repaired_path=gen/(routine.name+'_recovered_attempt.qasm');save_qasm(corrected_source(routine,a),repaired_path)
    source_check=verify_source_retry(repaired_path,routine.target,p,timeout_probability=1-p)
    require_verified(source_check)
    trial=gen/(routine.name+'_trial.qasm');save_qasm(native(routine.trial),trial)
    provenance.append({'name':routine.name,'source':routine.source,'lineage':routine.lineage,'adaptation':routine.note,'trial_sha256':hashlib.sha256(trial.read_bytes()).hexdigest(),'naive_control_audit':audit_naive_control(routine),'raw_attempt_check':raw,'recovered_attempt_check':source_check})
    for policy, cap in [('source_fixed', fixed), ('source_selected', n)]:
        if cap is None:
            continue
        path = gen / (routine.name + '_' + policy + '.qasm')
        circuit = compile_source_retry(routine, cap)
        save_qasm(circuit, path)
        probability = 1 - (1-p)**cap
        check = verify_source_retry(path, routine.target, probability, timeout_probability=(1-p)**cap)
        residuals = [check[k] for k in ('success_residual', 'timeout_residual', 'trace_residual')]
        verified = check['verified'] and all(np.isfinite(v) and v < 1e-9 for v in residuals)
        if not verified:
            require_verified(check)
        source_rows.append({
            'routine': routine.name, 'policy': policy, 'cap': cap,
            'p_per_attempt': p, 'expected_attempts': expected_attempts(p, cap),
            'expected_timeout_probability': (1-p)**cap,
            'static_counts': static_counts(circuit),
            'qasm_file': str(path.relative_to(out)),
            'verified': verified, **check,
        })
    body=static_counts(attempt(routine.target,p));cu=static_counts(native(controlled_target(routine.target)))
    for policy,cap in [('fixed_coherent_coin',fixed),('fixed_early_measure',fixed),('selected_early_measure',n),('deterministic',1)]:
        if cap is None:
            continue
        if policy=='deterministic':q=compile_deterministic(routine.target)
        elif policy=='fixed_coherent_coin':q=compile_retry(routine.target,p,cap)
        else:q=compile_early_measure(routine.target,p,cap)
        path=gen/(routine.name+'_'+policy+'.qasm');save_qasm(q,path)
        probability=1 if policy=='deterministic' else 1-(1-p)**cap
        check=verify(path,routine.target,probability,timeout_probability=0.0 if policy=='deterministic' else (1-p)**cap);counts=static_counts(q);ex=1 if policy=='deterministic' else expected_attempts(p,cap)
        if policy=='fixed_coherent_coin':worstcx=body['cx']*cap;excx=body['cx']*ex;worst1q=body['u']*cap;ex1q=body['u']*ex
        elif policy=='deterministic':worstcx=counts['cx'];excx=worstcx;worst1q=counts['u']+counts['x'];ex1q=worst1q
        else:worstcx=cu['cx'];excx=cu['cx']*probability;worst1q=cap+cu['u'];ex1q=ex+cu['u']*probability
        row={'routine':routine.name,'policy':policy,'cap':cap,'p_per_attempt':p,'expected_attempts':ex,'timeout_probability':1-probability,
            'worst_cx':worstcx,'expected_cx':excx,'worst_1q':worst1q,'expected_1q':ex1q,
            'worst_measure':cap,'expected_measure':ex,'worst_reset':0 if policy=='deterministic' else cap,'expected_reset':0 if policy=='deterministic' else ex,
            'static_cx':counts['cx'],'qasm_file':str(path.relative_to(out)),**check}
        require_verified(check)
        row['verified']=True
        if not row['verified']:raise AssertionError(row)
        rows.append(row)
    return rows, source_rows, provenance, unavailable


def main():
    parser = argparse.ArgumentParser(description='RetryGuard scoped exact-model benchmark')
    parser.add_argument('--manifest', help='JSON manifest of unitary OpenQASM trial circuits')
    parser.add_argument('--out', default='results')
    parser.add_argument('--timeout', type=float, default=.01)
    parser.add_argument('--max-attempts', type=int, default=16)
    args = parser.parse_args()
    try:
        validate_budget(args.timeout, args.max_attempts)
        entries = list(manifest_entries(args.manifest)) if args.manifest else [
            (index, r.name, r, None) for index, r in enumerate(fixtures(), 1)]
    except InputError as exc:
        print(json.dumps({'status': 'invalid_request', 'error': exc.as_dict()}, allow_nan=False), file=sys.stderr)
        return 2
    out = Path(args.out)
    rows, source_rows, provenance, errors, statuses = [], [], [], [], []
    diagnoses = []
    run_id = uuid.uuid4().hex[:12]
    try:
        generated = out / 'generated' / run_id
        generated.mkdir(parents=True, exist_ok=False)
        for index, name, routine, error in entries:
            stage = 'validation'
            artifact_dir = None
            diagnosis = None
            if error is None:
                try:
                    stage = 'analysis_or_generation'
                    diagnosis = diagnose_routine(routine)
                    artifact_dir = generated / routine.name
                    artifact_dir.mkdir()
                    new_rows, new_source, new_provenance, unavailable = generate(routine, args, out, artifact_dir)
                    attach_evidence(diagnosis, new_provenance[0], new_source, str((artifact_dir/(routine.name+'_recovered_attempt.qasm')).relative_to(out)))
                    diagnosis.update(item_index=index, batch_status='accepted')
                    diagnoses.append(diagnosis)
                    rows.extend(new_rows)
                    source_rows.extend(new_source)
                    provenance.extend(new_provenance)
                    statuses.append({'item_index': index, 'name': name, 'status': 'accepted', 'unavailable_policies': unavailable})
                    continue
                except InputError as exc:
                    error = exc
                except Exception as exc:
                    # Isolate unexpected implementation/SDK errors without mislabeling them as user mistakes.
                    error = InputError('PROCESSING_ERROR', f'{type(exc).__name__}: {exc}', 'processing')
                if artifact_dir is not None and artifact_dir.exists():
                    shutil.rmtree(artifact_dir)
            record = {'item_index': index, 'name': name, 'stage': stage, **error.as_dict()}
            diagnosis = diagnosis or input_diagnosis(name, error)
            diagnosis.update(item_index=index, batch_status='rejected', batch_error=error.as_dict())
            diagnoses.append(diagnosis)
            errors.append(record)
            statuses.append({'item_index': index, 'name': name, 'status': 'rejected', 'error': record})
            print(f'Item {index} ({name or "unnamed"}) [{error.code}]: {error}', file=sys.stderr)
        accepted = sum(item['status'] == 'accepted' for item in statuses)
        summary = {'status': 'partial' if errors and accepted else 'rejected' if errors else 'complete',
            'items_total': len(entries), 'items_accepted': accepted, 'items_rejected': len(errors),
            'all_verified': bool(rows or source_rows) and not errors and all(r['verified'] for r in rows + source_rows),
            'controlled_variants': len(rows), 'source_retry_variants': len(source_rows)}
        source_contract = {'max_timeout': args.timeout, 'max_attempts': args.max_attempts,
            'success': 'Declared uncontrolled target on reference-entangled data',
            'timeout': 'Identity on data after final failure recovery',
            'flag': 'Entire syndrome register: zero success, nonzero timeout',
            'initialization': 'All source ancillas initially zero; data arbitrary',
            'scope': 'Original trial retained; no external coherent control'}
        report = {'schema_version': 4, 'run_id': run_id, 'summary': summary,
            'model': 'Ideal continuous U + CX; not hardware timing or fault tolerant cost',
            'contract': {'max_timeout': args.timeout, 'max_attempts': args.max_attempts,
                'success': 'Declared controlled target for arbitrary reference-entangled inputs',
                'timeout': 'Identity on control and data with distinct failure flag',
                'observable_records': 'Final success flag only; detailed syndrome and timing records need not match.'},
            'environment': {'python': platform.python_version(), 'qiskit': qiskit.__version__, 'numpy': np.__version__},
            'primary_baseline': 'fixed_early_measure: cap derived from p >= 0.5; explicitly unavailable outside its domain or budget',
            'secondary_baseline': 'fixed_coherent_coin: coherent gate before measurement',
            'items': statuses, 'errors': errors, 'diagnostics': diagnoses, 'source_retry_contract': source_contract,
            'fixtures': provenance, 'source_retry_results': source_rows, 'results': rows}
        # Strict JSON prevents an unnoticed NaN/Infinity from entering evidence reports.
        documents = {'diagnostics.json': {'items': diagnoses}, 'benchmark.json': report, 'errors.json': {'summary': summary, 'errors': errors},
            'source_retry.json': {'contract': source_contract, 'results': source_rows}}
        for name, value in documents.items():
            path = out / name
            temp = out / (name + '.tmp')
            temp.write_text(json.dumps(value, indent=2, allow_nan=False))
            temp.replace(path)
        html_temp = out/'diagnostics.html.tmp'
        html_temp.write_text(render_html(diagnoses), encoding='utf-8')
        html_temp.replace(out/'diagnostics.html')
        with (out/'benchmark.csv').open('w', newline='') as stream:
            columns = list(dict.fromkeys(key for row in rows for key in row)) if rows else ['routine', 'policy', 'verified']
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        print(json.dumps({**summary, 'results': str(out/'benchmark.json')}, allow_nan=False, indent=2))
        return 1 if errors else 0
    except OSError as exc:
        print(json.dumps({'status': 'output_error', 'error': {'code': 'OUTPUT_IO', 'message': str(exc)} }), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
