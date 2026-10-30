# Release checklist

- PASS: original source preserved as baseline git commit.
- PASS: shared encoded target and separate floating/continuous references.
- PASS: all four requested tolerance scenarios.
- PASS: exact, Monte Carlo, importance sampling and actual IQAE.
- PASS: conditional-CDF baseline and continuous reference.
- PASS: numerical-error-aware three-way decisions.
- PASS: sampler counts, amplification history, resource accounting and QASM.
- PASS: isolated jobs, cancellation, idempotency, server limits and exports.
- PASS: full backend suite (138 tests), updated workbench suite (17 tests).
- PASS: 24 benchmark executions; no cherry-picked failure exclusions.
- PASS: model card, evidence summary, demo script and pinned dependencies.
- PASS WITH SCIENTIFIC LIMITATION: model-validation fallback exercised because
  no independent reference was supplied; coefficients remain illustrative.
- NOT CLAIMED: hardware speedup, production signoff, foundry calibration,
  total chip yield, fabrication cost savings or a new quantum algorithm.
- LOCAL RELEASE: no public endpoint or unrestricted API deployed.

- PASS: browser desktop 1440×1000 and mobile 390×844, no horizontal overflow; recorded load, fresh classical/quantum runs, keyboard inspection, CSV/ZIP exports, cancellation and reload.

- PASS: explicit benchmark accuracy-target/coverage summary and adaptive intermediate-circuit ZIP export tests.
