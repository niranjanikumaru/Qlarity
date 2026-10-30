"""
jobs.py — SQLite job store and async worker for the Qlarity computation service.

Architecture
------------
Jobs flow through states:  queued → running → completed | failed | cancelled

Storage: a single aiosqlite database file (qlarity_jobs.db by default).
Concurrency: each job runs in a dedicated asyncio Task via asyncio.create_task().
Workers execute the computation pipeline synchronously (Qiskit/scipy are
CPU-bound), wrapped in run_in_executor so FastAPI's event loop stays responsive.

Schema (jobs table)
--------------------
  job_id       TEXT  PRIMARY KEY  — uuid4 string
  status       TEXT               — JobStatus enum value
  label        TEXT
  queued_at    TEXT               — ISO datetime
  started_at   TEXT  NULLABLE
  finished_at  TEXT  NULLABLE
  scenario_json TEXT             — full ScenarioRequest as JSON
  results_json  TEXT NULLABLE    — RunResults as JSON (after completion)
  error_msg     TEXT NULLABLE
  progress      TEXT NULLABLE    — running status message

Public interface
----------------
  init_db(db_path)           — create table if not exists
  enqueue_job(scenario)      — insert row, return JobCreate
  get_job(job_id)            — return JobDetail | None
  list_jobs(limit, offset)   — return List[JobSummary]
  cancel_job(job_id)         — mark as cancelled if queued/running
  launch_worker(job_id, ...)  — start computation Task
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from backend.app.schemas import (
    Estimator,
    ExactResultSchema,
    ExportFormat,
    ISResultSchema,
    IQAEResultSchema,
    JobCreate,
    JobDetail,
    JobStatus,
    JobSummary,
    MonteCarloResultSchema,
    RunResults,
    ScenarioRequest,
    TrajectoryPoint,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_DB = Path(__file__).parent.parent / "qlarity_jobs.db"
_DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'queued',
    label        TEXT NOT NULL DEFAULT '',
    queued_at    TEXT NOT NULL,
    started_at   TEXT,
    finished_at  TEXT,
    scenario_json TEXT NOT NULL,
    results_json  TEXT,
    error_msg    TEXT,
    progress     TEXT
);
"""

# One worker thread per process — keeps the asyncio loop free
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qlarity_worker")


# ---------------------------------------------------------------------------
# DB initialisation
# ---------------------------------------------------------------------------

