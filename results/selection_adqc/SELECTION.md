# Alternative selection

Ideal continuous U/CX model. Default costs are illustrative weights, not hardware measurements.

All comparisons use the same uncontrolled target, identity-on-timeout contract and explicit success flag. Replacements do not retain source architecture/resource restrictions.

## adqc_j_beta061

Recommended: **deterministic**

| Candidate | Expected cost | Timeout | Eligible |
| --- | ---: | ---: | --- |
| repaired_source | 41.6328 | 0.0078125 | Yes |
| fixed_retry | 17.8203 | 0.0078125 | Yes |
| selected_retry | 17.8203 | 0.0078125 | Yes |
| deterministic | 6 | 0 | Yes |

Lowest weighted expected operation cost among verified, budget-feasible candidates; ties prefer lower timeout, then policy name.
