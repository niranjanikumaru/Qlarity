# Implementation status

Input: supplied `qlarity 2.0(1).zip` backend and `prompts.docx` (12 prompts).
A baseline git commit preserves the supplied source. The uploaded backend
contained no frontend. A new local dashboard is included.

## Baseline audit

Original physics/classical and API tests: 83 passed. The original API suite
emitted an asynchronous SQLite shutdown warning. Confirmed defects included
API/model default mismatch, unmatched classical/quantum predicates, bookkeeping
power counted as execution, misleading probability/amplitude documentation,
importance proposal in the wrong Vth direction, unused pilot, and terminal
cancellation overwrite. Original quantum fixtures used an all-pass threshold.

## Prompt mapping

| Prompt | Delivered |
|---|---|
| 1 — Baseline | Reversible baseline commit, original test run, issue audit |
| 2 — Contract | Pydantic scenario, domain defaults, units, target hashes, failure boundary, reversed yield intervals |
| 3 — Classical | Exact encoded, exact conditional CDF, MC Clopper–Pearson, full-support fixed-proposal IS with bounded-weight intervals; continuous quadrature separate |
| 4 — Encoding | Original example reproduced; weighted classification disagreement, signed probability difference, score bound, overflow checks, separate tails/discretization/model errors |
| 5 — Quantum | Nontrivial oracle validation, actual sampler ledger, counts, intervals, A/A-inverse and Grover counts, compiled executed circuits and QASM |
| 6 — Execution | Process-isolated local API, immutable snapshots, bounded queue/runtime/resources, idempotency, termination on cancellation, explicit recorded fallback |
| 7 — Benchmarks | 24 predefined runs, repeated seeds, scales/accuracy settings, charts, precision and resolution studies, fixed/adaptive comparison |
| 8 — Model validation | Required fallback: illustrative label and model card; no usable external reference supplied. Added CSV held-out validation utility for future reference data |
| 9 — Decisions | Four interventions, three decision states, modeled-target intervals and fixed assumptions |
| 10 — Adaptive | At most three checks, alpha/3 allocation, no sample reuse, explicit refinement reasons, cumulative resources, actual comparison showing no savings in recorded case |
| 11 — Dashboard | Define/compare/run/decide/evidence/export, interactive population, confidence/error/resource panels and benchmark charts |
| 12 — Release | Local setup, pinned dependencies, tests, model card, demo, claims, evidence summary and downloadable bundles |

## Verification

- Full backend suite: 138 passed before the additional QASM roundtrip test.
- Updated workbench suite: 17 passed, including exported QASM re-import checks.
- Tests verify nontrivial 128 input/flag basis cases, uncomputation, phase purity,
  Grover identities, ledger accounting, target identity, statistical boundary
  behavior, cancellation, idempotency and JSON/ZIP consistency.
- Benchmark: 24/24 executions completed; actual results in evidence/benchmark.json.
- Browser verification: desktop/mobile, fresh classical and quantum executions, recorded fallback, downloads, cancellation, reload and no JavaScript errors passed. See evidence/browser-verification.json.
- Deprecation warnings from Qiskit/Grover construction remain upstream; pinned
  dependencies are provided. Legacy API SQLite shutdown warning is not a
  failure of the new process-isolated server.

## Remaining scientific limitations

No independent SPICE/fabrication calibration, hardware run, correlated
manufacturing distribution, physical-model error bound, or practical quantum
advantage is established. Quantum encoding supports exactly four bins per axis;
other resolutions are explicitly classical-only. No external service was deployed.

## Entry points

Use `backend.serve:app` and README.md. The original backend.app.main is retained
for compatibility tests but is not the supported local dashboard entry point.

Final additions: benchmark-summary.json separates achieved error, interval width and coverage; ZIP bundles extract all adaptive intermediate circuits. Two dedicated regression tests cover these additions. The requirements lock marks uvloop as non-Windows.
