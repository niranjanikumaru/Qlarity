# Adversarial verification results

These QASM files deliberately include broken programs. They are test artifacts, not accepted repairs.

| Case | Intended behavior | Observed | Expected reason matched in both engines |
|---|---|---|---|
| valid_rare_timeout | Accept correct rare-timeout program | Accepted | Yes |
| rare_timeout_reset | Reject: timeout CONDITIONAL_STATE_MISMATCH | Rejected | Yes |
| rare_timeout_erased | Reject: timeout MISSING_BRANCH | Rejected | Yes |
| wrong_retry_cap | Reject: timeout BRANCH_PROBABILITY_MISMATCH | Rejected | Yes |
| controlled_phase_error | Reject: success CONDITIONAL_STATE_MISMATCH | Rejected | Yes |
| wrong_success_flag | Reject: success BRANCH_PROBABILITY_MISMATCH | Rejected | Yes |
| source_missing_final_recovery | Reject: timeout CONDITIONAL_STATE_MISMATCH | Rejected | Yes |

Rare timeout reset: timeout probability 1.0000e-32; absolute timeout residual 1.0000e-32; primary conditional timeout residual 1.0000.

The absolute 1e-9 threshold alone misses this state corruption. Conditioning on the rare timeout exposes it. See JSON for both engines, relative probabilities, and all failure reasons.
