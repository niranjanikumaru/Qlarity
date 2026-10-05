"""Instrument analysis; does not supply verifier output states."""
import numpy as np
from qiskit.quantum_info import Operator
from .validation import InputError, validate_trial, validate_target, validate_probability, validate_budget, validate_cap
TOL=1e-9

def extract(routine):
    validate_trial(routine.trial)
    m=2**(routine.trial.num_qubits-1)
    try:
        v=Operator(routine.trial).data
    except Exception as exc:
        raise InputError('UNSUPPORTED_GATE', 'Cannot evaluate the trial as a unitary matrix: ' + str(exc), 'qasm') from exc
    if not np.all(np.isfinite(v)):
        raise InputError('NONFINITE_CIRCUIT', 'Trial evaluates to nonfinite matrix entries.', 'qasm')
    if np.linalg.norm(v.conj().T@v-np.eye(len(v))) > TOL:
        raise InputError('NONUNITARY_CIRCUIT', 'Trial is not unitary.', 'qasm')
    ks=[v[np.ix_([j,j+m],[0,m])] for j in range(m)]
    if np.linalg.norm(sum(k.conj().T@k for k in ks)-np.eye(2))>TOL:raise InputError('INCOMPLETE_INSTRUMENT', 'Incomplete instrument: branch probabilities do not sum to identity.', 'qasm')
    return ks

def analyze(routine):
    target=validate_target(routine.target);ks=extract(routine)
    coeff=np.trace(target.conj().T@ks[0])/2
    if np.linalg.norm(ks[0]-coeff*target)>TOL:raise InputError('TARGET_MISMATCH', 'Success does not implement declared target; check target matrix, qubit ordering, and success syndrome.', 'target')
    p=float(abs(coeff)**2)
    if not np.isfinite(p) or p > 1+TOL:
        raise InputError('INVALID_PROBABILITY', 'Computed success probability is not finite or exceeds one.', 'qasm')
    if p<=TOL:raise InputError('ZERO_SUCCESS', 'Zero success probability or below numerical tolerance 1e-9.', 'qasm')
    p=min(p,1.0)
    repairs=[]
    for k in ks[1:]:
        weight=float(np.trace(k.conj().T@k).real/2)
        if weight<TOL:repairs.append(np.eye(2));continue
        if np.linalg.norm(k.conj().T@k-weight*np.eye(2))>TOL:raise InputError('IRREVERSIBLE_FAILURE', 'Failure leaks information; reject unitary recovery.', 'qasm')
        repairs.append((k/np.sqrt(weight)).conj().T)
    return {'p':p,'kraus':ks,'repairs':repairs}

def retry_cap(p,epsilon,max_attempts):
    p=validate_probability(p)
    epsilon,max_attempts=validate_budget(epsilon,max_attempts)
    for n in range(1,max_attempts+1):
        if (1-p)**n<=epsilon+1e-14:return n
    raise InputError('INFEASIBLE_BUDGET', f'No feasible retry cap: timeout {(1-p)**max_attempts:.6g} at cap {max_attempts} exceeds limit {epsilon:.6g}. Increase max_attempts or timeout.', 'max_attempts')

def expected_attempts(p,n):
    p=validate_probability(p);n=validate_cap(n)
    return sum((1-p)**k for k in range(n))

def superoperator(ks):return sum(np.kron(k.conj(),k) for k in ks)

def bounded_maps(success,failure,n):
    s=superoperator(success);f=superoperator(failure);acc=np.zeros_like(s);alive=np.eye(s.shape[0],dtype=complex)
    for _ in range(n):acc+=s@alive;alive=f@alive
    return acc,alive

def audit_naive_control(routine):
    """Specific wrapper: control every trial gate, leave ancillas zero on off arm.
No claim to analyze every possible controlled implementation.
"""
    ks=extract(routine)
    on=np.array([np.trace(k.conj().T@k).real/2 for k in ks])
    off=np.zeros(len(ks));off[0]=1
    return {'wrapper':'Naive gate-controlled trial with zero ancillas on off arm',
            'syndrome_total_variation':float(np.sum(np.abs(on-off))/2),
            'syndrome_leak_detected':bool(np.sum(np.abs(on-off))>=1e-9),
            'explanation':'Different syndrome probabilities reveal the coherent control branch; recovery cannot erase a recorded measurement.'}
