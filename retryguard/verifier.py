"""Density interpreter for re-imported QASM; no analyzer Kraus or recurrence reuse.
A second NumPy engine supplies independent essential operations; parsing remains shared.
"""
import numpy as np
from qiskit import qasm3
from qiskit.quantum_info import DensityMatrix
from .validation import validate_target, validate_probability

def add(out,key,rho):
    if key in out:out[key]+=rho
    else:out[key]=rho.copy()

def execute(q,rho):
    def run(block,states,qmap,cmap):
        for inst in block.data:
            op=inst.operation;inds=[qmap[block.find_bit(b).index] for b in inst.qubits];bits=[cmap[block.find_bit(b).index] for b in inst.clbits];out={}
            for key,state in states.items():
                if op.name=='if_else':
                    var,val=op.condition
                    if hasattr(var,'size'):
                        locs=[cmap[block.find_bit(b).index] for b in var];actual=sum(key[b]<<i for i,b in enumerate(locs))
                    else:actual=key[cmap[block.find_bit(var).index]]
                    branch=0 if actual==val else 1
                    if branch<len(op.blocks):
                        sub=run(op.blocks[branch],{key:state},inds,bits)
                        for k,s in sub.items():add(out,k,s)
                    else:add(out,key,state)
                elif op.name=='measure':
                    for value in (0,1):
                        mask=(((np.arange(state.shape[0])>>inds[0])&1)==value);r=state*mask[:,None]*mask[None,:]
                        if np.any(r):
                            k=list(key);k[bits[0]]=value;add(out,tuple(k),r)
                elif op.name=='reset':
                    bit=1<<inds[0];zero=[i for i in range(state.shape[0]) if not i&bit];r=np.zeros_like(state)
                    for i in zero:
                        for j in zero:r[i,j]=state[i,j]+state[i+bit,j+bit]
                    add(out,key,r)
                elif op.name=='barrier':add(out,key,state)
                else:add(out,key,DensityMatrix(state).evolve(op,qargs=inds).data)
            states=out
        return states
    return run(q,{(0,)*q.num_clbits:rho},list(range(q.num_qubits)),list(range(q.num_clbits)))

def choi_input(nq,data_bits):
    d=2**len(data_bits);v=np.zeros(2**(nq+len(data_bits)),complex)
    for x in range(d):
        ix=sum(((x>>j)&1)<<b for j,b in enumerate(data_bits))+(x<<nq);v[ix]=1/np.sqrt(d)
    return np.outer(v,v.conj())

def reduce(state,keep):
    n=int(round(np.log2(state.shape[0])));lost=[i for i in range(n) if i not in keep];d=2**len(keep);out=np.zeros((d,d),complex)
    def index(x,y):return sum(((x>>i)&1)<<b for i,b in enumerate(keep))+sum(((y>>i)&1)<<b for i,b in enumerate(lost))
    for i in range(d):
        for j in range(d):out[i,j]=sum(state[index(i,e),index(j,e)] for e in range(2**len(lost)))
    return out

def ideal_choi(u):
    v=u.reshape(-1,order='F')/np.sqrt(len(u));return np.outer(v,v.conj())

def verify_source(q,target,p):
    target=validate_target(target);p=validate_probability(p, allow_zero=True)
    a=q.num_qubits-1;states=execute(q,choi_input(q.num_qubits,[a]));out=[np.zeros((4,4),complex),np.zeros((4,4),complex)]
    for key,rho in states.items():out[0 if not any(key) else 1]+=reduce(rho,[a,q.num_qubits])
    return {'success_residual':float(np.linalg.norm(out[0]-p*ideal_choi(target))),
            'timeout_residual':float(np.linalg.norm(out[1]-(1-p)*ideal_choi(np.eye(2))))}

# Conditional checks below this probability are intentionally not certified.
CONDITIONAL_FLOOR = 1e-250
CHECK_TOL = 1e-9


