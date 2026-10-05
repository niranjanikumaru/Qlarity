"""Verified alternative selection for a common, uncontrolled target contract.

Run: python -m retryguard.selection --out results/selection
Costs are explicit ideal-model operation weights, never hardware estimates.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from qiskit import QuantumCircuit
from .analysis import analyze, retry_cap, expected_attempts
from .compiler import native, static_counts, compile_source_retry, save_qasm
from .fixtures import fixtures, manifest_entries
from .validation import InputError, validate_budget
from .verifier import verify_source_retry

DEFAULT_WEIGHTS = {'cx':10., 'one_qubit':1., 'measure':5., 'reset':5.}


def counts(q):
    c=static_counts(q)
    return {'cx':c['cx'], 'one_qubit':c['u']+c['x'], 'measure':c['measure'], 'reset':c['reset']}


def validate_weights(weights):
    if set(weights)!=set(DEFAULT_WEIGHTS) or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not np.isfinite(v) or v<0 for v in weights.values()) or not any(weights.values()):
        raise InputError('INVALID_COST_WEIGHTS','Costs must be finite, nonnegative, and at least one must be positive.','weights')


def rank(candidates, weights, timeout, require_source=False):
    validate_weights(weights)
    eligible=[]
    for c in candidates:
        reasons=list(c.get('unavailable_reasons',[]))
        if not reasons:
            if not c.get('verified'): reasons.append('Exported circuit did not pass both verifiers.')
            if c['timeout_probability']>timeout+1e-14: reasons.append('Timeout exceeds requested budget.')
            if require_source and not c['preserves_source']: reasons.append('Does not preserve original trial, as required.')
            c['weighted_expected_cost']=sum(weights[k]*c['expected_counts'][k] for k in weights)
        c['exclusion_reasons']=reasons
        c['eligible']=not reasons
        if c['eligible']:eligible.append(c)
    if not eligible:return {'policy':None,'reason':'No verified candidate satisfies the requested constraints.'}
    # Deterministic tie-breaking: cost, timeout, then policy name. No preferred retry policy.
    winner=min(eligible,key=lambda c:(c['weighted_expected_cost'],c['timeout_probability'],c['policy']))
    return {'policy':winner['policy'],'qasm_file':winner['qasm_file'],
            'weighted_expected_cost':winner['weighted_expected_cost'],
            'reason':'Lowest weighted expected operation cost among verified, budget-feasible candidates; ties prefer lower timeout, then policy name.',
            'tied_policies':[c['policy'] for c in eligible if abs(c['weighted_expected_cost']-winner['weighted_expected_cost'])<1e-12]}


def replacement(target,p,cap):
    """Uncontrolled target; ancilla 0, data 1, syndrome zero means success."""
    q=QuantumCircuit(2,1)
    rotation=QuantumCircuit(1);rotation.ry(2*np.arccos(np.sqrt(p)),0);rotation=native(rotation)
    gate=QuantumCircuit(1);gate.unitary(target,0);gate=native(gate)
    def trial():
        q.compose(rotation,qubits=[0],inplace=True);q.measure(0,0)
        with q.if_test((q.clbits[0],0)):q.compose(gate,qubits=[1],inplace=True)
    trial()
    for _ in range(1,cap):
        with q.if_test((q.clbits[0],1)):
            q.reset(0);trial()
    return q


def deterministic(target):
    q=QuantumCircuit(2,1);q.unitary(target,1)
    # Measure initially zero ancilla to expose the same final success convention.
    q.measure(0,0)
    return native(q)


def compare(routine,out,timeout=.01,max_attempts=16,weights=None,require_source=False):
    validate_budget(timeout,max_attempts)
    weights=dict(DEFAULT_WEIGHTS if weights is None else weights);validate_weights(weights)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    a=analyze(routine);p=a['p'];candidates=[]
    trial=counts(native(routine.trial));ancillas=routine.trial.num_qubits-1
    recovery={k:0. for k in weights}
    for kraus,repair in zip(a['kraus'][1:],a['repairs']):
        q=QuantumCircuit(1);q.unitary(repair,0);c=counts(native(q))
        weight=float(np.trace(kraus.conj().T@kraus).real/2)
        for k in recovery:recovery[k]+=weight*c[k]
    target=QuantumCircuit(1);target.unitary(routine.target,0);target_counts=counts(native(target))
    coin=QuantumCircuit(1);coin.ry(2*np.arccos(np.sqrt(p)),0);coin_counts=counts(native(coin))
    for policy in ('repaired_source','fixed_retry','selected_retry','deterministic'):
        c={'policy':policy,'preserves_source':policy=='repaired_source'}
        try:
            if policy=='deterministic':cap=1
            elif policy=='fixed_retry':
                if p<.5:raise InputError('BASELINE_DOMAIN','Fixed retry assumes p >= 0.5.','probability')
                cap=retry_cap(.5,timeout,max_attempts)
            else:cap=retry_cap(p,timeout,max_attempts)
        except InputError as e:
            c.update(unavailable_reasons=[e.code+': '+str(e)],verified=False)
            candidates.append(c);continue
        t=0. if policy=='deterministic' else (1-p)**cap
        ex=1. if policy=='deterministic' else expected_attempts(p,cap)
        if policy=='repaired_source':
            q=compile_source_retry(routine,cap)
            expected={k:ex*(trial[k]+recovery[k]) for k in weights}
            expected['measure']+=ancillas*ex
            expected['reset']+=ancillas*max(0.,ex-1)
        elif policy=='deterministic':
            q=deterministic(routine.target);expected=counts(q)
        else:
            q=replacement(routine.target,p,cap)
            expected={k:coin_counts[k]*ex+target_counts[k]*(1-t) for k in weights}
            expected['measure']+=ex;expected['reset']+=max(0.,ex-1)
        path=out/(policy+'.qasm');save_qasm(q,path)
        verification=verify_source_retry(path,routine.target,1-t,timeout_probability=t)
        c.update(cap=cap,timeout_probability=t,expected_attempts=ex,expected_counts=expected,
                 static_counts_upper_bound=counts(q),qasm_file=path.name,
                 verified=verification['verified'],verification=verification)
        candidates.append(c)
    recommendation=rank(candidates,weights,timeout,require_source)
    return {'routine':routine.name,'source':routine.source,'lineage':routine.lineage,
            'contract':{'target':'Uncontrolled target on arbitrary reference-entangled data',
                        'timeout':'Identity on data; syndrome zero means success',
                        'max_timeout':timeout,'max_attempts':max_attempts,'require_source':require_source,
                        'records':'Only final status and data contract match; detailed syndrome/timing records may differ.'},
            'cost_model':{'weights':weights,'units':'Dimensionless operation-cost proxy; not measured latency, energy, money, or fault-tolerant cost.',
                          'objective':'Expected cost per invocation, including timed-out invocations; no automatic reruns after timeout.',
                          'counting':'Source includes every failure recovery, final failure recovery, all syndrome measurements, and resets before retries. Classical branch evaluation and idle costs are excluded. Static counts are conservative upper bounds, not executed worst-case paths.',
                          'phase':'Global phase of an uncontrolled target is unobservable; this ranking cannot be reused for a controlled target.'},
            'candidates':candidates,'recommendation':recommendation}


def markdown(report):
    lines=['# Alternative selection','', 'Ideal continuous U/CX model. Default costs are illustrative weights, not hardware measurements.', '',
           'All comparisons use the same uncontrolled target, identity-on-timeout contract and explicit success flag. Replacements do not retain source architecture/resource restrictions.','']
    for item in report['items']:
        lines+=['## '+str(item['name']),'']
        if item['status']=='rejected':lines += [item['error']['message'],''];continue
        r=item['comparison'];lines+=['Recommended: **'+str(r['recommendation']['policy'])+'**','',
              '| Candidate | Expected cost | Timeout | Eligible |','| --- | ---: | ---: | --- |']
        for c in r['candidates']:
            cost=c.get('weighted_expected_cost');timeout=c.get('timeout_probability')
            lines.append('| '+c['policy']+' | '+('—' if cost is None else f'{cost:.6g}')+' | '+('—' if timeout is None else f'{timeout:.6g}')+' | '+('Yes' if c['eligible'] else '; '.join(c['exclusion_reasons']))+' |')
        lines+=['',r['recommendation']['reason'],'']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest');parser.add_argument('--out',default='results/selection')
    parser.add_argument('--timeout',type=float,default=.01);parser.add_argument('--max-attempts',type=int,default=16)
    parser.add_argument('--require-source',action='store_true')
    for name,value in DEFAULT_WEIGHTS.items():parser.add_argument('--cost-'+name.replace('_','-'),type=float,default=value)
    args=parser.parse_args();weights={k:getattr(args,'cost_'+k) for k in DEFAULT_WEIGHTS}
    try:
        validate_budget(args.timeout,args.max_attempts);validate_weights(weights)
        entries=list(manifest_entries(args.manifest)) if args.manifest else [(i,r.name,r,None) for i,r in enumerate(fixtures(),1)]
    except InputError as e:
        print(json.dumps(e.as_dict()),file=sys.stderr);return 2
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True);items=[]
    for index,name,r,error in entries:
        try:
            if error:raise error
            result=compare(r,out/str(index),args.timeout,args.max_attempts,weights,args.require_source)
            items.append({'name':name,'status':'accepted','artifact_directory':str(index),'comparison':result})
        except InputError as e:items.append({'name':name,'status':'rejected','error':e.as_dict()})
    report={'schema_version':1,'items':items}
    (out/'selection.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    (out/'SELECTION.md').write_text(markdown(report))
    print(json.dumps({i['name']:i['comparison']['recommendation']['policy'] if i['status']=='accepted' else 'rejected' for i in items},indent=2))
    return 1 if any(i['status']=='rejected' or i['comparison']['recommendation']['policy'] is None for i in items) else 0

if __name__=='__main__':sys.exit(main())
