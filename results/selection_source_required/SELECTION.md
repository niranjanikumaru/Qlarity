# Alternative selection

Ideal continuous U/CX model. Default costs are illustrative weights, not hardware measurements.

All comparisons use the same uncontrolled target, identity-on-timeout contract and explicit success flag. Replacements do not retain source architecture/resource restrictions.

## ibm_rx

Recommended: **repaired_source**

| Candidate | Expected cost | Timeout | Eligible |
| --- | ---: | ---: | --- |
| repaired_source | 243.109 | 0.00741577 | Yes |
| fixed_retry | 13.5806 | 0.00104284 | Does not preserve original trial, as required. |
| selected_retry | 13.4621 | 0.00741577 | Does not preserve original trial, as required. |
| deterministic | 6 | 0 | Does not preserve original trial, as required. |

Lowest weighted expected operation cost among verified, budget-feasible candidates; ties prefer lower timeout, then policy name.

## guppy_v3

Recommended: **repaired_source**

| Candidate | Expected cost | Timeout | Eligible |
| --- | ---: | ---: | --- |
| repaired_source | 258.593 | 0.00741577 | Yes |
| fixed_retry | 13.5806 | 0.00104284 | Does not preserve original trial, as required. |
| selected_retry | 13.4621 | 0.00741577 | Does not preserve original trial, as required. |
| deterministic | 6 | 0 | Does not preserve original trial, as required. |

Lowest weighted expected operation cost among verified, budget-feasible candidates; ties prefer lower timeout, then policy name.

## gearbox

Recommended: **repaired_source**

| Candidate | Expected cost | Timeout | Eligible |
| --- | ---: | ---: | --- |
| repaired_source | 26.2717 | 0.00267081 | Yes |
| fixed_retry | 10.2359 | 3.1378e-05 | Does not preserve original trial, as required. |
| selected_retry | 10.1957 | 0.00267081 | Does not preserve original trial, as required. |
| deterministic | 6 | 0 | Does not preserve original trial, as required. |

Lowest weighted expected operation cost among verified, budget-feasible candidates; ties prefer lower timeout, then policy name.
