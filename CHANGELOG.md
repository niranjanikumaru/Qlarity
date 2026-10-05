# RetryGuard 0.5.0

- Add a second NumPy interpreter with independent essential operations and reference handling.
- Retain rare trajectories and verify conditional states, relative probabilities, and engine agreement.
- Supply timeout probability directly; fail certification for missing, unexpected or numerically unresolved branches.
- Preserve branch-specific verification failure reasons in CLI errors.
- Add a reproducible seven-case adversarial QASM corpus, all matching expected outcomes.
- Add fifteen verifier tests; 49 tests pass.

# RetryGuard 0.4.0

- Add outcome-by-outcome diagnosis of the original source's success and timeout contracts.
- Show concrete affected states and discriminating measurements, plus recovery proposals.
- Explain irreversible outcomes through input-dependent measurement probabilities.
- Preserve diagnoses for rejected analyzable circuits and avoid fabricated states for invalid inputs.
- Add offline diagnostics.html and machine-readable diagnostics.json, with verified QASM links.
- Add eight tests including an independent density-execution check of the illustrative bit-flip witness; 34 tests pass.

# RetryGuard 0.3.0

- Validate matrix shape, type, finiteness and unitarity; reject unsupported trial operations and unbound/nonfinite parameters.
- Validate manifests, paths, required fields, unknown fields and duplicate names with stable InputError codes.
- Isolate rejected items and generation failures; preserve valid results and remove partial failed artifacts.
- Add errors.json, per-item statuses, strict JSON, run-specific artifact paths and CLI exit codes.
- Report unavailable policies without blocking feasible selected or deterministic alternatives.
- Add eleven tests for validation, mixed/all-rejected batches, baseline availability and output isolation; 26 tests now pass.

# RetryGuard 0.2.0

- Add compile_source_retry(routine, cap), retaining the original source trial.
- Stop after success, reset only ancillas between attempts, and recover all failures including exhaustion.
- Add QASM round-trip source-loop Choi checks including trace completeness.
- Generate source_fixed and source_selected QASM for each input.
- Record separate source contracts and results in benchmark schema version 2 and source_retry.json.
- Count both branches when reporting static instructions.
- Add six tests covering multiple caps, terminal recovery, resets, early stopping, cap validation, and CLI integration.

Scope: uncontrolled source loops only; coherent-control source transformation, general input hardening, and baseline feasibility improvements remain future work. Existing controlled alternatives remain available.

## 0.6.0 — external example evaluation

- Added a source-derived ancilla-driven gate adapter outside built-in fixtures; core hashes unchanged.
- Added cap 1/2/7/32 exported-QASM checks and a deterministic natural feed-forward comparator.
- Added frozen teammate T-injection task, attestation checks, and submission harness; actual independent authorship remains pending.
- Added negative target/task and baseline-tampering regression tests.

## 0.7.0 — honest alternative selection

- New `python -m retryguard.selection` compares four verified implementations under the same uncontrolled contract.
- Explicit expected operation weights, timeout feasibility, source constraints, exclusions, and deterministic tie-breaking.
- Includes final-failure recovery cost and resets only before subsequent attempts.
- Deterministic execution wins under default assumptions; no unsupported retry-savings claim.
- Retains all previously frozen core files; selection is a separate module.

## 0.8.0 — local interactive report

- Added browser interface with examples, manifest/QASM uploads, budgets and cost weights.
- Added isolated execution, honest progress states, stale-result invalidation and verified artifact downloads.
- Added live HTTP and upload rejection integration tests; 67 tests pass.
