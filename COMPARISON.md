# Comparison and evidence boundary

Accessed 3 October 2026. This is a targeted comparison, not a systematic literature review. AutoQ and HornBro were not installed or benchmarked in this run.

| Comparator | Primary documented purpose | Specific RetryGuard difference | Evidence still needed |
|---|---|---|---|
| AutoQ 2.0 | Automata-based partial correctness over pure-state sets, up to nonzero scaling; README explicitly excludes mixed states | This prototype numerically checks unnormalized success and timeout Choi maps and reports probabilities/costs | Run matched tasks; compare required specifications, supported semantics and developer effort; do not claim broader verification strength |
| HornBro | Automated quantum program repair using a homotopy-like approach | Restricted analytic recovery plus generation and verification of bounded retry policies | Run overlapping supported tasks; establish whether existing configuration already covers the workflow |
| CUDA-Q Logical retry API | Explicit retry and exhaustion policies for gadgets | Instrument-level numerical checking of a small declared input/output contract | Integrate or compare identical gadgets; runtime policy support alone is not a correctness oracle |
| Direct Qiskit script | General circuit construction and simulation | One manifest command emits source audit, correction circuit, alternatives and a joint report | Timed task study against a reasonable well-documented Qiskit reference script |

A documented representational distinction from AutoQ exists. A demonstrated user productivity improvement or missing capability across all tools does not yet exist. QPMC and other superoperator model checkers prevent any claim that mixed-state/probabilistic verification itself is new.

## Benchmark to establish usability

Give 3 teammates the same six tasks (three clean, three injected defects), a target contract, and a prepared reference script. Randomize tool order. Record completion, correct diagnosis, timeout coverage, manual specification lines, and elapsed time. Do not count initial installation time selectively. Save inputs, outputs, tool versions, and raw timings. A practical success gate is fewer manual steps without a correctness regression; choose the quantitative target before seeing results.

## Important source interpretation

The IBM tutorial is an educational RUS circuit, not a promise to preserve data after bounded exhaustion. Its last-failure behavior violates our stronger proposed timeout contract; this is not automatically an IBM bug. Guppy's documentation already notes a missing-correction issue in its source paper. Our missing-recovery tests reproduce the importance of correction; they do not discover a previously unknown defect.

## Primary sources

1. IBM pinned RUS tutorial: https://github.com/Qiskit/documentation/blob/24612fc664d3d7167d54fb493312f3b7bb5299c9/docs/tutorials/repeat-until-success.ipynb
2. Guppy example: https://docs.quantinuum.com/guppy/guppylang/examples/repeat-until-success.html
3. Wiebe and Roetteler, Quantum arithmetic and numerical analysis using RUS circuits: https://arxiv.org/abs/1406.2040
4. Guerreschi, controlled-RUS distortion and fixed-point OAA: https://arxiv.org/abs/1808.02900
5. AutoQ source and README: https://github.com/fmlab-iis/AutoQ
6. HornBro paper: https://liqianglu-zju.github.io/files/conference/2025/FSE_2025_HornBro.pdf
7. CUDA-Q Logical: https://nvidia.github.io/cuda-quantum/latest/preview/logical/use-cases/gadgets-and-verification.html
8. Quantum model checking overview: https://pmc.ncbi.nlm.nih.gov/articles/PMC8291611/

## What would justify a stronger claim

A new paper or a high judge rating requires more than adding fixtures. Prioritize a real user task that established tools make difficult, a source adapter that removes manual work, and a backend-relevant resource win that survives the strongest simple baseline. If deterministic synthesis dominates the intended deployment, change the deployment assumptions honestly or focus the product on contract diagnosis. Do not hide that baseline or add QML to make the pitch sound quantum.
