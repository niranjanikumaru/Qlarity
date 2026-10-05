"""Readable branch explanations. Illustrative witnesses are not the verifier."""
import html
import numpy as np
from .analysis import extract, TOL
from .validation import InputError, validate_target

I = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], complex)
Y = np.array([[0, -1j], [1j, 0]], complex)
Z = np.diag([1, -1]).astype(complex)
PROBES = [('zero |0>', np.array([1, 0], complex)),
          ('one |1>', np.array([0, 1], complex)),
          ('plus |+>', np.array([1, 1], complex)/np.sqrt(2)),
          ('minus |->', np.array([1, -1], complex)/np.sqrt(2)),
          ('plus-i |+i>', np.array([1, 1j], complex)/np.sqrt(2)),
          ('minus-i |-i>', np.array([1, -1j], complex)/np.sqrt(2))]


def state_label(state):
    for label, probe in PROBES:
        if abs(np.vdot(probe, state))**2 >= 1-1e-9:
            return label
    return 'a rotated pure state (distinguished by the measurement below)'


def witness(k, expected, correction=None):
    """Choose a concrete probe and measurement that expose the state change."""
    best = None
    for label, state in PROBES:
        actual = k @ state
        probability = float(np.vdot(actual, actual).real)
        if probability <= TOL:
            continue
        actual /= np.sqrt(probability)
        desired = expected @ state
        for basis, observable in [('X', X), ('Y', Y), ('Z', Z)]:
            expected_plus = float(np.clip((1+np.vdot(desired, observable@desired).real)/2, 0, 1))
            actual_plus = float(np.clip((1+np.vdot(actual, observable@actual).real)/2, 0, 1))
            gap = abs(actual_plus-expected_plus)
            record = {'input_state': label, 'expected_state': state_label(desired), 'actual_state': state_label(actual), 'branch_probability': probability,
                'measurement_basis': basis, 'expected_plus_probability': expected_plus,
                'actual_plus_probability': actual_plus, 'measurement_gap': gap}
            if correction is not None:
                repaired = correction @ actual
                record['corrected_plus_probability'] = float(np.clip((1+np.vdot(repaired, observable@repaired).real)/2, 0, 1))
            if best is None or gap > best['measurement_gap'] + 1e-12:
                best = record
    return best


def recovery_description(unitary):
    candidates = [('X', X, 'Apply an X gate to undo the bit flip.'),
        ('Y', Y, 'Apply a Y gate to undo the combined bit and phase flip.'),
        ('Z', Z, 'Apply a Z gate to undo the phase flip.'),
        ('H', (X+Z)/np.sqrt(2), 'Apply a Hadamard gate to undo the basis change.'),
        ('S', np.diag([1,1j]), 'Apply an S phase gate.'),
        ('Sdg', np.diag([1,-1j]), 'Apply an inverse S phase gate.'),
        ('identity', I, 'No data correction is needed for this outcome.')]
    for name, matrix, text in candidates:
        coefficient = np.trace(matrix.conj().T@unitary)/2
        if np.linalg.norm(unitary-coefficient*matrix) < TOL:
            return {'kind': name, 'instruction': text}
    return {'kind': 'unitary_inverse', 'instruction': 'Apply the generated inverse single-qubit rotation to undo this branch’s data rotation.'}


