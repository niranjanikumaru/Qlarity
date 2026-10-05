# Teammate handoff: magic-state T injection

Status: awaiting a real independently written submission. No source circuit or claimed teammate identity is supplied here.

Build a gate-only two-qubit OpenQASM 3 trial implementing the task in `task.json`, using the source below. Write your adapter without consulting RetryGuard's analyzer/compiler implementation or this project's generated repairs. Disclose any AI assistance. The task and core hashes were frozen before submission; do not edit them.

Source: IBM Quantum Learning, “Controlling error propagation,” magic-state injection discussion:
https://quantum.cloud.ibm.com/learning/en/courses/foundations-of-quantum-error-correction/fault-tolerant-quantum-computing/controlling-error-propagation

Use ancilla q0 initialized in zero (include resource-state preparation in the trial) and data q1. The harness adds terminal ancilla measurement. Syndrome zero must implement T with probability 1/2. Syndrome one must be proportional to T†. No measurement, reset, or conditional logic is allowed inside the submitted trial. The target includes the phase convention T=diag(1, exp(i*pi/4)). Source-native conditional S can make injection deterministic; retries here test the imposed unchanged-input timeout contract, not an efficiency claim. Native T gates are permitted for resource preparation in this prototype; it does not model fault-tolerant magic-state cost.

Submit a directory containing:

1. `trial.qasm`: your gate-only adapter.
2. `manifest.json`: a one-item JSON list with name, qasm (relative filename), target_real, target_imag (copy the frozen task's matrices), source (URL), lineage (magic-state gate injection), and optional note. Use a lowercase underscore-separated name.
3. `authorship.json`: fields `author` (actual author), `written_independently_of_retryguard_core` (true), `core_author_involved` (false), `ai_assistance_disclosed` (nonempty description, including “none” if appropriate), `source_url`, and `notes` (how it was written and what was consulted).

The recipient runs:

```sh
python evaluation/run_evaluation.py --teammate-manifest /path/to/submission/manifest.json --authorship /path/to/submission/authorship.json --out results/teammate_review
```

The harness checks the frozen core and task, layout, success target, failure branch, probability, and exported caps 1, 2, 7, and 32 using both engines. Wrong contracts are rejected; do not tune the analyzer to make a submission pass. Preserve failed submissions and their errors as evaluation evidence.

A successful run records semantic results and the author's self-attestation. It still labels authorship `self_attested_pending_human_review`; software cannot authenticate independence. A reviewer must confirm actual authorship and record the review separately before declaring the full acceptance item complete.
