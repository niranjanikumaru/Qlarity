# Honest alternative selection — v0.7.0

Run the selector from the extracted project root:

```sh
python -m retryguard.selection --out results/selection
python -m retryguard.selection --manifest evaluation/new_family/manifest.json --out results/selection_adqc
python -m retryguard.selection --require-source --out results/selection_source_required
```

Each run writes `selection.json`, a readable `SELECTION.md`, and the four exported QASM alternatives in each item directory. The JSON retains both verifier results, gate counts, timeout probabilities, exclusions, and the winning artifact. Input rejections are isolated by manifest item.

## What is compared

All four candidates implement the **uncontrolled** declared target on arbitrary reference-entangled input. On timeout they restore the input, with an explicit failure status. They do not promise identical timing or detailed measurement records. This comparison is separate from the earlier controlled-replacement benchmark; costs from different target contracts are never pooled.

| Candidate | Implementation | Retry budget |
| --- | --- | --- |
| Repaired source | Original trial with outcome-specific correction after every failure, including the final failure | Smallest cap meeting the declared timeout limit |
| Fixed retry | Independent coin measured before directly implementing target | Conservative cap derived from p >= 0.5; unavailable below that domain |
| Selected retry | Same direct-target replacement, with coin probability equal to source success probability | Smallest cap meeting timeout limit |
| Deterministic | Direct native target and measurement of a zero ancilla to provide an explicit success flag | One execution, zero timeout |

“Repaired source” here means its full bounded loop. Fixed and selected retry are explicit replacement implementations, not repairs of the original trial. Direct target synthesis is allowed only within this ideal continuous U/CX model. A fixed policy is excluded when its cap exceeds max_attempts, even if a different policy is feasible. Deterministic execution remains eligible when retry policies are infeasible.

## Selection rules

A candidate must pass success and timeout checks in both verifier engines, satisfy the timeout limit, and meet source-preservation constraints. Selection minimizes weighted expected operation cost per invocation. Timeouts are included in that expectation; the model does not silently rerun the entire invocation. Equal costs prefer lower timeout, then policy name. No retry policy receives preference.

Default illustrative weights are CX=10, one-qubit gate=1, measurement=5, reset=5. Override them explicitly:

```sh
python -m retryguard.selection --cost-cx 20 --cost-one-qubit 1 --cost-measure 10 --cost-reset 10 --out results/custom_selection
```

These weights are dimensionless assumptions, not measurements of device latency, energy, money, noise, or fault-tolerant resources. No classical condition-evaluation, idle-time, connectivity, pulse scheduling, or magic-state costs are included. Results are recommendations among these four implementations under the stated model, not global circuit optimality claims.

For success probability p and cap n, expected attempts E = sum over k=0..n-1 of (1-p)^k, and timeout t=(1-p)^n.

- Source: E times trial cost plus E times probability-weighted failure recovery cost; aE measurements and a(E-1) resets for a ancillas. This includes recovery on final timeout.
- Fixed/selected replacement: E coin preparations, E measurements, E-1 resets, and target gates with probability 1-t.
- Deterministic: emitted target gates and one explicit success-flag measurement.

Static operation counts are reported separately as conservative upper bounds. Mutually exclusive recovery blocks are not all charged as executed operations. The expectation is valid for the accepted, state-independent branch probabilities; it is not inferred by treating every static branch as executed.

Use `--require-source` when the original trial must be retained. Other original architectural restrictions are not automatically inferred. Replacement candidates remain displayed with an exclusion reason so users can see why a lower raw cost cannot win under this constraint.

## Current evidence and judge-facing interpretation

The default model selects deterministic execution for the three built-in examples and the added ancilla-driven gate. With source preservation required, repaired source wins among eligible alternatives. These results support honest selection and verified repair capability. They do **not** establish retry savings over deterministic execution. Relative savings versus a weaker fixed retry baseline alone would overstate the evidence.

The earlier external-evaluation freeze is retained: seven core files remain unchanged. Selection is implemented in a new module and does not tune the analyzer to fit examples. Independently authored teammate evaluation remains pending.
