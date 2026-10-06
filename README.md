# Qlarity 0.5

A small, runnable research prototype for **bounded quantum retry contracts**. It analyzes source-derived trial circuits, emits recovery and coherence-safe alternatives, verifies success and timeout maps after OpenQASM round-trip, and reports honest resource comparisons.

This is classical software for quantum programs. It is not QML, quantum error correction, a new recovery theorem, or a claimed quantum advantage.

## Run

Python 3.12 or newer is recommended. The recorded run used Python 3.12.14 and the exact package versions in requirements.txt. Use a fresh virtual environment.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m retryguard --out results
python -m retryguard --manifest fixtures.json --out my_results
```

No IBM account, cloud hardware, API key, or network is required after installing dependencies. The report includes JSON, CSV, and executable OpenQASM 3 circuits. The simulator is ideal and exact up to floating-point precision. QASM is re-imported and executed by a separate density-matrix interpreter.

## What is supported

- One data qubit and one or two ancillas initialized in zero.
- A unitary trial followed by measurement of every ancilla. The highest-index qubit is data; lower qubits are ancillas.
- Syndrome zero denotes success, implementing the explicitly supplied 2x2 unitary target times a scalar.
- Every other syndrome must have a Kraus operator proportional to a unitary. Recovery is generated from that operator; irreversible branches are rejected.
- Constant classical circuit parameters, a known target matrix including its phase, and a fixed maximum attempt count of 1 to 32.
- The included baseline assumes success probability at least 1/2. Outside this domain, fixed baselines are marked unavailable; feasible selected and deterministic policies remain available.
- Compiled controlled alternatives use one external control, one data qubit, and one coin ancilla; success bit 1 means success, bit 0 after the cap means timeout.

Not supported: arbitrary Guppy/Qiskit program parsing, dynamic data-dependent trial selection, unresolved environment channels, quantum input angles, large registers, hardware noise, formal symbolic proofs, or fault-tolerant rotation synthesis. The Guppy example uses an explicitly documented deferred-measurement adaptation. Three source-derived implementations represent two mathematical lineages.

## Add a routine

Supply a JSON list matching fixtures.json. Each record has name, qasm, target_real, target_imag, source, lineage, and note. QASM paths are relative to the manifest. Names use 1 to 64 lowercase letters, digits, or underscores. Unknown fields are rejected; qasm paths must stay within the manifest directory. Gate-only QASM must describe the supported unitary trial, not an entire application. The analyzer derives branch operators; it does not trust supplied probabilities or recovery matrices.

```bash
python -m retryguard --manifest fixtures.json --timeout 0.01 --max-attempts 16 --out custom
```

Each rejected item receives a structured error and the batch continues. A fixed baseline that cannot meet the budget is marked unavailable; it does not block feasible selected policies or the deterministic alternative.

## Generated alternatives

1. `recovered_attempt`: original trial with a generated correction on every failure, including the final failure. This file uses syndrome zero for success.
2. `fixed_coherent_coin`: balanced coin and quantum-controlled target before measurement; secondary, weaker baseline.
3. `fixed_early_measure`: measure the independent coin first, apply the controlled target only on success; primary, stronger baseline with cap 7 for a 1% timeout contract and p >= 0.5.
4. `selected_early_measure`: same strong template, smallest feasible cap using analyzed p.
5. `deterministic`: directly synthesize the controlled target and flag success. Included because arbitrary continuous rotations are allowed by the declared gate model.

The generator is **contract-based recompilation**, not a semantics-preserving rewrite of an unsafe original controlled loop. The contract requires correct controlled target on success, identity on control and data on timeout, and timeout probability <= the limit. Detailed syndromes and exact timing distribution are not preserved. Strong and selected retry policies have different timeout probabilities but satisfy the same fixed bound. If identical probability distributions are required, changing the cap is not permitted.

## Verification and tests

The analyzer extracts Kraus operators using a unitary matrix. The verifier reads emitted QASM, executes gates/measurements/resets/conditionals on density matrices, and checks the unnormalized Choi state for both final flags. This checks the entire input operation, including entanglement with a reference, not only a few basis states. Success and timeout are kept separate; postselection is not treated as a trace-preserving channel.

The primary verifier uses Qiskit gate evolution; a second NumPy engine implements essential gates, measurement, reset, reference preparation and partial trace separately. Both still share Qiskit QASM parsing and NumPy, so this is not a fully independent software stack or formal proof. Tolerance is 1e-9 in normalized-input Choi Frobenius norm. Runtime checks also enforce trace completeness. Mutation tests detect timeout reset, wrong controlled relative phase, and corrupted success flag. A synthetic input that leaks information is rejected. None of these injected mutations is presented as a newly discovered upstream bug.

## Actual evidence

See results/benchmark.json, results/benchmark.csv, results/test_log.txt, and RESULTS.md. Twelve controlled alternatives and six bounded source-loop variants passed success and timeout checks. Forty-nine tests passed, including source-loop QASM round trips at caps 1, 2, 5, 7, and 32. Manifest ingestion was also run on all three fixtures.

Main finding: relative to the strong fixed baseline, selected caps reduce maximum measurement/reset rounds from 7 to 5, 5, and 4 (28.6%, 28.6%, 42.9%). Expected measurement reductions are only about 0.64%, 0.64%, and 0.26%. Worst executed CX remains 2 for both strong templates. Do not market static circuit-size reductions as executed-gate savings. The deterministic option uses two CX, one measurement, and no reset under this native-rotation model; it is a serious alternative, not something to hide.

## Files

- retryguard/fixtures.py: provenance and source adapters.
- retryguard/analysis.py: operator extraction, recovery eligibility, retry cap, specific naive-control audit.
- retryguard/compiler.py: executable Qiskit/OpenQASM templates.
- retryguard/verifier.py: independent density interpreter and Choi checks.
- retryguard/__main__.py: batch CLI and benchmark outputs.
- tests/test_retryguard.py: contract, mutation, and rejection tests.
- fixtures.json: editable gate-level manifest.
- COMPARISON.md: research positioning and remaining evidence.

## Research claim boundary

The recovery criterion, controlled-RUS distortion, geometric cap choice, and early measurement of an independent coin are established techniques. The contribution currently demonstrated is a compact workflow combining explicit timeout contracts, automatic source-derived analysis, executable alternatives, and round-trip checks. Novelty across the literature, better usability than existing tools, hardware savings, and a finalist-level score remain unproven.

## Bounded original-source retry loops in 0.2

The standard CLI now also generates `<routine>_source_fixed.qasm` and
`<routine>_source_selected.qasm`. These retain the original trial gates, execute
outcome-specific recovery after every failure, reset only the ancillas before
retrying, and stop executing trials after success. The last permitted failure
is recovered too, returning the data unchanged on timeout. Source ancillas
must initially be zero. The data may be entangled with an untouched reference.

These circuits have **no external coherent control**. They implement the target
on one data qubit, while the older controlled alternatives implement a controlled
target. The two families have separate contracts and result lists; their costs
must not be compared as though they implement the same operation.

The source loop retains its full syndrome register: **all zero means success;
any nonzero value means timeout**. This differs from the older controlled
alternatives' one-bit flag (1 means success). Failed measurement records remain
classical; ancillas may be discarded after termination. No identity claim is
made for the ancillary outputs or detailed measurement histories.

`results/source_retry.json` and `benchmark.json`'s `source_retry_results` contain
source-loop checks, cap, probabilities, and static instruction counts. Static
counts include mutually exclusive and skipped branches and are not executed
resource estimates. The benchmark schema is now version 4; the existing CSV
continues to contain controlled alternatives only. The CLI prints separate
`controlled_variants` and `source_retry_variants` counts.

The verifier re-imports each emitted QASM and checks unnormalized success and
timeout Choi maps plus total trace at tolerance 1e-9. Tests intentionally omit
final recovery and ancilla resets, and repeat a deterministic successful trial.
Verification remains numerical ideal-model checking, not hardware validation
or a formal proof; conditional checks are now included for positive expected branches at or above
1e-250. Smaller branches are explicitly unresolved and prevent certification.

To build an explicit cap using the Python API:

```python
from pathlib import Path
from retryguard.fixtures import fixtures
from retryguard.compiler import compile_source_retry, save_qasm