async def init_db(db_path: Path = _DEFAULT_DB) -> None:
    """Create the jobs table if it does not exist."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_DDL)
        await db.commit()


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def enqueue_job(
    scenario: ScenarioRequest,
    db_path: Path = _DEFAULT_DB,
) -> JobCreate:
    """Insert a new queued job row and return its creation receipt."""
    job_id = str(uuid.uuid4())
    queued_at = _now_iso()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO jobs
               (job_id, status, label, queued_at, scenario_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                job_id,
                JobStatus.QUEUED.value,
                scenario.label,
                queued_at,
                scenario.model_dump_json(),
            ),
        )
        await db.commit()
    return JobCreate(
        job_id=job_id,
        status=JobStatus.QUEUED,
        queued_at=datetime.fromisoformat(queued_at),
        label=scenario.label,
    )


async def get_job(
    job_id: str,
    db_path: Path = _DEFAULT_DB,
) -> Optional[JobDetail]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_detail(dict(row))


async def list_jobs(
    limit: int = 50,
    offset: int = 0,
    db_path: Path = _DEFAULT_DB,
) -> List[JobSummary]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs ORDER BY queued_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_summary(dict(r)) for r in rows]


async def cancel_job(
    job_id: str,
    db_path: Path = _DEFAULT_DB,
) -> bool:
    """Mark a queued or running job as cancelled. Returns True if updated."""
    async with aiosqlite.connect(db_path) as db:
        result = await db.execute(
            """UPDATE jobs SET status = ?, finished_at = ?
               WHERE job_id = ? AND status IN ('queued', 'running')""",
            (JobStatus.CANCELLED.value, _now_iso(), job_id),
        )
        await db.commit()
        return result.rowcount > 0


async def _update_job(
    job_id: str,
    db_path: Path,
    **kwargs: Any,
) -> None:
    """Generic patch helper — updates only the provided columns."""
    if not kwargs:
        return
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    await _raw_execute(
        db_path,
        f"UPDATE jobs SET {cols} WHERE job_id = ? AND status != 'cancelled'",
        (*kwargs.values(), job_id),
    )


async def _raw_execute(db_path: Path, sql: str, params: tuple = ()) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(sql, params)
        await db.commit()


# ---------------------------------------------------------------------------
# Row → schema converters
# ---------------------------------------------------------------------------

def _row_to_summary(row: Dict[str, Any]) -> JobSummary:
    scenario = ScenarioRequest.model_validate_json(row["scenario_json"])
    return JobSummary(
        job_id=row["job_id"],
        status=JobStatus(row["status"]),
        label=row["label"],
        queued_at=datetime.fromisoformat(row["queued_at"]),
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
        estimators=[e.value for e in scenario.estimators],
        I_limit_A=scenario.I_limit_A,
        error_msg=row["error_msg"],
    )


def _row_to_detail(row: Dict[str, Any]) -> JobDetail:
    scenario = ScenarioRequest.model_validate_json(row["scenario_json"])
    results: Optional[RunResults] = None
    if row["results_json"]:
        results = RunResults.model_validate_json(row["results_json"])
    return JobDetail(
        job_id=row["job_id"],
        status=JobStatus(row["status"]),
        label=row["label"],
        queued_at=datetime.fromisoformat(row["queued_at"]),
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
        estimators=[e.value for e in scenario.estimators],
        I_limit_A=scenario.I_limit_A,
        error_msg=row["error_msg"],
        scenario=scenario,
        results=results,
        progress=row["progress"],
    )


# ---------------------------------------------------------------------------
# Computation pipeline (runs in thread pool)
# ---------------------------------------------------------------------------

def _run_pipeline(scenario: ScenarioRequest) -> RunResults:
    """
    Synchronous computation pipeline executed in a thread-pool worker.
    Order: exact → monte_carlo → importance_sampling → iqae
    Each estimator's result is passed along so later estimators can use
    the exact p_fail as a reference.
    """
    from backend.app.physics.leakage import NominalDevice, OperatingPoint
    from backend.app.physics.variations import build_discrete_var, JointDistribution
    from backend.app.physics.discretize import build_quantised_score
    from backend.app.classical.exact import exact_integer, ExactResult
    from backend.app.classical.monte_carlo import run_monte_carlo
    from backend.app.classical.importance_sampling import run_importance_sampling
    from backend.app.quantum.oracle import build_oracle
    from backend.app.quantum.iqae import run_iqae

    # Build domain objects from request
    device = NominalDevice(
        L0_nm=scenario.device.L0_nm,
        tox0_nm=scenario.device.tox0_nm,
        Vth0_V=scenario.device.Vth0_V,
        I0_A_per_um=scenario.device.I0_A_per_um,
        n_ideality=scenario.device.n_ideality,
        alpha_L_V_per_nm=scenario.device.alpha_L_V_per_nm,
        alpha_tox_V_per_nm=scenario.device.alpha_tox_V_per_nm,
        I_ref_A=scenario.device.I_ref_A,
    )
    op = OperatingPoint(
        Vds=scenario.operating.Vds,
        Vgs=scenario.operating.Vgs,
        Vbs=scenario.operating.Vbs,
        temperature_K=scenario.operating.temperature_K,
        W_um=scenario.operating.W_um,
    )
    v = scenario.variations
    joint = JointDistribution(
        var_L=build_discrete_var("delta_L",   "nm", v.sigma_L_nm),
        var_tox=build_discrete_var("delta_tox", "nm", v.sigma_tox_nm),
        var_vth=build_discrete_var("delta_vth", "mV", v.sigma_vth_mV),
    )
    I_limit = scenario.I_limit_A

    qmodel = build_quantised_score(joint, I_limit, op, device, scale=scenario.qae_scale)
    results = RunResults()
    exact_p: Optional[float] = None

    estimator_set = set(scenario.estimators)

    # 1. Exact enumeration (cheap — always run first if requested)
    if Estimator.EXACT in estimator_set:
        r = exact_integer(joint, qmodel)
        exact_p = float(r.p_fail)
        results.exact = ExactResultSchema(
            method=r.method,
            p_fail=float(r.p_fail),
            yield_=float(r.yield_),
            n_states=int(r.n_states),
            elapsed_s=float(r.elapsed_s),
            notes=list(r.notes),
        )
        results.exact_p_fail = exact_p

    # 2. Monte Carlo
    if Estimator.MONTE_CARLO in estimator_set:
        p = scenario.classical
        r = run_monte_carlo(
            joint, I_limit, op, device,
            n_samples=p.n_samples,
            seed=p.seed,
            alpha=p.alpha,
            exact_p_fail=exact_p,
            qmodel=qmodel,
            use_integer_predicate=True,
        )
        traj = [
            TrajectoryPoint(sample_index=t[0], p_fail_running=float(t[1]))
            for t in (r.trajectory or [])
        ]
        results.monte_carlo = MonteCarloResultSchema(
            p_fail_estimate=float(r.p_fail_estimate),
            yield_estimate=float(r.yield_estimate),
            ci_lower=float(r.ci_lower),
            ci_upper=float(r.ci_upper),
            ci_alpha=float(r.ci_alpha),
            n_samples=int(r.n_samples),
            n_failures=int(r.n_failures),
            elapsed_s=float(r.elapsed_s),
            seed=int(r.seed),
            error_vs_exact=float(r.error_vs_exact) if r.error_vs_exact is not None else None,
            relative_error=float(r.relative_error) if r.relative_error is not None else None,
            trajectory=traj,
        )

    # 3. Importance sampling
    if Estimator.IMPORTANCE_SAMPLING in estimator_set:
        p = scenario.classical
        r = run_importance_sampling(
            joint, I_limit, op, device,
            n_samples=p.n_samples,
            seed=p.seed,
            alpha=p.alpha,
            exact_p_fail=exact_p,
            qmodel=qmodel,
        )
        results.importance_sampling = ISResultSchema(
            p_fail_estimate=float(r.p_fail_estimate),
            yield_estimate=float(r.yield_estimate),
            ci_lower=float(r.ci_lower),
            ci_upper=float(r.ci_upper),
            ci_alpha=float(r.ci_alpha),
            n_samples=int(r.n_samples),
            n_pilot=int(r.n_pilot),
            ess=float(r.ess),
            max_weight=float(r.max_weight),
            weight_cv=float(r.weight_cv),
            elapsed_s=float(r.elapsed_s),
            seed=int(r.seed),
            proposal_description=str(r.proposal_description),
            error_vs_exact=float(r.error_vs_exact) if r.error_vs_exact is not None else None,
            relative_error=float(r.relative_error) if r.relative_error is not None else None,
        )

    # 4. IQAE (most expensive — runs last)
    if Estimator.IQAE in estimator_set:
        qp = scenario.iqae
        qmodel = build_quantised_score(joint, I_limit, op, device, scale=scenario.qae_scale)
        if 7 + qmodel.accumulator_bits > 16:
            raise ValueError("Legacy IQAE width exceeds 16-qubit limit; lower qae_scale")
        oracle_result = build_oracle(joint, qmodel, validate=False)
        r = run_iqae(
            oracle_result,
            epsilon_target=qp.epsilon_target,
            alpha=qp.alpha,
            default_shots=qp.default_shots,
            seed=qp.seed,
            confint_method=qp.confint_method,
            exact_p_fail=exact_p,
        )
        results.iqae = IQAEResultSchema(
            p_fail_estimate=float(r.p_fail_estimate),
            yield_estimate=float(r.yield_estimate),
            p_fail_ci_lower=float(r.p_fail_ci_lower),
            p_fail_ci_upper=float(r.p_fail_ci_upper),
            yield_ci_lower=float(r.yield_ci_lower),
            yield_ci_upper=float(r.yield_ci_upper),
            amplitude_estimate=float(r.amplitude_estimate),
            amplitude_ci=(float(r.amplitude_ci[0]), float(r.amplitude_ci[1])),
            epsilon_target=float(r.epsilon_target),
            alpha=float(r.alpha),
            confint_method=str(r.confint_method),
            powers=list(r.powers),
            shots_per_circuit=list(r.shots_per_circuit) if r.shots_per_circuit else [],
            num_oracle_queries=int(r.num_oracle_queries),
            NA_our_count=int(r.NA_our_count),
            n_total_qubits=int(r.n_total_qubits),
            circuit_depth_raw=int(r.circuit_depth_raw),
            n_acc_qubits=int(r.n_acc_qubits),
            elapsed_s=float(r.elapsed_s),
            seed=int(r.seed),
            backend=str(r.backend),
            error_vs_exact=float(r.error_vs_exact) if r.error_vs_exact is not None else None,
            interval_contains_exact=r.interval_contains_exact,
            grover_power_notes=list(r.grover_power_notes or []),
        )

    return results


# ---------------------------------------------------------------------------
# Async worker launcher
# ---------------------------------------------------------------------------

async def launch_worker(
    job_id: str,
    scenario: ScenarioRequest,
    db_path: Path = _DEFAULT_DB,
) -> None:
    """
    Launch the computation pipeline in the thread pool.
    Updates the DB row at each state transition.
    """
    loop = asyncio.get_event_loop()

    # Mark as running
    await _update_job(job_id, db_path,
                      status=JobStatus.RUNNING.value,
                      started_at=_now_iso(),
                      progress="Running computation pipeline...")
    try:
        results: RunResults = await loop.run_in_executor(
            _executor, _run_pipeline, scenario
        )
        await _update_job(
            job_id, db_path,
            status=JobStatus.COMPLETED.value,
            finished_at=_now_iso(),
            results_json=results.model_dump_json(),
            progress="Completed.",
        )
    except asyncio.CancelledError:
        await _update_job(job_id, db_path,
                          status=JobStatus.CANCELLED.value,
                          finished_at=_now_iso(),
                          progress="Cancelled.")
        raise
    except Exception as exc:  # noqa: BLE001
        await _update_job(
            job_id, db_path,
            status=JobStatus.FAILED.value,
            finished_at=_now_iso(),
            error_msg=str(exc)[:2000],
            progress=f"Failed: {exc}",
        )


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def build_json_export(job: JobDetail) -> str:
    """Serialise full job detail to compact JSON."""
    return job.model_dump_json(indent=2)


def build_csv_export(job: JobDetail) -> str:
    """Flatten top-level scalar fields from all estimator results into CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    header = [
        "job_id", "label", "status", "I_limit_A", "estimator",
        "p_fail", "yield_", "ci_lower", "ci_upper", "elapsed_s", "notes",
    ]
    writer.writerow(header)

    def _row(estimator: str, p_fail: float, yield_: float,
             ci_lo: float, ci_hi: float, elapsed: float, notes: str = "") -> None:
        writer.writerow([
            job.job_id, job.label, job.status.value,
            job.I_limit_A, estimator,
            round(p_fail, 8), round(yield_, 8),
            round(ci_lo, 8), round(ci_hi, 8),
            round(elapsed, 4), notes,
        ])

    r = job.results
    if r:
        if r.exact:
            _row("exact", r.exact.p_fail, r.exact.yield_,
                 r.exact.p_fail, r.exact.p_fail, r.exact.elapsed_s,
                 "; ".join(r.exact.notes))
        if r.monte_carlo:
            mc = r.monte_carlo
            _row("monte_carlo", mc.p_fail_estimate, mc.yield_estimate,
                 mc.ci_lower, mc.ci_upper, mc.elapsed_s)
        if r.importance_sampling:
            iss = r.importance_sampling
            _row("importance_sampling", iss.p_fail_estimate, iss.yield_estimate,
                 iss.ci_lower, iss.ci_upper, iss.elapsed_s)
        if r.iqae:
            q = r.iqae
            _row("iqae", q.p_fail_estimate, q.yield_estimate,
                 q.p_fail_ci_lower, q.p_fail_ci_upper, q.elapsed_s,
                 f"qubits={q.n_total_qubits} NA={q.NA_our_count}")

    return buf.getvalue()
