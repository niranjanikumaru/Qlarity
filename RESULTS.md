# Recorded benchmark results

Ideal simulation; 1% maximum timeout; coherent-control input may be entangled with a reference. Numerical tolerance 1e-9.

| Routine | Primary fixed cap | Selected cap | Worst round reduction | Expected round reduction | Selected timeout |
|---|---:|---:|---:|---:|---:|
| ibm_rx | 7 | 5 | 28.57% | 0.638% | 0.7416% |
| guppy_v3 | 7 | 5 | 28.57% | 0.638% | 0.7416% |
| gearbox | 7 | 4 | 42.86% | 0.264% | 0.2671% |

All 12 variants passed success, timeout and total trace checks. Maximum success residual: 1.2818015370494815e-15.

Worst executed CX remains 2 for both early-measure policies. Static QASM counts sum mutually exclusive success branches and are NOT executed worst-case counts. A deterministic target implementation also uses 2 CX, with one measurement and no resets.

The weaker coherent-coin implementation uses substantially more CX; this reflects template choice, not a new quantum speedup. Primary claims use the stronger fixed early-measure baseline.

Lower expected rounds partly result from stopping earlier and accepting more flagged timeouts, always below the same 1% limit. This is not equal-distribution equivalence or lower error per successful output.

Source routine recovery checks and the naive-control syndrome leakage audit are in benchmark.json. Missing corrections are deliberately omitted trial recoveries, not newly discovered upstream bugs.

## Bounded source retry loops in version 0.2

These six variants retain the original trial and implement an uncontrolled
one-data-qubit target. They are separate from the controlled alternatives above.
All source loops passed QASM round-trip success, timeout, and trace checks.

| Routine | Policy | Cap | Timeout probability | Largest residual |
|---|---|---:|---:|---:|
| ibm_rx | source_fixed | 7 | 0.0010428429 | 3.710e-16 |
| ibm_rx | source_selected | 5 | 0.0074157715 | 3.683e-16 |
| guppy_v3 | source_fixed | 7 | 0.0010428429 | 6.661e-16 |
| guppy_v3 | source_selected | 5 | 0.0074157715 | 6.661e-16 |
| gearbox | source_fixed | 7 | 0.0000313780 | 4.352e-16 |
| gearbox | source_selected | 4 | 0.0026708101 | 5.082e-16 |

The suite now contains 15 passing tests. All three source routines were checked
at caps 1, 2, 5, 7 and 32 after QASM export/import. Deliberately omitting final
recovery leaves success correct but fails timeout verification. Omitting ancilla
reset and incorrectly repeating a successful trial are also detected.
Both built-in fixture and manifest CLI runs passed all 18 generated variants.
The source loop uses syndrome zero for success and any nonzero syndrome for
timeout. Static instruction counts are reported separately from executed cost.
The largest source-loop residual in the default run is below 7e-16. These are
ideal-model numerical results, not experimental hardware results.

## Input validation and batch isolation in version 0.3

All 26 tests pass. The ordinary built-in and manifest runs each retain 12 verified
controlled alternatives and 6 verified source loops. The included mixed example
accepts two items and rejects two with MISSING_FIELD and INVALID_MATRIX while
preserving 8 controlled alternatives and 4 source loops. Its summary reports
partial status and all_verified false; accepted rows remain individually verified.
See results/mixed_example/errors.json and cli_log.txt for actual diagnostics.

Boundary tests cover NaN/Infinity, matrix shape and type, nonunitarity, invalid
probabilities and caps, unsupported operations, unbound/nonfinite parameters,
malformed JSON, duplicate keys/names, missing/unknown fields and invalid paths.
The tests also cover all-rejected batches, removal of partially generated files,
no stale report references, low-success routines, and unavailable retry policies.
Actual CLI checks confirmed exit 0 for success, 1 for a mixed batch, and 2 for
an invalid global budget. This update adds validation and reporting behavior;
it does not strengthen the underlying ideal-model numerical correctness claim.