routine = next(fixtures())
save_qasm(compile_source_retry(routine, 5), Path("ibm_source_cap5.qasm"))
```

The cap API accepts integers from 1 through 32, analyzes recovery eligibility
internally, and does not select a probability budget for the caller. Use the
CLI for budget-based selection. Version 0.3 adds input validation, per-item
batch isolation, and explicit baseline availability.

## Input validation and batch errors in 0.3

Targets must be finite numeric 2 by 2 unitary matrices. Real and imaginary
manifest components must separately be real numeric 2 by 2 matrices. Strings,
booleans, ragged arrays, NaN and infinity are rejected. Trials must contain
2 or 3 qubits, no classical registers, and only bound unitary gates (barriers
are permitted). Measurements, resets, delays, control flow, nonfinite gate
parameters, and unevaluable gates are rejected before generation.

Timeout limits must be finite real numbers strictly between 0 and 1. Caps must
be integers from 1 to 32. Per-attempt probabilities must be finite and in (0, 1].
The analyzer rejects success probabilities at or below numerical tolerance 1e-9.
Python API validators raise InputError, a ValueError subclass with code and field.

The manifest is a nonempty list. Each item requires name, qasm, target_real,
target_imag, source, and lineage; note is optional. Duplicate names reject all
items sharing that name; other items continue. Unknown fields are rejected to
catch misspelled contracts. Malformed JSON, duplicate JSON object keys, an invalid
root, unreadable manifest, or invalid global CLI budgets prevent the batch from
starting and produce an error on stderr.

`benchmark.json` now contains `items`, `errors`, and `summary` alongside successful
results. `errors.json` contains the summary and rejections. Errors include the
1-based item index, name when available, stage, field, stable code, and message.
A partial batch never has `all_verified: true`; each accepted result retains its
own verified flag. A batch with no accepted items still writes JSON reports and
a header-only CSV. Unexpected SDK/generation exceptions are labeled
PROCESSING_ERROR rather than being presented as input mistakes.

Missing fixed or selected implementations appear in each accepted item's
`unavailable_policies`. If retry caps cannot meet the budget, deterministic
execution may still be valid. Missing policies are not claimed as verified.
The fixed baseline remains restricted to p >= 0.5; selected policies may support
lower probabilities. A valid item can therefore be accepted with unavailable
policies, and callers should inspect that list before comparing costs.

Exit codes:
- 0: every item accepted; inspect unavailable_policies for infeasible alternatives.
- 1: one or more items rejected, including an all-rejected batch; reports are saved.
- 2: invalid global request, argument parsing failure, or output I/O failure.

Artifacts use `generated/<run_id>/<routine>/...`; follow the QASM paths in the
current report. Earlier run directories can remain for reference, but are not
part of the new results. A failed item's partial artifact directory is removed.
JSON report files are individually replaced atomically and disallow nonfinite
numbers. Simultaneous writers to the same output directory are not supported.

Try the included mixed batch (intentionally exits with code 1):

```bash
python -m retryguard --manifest examples/mixed_manifest.json --out mixed_results
```

Two valid items produce QASM; two invalid items report MISSING_FIELD and
INVALID_MATRIX. Inspect mixed_results/errors.json for the rejection details.

## Explainable failure diagnosis in 0.4

After each batch, open `results/diagnostics.html` in a browser. The report is an
offline HTML file with no external assets or scripts. `diagnostics.json` and the
benchmark's diagnostics list expose the same evidence for other interfaces.

For each analyzable source, the report identifies the measured outcome, the
success or timeout contract, whether it is satisfied before recovery, and an
illustrative input state. It shows the expected and actual output state where
these match named states, plus a measurement whose probabilities expose the
change. X/Z/etc. corrections are named when applicable; otherwise it proposes
the generated inverse single-qubit rotation. Verified recovery and bounded-loop
QASM links appear only after generation and verification succeed.

Example: IBM outcome 01 changes input |0> to |1>, violating unchanged-data timeout.
An X correction restores |0>; the complete emitted recovered attempt also passes
success and timeout verification. Apply recovery after every failure, including
the last, before returning or retrying. The full syndrome is displayed in order
c[highest]...c[0]; 00 is success for two-ancilla trials.

Branches that already preserve data are labeled satisfied. Negligible branches
are labeled below tolerance without a conditional-state certification. If an
outcome leaks information, the report provides two inputs with different outcome
probabilities and explicitly declines to propose a deterministic unitary repair.
A wrong successful operation requests review of the target/order/label, without
silently changing the contract. Invalid inputs receive a plain-language error,
not an invented quantum-state explanation.

These diagnoses concern the original trial with its terminal ancilla measurement
and no recovery. They are not a general debugger for arbitrary submitted dynamic
programs or a claim of new upstream defects. The state examples are chosen from
six standard single-qubit states to make the failure understandable. They are
illustrations, not substitutes for the exported-program Choi checks. The separate
naive-control diagnostic is limited to its explicitly stated wrapper; source
failure recovery does not by itself repair coherent-control leakage.

Run a demonstrator with a repairable input, an irreversible input, and a wrong
success target (intentionally exits 1 because two items are rejected):

```bash
python -m retryguard --manifest examples/diagnosis_manifest.json --out diagnosis_demo
```

Open `diagnosis_demo/diagnostics.html`. The package includes a recorded run in
`results/diagnosis_example`, as well as the ordinary and mixed-batch reports.

## Stronger verifier coverage in 0.5

Every accepted exported recovered attempt, source loop, and controlled alternative
is now checked by two execution engines. The second engine in independent.py
uses explicit NumPy gate matrices rather than Qiskit Operator/DensityMatrix gate
evolution. It independently implements measurement, reset, reference preparation,
partial trace and the expected Choi-state construction. The controlled target is
constructed separately in the two paths. QASM parsing, circuit objects, NumPy,
and the declared contract remain shared; this is implementation diversity, not
formal proof or full stack independence.

Verification now includes absolute branch-map errors, total trace, each nonzero
branch's conditional output state, relative branch probability error, and engine
agreement. All checked residuals use tolerance 1e-9. Tiny nonzero trajectories are
no longer discarded using the old absolute 1e-15 cutoff.

The CLI supplies timeout probability separately as (1-p)**cap. Python callers
should pass timeout_probability explicitly to verify/verify_source_retry: forming
1-success can round a rare timeout to zero. Positive branches below 1e-250 are
reported as unresolved, not certified. A zero-expected branch is not normalized;
if either engine observes nonzero mass, certification fails (including tiny mass
with UNRESOLVED_UNEXPECTED_BRANCH). This conservative rule can reject numerical
roundoff and is deliberately not a claim of exact mathematical impossibility.

Use result['verified'] and result['failures']; checking only the old success_residual
and timeout_residual fields is insufficient. Failures identify branch, engine and
reason, such as CONDITIONAL_STATE_MISMATCH, BRANCH_PROBABILITY_MISMATCH, MISSING_BRANCH,
ENGINE_DISAGREEMENT or UNRESOLVED_RARE_BRANCH. The CLI preserves these reasons in
rejection details. The lightweight verify_source helper remains a legacy
single-engine, absolute-only in-memory diagnostic; it does not certify exported
programs. Exported recovery now uses verify_source_retry with both engines.

Reproduce the adversarial corpus:

```bash
python -m retryguard.adversarial --out results/adversarial
```

ADVERSARIAL_RESULTS.md summarizes seven cases: one valid rare-timeout program and
six intentionally broken programs. All six mutations fail for the expected reason
in both engines. The package includes their QASM and full JSON verification output.
These deliberately broken files are test artifacts, not accepted repairs.

The key regression has timeout probability about 1e-32 and a reset of the data
only on timeout. Its absolute timeout residual is about 1e-32, which passes the
old absolute threshold. Its conditional timeout residual is 1.0, which correctly
fails the new check. A correct program at the same probability still passes.
A simulated fault in the second engine and known-answer primitive tests also
exercise the cross-check. This remains ideal numerical simulation, not hardware
validation, a theorem, or a guarantee that all implementation bugs are absent.

## External examples (v0.6.0)

See [evaluation/README.md](evaluation/README.md) for the new ancilla-driven gate family, exported caps and natural feed-forward comparator, evaluated against seven unchanged core files. Run `python evaluation/run_evaluation.py`. A frozen task and submission harness are ready for a real teammate T-injection adapter; independent submission and human authorship review remain pending. This is post-freeze evaluation, not a blinded holdout.

## Honest alternative selection (v0.7.0)

Run `python -m retryguard.selection`. This verifies and ranks repaired source, fixed retry, selected retry, and deterministic implementations under one uncontrolled target contract. Read [ALTERNATIVE_SELECTION.md](ALTERNATIVE_SELECTION.md) for cost assumptions, source constraints, command examples, and limitations. Default results recommend deterministic execution; retries are not presented as a cost win over it. `--require-source` restricts eligibility to preserving the original trial. Existing core and external-evaluation hashes are unchanged.

## Interactive report (v0.8.0)

Run `python -m retryguard.web`, then open http://127.0.0.1:8765. Load → diagnose → repair → verify → compare → download uses actual backend execution. See [INTERACTIVE_REPORT.md](INTERACTIVE_REPORT.md) for setup, uploads and limits.

## Cinematic frontend edition

The interface now uses React, GSAP, Framer Motion and procedural Three.js/WebGL graphics. Launch with the same `python -m retryguard.web` command. No frontend installation is needed: the built page is included. See [frontend/README.md](frontend/README.md) for frontend source, rebuilding, provenance and browser QA. All Python source and tests remain unchanged. Actual browser previews are included in `frontend/previews/`.

## Minimal nebula entrance

The opening page now shows only the supplied nebula shader and **Enter workspace / How it works**. The execution workspace opens separately. TypeScript, Tailwind and shadcn-compatible component paths are configured in `frontend/`. Python code, dependencies and tests are unchanged; launch remains `python -m retryguard.web`.

## Interactive how-it-works guide

The entrance now includes a hands-on four-chapter walkthrough: select a branch, toggle recovery, adjust the retry cap, and explore implementation eligibility. Toy-model calculations are labeled and never presented as live verification. The final step opens the actual workspace. Backend files remain unchanged.
