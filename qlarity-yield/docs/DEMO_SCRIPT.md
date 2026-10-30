# Three-minute demonstration

0:00–0:25 — State the engineering question: which tolerance scenario meets a
modeled leakage-yield target? Specify that this is a single-transistor illustrative
model, not chip yield or lifetime reliability.

0:25–0:50 — Load the nominal scenario. Show units, temperature, leakage threshold,
independent distributions, 70% yield target and 25% tolerance reduction. Select
scale 16 for the supplied recorded example, or retain scale 8 to expose the
larger encoding discrepancy.

0:50–1:25 — Start a fresh four-scenario run. Explain the unchanged conditions and
individual versus combined tolerance interventions. If live execution is
unavailable, explicitly click the recorded example; do not present it as live.

1:25–1:55 — Inspect the actual decisions: meets, misses or unresolved. Show the
encoded interval and the wider decision interval. Explain why encoding error
can prevent a conclusion even when sampling uncertainty is small.

1:55–2:30 — Open quantum evidence: actual k values, shots, measurement counts,
interval progression, compiled depth and gate counts. Compare the same encoded
target with MC, importance sampling, exact enumeration and conditional CDF.
Distinguish query counts from time and simulator time from hardware time.

2:30–3:00 — Show benchmark results without forcing a quantum win. Export a JSON,
CSV and full evidence ZIP from a completed live run. Close with the demonstrated
capability and the unresolved practical-advantage and calibration questions.
