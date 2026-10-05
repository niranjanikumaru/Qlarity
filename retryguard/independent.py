"""Second density engine: explicit NumPy matrices, no Qiskit evolution/operators.

QASM parsing and circuit objects remain shared with Qiskit. Gate matrices, reset,
measurement, reference preparation and partial trace are implemented here.
"""
import numpy as np
from .validation import InputError


def local_gate(name, params):
    if name == 'u':
        theta, phi, lam = map(float, params)
        c, s = np.cos(theta/2), np.sin(theta/2)
        return np.array([[c, -np.exp(1j*lam)*s],
                         [np.exp(1j*phi)*s, np.exp(1j*(phi+lam))*c]])
    gates = {'id': np.eye(2), 'x': [[0,1],[1,0]], 'y': [[0,-1j],[1j,0]],
             'z': [[1,0],[0,-1]], 'h': np.array([[1,1],[1,-1]])/np.sqrt(2),
             's': [[1,0],[0,1j]], 'sdg': [[1,0],[0,-1j]],
             't': [[1,0],[0,np.exp(1j*np.pi/4)]], 'tdg': [[1,0],[0,np.exp(-1j*np.pi/4)]]}
    if name in gates:
        return np.array(gates[name], dtype=complex)
    if name in ('rx', 'ry', 'rz'):
        theta = float(params[0]); pauli = np.array(gates[{'rx':'x','ry':'y','rz':'z'}[name]], complex)
        return np.cos(theta/2)*np.eye(2)-1j*np.sin(theta/2)*pauli
    if name == 'cx':
        # Local bit zero is control, local bit one is target.
        matrix = np.zeros((4,4), complex)
        for col in range(4): matrix[col ^ (2 if col & 1 else 0), col] = 1
        return matrix
    raise InputError('ORACLE_UNSUPPORTED_GATE', f'Second verifier does not implement gate {name!r}; cross-check cannot be certified.', 'verification')


def embed(matrix, wires, total):
    full = np.zeros((2**total,2**total), complex)
    for column in range(2**total):
        local_column = sum(((column>>wire)&1)<<j for j,wire in enumerate(wires))
        base = column
        for wire in wires: base &= ~(1<<wire)
        for local_row in range(len(matrix)):
            row = base | sum(((local_row>>j)&1)<<wire for j,wire in enumerate(wires))
            full[row,column] = matrix[local_row,local_column]
    return full


def seed(total_program_qubits, data_wires):
    total = total_program_qubits+len(data_wires)
    amplitudes = np.zeros([2]*total,complex)
    for value in range(2**len(data_wires)):
        bits = [0]*total
        for j,wire in enumerate(data_wires):
            bits[total-1-wire] = (value>>j)&1
            bits[total-1-(total_program_qubits+j)] = (value>>j)&1
        amplitudes[tuple(bits)] = 1/np.sqrt(2**len(data_wires))
    vector=amplitudes.reshape(-1)
    return np.outer(vector, vector.conj())


def partial_trace(rho, keep):
    total = (len(rho)).bit_length()-1
    tensor = rho.reshape([2]*(2*total))
    # Trace unwanted tensor axes from high to low array axis, retaining bit order.
    remaining = list(reversed(range(total)))
    for wire in sorted(set(range(total))-set(keep)):
        axis = remaining.index(wire)
        tensor = np.trace(tensor, axis1=axis, axis2=axis+len(remaining))
        remaining.remove(wire)
    desired = list(reversed(keep))
    order = [remaining.index(wire) for wire in desired]
    tensor = tensor.transpose(order+[i+len(keep) for i in order])
    return tensor.reshape(2**len(keep),2**len(keep))


def choi(target):
    # Form output amplitudes by applying target to each reference-tagged basis state.
    dimension=len(target);vector=np.zeros(dimension**2,complex)
    for reference in range(dimension):
        for output in range(dimension):
            vector[reference*dimension+output]=target[output,reference]/np.sqrt(dimension)
    return np.outer(vector,vector.conj())


def execute(q, initial):
    total=(len(initial)).bit_length()-1
    cache={}
    def operator(matrix, wires, key):
        cache_key=(key,tuple(wires))
        if cache_key not in cache:cache[cache_key]=embed(matrix,wires,total)
        return cache[cache_key]
    def advance(circuit, classical, state, qmap, cmap):
        trajectories=[(classical,state)]
        for instruction in circuit.data:
            operation=instruction.operation
            wires=[qmap[circuit.find_bit(bit).index] for bit in instruction.qubits]
            destinations=[cmap[circuit.find_bit(bit).index] for bit in instruction.clbits]
            emitted=[]
            for record,rho in trajectories:
                if operation.name=='if_else':
                    variable,expected=operation.condition
                    condition_bits=list(variable) if hasattr(variable,'size') else [variable]
                    actual=sum(record[cmap[circuit.find_bit(bit).index]]*(2**j) for j,bit in enumerate(condition_bits))
                    selected=0 if actual==expected else 1
                    if selected<len(operation.blocks):
                        emitted.extend(advance(operation.blocks[selected],record,rho,wires,destinations))
                    else:emitted.append((record,rho))
                elif operation.name=='measure':
                    for outcome in (0,1):
                        projector=np.diag([1-outcome,outcome])
                        m=operator(projector,wires,('project',outcome))
                        projected=m@rho@m.conj().T
                        if np.any(projected):
                            updated=list(record);updated[destinations[0]]=outcome
                            emitted.append((tuple(updated),projected))
                elif operation.name=='reset':
                    zero=operator(np.array([[1,0],[0,0]]),wires,('reset',0))
                    one=operator(np.array([[0,1],[0,0]]),wires,('reset',1))
                    emitted.append((record,zero@rho@zero.conj().T+one@rho@one.conj().T))
                elif operation.name=='barrier':emitted.append((record,rho))
                else:
                    key=(operation.name,tuple(float(p) for p in operation.params))
                    unitary=operator(local_gate(operation.name,operation.params),wires,key)
                    emitted.append((record,unitary@rho@unitary.conj().T))
            # Merge only identical complete classical records, without discarding tiny branches.
            grouped={}
            for record,rho in emitted:
                grouped[record]=grouped.get(record,0)+rho
            trajectories=list(grouped.items())
        return trajectories
    return dict(advance(q,(0,)*q.num_clbits,initial,list(range(q.num_qubits)),list(range(q.num_clbits))))


def branch_maps(q, data_wires, source=False):
    states=execute(q,seed(q.num_qubits,data_wires))
    keep=data_wires+list(range(q.num_qubits,q.num_qubits+len(data_wires)))
    outputs=[np.zeros((2**len(keep),2**len(keep)),complex) for _ in range(2)]
    for record,state in states.items():
        success=(not any(record)) if source else bool(record[0])
        outputs[int(success)]+=partial_trace(state,keep)
    return outputs
