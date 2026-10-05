"""Executable templates in continuous U + CX basis."""
import numpy as np
from qiskit import QuantumCircuit,transpile,qasm3
from qiskit.circuit.library import UnitaryGate
from .validation import validate_probability, validate_cap, validate_target

def native(q):return transpile(q,basis_gates=['u','cx'],optimization_level=1,seed_transpiler=17)

def controlled_target(target):
    target=validate_target(target)
    q=QuantumCircuit(2);q.append(UnitaryGate(target).control(),[0,1]);return q

def corrected_source(routine,analysis,include_final_recovery=True):
    a=routine.trial.num_qubits-1;q=QuantumCircuit(a+1,a);q.compose(native(routine.trial),inplace=True);q.measure(range(a),range(a))
    if include_final_recovery:
        for j,r in enumerate(analysis['repairs'],1):
            patch=QuantumCircuit(1);patch.unitary(r,0)
            with q.if_test((q.cregs[0],j)):q.compose(native(patch),qubits=[a],inplace=True)
    return q

def compile_source_retry(routine, n):
    """Bounded, uncontrolled retry of the original trial; syndrome 0 is success.

    Ancillas alone are reset before retries. Every failed attempt is repaired,
    including the last. The data register is never reset. Analyze internally so
    an unsupported source cannot be paired with an unrelated recovery result.
    """
    from .analysis import analyze
    n=validate_cap(n)
    analysis = analyze(routine)
    a = routine.trial.num_qubits - 1
    body = corrected_source(routine, analysis)
    q = QuantumCircuit(a + 1, a)
    # The initial zero classical register is not yet a success measurement.
    q.compose(body, qubits=q.qubits, clbits=q.clbits, inplace=True)
    stopped = QuantumCircuit(a + 1, a)
    retry = QuantumCircuit(a + 1, a)
    retry.reset(range(a))
    retry.compose(body, inplace=True)
    for _ in range(1, n):
        # Explicit blocks retain complete quantum and classical register maps.
        q.if_else((q.cregs[0], 0), stopped, retry, q.qubits, q.clbits)
    return q

def attempt(target,p):
    p=validate_probability(p);target=validate_target(target)
    q=QuantumCircuit(3);q.ry(2*np.arcsin(np.sqrt(p)),2)
    q.append(controlled_target(target).to_gate().control(),[2,0,1]);return native(q)

def compile_retry(target,p,n):
    p=validate_probability(p);n=validate_cap(n);target=validate_target(target)
    body=attempt(target,p);q=QuantumCircuit(3,1)
    for _ in range(n):
        with q.if_test((q.clbits[0],False)):
            q.reset(2);q.compose(body,inplace=True);q.measure(2,0)
    return q

def compile_deterministic(target):
    q=QuantumCircuit(3,1);q.compose(native(controlled_target(target)),qubits=[0,1],inplace=True);q.x(2);q.measure(2,0);return q

def static_counts(q):
    result={'u':0,'cx':0,'measure':0,'reset':0,'x':0}
    for inst in q.data:
        if inst.operation.name=='if_else':
            for block in inst.operation.blocks:
                sub=static_counts(block)
                for k in result:result[k]+=sub[k]
        elif inst.operation.name in result:result[inst.operation.name]+=1
        else:raise ValueError('Unexpected emitted operation '+inst.operation.name)
    return result

def save_qasm(q,path):path.write_text(qasm3.dumps(q))

def compile_early_measure(target,p,n):
    """Stronger fixed-policy baseline: measure data-independent coin before CU."""
    p=validate_probability(p);n=validate_cap(n);target=validate_target(target)
    q=QuantumCircuit(3,1);rotation=QuantumCircuit(1);rotation.ry(2*np.arcsin(np.sqrt(p)),0)
    rotation=native(rotation);cu=native(controlled_target(target))
    for _ in range(n):
        with q.if_test((q.clbits[0],False)):
            q.reset(2);q.compose(rotation,qubits=[2],inplace=True);q.measure(2,0)
            with q.if_test((q.clbits[0],True)):q.compose(cu,qubits=[0,1],inplace=True)
    return q