def diagnose_routine(routine):
    target = validate_target(routine.target)
    operators = extract(routine)
    width = routine.trial.num_qubits-1
    branches = []
    for syndrome, k in enumerate(operators):
        effect = k.conj().T@k
        weight = float(np.trace(effect).real/2)
        expected = target if syndrome == 0 else I
        coefficient = np.trace(expected.conj().T@k)/2
        residual = float(np.linalg.norm(k-coefficient*expected))
        recoverable = bool(np.linalg.norm(effect-weight*I) <= TOL)
        negligible = weight <= TOL
        correction = (k/np.sqrt(weight)).conj().T if recoverable and not negligible and syndrome else None
        violated = bool(not negligible and residual > TOL)
        if negligible:
            status = 'below_tolerance'
            explanation = 'This outcome has negligible average probability at the configured numerical tolerance; no conditional-state diagnosis is certified.'
        elif not violated:
            status = 'satisfied'
            explanation = 'The successful outcome performs the declared target.' if syndrome == 0 else 'This failure outcome already preserves the data, up to an unobservable phase.'
        elif syndrome == 0:
            status = 'violated'
            explanation = 'The outcome labeled success changes the data differently from the declared target.'
        elif recoverable:
            status = 'violated'
            explanation = 'This failure changes the data. If execution stops here without recovery, timeout returns the wrong state.'
        else:
            status = 'violated'
            explanation = 'This failure reveals information about the input state. A deterministic unitary correction cannot restore every possible input.'
        proposal = None
        if syndrome == 0 and violated:
            proposal = {'kind': 'review_target', 'instruction': 'Check the intended target, qubit order, and success label. No automatic replacement target is proposed.'}
        elif not negligible and syndrome:
            proposal = recovery_description(correction) if recoverable else {
                'kind': 'not_repairable', 'instruction': 'Reject this routine for unitary recovery; redesign the trial or use a separately justified recovery model.'}
        probe = witness(k, expected, correction) if not negligible else None
        probabilities = [(label, float(np.vdot(k@state, k@state).real)) for label,state in PROBES]
        low, high = min(probabilities, key=lambda x:x[1]), max(probabilities, key=lambda x:x[1])
        branches.append({'syndrome': syndrome, 'bits': format(syndrome, f'0{width}b'),
            'contract': 'success_target' if syndrome == 0 else 'timeout_preserves_data',
            'status': status, 'explanation': explanation,
            'probability': weight if recoverable else None,
            'probability_note': 'Input-independent probability.' if recoverable else 'Probability depends on the input; no single probability applies.',
            'probability_witness': {'low_input':low[0], 'low_probability':low[1], 'high_input':high[0], 'high_probability':high[1]} if not recoverable else None,
            'affected_state': probe, 'proposed_correction': proposal,
            'correction_verified': False,
            'operator_residual': residual})
    # Off arm leaves ancillas zero; on-arm distribution is shown for the maximally mixed input.
    on_probabilities = [float(np.trace(k.conj().T@k).real/2) for k in operators]
    leakage = float(sum(abs(p-(1 if i==0 else 0)) for i,p in enumerate(on_probabilities))/2)
    return {'routine': routine.name, 'scope': 'Original unitary trial followed by ancilla measurement, before recovery. Failure outcomes are potential terminal timeouts.',
        'bit_order': 'Displayed bits are c[highest]...c[0]; integer syndrome 0 is success.',
        'source_caveat': 'These are checks against RetryGuard’s declared timeout contract, not claims of previously unknown upstream bugs.',
        'branches': branches,
        'naive_control': {'scope': 'Specific wrapper that controls every trial gate and leaves off-arm ancillas zero.',
            'leak_detected': leakage > TOL, 'distribution_distance':leakage,
            'explanation': 'Measurement outcomes distinguish the run and do-not-run arms and can damage their superposition.' if leakage > TOL else 'No syndrome-distribution difference detected for this audit; this alone does not certify coherent control.',
            'proposal': 'Do not apply this naive wrapper. The separately verified controlled replacement circuits are available for accepted inputs; source recovery alone does not fix control leakage.'},
        'evidence_note': 'State examples illustrate the diagnosis; exported-program Choi checks establish the numerical contract checks. This is ideal-model verification, not a formal proof.',
        'verified_artifacts': []}


def input_diagnosis(name, error):
    return {'routine': name or 'unnamed', 'scope': 'Input validation', 'branches': [],
        'input_error': error.as_dict(), 'explanation': 'Circuit behavior was not diagnosed because this input could not be analyzed. ' + str(error),
        'verified_artifacts': [], 'evidence_note': 'No affected quantum state or repair is asserted for this invalid input.'}


def attach_evidence(diagnosis, provenance, source_rows, corrected_file):
    check = provenance['recovered_attempt_check']
    # Success/timeout Choi checks on the emitted recovered attempt validate the complete instrument.
    passed = check['verified'] if 'verified' in check else all(np.isfinite(v) and v < TOL for k,v in check.items() if k.endswith('residual'))
    for branch in diagnosis['branches']:
        if branch['syndrome'] and branch['proposed_correction'] and branch['proposed_correction']['kind'] != 'not_repairable':
            branch['correction_verified'] = bool(passed and branch['status'] != 'below_tolerance')
    diagnosis['recovered_attempt_check'] = check
    diagnosis['verified_artifacts'] = [{'kind':'recovered_attempt', 'qasm_file':corrected_file}] + [
        {'kind':row['policy'], 'cap':row['cap'], 'qasm_file':row['qasm_file'],
         'success_residual':row['success_residual'], 'timeout_residual':row['timeout_residual']} for row in source_rows]


