"""Summarize measured accuracy and coverage, without implying a speedup."""
from collections import defaultdict
from .classical.monte_carlo import clopper_pearson

def summarize(dataset):
    groups=defaultdict(list);errors=[]
    for run in dataset['runs']:
        if 'result' not in run:
            errors.append({'scenario':run['scenario'],'error':run.get('error','missing result')});continue
        reference=run['result']['reference']['encoded'];epsilon=run['scenario']['epsilon']
        for result in run['result']['results']:
            error=abs(result['p_fail']-reference)
            groups[result['method']].append(dict(error=error,within_target=error<=epsilon,
                covered=result['ci'][0]<=reference<=result['ci'][1],
                half_width=(result['ci'][1]-result['ci'][0])/2,
                interval_target=(result['ci'][1]-result['ci'][0])/2<=epsilon,
                classical_evaluations=result.get('model_evaluations',0),
                conditional_queries=result.get('conditional_queries',0),
                oracle_calls=result.get('oracle_calls',0),elapsed_s=result['elapsed_s']))
    rows=[]
    for method,values in groups.items():
        n=len(values);covered=sum(x['covered'] for x in values);achieved=sum(x['within_target'] for x in values)
        rows.append(dict(method=method,runs=n,within_accuracy_target=achieved,accuracy_target_fraction=achieved/n,
            interval_half_width_target=sum(x['interval_target'] for x in values),
            covered=covered,coverage=covered/n,coverage_binomial_interval=list(clopper_pearson(covered,n)),
            mean_absolute_error=sum(x['error'] for x in values)/n,
            max_absolute_error=max(x['error'] for x in values),
            total_classical_evaluations=sum(x['classical_evaluations'] for x in values),
            total_conditional_queries=sum(x['conditional_queries'] for x in values),
            total_oracle_calls=sum(x['oracle_calls'] for x in values),
            mean_elapsed_s=sum(x['elapsed_s'] for x in values)/n))
    return dict(rows=rows,errors=errors,note='Descriptive aggregation across heterogeneous cases. Binomial intervals summarize observed coverage but do not certify uniform algorithm coverage. Fixed budgets; no practical speedup established. Shared preprocessing excluded from method-specific resource columns.')
