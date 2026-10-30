"""Predeclared benchmark, resolution study, adaptive comparison and charts."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import argparse,itertools,json,time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from backend.app.workbench import Scenario,analyze,run_experiment,adaptive,continuous_reference
from backend.app.classical.monte_carlo import clopper_pearson
OUT=ROOT/'evidence';OUT.mkdir(exist_ok=True)

def slim(r):
    r=json.loads(json.dumps(r))
    r.pop('population',None)
    for x in r['results']:
        if 'quantum' in x:x['quantum'].pop('circuits',None)
    return r

def charts(b,resolution):
    methods=[r['method'] for r in b['runs'][0]['result']['results']]
    fig,axs=plt.subplots(2,1,figsize=(6,5),constrained_layout=True)
    for i,m in enumerate(methods):
        vals=[];covered=0
        for run in b['runs']:
            if 'result' not in run:continue
            r=next(x for x in run['result']['results'] if x['method']==m);p=run['result']['reference']['encoded']
            vals.append(abs(r['p_fail']-p));covered+=r['ci'][0]<=p<=r['ci'][1]
        axs[0].scatter([i]*len(vals),vals,s=13,alpha=.5)
        lo,hi=clopper_pearson(covered,len(vals));cov=covered/len(vals)
        axs[1].errorbar(i,cov,yerr=[[cov-lo],[hi-cov]],fmt='o',capsize=4)
    for ax in axs:ax.set_xticks(range(len(methods)),methods,rotation=18,fontsize=8);ax.grid(alpha=.2)
    axs[0].set_ylabel('Absolute probability error');axs[1].set_ylabel('Observed coverage + binomial CI');axs[1].set_ylim(0,1.05)
    fig.suptitle('Small predefined suite; coverage sample is limited',fontsize=10);fig.savefig(OUT/'accuracy.svg');plt.close(fig)
    fig,ax=plt.subplots(figsize=(6,5),constrained_layout=True)
    for m in methods:
        xs=[];ys=[]
        for run in b['runs']:
            if 'result' not in run:continue
            r=next(x for x in run['result']['results'] if x['method']==m);p=run['result']['reference']['encoded']
            xs.append(r.get('oracle_calls',r.get('model_evaluations',0)) or r.get('conditional_queries',1));ys.append(max(abs(r['p_fail']-p),1e-7))
        ax.scatter(xs,ys,label=m,alpha=.6)
    ax.set_xscale('log');ax.set_yscale('log');ax.set_xlabel('Classical evaluations / CDF queries / quantum A calls\nDifferent resources; shared preprocessing excluded');ax.set_ylabel('Absolute error (zeros plotted at 1e-7)');ax.legend(fontsize=8);ax.grid(alpha=.2);fig.savefig(OUT/'cost.svg');plt.close(fig)
    fig,axs=plt.subplots(2,1,figsize=(6,5),constrained_layout=True)
    rs=resolution['precision'];axs[0].plot([r['scale'] for r in rs],[r['disagreement'] for r in rs],'o-',color='#d86d42');axs[0].set_ylabel('Disagreement mass')
    axs[1].plot([r['scale'] for r in rs],[r['two_qubit_gates'] for r in rs],'o-',color='#315d45');axs[1].set_ylabel('A two-qubit gates');axs[1].set_xlabel('Arithmetic scale')
    for ax in axs:ax.grid(alpha=.2)
    fig.savefig(OUT/'encoding.svg');plt.close(fig)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--quick',action='store_true');args=parser.parse_args()
    # Cases fixed before measurements, not selected by which estimator wins.
    seeds=[11,29] if args.quick else [11,29,47]
    design=list(itertools.product([1.1e-10,1.5e-10],[8,16],[.05,.025],seeds))
    b=dict(description='Fixed budgets, not a certified equal-cost speedup experiment. Repeated seeds share scenarios; aggregate coverage is descriptive. Every method targets the encoded finite distribution.',
        suite=dict(limits=[1.1e-10,1.5e-10],scales=[8,16],epsilon=[.05,.025],seeds=seeds),runs=[])
    for limit,scale,eps,seed in design:
        # Hoeffding-based budgets ensure conservative requested half-widths for MC/IS.
        s=Scenario(I_limit_A=limit,scale=scale,epsilon=eps,seed=seed,samples=min(100000,int(np.ceil(2*np.log(2/.05)/eps**2))),compare=False)
        print('BENCH',limit,scale,eps,seed,flush=True)
        try:b['runs'].append(dict(scenario=s.model_dump(),result=slim(analyze(s))))
        except Exception as exc:b['runs'].append(dict(scenario=s.model_dump(),error=str(exc)))
        (OUT/'benchmark.json').write_text(json.dumps(b,indent=2,allow_nan=False))
    res=dict(resolution=[],precision=[])
    c=continuous_reference(Scenario(quantum=False))
    for bins in [2,4,8,16]:
        r=analyze(Scenario(quantum=False,bins=bins));res['resolution'].append(dict(bins=bins,states=bins**3,p_float=r['reference']['discrete_float'],continuous=c['p_fail'],difference=r['reference']['discrete_float']-c['p_fail']))
    for scale in [4,8,16,32]:
        r=analyze(Scenario(scale=scale,compare=False));q=r['results'][-1]['quantum']
        res['precision'].append(dict(scale=scale,disagreement=r['approximation']['disagreement_mass'],qubits=q['n_total_qubits'],two_qubit_gates=q['resources']['A']['two_qubit_gates']))
    (OUT/'resolution.json').write_text(json.dumps(res,indent=2));charts(b,res)
    print('RECORDED EXAMPLE',flush=True)
    example=run_experiment(Scenario(scale=16),print);example['execution']='recorded'
    (OUT/'example.json').write_text(json.dumps(example,indent=2,allow_nan=False))
    print('ADAPTIVE COMPARISON',flush=True)
    s=Scenario(compare=False,adaptive=True)
    a=adaptive(s,print)
    fixed=analyze(s.model_copy(update={'adaptive':False,'scale':32,'epsilon':.02}))
    # Strip QASM from benchmark-only copies; live adaptive result keeps full evidence.
    a['result']=slim(a['result'])
    for x in a['attempts']:x['result']=slim(x['result'])
    (OUT/'adaptive.json').write_text(json.dumps(dict(adaptive=a,fixed=slim(fixed),note='Same nominal family confidence; different stopping goals. Report costs and decisions without assuming savings.'),indent=2,allow_nan=False))
    from backend.app.benchmark_report import summarize
    (OUT/'benchmark-summary.json').write_text(json.dumps(summarize(b),indent=2,allow_nan=False))
    print('DONE',flush=True)
if __name__=='__main__':main()
