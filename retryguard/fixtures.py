"""Manually sourced gate fixtures, not an upstream source parser."""
from dataclasses import dataclass
import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import UnitaryGate
I=np.eye(2,dtype=complex); X=np.array([[0,1],[1,0]],complex); Z=np.diag([1,-1]).astype(complex)
@dataclass
class Routine:
    name:str
    trial:QuantumCircuit
    target:np.ndarray
    source:str
    lineage:str
    note:str

def fixtures():
    q=QuantumCircuit(3,name='ibm_rx')
    q.h(2);q.h([0,1]);q.ccx(0,1,2);q.s(2);q.ccx(0,1,2);q.h([0,1]);q.h(2)
    yield Routine('ibm_rx',q,(2*I-1j*X)/np.sqrt(5),
      'https://github.com/Qiskit/documentation/blob/24612fc664d3d7167d54fb493312f3b7bb5299c9/docs/tutorials/repeat-until-success.ipynb',
      'Paetznick Svore rotation synthesis','Pinned IBM gate sequence; explicit target phase contract for coherent control.')
    q=QuantumCircuit(3,name='guppy_v3');q.h([0,1]);q.tdg(0);q.cx(1,0);q.t(0);q.h(0)
    second=QuantumCircuit(2);second.t(1);second.z(1);second.cx(1,0);second.t(0);second.h(0)
    q.append(second.to_gate().control(1,ctrl_state=0),[0,1,2])
    yield Routine('guppy_v3',q,(I+2j*Z)/np.sqrt(5),
      'https://docs.quantinuum.com/guppy/guppylang/examples/repeat-until-success.html',
      'Paetznick Svore rotation synthesis','First measurement deferred. Measuring otherwise discarded b refines early failure. Generated corrections are analyzed independently.')
    theta=.37;q=QuantumCircuit(2,name='gearbox');q.ry(2*theta,0)
    q.append(UnitaryGate(-1j*X).control(),[0,1]);q.ry(-2*theta,0)
    c=np.cos(theta)**2;s=np.sin(theta)**2
    yield Routine('gearbox',q,(c*I-1j*s*X)/np.sqrt(c*c+s*s),
      'https://arxiv.org/abs/1406.2040','Wiebe Kliuchnikov gearbox',
      'One-input gearbox realization with Ry convention and theta 0.37. Independent implementation of published instrument, not source-code import.')

def manifest_entries(path):
    """Yield (1-based item index, display name, routine, error), isolating items."""
    import json, re
    from pathlib import Path
    from collections import Counter
    from qiskit import qasm3
    from .validation import InputError, numeric_matrix, validate_target, validate_trial
    path = Path(path)
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InputError('DUPLICATE_JSON_KEY', f'Duplicate JSON key: {key}.', 'manifest')
            result[key] = value
        return result
    try:
        contents = path.read_text()
    except (OSError, UnicodeError, ValueError) as exc:
        raise InputError('MANIFEST_READ', f'Cannot read manifest: {exc}', 'manifest') from exc
    try:
        items = json.loads(contents, object_pairs_hook=unique_keys)
    except json.JSONDecodeError as exc:
        raise InputError('MANIFEST_JSON', f'Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.', 'manifest') from exc
    if not isinstance(items, list) or not items:
        raise InputError('MANIFEST_ROOT', 'Manifest must be a nonempty JSON list of routine objects.', 'manifest')
    counts = Counter(item.get('name') for item in items if isinstance(item, dict) and isinstance(item.get('name'), str))
    required = {'name', 'qasm', 'target_real', 'target_imag', 'source', 'lineage'}
    for index, item in enumerate(items, 1):
        name = item.get('name') if isinstance(item, dict) and isinstance(item.get('name'), str) else None
        try:
            if not isinstance(item, dict):
                raise InputError('MANIFEST_ITEM', 'Each manifest item must be an object.', 'item')
            missing = required - item.keys()
            if missing:
                raise InputError('MISSING_FIELD', 'Missing required fields: ' + ', '.join(sorted(missing)) + '.', sorted(missing)[0])
            unknown = item.keys() - required - {'note'}
            if unknown:
                raise InputError('UNKNOWN_FIELD', 'Unknown fields: ' + ', '.join(sorted(unknown)) + '.', sorted(unknown)[0])
            if name is None or not re.fullmatch(r'[a-z0-9_]{1,64}', name):
                raise InputError('INVALID_NAME', 'name must contain 1 to 64 lowercase letters, digits, or underscores.', 'name')
            if counts[name] > 1:
                raise InputError('DUPLICATE_NAME', f'Name {name!r} occurs more than once; give each item a unique name.', 'name')
            for field in ('qasm', 'source', 'lineage'):
                if not isinstance(item[field], str) or not item[field].strip():
                    raise InputError('INVALID_FIELD', f'{field} must be a nonempty string.', field)
            if 'note' in item and not isinstance(item['note'], str):
                raise InputError('INVALID_FIELD', 'note must be a string.', 'note')
            target = numeric_matrix(item['target_real'], 'target_real', True) + 1j*numeric_matrix(item['target_imag'], 'target_imag', True)
            target = validate_target(target)
            relative = Path(item['qasm'])
            try:
                source = (path.parent/relative).resolve()
            except (OSError, ValueError, RuntimeError) as exc:
                raise InputError('QASM_PATH', f'Cannot resolve qasm path: {exc}', 'qasm') from exc
            if relative.is_absolute() or not source.is_relative_to(path.parent.resolve()):
                raise InputError('QASM_PATH', 'qasm must be a relative path within the manifest directory.', 'qasm')
            try:
                text = source.read_text()
            except (OSError, UnicodeError, ValueError) as exc:
                raise InputError('QASM_READ', f'Cannot read QASM file {item["qasm"]!r}: {exc}', 'qasm') from exc
            try:
                trial = qasm3.loads(text)
            except Exception as exc:
                raise InputError('QASM_PARSE', f'Cannot parse QASM file {item["qasm"]!r}: {exc}', 'qasm') from exc
            validate_trial(trial)
            yield index, name, Routine(name, trial, target, item['source'], item['lineage'], item.get('note', 'User supplied adapter')), None
        except InputError as exc:
            yield index, name, None, exc


def load_manifest(path):
    """Strict Python iterator; the CLI uses manifest_entries for batch isolation."""
    for _, _, routine, error in manifest_entries(path):
        if error:
            raise error
        yield routine
