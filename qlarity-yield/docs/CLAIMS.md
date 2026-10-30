# Claims and limitations

| Status | Claim |
|---|---|
| Implemented and testable | Real reversible arithmetic oracle and IQAE execution |
| Implemented and testable | Matched encoded-target classical comparisons |
| Implemented and testable | Three-way decisions including numerical disagreement |
| Implemented and testable | Actual executed rounds, counts, intervals, QASM and resources |
| Implemented and testable | Cancellable local jobs and reproducible exports |
| Theoretical motivation | Amplitude estimation can improve query scaling over ordinary MC under its assumptions |
| Not established | Practical speedup over classical methods |
| Not established | New quantum algorithm or novel adaptive-confidence method |
| Not established | Foundry-calibrated accuracy, production signoff or fabricated chip yield |

The small model is easily solved classically. Exact/CDF methods may be best.
Recorded quantum evidence uses an ideal finite-shot statevector simulator, not
hardware. All-to-all compilation excludes physical routing and hardware noise.
The shared finite-grid validation cost is disclosed and cannot be omitted from
an end-to-end advantage claim. Importance-sampling Hoeffding bounds are valid
but conservative; they are not representative of every advanced classical method.

Local job history does not survive restart. The legacy API is not the supported
execution path. Optional physical hardware, public hosting and SPICE calibration
are deliberately absent from this local release.