def compare_branches(outputs, independent_outputs, target, success_probability, timeout_probability, independent_target=None):
    """Check absolute maps, conditional states, probability ratios, and engine agreement."""
    from .independent import choi as second_choi
    probabilities = [timeout_probability, success_probability]
    ideals = [ideal_choi(np.eye(len(target))), ideal_choi(target)]
    other_ideals = [second_choi(np.eye(len(target))), second_choi(target if independent_target is None else independent_target)]
    result = {}; branches = []; failures = []
    for index, name in enumerate(('timeout', 'success')):
        expected = probabilities[index]
        actual = float(np.trace(outputs[index]).real)
        other_actual = float(np.trace(independent_outputs[index]).real)
        result[name+'_probability'] = actual
        result[name+'_residual'] = float(np.linalg.norm(outputs[index]-expected*ideals[index]))
        result['independent_'+name+'_residual'] = float(np.linalg.norm(independent_outputs[index]-expected*other_ideals[index]))
        result[name+'_engine_agreement_residual'] = float(np.linalg.norm(outputs[index]-independent_outputs[index]))
        branch = {'branch': name, 'expected_probability': expected, 'actual_probability': actual,
                  'independent_probability': other_actual}
        for engine, observed, matrix, ideal in [('primary',actual,outputs[index],ideals[index]),
                                               ('independent',other_actual,independent_outputs[index],other_ideals[index])]:
            if expected == 0:
                branch[engine+'_conditional_status'] = 'zero_expected_absolute_check_only'
                if observed != 0:
                    branch[engine+'_conditional_status'] = 'unexpected_mass_not_certified'
                    failures.append({'code':'UNEXPECTED_BRANCH' if abs(observed)>CHECK_TOL else 'UNRESOLVED_UNEXPECTED_BRANCH','branch':name,'engine':engine})
            elif expected < CONDITIONAL_FLOOR:
                branch[engine+'_conditional_status'] = 'below_resolution'
                failures.append({'code':'UNRESOLVED_RARE_BRANCH','branch':name,'engine':engine})
            else:
                probability_error = abs(observed/expected-1)
                result[engine+'_'+name+'_relative_probability_residual'] = float(probability_error)
                if probability_error >= CHECK_TOL:
                    failures.append({'code':'BRANCH_PROBABILITY_MISMATCH','branch':name,'engine':engine})
                if observed < CONDITIONAL_FLOOR or not np.isfinite(observed):
                    branch[engine+'_conditional_status'] = 'missing_or_unresolved'
                    failures.append({'code':'MISSING_BRANCH','branch':name,'engine':engine})
                else:
                    conditional = float(np.linalg.norm(matrix/observed-ideal))
                    result[engine+'_'+name+'_conditional_residual'] = conditional
                    branch[engine+'_conditional_status'] = 'checked'
                    if conditional >= CHECK_TOL or not np.isfinite(conditional):
                        failures.append({'code':'CONDITIONAL_STATE_MISMATCH','branch':name,'engine':engine})
        if actual >= CONDITIONAL_FLOOR and other_actual >= CONDITIONAL_FLOOR:
            disagreement = float(np.linalg.norm(outputs[index]/actual-independent_outputs[index]/other_actual))
            result[name+'_conditional_engine_agreement_residual'] = disagreement
            if disagreement >= CHECK_TOL or not np.isfinite(disagreement):
                failures.append({'code':'ENGINE_DISAGREEMENT','branch':name,'engine':'cross_check'})
        for field in (name+'_residual','independent_'+name+'_residual'):
            if result[field] >= CHECK_TOL or not np.isfinite(result[field]):
                failures.append({'code':'BRANCH_MAP_MISMATCH','branch':name,'engine': 'independent' if field.startswith('independent') else 'primary'})
        branches.append(branch)
    result['trace_residual'] = float(abs(sum(np.trace(x).real for x in outputs)-1))
    result['independent_trace_residual'] = float(abs(sum(np.trace(x).real for x in independent_outputs)-1))
    if max(result['trace_residual'],result['independent_trace_residual']) >= CHECK_TOL:
        failures.append({'code':'TRACE_MISMATCH','branch':'total','engine':'cross_check'})
    result['verified'] = not failures and all(np.isfinite(v) and v < CHECK_TOL for k,v in result.items() if k.endswith('residual'))
    result['branch_checks'] = branches
    result['failures'] = failures
    result['independence_scope'] = 'Separate gate matrices, measurement, reset, reference preparation and partial trace; shared Qiskit QASM parser, NumPy and declared contract.'
    return result


def verify_export(path, target, probability, timeout_probability=None, source=False):
    from .independent import branch_maps
    from .validation import InputError
    target=validate_target(target); probability=validate_probability(probability, allow_zero=True)
    provided = timeout_probability is not None
    timeout_probability = 1-probability if timeout_probability is None else validate_probability(timeout_probability, allow_zero=True)
    if abs(probability+timeout_probability-1) > 1e-12:
        raise InputError('INCONSISTENT_PROBABILITIES', 'Success and timeout probabilities must sum to one.', 'probability')
    q=qasm3.loads(path.read_text())
    if source:
        a=q.num_qubits-1
        if a not in (1,2) or q.num_clbits!=a:
            raise InputError('VERIFIER_LAYOUT', 'Expected one data qubit and a complete syndrome register.', 'verification')
        data=[a]; expected_target=target; second_target=target
    else:
        if q.num_qubits!=3 or q.num_clbits!=1:
            raise InputError('VERIFIER_LAYOUT', 'Expected control, data, coin and one flag bit.', 'verification')
        data=[0,1]; expected_target=np.eye(4,dtype=complex)
        expected_target[np.ix_([1,3],[1,3])]=target
        second_target=np.kron(np.eye(2),np.diag([1,0]))+np.kron(target,np.diag([0,1]))
    states=execute(q,choi_input(q.num_qubits,data))
    keep=data+list(range(q.num_qubits,q.num_qubits+len(data)))
    outputs=[np.zeros((2**len(keep),2**len(keep)),complex) for _ in range(2)]
    for key,rho in states.items():
        success=(not any(key)) if source else bool(key[0])
        outputs[int(success)]+=reduce(rho,keep)
    independent_outputs=branch_maps(q,data,source)
    result=compare_branches(outputs,independent_outputs,expected_target,probability,timeout_probability,second_target)
    result['timeout_probability_supplied'] = provided
    result['probability_note'] = 'Timeout supplied separately to avoid cancellation in 1-success.' if provided else 'Timeout inferred as 1-success; pass timeout_probability explicitly for rare-branch verification.'
    return result


def verify(path, target, probability, *, timeout_probability=None):
    return verify_export(path,target,probability,timeout_probability,source=False)


def verify_source_retry(path, target, probability, *, timeout_probability=None):
    return verify_export(path,target,probability,timeout_probability,source=True)
