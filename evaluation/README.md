# External practical examples (v0.6.0)

Run from the extracted project root after installing requirements:

```sh
python evaluation/run_evaluation.py
python -m retryguard --manifest evaluation/new_family/manifest.json --out results/new_family_cli
```

The first command checks SHA-256 digests of seven core files and two predeclared task contracts before and after evaluation. It refuses changed baselines. The second command exercises the normal, unchanged manifest/CLI path. The new family is external to the built-in fixture list. Neither the analyzer nor compiler nor either verifier was modified to accommodate it.

## New family: ancilla-driven quantum computation

This is an assistant-written adapter of the **published** Anders et al. paper, Phys. Rev. A 82, 020301(R) (2010), Fig. 2 and Eqs. (1)–(2): https://doi.org/10.1103/PhysRevA.82.020301 . Accessible published PDF: https://www.pure.ed.ac.uk/ws/portalfiles/portal/694868/e020301.pdf . Use the published version's Z rotation convention, not the first arXiv draft.

With beta = 0.61, J = H exp(i beta Z/2), the two branch operators are J/sqrt(2) and XJ/sqrt(2). Both outcomes have probability 1/2. The declared retry contract accepts outcome zero and recovers outcome one with J†X. Tests check those analytic equations independently of the analyzer's recovery output.

| Exported cap | Expected timeout | Required behavior |
| --- | --- | --- |
| 1 | 0.5 | Successful branch applies J; timeout restores input |
| 2 | 0.25 | Same contract |
| 7 | 0.0078125 | Same contract; meets timeout budget 0.01 |
| 32 | 2.3283064365386963e-10 | Same contract, including normalized rare timeout |

Both verifier engines evaluate the exported QASM. Results are in `results/external_evaluation/report.json`; normal CLI reports are in `results/new_family_cli/`.

This is a different published family from rotation synthesis and gearbox. It is a **post-freeze source-derived evaluation**, not a blinded holdout or an independently written teammate adapter. The adapter author had access to the core. Freezing hashes makes later accommodation detectable; it does not establish independent authorship or prevent benchmark selection bias.

The source protocol naturally applies conditional X after outcome one: both outcomes then succeed, without retries. `natural_feedforward.qasm` is separately verified with that explicit output contract. RetryGuard's recovery also uses direct register rotations; it does not preserve ADQC's original restriction on direct register control. Passing this experiment establishes compatibility within RetryGuard's native U/CX model, not an architectural implementation or an efficiency advantage.

## Independent teammate adapter: pending

See `teammate/README.md`. No teammate submission was available. The report therefore records `awaiting_independent_submission`, `semantic_pass: null`, and `requested_acceptance_complete: false`. An assistant-created adapter must not be relabeled as independent evidence. The harness separates semantic verification from authorship attestation, which requires human review.
