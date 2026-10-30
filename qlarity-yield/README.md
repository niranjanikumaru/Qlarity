# Qlarity — Semiconductor leakage-yield workbench

A local, reproducible comparison of exact enumeration, conditional CDF calculation,
Monte Carlo, importance sampling and actual IQAE circuits. The dashboard compares
baseline, tighter gate length, tighter threshold voltage and their combination.

## Start (Python 3.12)

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell instead:
# .venv\Scripts\Activate.ps1
pip install -r requirements-lock.txt
python -m uvicorn backend.serve:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The frontend and calculation API are served together.
No Node build step or external frontend assets are required. Installation needs
package access; execution thereafter can run offline.

Use **Run four-scenario comparison** for fresh execution. **Open recorded,
verified example** loads saved evidence and is explicitly labeled recorded.
JSON/CSV exports are available for both. Completed live and recorded runs also export ZIP
bundles with circuits, ledger, scenario, benchmark and documentation files.
Recorded-run circuits are also individually downloadable from the round table.

## Scope and targets

- Model: illustrative 65 nm bulk nMOS subthreshold expression, not calibrated
  to a foundry, SPICE reference, or fabricated devices.
- Independent ±3σ-conditioned Gaussians, represented by equal-mass bins.
- Fixed Vds=1 V, Vgs=0 V, Vbs=0 V and W=1 µm; temperature is adjustable.
  This expression has no Vds/Vbs dependence despite retaining those metadata.
- Failure is Ioff >= limit, including equality.
- Every estimator in a comparison targets the same encoded integer predicate.
- Decisions target the original finite-grid floating-point predicate. Intervals
  are widened using exhaustively measured weighted classification disagreement.
- Discretization and physical-model uncertainty are NOT covered by these intervals.
- Continuous quadrature is reported separately, never as the encoded target.
- The 4-bin quantum encoding is verified; 2/8/16 bins support classical-only
  resolution studies. Increasing states is not itself evidence of advantage.

## Confidence and costs

Monte Carlo uses Clopper–Pearson. Importance sampling uses a fixed, full-support
mixture proposal and bounded-weight Hoeffding intervals (conservative, including
zero failures). IQAE uses Qiskit's beta interval procedure. Its epsilon controls
probability error, not square-root amplitude error.

Adaptive mode permits three checks and allocates alpha/3 per check. No sample
reuse is claimed. Confidence is per scenario, not a simultaneous guarantee
across scenarios or estimators.

The exact reference and encoding-disagreement calculation enumerate the grid.
Their cost is reported separately; they are validation work, not a scalable
quantum speedup. Conditional CDF calculation exploits the model's separability.
Quantum calls, classical evaluations, gate counts and simulator runtimes are
separate metrics. This release does not demonstrate practical quantum advantage.

## Tests and evidence

```bash
python -m pytest backend/tests/test_workbench.py -q
python -m pytest backend/tests/test_physics_classical.py backend/tests/test_api.py -q
python scripts/benchmark.py
```

Benchmark cases are predefined. The output includes repeated seeds, two accuracy
settings and scales, resolution studies, precision/resource trade-offs and an
adaptive/fixed comparison. Regeneration can take several minutes. The current
small suite is not sufficient to certify nominal coverage or practical speedup.

## Runtime limits and privacy

The new server accepts loopback clients only, rejects cross-origin mutations,
and binds to 127.0.0.1 in the documented command. It permits two running workers,
four active/queued jobs, a 180-second per-job timeout, at most 16 quantum qubits,
1024 shots per round, 100,000 classical samples and bounded accuracy/precision.
Each computation runs in its own process; cancellation terminates that process.
Idempotency keys prevent duplicate submissions. Local history is in memory,
limited to 40 jobs, and expires on restart. Export important results.

This is a local release, not a publicly hosted service. Do not use the legacy
`backend.app.main` entry point for deployment. It is retained for compatibility
and regression tests; the new workflow is `backend.serve:app`.

## Source map

- `backend/app/workbench.py`: shared contract, matched estimators, bounds,
  conditional integration, comparisons and adaptive decisions.
- `backend/app/quantum/`: original reversible arithmetic oracle plus corrected
  IQAE evidence capture and resource accounting.
- `backend/serve.py`: local process-isolated API, cancellation and export.
- `web/`: responsive dashboard and interactive process population.
- `scripts/benchmark.py`: reproducible evidence generation.
- `evidence/`: actual recorded runs, benchmark results and charts.
- `docs/`: model card, demo script, claims, limitations and release checks.

See `IMPLEMENTATION_STATUS.md` for the mapping to all twelve requested prompts.
