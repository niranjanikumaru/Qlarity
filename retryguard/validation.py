"""Public input checks and stable, machine-readable rejection reasons."""
from numbers import Real, Integral
import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import Gate, Barrier


class InputError(ValueError):
    def __init__(self, code, message, field=None, details=None):
        super().__init__(message)
        self.code, self.field = code, field
        self.details = details

    def as_dict(self):
        result = {'code': self.code, 'field': self.field, 'message': str(self)}
        if self.details is not None:
            result['details'] = self.details
        return result


def finite_real(value, field):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
        raise InputError('INVALID_NUMBER', f'{field} must be a finite real number.', field)
    return float(value)


def validate_probability(p, allow_zero=False):
    p = finite_real(p, 'probability')
    if not (0 <= p <= 1) or (not allow_zero and p == 0):
        raise InputError('INVALID_PROBABILITY', 'probability must be greater than zero and at most one.' if not allow_zero else 'probability must be between zero and one.', 'probability')
    return p


def validate_cap(n):
    if isinstance(n, (bool, np.bool_)) or not isinstance(n, Integral) or not 1 <= n <= 32:
        raise InputError('INVALID_CAP', 'max_attempts must be an integer from 1 to 32.', 'max_attempts')
    return int(n)


def validate_budget(epsilon, n):
    epsilon = finite_real(epsilon, 'timeout')
    if not 0 < epsilon < 1:
        raise InputError('INVALID_TIMEOUT', 'timeout must be strictly between zero and one.', 'timeout')
    return epsilon, validate_cap(n)


def numeric_matrix(value, field, real_only=False):
    def has_bool(item):
        if isinstance(item, (bool, np.bool_)):
            return True
        if isinstance(item, (list, tuple)):
            return any(has_bool(x) for x in item)
        return False
    if has_bool(value):
        raise InputError('INVALID_MATRIX', f'{field} must not contain boolean entries.', field)
    try:
        matrix = np.asarray(value)
    except (ValueError, TypeError) as exc:
        raise InputError('INVALID_MATRIX', f'{field} must be a rectangular 2 by 2 numeric matrix.', field) from exc
    kinds = 'iuf' if real_only else 'iufc'
    if matrix.shape != (2, 2) or matrix.dtype.kind not in kinds:
        raise InputError('INVALID_MATRIX', f'{field} must be a 2 by 2 matrix of numbers, without strings or booleans.', field)
    if not np.all(np.isfinite(matrix)):
        raise InputError('NONFINITE_MATRIX', f'{field} contains NaN or infinity; provide finite entries.', field)
    return matrix.astype(float if real_only else complex)


def validate_target(target):
    target = numeric_matrix(target, 'target')
    with np.errstate(over='ignore', invalid='ignore'):
        residual = np.linalg.norm(target.conj().T @ target - np.eye(2))
    if not np.isfinite(residual) or residual > 1e-9:
        raise InputError('NONUNITARY_TARGET', 'Nonunitary target: target must satisfy U†U = I within tolerance 1e-9.', 'target')
    return target


def validate_trial(trial):
    if not isinstance(trial, QuantumCircuit):
        raise InputError('INVALID_CIRCUIT', 'trial must be a Qiskit QuantumCircuit.', 'qasm')
    if trial.num_qubits not in (2, 3):
        raise InputError('UNSUPPORTED_QUBITS', 'Require one data qubit and one or two clean ancillas (2 or 3 qubits total).', 'qasm')
    if trial.num_clbits:
        raise InputError('UNSUPPORTED_CLASSICAL_BITS', 'Trial input must be gate-only, with no classical registers; RetryGuard adds measurements.', 'qasm')
    if trial.parameters:
        raise InputError('UNBOUND_PARAMETERS', 'Bind all trial parameters to finite constants before analysis.', 'qasm')
    if not np.isfinite(float(trial.global_phase)):
        raise InputError('NONFINITE_GATE', 'Trial global phase must be finite.', 'qasm')
    for index, inst in enumerate(trial.data):
        op = inst.operation
        if isinstance(op, Barrier):
            continue
        if not isinstance(op, Gate):
            raise InputError('UNSUPPORTED_OPERATION', f'Instruction {index} ({op.name}) is not a unitary gate. Measurements, resets, delays, and control flow are unsupported in trial inputs.', 'qasm')
        for param in op.params:
            try:
                valid = np.all(np.isfinite(np.asarray(param, dtype=complex)))
            except (TypeError, ValueError):
                valid = False
            if not valid:
                raise InputError('NONFINITE_GATE', f'Instruction {index} ({op.name}) has a nonfinite or nonnumeric parameter.', 'qasm')
    return trial
