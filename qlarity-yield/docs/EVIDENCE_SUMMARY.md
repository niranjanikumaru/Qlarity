# Recorded evidence summary

Predeclared benchmark: 24 runs; 0 execution errors.

| Scenario | Discrete float failure | Encoded failure | IQAE decision |
|---|---:|---:|---|
| Baseline | 31.2500% | 31.2500% | misses modeled target |
| Tighter gate length | 31.2500% | 31.2500% | misses modeled target |
| Tighter threshold voltage | 25.0000% | 25.0000% | meets modeled target |
| Combined | 25.0000% | 25.0000% | meets modeled target |

Adaptive example: 3 checks, 8704 A/A-inverse calls. Fixed comparison: 2816 calls. Adaptive did not save calls in this example.

Counts are simulator evidence, not a quantum hardware speedup. Model validation is numerical only; no external device reference was provided.

## Benchmark interval coverage (descriptive small suite)

| Method | Covered / runs | Mean absolute error |
|---|---:|---:|
| Exact encoded | 24/24 | 0.000000 |
| Conditional CDF | 24/24 | 0.000000 |
| Monte Carlo | 22/24 | 0.005158 |
| Importance sampling | 24/24 | 0.004871 |
| IQAE | 24/24 | 0.004129 |

The suite is too small to certify coverage. Exact methods have no sampling uncertainty. Statistical intervals do not include physical-model or discretization error.
