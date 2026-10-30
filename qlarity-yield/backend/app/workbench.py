"""Versioned, matched-target leakage-yield experiment. All calculations are real."""
from __future__ import annotations
import hashlib, itertools, json, math, time
from dataclasses import asdict
from typing import Literal
import numpy as np
from scipy import stats, integrate
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .physics.leakage import NominalDevice, OperatingPoint, compute_leakage, thermal_voltage
from .physics.variations import build_discrete_var, JointDistribution
from .physics.discretize import build_quantised_score
from .classical.monte_carlo import clopper_pearson

MODEL_ID = 'illustrative-bulk-nmos-v2'
DEVICE = asdict(NominalDevice())
OPERATING = asdict(OperatingPoint())

class Scenario(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    label: str = Field(default='Illustrative 65 nm bulk nMOS', max_length=100)
    sigma_L_nm: float = Field(3., gt=0, le=10)
    sigma_tox_nm: float = Field(.1, gt=0, le=.3)
    sigma_vth_mV: float = Field(15., gt=0, le=60)
    I_limit_A: float = Field(1.25e-10, gt=1e-14, le=1e-6)
    temperature_K: float = Field(300., ge=250, le=400)
    bins: Literal[2,4,8,16] = 4
    scale: int = Field(8, ge=2, le=64)
    max_failure_probability: float = Field(.3, ge=0, le=1)
    reduction: float = Field(.25, gt=0, le=.75)
    alpha: float = Field(.05, ge=.001, le=.2)
    epsilon: float = Field(.05, ge=.02, le=.2)
    samples: int = Field(4096, ge=256, le=100000)
    shots: int = Field(256, ge=64, le=1024)
    seed: int = Field(42, ge=0, le=2147483647)
    quantum: bool = True
    adaptive: bool = False
    compare: bool = True
    @model_validator(mode='after')
    def supported(self):
        if self.quantum and self.bins != 4:
            raise ValueError('The verified quantum encoding supports exactly 4 bins; use classical mode for resolution studies.')
        return self

def model_card():
    return dict(id=MODEL_ID, device=DEVICE, operating=OPERATING,
        formula='Ioff = I0*(W/L_um)*exp(-(Vth0 + alpha_L*dL + alpha_tox*dtox + dVth_mV/1000 - Vgs)/(n*kT/q))',
        provenance='Illustrative educational subthreshold expression, not a foundry-calibrated BSIM implementation.',
        reference='https://bsim.berkeley.edu/models/bsim4/',
        validation='Numerical implementation checks only; no independent SPICE or fabrication validation supplied.',
        limitations=['Independent inputs; no correlations.', 'Vds and Vbs are metadata only: this model has no drain/body dependence.',
        'No aging, circuit-level aggregation or overall chip-yield prediction.', 'Distribution and device parameters are illustrative.',
        'Continuous Gaussian tails include physically invalid geometries: only the truncated domain is modeled.'],
        distribution='Independent N(0,sigma), conditioned on all three inputs lying within ±3 sigma; equal-mass bins represented by conditional means.',
        units=dict(sigma_L_nm='nm',sigma_tox_nm='nm',sigma_vth_mV='mV',I_limit_A='A',temperature_K='K'),
        failure='Ioff >= I_limit; equality is failure', default_scenario=Scenario().model_dump())

def domain(s):
    device=NominalDevice(); op=OperatingPoint(temperature_K=s.temperature_K)
    vs=[build_discrete_var(n,u,v,n_bins=s.bins) for n,u,v in [('delta_L','nm',s.sigma_L_nm),('delta_tox','nm',s.sigma_tox_nm),('delta_vth','mV',s.sigma_vth_mV)]]
    joint=JointDistribution(*vs); q=build_quantised_score(joint,s.I_limit_A,op,device,scale=s.scale)
    return device,op,joint,q

def identity(s):
    d={k:v for k,v in s.model_dump().items() if k in ['sigma_L_nm','sigma_tox_nm','sigma_vth_mV','I_limit_A','temperature_K','bins','scale']}
    return MODEL_ID+':'+hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()[:16]

def decision(ci,target):
    lo,hi=ci
    return 'meets modeled target' if hi<=target else 'misses modeled target' if lo>target else 'unresolved'

def result(method,p,ci,s,tid,delta,elapsed,**extras):
    # Weighted classification disagreement is an exhaustive finite-grid bound.
    bounded=[max(0.,ci[0]-delta),min(1.,ci[1]+delta)]
    return dict(method=method,p_fail=float(p),yield_estimate=1-float(p),ci=list(map(float,ci)),
        yield_ci=[1-float(ci[1]),1-float(ci[0])],target_id=tid+':encoded',
        decision_target_id=tid+':discrete-float',decision_ci=bounded,
        decision=decision(bounded,s.max_failure_probability),alpha=s.alpha,
        elapsed_s=elapsed,seed=s.seed,**extras)

def conditional_reference(joint,q):
    # Monotone-independent additive score: sort one marginal and use its CDF.
    t=time.perf_counter(); vals=np.array(q.C_vth); order=np.argsort(vals)
    vals=vals[order]; cum=np.r_[0.,np.cumsum(np.array(joint.var_vth.probabilities)[order])]
    p=0.
    for i,a in enumerate(q.C_L):
        for j,b in enumerate(q.C_tox):
            ix=np.searchsorted(vals,q.T-q.C0-a-b,side='left')
            p+=joint.var_L.probabilities[i]*joint.var_tox.probabilities[j]*(1-cum[ix])
    return float(p),time.perf_counter()-t

def continuous_reference(s):
    """Integrate out Vth analytically; integrate the remaining two variables."""
    d=NominalDevice(); op=OperatingPoint(temperature_K=s.temperature_K)
    a,b=stats.norm.cdf(-3),stats.norm.cdf(3); mass=b-a; nvt=d.n_ideality*thermal_voltage(op.temperature_K)
    def inner(zt,zl):
        L=zl*s.sigma_L_nm; tox=zt*s.sigma_tox_nm
        critical=1000*(op.Vgs-d.Vth0_V-d.alpha_L_V_per_nm*L-d.alpha_tox_V_per_nm*tox+nvt*math.log(d.I0_A_per_um*op.W_um/((d.L0_nm+L)*.001*s.I_limit_A)))
        prob=np.clip((stats.norm.cdf(critical/s.sigma_vth_mV)-a)/mass,0,1)
        return float(prob)*stats.norm.pdf(zl)*stats.norm.pdf(zt)/mass**2
    t=time.perf_counter(); val,err=integrate.dblquad(inner,-3,3,-3,3,epsabs=2e-6,epsrel=2e-5)
    continuous_spec={k:getattr(s,k) for k in ['sigma_L_nm','sigma_tox_nm','sigma_vth_mV','I_limit_A','temperature_K']}
    cid=hashlib.sha256(json.dumps(continuous_spec,sort_keys=True).encode()).hexdigest()[:16]
    return dict(p_fail=val,quadrature_error_estimate=err,elapsed_s=time.perf_counter()-t,
        target_id=MODEL_ID+':'+cid+':continuous-truncated',
        note='Numerical quadrature error estimate, not a rigorous physical-error bound. Different target from finite-grid estimators.')

def analyze(s:Scenario,progress=lambda msg:None):
    t0=time.perf_counter(); d,op,joint,q=domain(s); tid=identity(s)
    vs=[joint.var_L,joint.var_tox,joint.var_vth]
    ids=np.array(list(itertools.product(range(s.bins),repeat=3)))
    weights=np.array([np.prod([vs[k].probabilities[row[k]] for k in range(3)]) for row in ids])
    scores=np.array([q.score(*row) for row in ids]); flags=scores>=q.T
    currents=np.array([compute_leakage(*[vs[k].values[row[k]] for k in range(3)],op,d)[0] for row in ids])
    float_flags=currents>=s.I_limit_A
    exact=float(weights@flags); float_p=float(weights@float_flags)
    delta=float(weights@(flags!=float_flags)); prep=time.perf_counter()-t0
    logvals=np.log(currents/d.I_ref_A)
    score_error=float(np.max(np.abs(logvals-scores/s.scale)))
    # Four nearest-integer roundings, each <= .5/scale. Exact separability.
    analytic_bound=2/s.scale
    assert score_error<=analytic_bound+1e-10
    assert 0<=q.S_min+q.B<=q.S_max+q.B<2**q.accumulator_bits
    lower=float(weights@(scores/s.scale-analytic_bound>=q.float_g_threshold))
    upper=float(weights@(scores/s.scale+analytic_bound>=q.float_g_threshold))
    out=dict(schema_version=2,scenario=s.model_dump(),target_id=tid,model=model_card(),
        distribution=asdict(joint),execution='fresh',reference=dict(encoded=exact,discrete_float=float_p,
        signed_encoding_difference=exact-float_p,states=len(ids),preprocessing_s=prep,reference_evaluations=len(ids)),
        approximation=dict(disagreement_mass=delta,score_error_observed=score_error,score_error_bound=analytic_bound,
        float_probability_bracket=[lower,upper],omitted_tail_mass=joint.total_omitted_tail_mass(),
        discretization='Not covered by decision interval; see continuous reference and resolution study.',
        physical_model='Unquantified; illustrative, not fabrication validated.',
        rounding='Python nearest integer (ties to even); threshold ceil(scale*log(limit/Iref)).',
        bound_scope='Exact weighted disagreement on this finite grid; exhaustive validation cost included separately. No scalable shortcut claimed.'),
        population=[dict(index=i,delta_L_nm=float(vs[0].values[row[0]]),delta_tox_nm=float(vs[1].values[row[1]]),delta_vth_mV=float(vs[2].values[row[2]]),current_A=float(currents[i]),weight=float(weights[i]),encoded_failure=bool(flags[i]),float_failure=bool(float_flags[i])) for i,row in enumerate(ids)],results=[])
    out['results'].append(result('Exact encoded',exact,[exact,exact],s,tid,delta,prep,model_evaluations=len(ids),interval_method='Exact finite sum'))
    cp,ct=conditional_reference(joint,q)
    out['results'].append(result('Conditional CDF',cp,[cp,cp],s,tid,delta,ct,model_evaluations=0,conditional_queries=s.bins**2,
        interval_method='Exact weighted marginal CDF',preprocessing_contributions=3*s.bins+1))
    rng=np.random.default_rng(s.seed)
    def evaluate(indices):
        return (q.C0+np.array(q.C_L)[indices[:,0]]+np.array(q.C_tox)[indices[:,1]]+np.array(q.C_vth)[indices[:,2]]>=q.T)
    progress(s.label+': Monte Carlo')
    t=time.perf_counter(); ix=np.column_stack([rng.choice(s.bins,s.samples,p=v.probabilities) for v in vs]); f=evaluate(ix)
    ci=clopper_pearson(int(f.sum()),s.samples,s.alpha)
    out['results'].append(result('Monte Carlo',f.mean(),ci,s,tid,delta,time.perf_counter()-t,model_evaluations=s.samples,failures=int(f.sum()),interval_method='Clopper-Pearson fixed sample'))
    progress(s.label+': importance sampling')
    t=time.perf_counter()
    # Fixed physics-informed proposal. No unreported training or failure lookup.
    shifted=[]
    for v in vs:
        z=np.exp(-.7*np.array(v.values)/v.sigma)*np.array(v.probabilities); shifted.append(z/z.sum())
    ix=np.column_stack([rng.choice(s.bins,s.samples,p=p) for p in shifted]); original=rng.random(s.samples)<.5
    for k,v in enumerate(vs): ix[original,k]=rng.choice(s.bins,int(original.sum()),p=v.probabilities)
    p=np.prod([np.array(v.probabilities)[ix[:,k]] for k,v in enumerate(vs)],axis=0)
    shifted_p=np.prod([shifted[k][ix[:,k]] for k in range(3)],axis=0)
    w=p/(.5*p+.5*shifted_p); terms=evaluate(ix)*w; est=float(terms.mean())
    # q>=.5p -> 0<=f*p/q<=2. Hoeffding is conservative and valid at zero failures.
    margin=2*math.sqrt(math.log(2/s.alpha)/(2*s.samples)); ci=[max(0,est-margin),min(1,est+margin)]
    out['results'].append(result('Importance sampling',est,ci,s,tid,delta,time.perf_counter()-t,
        model_evaluations=s.samples,pilot_evaluations=0,interval_method='Bounded-weight Hoeffding; conservative finite-sample',
        proposal='0.5 original + 0.5 product of lower-tail exponential tilts; fixed before sampling',
        ess=float(w.sum()**2/(w@w)),max_weight=float(w.max()),weight_cv=float(w.std()/w.mean()),
        diagnostics=['Low effective sample size'] if w.sum()**2/(w@w)<.1*s.samples else []))
    if s.quantum:
        progress(s.label+': constructing and executing IQAE')
        from .quantum.oracle import build_oracle
        from .quantum.iqae import run_iqae
        if 7+q.accumulator_bits>16: raise ValueError('Quantum width exceeds the 16-qubit execution limit')
        oracle=build_oracle(joint,q,validate=False)
        quantum=run_iqae(oracle,epsilon_target=s.epsilon,alpha=s.alpha,default_shots=s.shots,seed=s.seed,exact_p_fail=exact)
        qr=asdict(quantum)
        r=result('IQAE',quantum.p_fail_estimate,[quantum.p_fail_ci_lower,quantum.p_fail_ci_upper],s,tid,delta,quantum.elapsed_s,
            model_evaluations=0,oracle_calls=quantum.NA_our_count,interval_method='IQAE beta intervals',quantum=qr)
        out['results'].append(r)
    out['elapsed_s']=time.perf_counter()-t0
    return out

def variants(s):
    out=[s.model_copy(update={'label':'Baseline'})]
    for label,keys in [('Tighter gate length',['sigma_L_nm']),('Tighter threshold voltage',['sigma_vth_mV']),('Combined',['sigma_L_nm','sigma_vth_mV'])]:
        out.append(s.model_copy(update={'label':label,**{k:getattr(s,k)*(1-s.reduction) for k in keys}}))
    return out

def adaptive(s,progress):
    """At most 3 independent IQAE checks; Bonferroni alpha/3 across checks."""
    attempts=[]; current=s.model_copy(update={'alpha':s.alpha/3,'adaptive':False,'compare':False})
    for n in range(3):
        r=analyze(current,progress); qr=r['results'][-1]; delta=r['approximation']['disagreement_mass']
        width=(qr['ci'][1]-qr['ci'][0])/2
        reason='decision resolved' if qr['decision']!='unresolved' else 'encoding dominates' if delta>width else 'sampling dominates'
        attempts.append(dict(step=n+1,reason=reason,result=r))
        if qr['decision']!='unresolved': break
        if reason=='encoding dominates': current=current.model_copy(update={'scale':min(64,current.scale*2)})
        else: current=current.model_copy(update={'epsilon':max(.02,current.epsilon/2),'shots':min(1024,current.shots*2)})
        current=current.model_copy(update={'seed':s.seed+n+1})
    return dict(attempts=attempts,result=attempts[-1]['result'],family_alpha=s.alpha,
        stopping='Bonferroni alpha/3; at most three checks; no sample reuse',
        total_oracle_calls=sum(a['result']['results'][-1].get('oracle_calls',0) for a in attempts),
        total_elapsed_s=sum(a['result']['elapsed_s'] for a in attempts),exhausted=attempts[-1]['result']['results'][-1]['decision']=='unresolved')

def run_experiment(s,progress=lambda msg:None):
    scenarios=variants(s) if s.compare else [s]
    output=dict(schema_version=2,execution='fresh',model=model_card(),request=s.model_dump(),scenarios=[],
        confidence_scope='Per estimator and scenario. Adaptive steps use alpha/3; no simultaneous guarantee across different scenarios.',
        runtime='Ideal finite-shot statevector simulation; simulator runtime is not quantum hardware runtime.')
    for scenario in scenarios:
        if s.adaptive and s.quantum:
            a=adaptive(scenario,progress); r=a.pop('result'); r['adaptive']=a
        else: r=analyze(scenario,progress)
        output['scenarios'].append(r)
    progress('Continuous reference (separate target)')
    output['continuous_reference']=continuous_reference(s)
    tail=output['scenarios'][0]['approximation']['omitted_tail_mass']; c=output['continuous_reference']['p_fail']
    output['continuous_reference']['unknown_tail_extension']=[(1-tail)*c,(1-tail)*c+tail]
    output['continuous_reference']['tail_note']='Hypothetical extension assigning arbitrary outcomes outside modeled support; not a validated full Gaussian device model.'
    progress('Completed')
    return output
