# Existing Tools & Research Comparison

This table evaluates RetryGuard against existing approaches for quantum circuit verification, RUS (Repeat-Until-Success) synthesis, and repair, focusing on their support for bounded retry loops and mixed-state timeout contracts.

| Feature | AutoQ 2.0 | HornBro | CUDA-Q Logical API | RetryGuard (Prototype) |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Purpose** | Automata-based formal verification of partial correctness. | Automated quantum program repair via homotopy-like methods. | Fault-tolerant compilation and orchestration. | Analysis, repair, and synthesis of bounded retry loops. |
| **Supported Inputs / Semantics** | Pure-state sets (tree automata). Explicitly excludes mixed states. | Restricted analytic recovery on standard datasets (Bugs4Q, Qbugs). | High-level C++/Python hybrid orchestration. | Explicitly handles **mixed states**, one target, small ancilla counts. |
| **Diagnoses & Generates Repair?** | No. Only verifies a supplied quantum circuit/program. | Yes. Generates repairs for algorithmic bugs. | No. It provides an API for retries, but does not synthesize the repair logic. | **Yes.** Extracts Kraus operators and synthesizes the exact recovery unitary. |
| **Checks Data Preservation on Timeout?** | No. | No. Focuses on producing a "correct" program overall. | No. | **Yes.** Evaluates unnormalized Choi maps to verify data preservation. |
| **Exports Executable Result & Compares Costs?** | No. | Yes, exports the fixed circuit. | N/A (Handles execution directly). | **Yes.** Exports QASM and compares deterministic vs. retry execution costs. |

## What RetryGuard Adds
While tools like **AutoQ** excel at formal verification of large pure-state circuits, and **HornBro** addresses general semantic bug fixing, neither addresses the specific physical realities of **bounded probabilistic retry loops**. 

RetryGuard uniquely provides:
1. **Unnormalized Choi map checking:** Proving that data is preserved even when a loop reaches its timeout limit and execution is aborted.
2. **Coherence-aware alternative synthesis:** Automatically selecting between fixed baselines and dynamically capped implementations to minimize execution costs while satisfying strict timeout contracts.