## Explainable diagnosis in version 0.4

All 34 tests pass. Read results/diagnostics.html for the ordinary source examples;
results/diagnosis_example/diagnostics.html includes a repairable source, a synthetic
information-leaking source, and a synthetic incorrect success operation. The
latter two are rejected, but their branch explanations are retained.

The IBM witness reports outcome 01 with probability 12.5% on input |0>, producing
|1> before recovery. An X gate restores |0>. A separate density-interpreter test
confirms the branch probability and the before/after measurement result. Guppy's
phase-flip outcome and already-safe failure are distinguished. Negligible branches
receive no conditional-state guarantee. Global phase alone is not falsely labeled
as corruption. HTML escapes input text, and artifact links are only attached to
successfully verified generated circuits.

The six standard input states provide understandable illustrations, not exhaustive
proofs. The existing complete-operation Choi checks remain the numerical evidence.
This release diagnoses supported source trials; it does not locate arbitrary
instruction defects in general dynamic programs. Teammate usability has not yet
been measured in a user study.

## Stronger verification in version 0.5

All 49 tests pass. The seven-case adversarial corpus accepts the valid rare-timeout
program and rejects all six deliberately broken programs for the expected reason
in both engines. See results/adversarial/ADVERSARIAL_RESULTS.md and the associated
JSON and QASM files. Failures distinguish conditional-state corruption, incorrect
branch probability, missing timeout, and wrong controlled phase.

The rare-timeout reset case has probability approximately 1e-32. Its absolute
timeout residual is approximately 1e-32, but its conditional timeout residual is
1.0. This is a concrete regression that the old absolute-only check would miss.
The new engines preserve the branch, compare its conditional state and probability,
and reject the mutation while accepting the valid program at the same probability.

The second engine implements essential gate matrices, measurements, resets,
reference preparation, and partial trace separately. Qiskit QASM parsing and NumPy
remain shared. Known-answer primitive tests and an injected second-engine fault
exercise this boundary. Positive expected branches below 1e-250 are unresolved;
zero-expected branches with observed nonzero mass also fail certification. These
are conservative numerical policies rather than claims of exact symbolic proof.

## External evaluation — v0.6.0

One additional family (ancilla-driven gates) passed the unchanged analyzer through the manifest CLI: one accepted item, four controlled variants and two source-retry variants, all verified. Separate source exports at caps 1, 2, 7, and 32 passed both verifier engines, including timeout-state checks. The source-native deterministic feed-forward comparator also passed. Seven core files and two task contracts retain their pre-adapter SHA-256 hashes.

This is assistant-authored post-freeze evidence, not a blinded independent holdout. The independently written teammate adapter is pending; the frozen T-injection task and submission harness are included. Synthetic harness tests do not count as teammate submissions. Full acceptance remains incomplete. See evaluation/README.md and results/external_evaluation/report.json.

Validation: 56 regression tests passed (results/test_log.txt).

## Alternative selection — v0.7.0

64 regression tests pass. The selector exports and independently checks four candidates for each of the three built-in routines and the external ADQC case. Under default illustrative weights (CX 10, one-qubit 1, measurement 5, reset 5), deterministic execution wins in all four cases. Its expected cost is 6 proxy units and timeout is zero. With source preservation required, repaired source is recommended for all three built-ins; cheaper replacements are explicitly ineligible.

Read results/selection/SELECTION.md, results/selection_adqc/SELECTION.md, and results/selection_source_required/SELECTION.md. JSON reports include verification evidence, exclusions and emitted QASM paths. These results do not prove a retry-cost advantage or hardware benefit. Seven frozen core files remain unchanged.

## Interactive report — v0.8.0

67 regression tests passed, including a live HTTP request through the subprocess worker, verification of all four alternatives, recommendation and evidence ZIP download. Invalid uploaded targets retain a diagnosis and expose no unchecked circuit downloads. Browser JavaScript syntax was checked. Visual browser QA was unavailable because the browser executable was absent and its installation failed; no rendered-browser validation is claimed.