def render_html(diagnoses):
    esc = lambda value: html.escape(str(value), quote=True)
    parts = ['''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RetryGuard failure diagnosis</title>
<style>body{font:17px/1.6 system-ui,sans-serif;color:#182532;background:#f6f8fa;margin:0;overflow-wrap:anywhere}main{max-width:960px;margin:auto;padding:36px 24px}h1,h2,h3{line-height:1.2}section{background:white;border:1px solid #d5dce3;padding:24px;margin:22px 0;border-radius:8px}article{border-top:1px solid #d5dce3;padding:16px 0}table{border-collapse:collapse;width:100%;margin:16px 0}td,th{text-align:left;border:1px solid #d5dce3;padding:10px}small{color:#526170}a{color:#075eaa}code{overflow-wrap:anywhere}summary{cursor:pointer;font-weight:600}.violated{color:#a32424}.satisfied{color:#17603b}</style>
<main><h1>RetryGuard failure diagnosis</h1><p>Read the branch, the violated contract, and a concrete input-state example. Then inspect the proposed correction and the verification evidence.</p><p>A routine may be accepted for repair while its original uncorrected failure branch violates the timeout contract. X, Y, and Z below are measurement bases; “plus outcome” means the +1 result: |0&gt; for Z, |+&gt; for X, and |+i&gt; for Y.</p>''']
    for d in diagnoses:
        parts.append(f'<section><h2>{esc(d["routine"])}</h2><p><b>Batch result:</b> {esc(d.get("batch_status","unknown"))}</p><p>{esc(d["scope"])}</p>')
        if d.get('input_error'):
            parts.append(f'<p>{esc(d["explanation"])}</p><p><b>Error:</b> {esc(d["input_error"]["code"])}</p>')
        if d.get('batch_error'):
            parts.append(f'<p><b>Generation rejected:</b> {esc(d["batch_error"]["message"])}</p>')
        if d.get('bit_order'):
            parts.append(f'<small>{esc(d["bit_order"])}</small>')
        for b in d['branches']:
            parts.append(f'<article><h3>Outcome {esc(b["bits"])} — {"success" if b["syndrome"]==0 else "failure"}</h3><p class="{esc(b["status"])}"><b>{esc(b["status"].replace("_"," ").capitalize())}:</b> {esc(b["explanation"])}</p><p><b>Contract:</b> {"Apply the declared target on success." if b["syndrome"]==0 else "Return the original data unchanged on timeout."}</p>')
            if b['probability'] is not None:
                parts.append(f'<p>Outcome probability: {b["probability"]:.4%} per attempt, independent of the data input.</p>')
            w=b['affected_state']
            if w and w['measurement_gap']>TOL:
                parts.append(f'<p><b>State change:</b> The contract requires {esc(w["expected_state"])}; this branch returns {esc(w["actual_state"])}.</p>')
                parts.append(f'<p><b>Affected state:</b> Prepare {esc(w["input_state"])}. Condition on outcome {esc(b["bits"])} and measure the data in the {esc(w["measurement_basis"])} basis. This branch occurs with probability {w["branch_probability"]:.4%} for this input.</p><table><tr><th>Case</th><th>Chance of plus outcome</th></tr><tr><td>Required by contract</td><td>{w["expected_plus_probability"]:.4%}</td></tr><tr><td>Without correction</td><td>{w["actual_plus_probability"]:.4%}</td></tr>')
                if 'corrected_plus_probability' in w:
                    parts.append(f'<tr><td>After proposed correction (calculated example)</td><td>{w["corrected_plus_probability"]:.4%}</td></tr>')
                parts.append('</table>')
            pw=b['probability_witness']
            if pw:
                parts.append(f'<p><b>Information leak:</b> This outcome occurs with probability {pw["low_probability"]:.4%} for {esc(pw["low_input"])} but {pw["high_probability"]:.4%} for {esc(pw["high_input"])}. Observing it therefore reveals information about the input.</p>')
            if b['proposed_correction']:
                parts.append(f'<p><b>Proposed correction:</b> {esc(b["proposed_correction"]["instruction"])}</p>')
                if b['syndrome'] and b['proposed_correction']['kind']!='not_repairable':
                    parts.append('<p>Apply it after this outcome on every failed attempt, including the final allowed attempt; reset only the ancillas before retrying.</p>')
                parts.append(f'<p><b>Exported recovery check:</b> {"Passed the complete recovered-attempt success and timeout checks." if b["correction_verified"] else "No verified emitted correction is claimed for this branch."}</p>')
            parts.append('</article>')
        if d.get('naive_control'):
            parts.append(f'<details><summary>Separate coherent-control diagnostic</summary><p>{esc(d["naive_control"]["scope"])}</p><p>{esc(d["naive_control"]["explanation"])}</p><p>{esc(d["naive_control"]["proposal"])}</p></details>')
        if d['verified_artifacts']:
            parts.append('<h3>Verified executable artifacts</h3><ul>')
            for item in d['verified_artifacts']:
                parts.append(f'<li><a href="{esc(item["qasm_file"])}">{esc(item["kind"])}{(" — cap "+str(item["cap"])) if "cap" in item else ""}</a></li>')
            parts.append('</ul>')
        parts.append(f'<p><small>{esc(d.get("source_caveat",""))} {esc(d["evidence_note"])}</small></p></section>')
    parts.append('</main></html>')
    return ''.join(parts)
