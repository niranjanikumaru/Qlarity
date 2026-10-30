import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
b=json.loads((root/'evidence/benchmark.json').read_text());e=json.loads((root/'evidence/example.json').read_text());a=json.loads((root/'evidence/adaptive.json').read_text())
lines=['# Recorded evidence summary','',f"Predeclared benchmark: {len(b['runs'])} runs; {sum('error' in r for r in b['runs'])} execution errors.",'','| Scenario | Discrete float failure | Encoded failure | IQAE decision |','|---|---:|---:|---|']
for s in e['scenarios']:lines.append(f"| {s['scenario']['label']} | {s['reference']['discrete_float']:.4%} | {s['reference']['encoded']:.4%} | {s['results'][-1]['decision']} |")
lines+=['',f"Adaptive example: {len(a['adaptive']['attempts'])} checks, {a['adaptive']['total_oracle_calls']} A/A-inverse calls. Fixed comparison: {a['fixed']['results'][-1]['oracle_calls']} calls. Adaptive did not save calls in this example.",'','Counts are simulator evidence, not a quantum hardware speedup. Model validation is numerical only; no external device reference was provided.','', '## Benchmark interval coverage (descriptive small suite)','','| Method | Covered / runs | Mean absolute error |','|---|---:|---:|']
methods=b['runs'][0]['result']['results']
for m in methods:
 vals=[];covered=0
 for run in b['runs']:
  if 'result' not in run:continue
  r=next(x for x in run['result']['results'] if x['method']==m['method']);p=run['result']['reference']['encoded']
  vals.append(abs(r['p_fail']-p));covered+=r['ci'][0]<=p<=r['ci'][1]
 lines.append(f"| {m['method']} | {covered}/{len(vals)} | {sum(vals)/len(vals):.6f} |")
lines+=['','The suite is too small to certify coverage. Exact methods have no sampling uncertainty. Statistical intervals do not include physical-model or discretization error.']
(root/'docs/EVIDENCE_SUMMARY.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines))
