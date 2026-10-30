"""
main.py — FastAPI application for the Qlarity computation service.

Endpoints
---------
  GET  /                    Health check
  GET  /models              Physics model info and parameter defaults
  POST /scenarios/validate  Validate a scenario payload (no computation)
  POST /runs                Queue a new computation job
  GET  /runs                List all jobs (paginated)
  GET  /runs/{id}           Full job detail + results
  DELETE /runs/{id}         Cancel a queued or running job
  GET  /runs/{id}/export    Download results as JSON or CSV

Lifespan
--------
  On startup: initialise the SQLite database.

CORS
----
  All origins are allowed in development. Restrict in production via env var.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from backend.app import jobs as job_store
from backend.app.schemas import (
    Estimator,
    ExportFormat,
    JobCreate,
    JobDetail,
    JobStatus,
    JobSummary,
    ModelInfo,
    RunResults,
    ScenarioRequest,
    ValidationResponse,
    DeviceParams,
    OperatingParams,
    VariationParams,
)

# ---------------------------------------------------------------------------
# Database path (can be overridden by env var for testing)
# ---------------------------------------------------------------------------

_DB_PATH = Path(os.environ.get("QLARITY_DB", str(job_store._DEFAULT_DB)))


# ---------------------------------------------------------------------------
# Lifespan: init DB on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await job_store.init_db(_DB_PATH)
    yield


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Qlarity — Quantum Yield Estimation API",
    description=(
        "Estimates semiconductor transistor failure probability and specification yield "
        "using classical (exact, Monte Carlo, importance sampling) and quantum "
        "(Iterative Amplitude Estimation) methods."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/", tags=["health"], summary="Health check")
async def root() -> dict:
    return {"status": "ok", "service": "qlarity-api", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# GET /models  — physics model metadata
# ---------------------------------------------------------------------------

@app.get(
    "/models",
    response_model=ModelInfo,
    tags=["models"],
    summary="Describe available physics model and parameter defaults",
)
async def get_models() -> ModelInfo:
    return ModelInfo(
        name="Bulk CMOS Sub-threshold Leakage Model",
        description=(
            "Illustrative sub-threshold leakage model (Taur & Ning, 2nd ed., §3.2). "
            "Three manufacturing variation sources: gate-length deviation δL, "
            "oxide-thickness deviation δtox, and residual Vth offset δVth. "
            "Each is discretised to 4 representative values from a truncated Gaussian. "
            "NOT foundry-calibrated — educational/illustrative use only."
        ),
        device_defaults=DeviceParams(),
        operating_defaults=OperatingParams(),
        variation_defaults=VariationParams(),
        estimators_available=[e.value for e in Estimator],
        notes=[
            "Coefficient values are illustrative and NOT foundry-calibrated.",
            "Joint distribution assumes independence of the three variation sources.",
            "Equality I_off == I_limit counts as failure (spec §5).",
        ],
    )


# ---------------------------------------------------------------------------
# POST /scenarios/validate  — dry-run validation
# ---------------------------------------------------------------------------

@app.post(
    "/scenarios/validate",
    response_model=ValidationResponse,
    tags=["scenarios"],
    summary="Validate a scenario payload and compute derived quantities",
)
async def validate_scenario(scenario: ScenarioRequest) -> ValidationResponse:
    """
    Parse and validate a scenario without queuing computation.
    Returns warnings (e.g. unrealistic parameter values) and, if valid,
    derived quantities: exact failure probability and quantisation model info.
    """
    warnings: List[str] = []
    errors:   List[str] = []
    derived:  dict      = {}

    # Business-logic warnings (schema already enforces hard limits)
    dev = scenario.device
    if dev.L0_nm < 20 or dev.L0_nm > 500:
        warnings.append(f"L0_nm={dev.L0_nm} is outside typical range [20, 500] nm.")
    if dev.tox0_nm < 0.5 or dev.tox0_nm > 10:
        warnings.append(f"tox0_nm={dev.tox0_nm} is outside typical range [0.5, 10] nm.")

    v = scenario.variations
    if v.sigma_L_nm > dev.L0_nm * 0.2:
        warnings.append(
            f"sigma_L_nm={v.sigma_L_nm} is > 20% of L0_nm={dev.L0_nm}; "
            "distribution may not represent realistic manufacturing spread."
        )

    # Run exact enumeration for derived quantities
    try:
        from backend.app.physics.leakage import NominalDevice, OperatingPoint
        from backend.app.physics.variations import (
            build_discrete_var, JointDistribution,
        )
        from backend.app.physics.discretize import build_quantised_score
        from backend.app.classical.exact import exact_float

        device = NominalDevice(
            L0_nm=dev.L0_nm, tox0_nm=dev.tox0_nm,
            Vth0_V=dev.Vth0_V, I0_A_per_um=dev.I0_A_per_um,
            n_ideality=dev.n_ideality, alpha_L_V_per_nm=dev.alpha_L_V_per_nm,
            alpha_tox_V_per_nm=dev.alpha_tox_V_per_nm, I_ref_A=dev.I_ref_A,
        )
        op = OperatingPoint(
            Vds=scenario.operating.Vds, Vgs=scenario.operating.Vgs,
            Vbs=scenario.operating.Vbs,
            temperature_K=scenario.operating.temperature_K,
            W_um=scenario.operating.W_um,
        )
        # Build joint distribution with user-specified sigmas
        joint = JointDistribution(
            var_L=build_discrete_var("delta_L", "nm", v.sigma_L_nm),
            var_tox=build_discrete_var("delta_tox", "nm", v.sigma_tox_nm),
            var_vth=build_discrete_var("delta_vth", "mV", v.sigma_vth_mV),
        )
        exact = exact_float(joint, scenario.I_limit_A, op, device)
        derived["exact_p_fail"]  = round(float(exact.p_fail), 8)
        derived["exact_yield"]   = round(float(exact.yield_), 8)
        derived["n_states"]      = int(exact.n_states)

        # Quantisation model summary (fast, no statevector)
        qmodel = build_quantised_score(
            joint, scenario.I_limit_A, op, device, scale=scenario.qae_scale
        )
        derived["qmodel"] = {
            "accumulator_bits": qmodel.accumulator_bits,
            "T": qmodel.T,
            "B": qmodel.B,
            "n_total_qubits": 7 + qmodel.accumulator_bits,
            "quantisation_error_mass": round(float(qmodel.quantisation_error_mass), 8),
        }

        if exact.p_fail == 0:
            warnings.append("Exact p_fail = 0: all transistors pass at this threshold. IQAE will always return 0.")
        if exact.p_fail == 1:
            warnings.append("Exact p_fail = 1: all transistors fail. IQAE will always return 1.")
        if Estimator.IQAE in scenario.estimators and qmodel.quantisation_error_mass > 0.01:
            warnings.append(
                f"Quantisation error mass = {qmodel.quantisation_error_mass:.4f} > 1%. "
                "IQAE result may differ from classical. Increase qae_scale to reduce this."
            )

    except Exception as exc:  # noqa: BLE001
        errors.append(f"Derived computation failed: {exc}")

    return ValidationResponse(
        valid=len(errors) == 0,
        warnings=warnings,
        errors=errors,
        derived=derived,
    )


# ---------------------------------------------------------------------------
# POST /runs  — queue a new job
# ---------------------------------------------------------------------------

@app.post(
    "/runs",
    response_model=JobCreate,
    status_code=202,
    tags=["runs"],
    summary="Queue a new computation run",
)
async def create_run(scenario: ScenarioRequest) -> JobCreate:
    """
    Validates and queues the scenario for computation.
    Returns immediately with a job_id; poll GET /runs/{id} for results.
    """
    receipt = await job_store.enqueue_job(scenario, _DB_PATH)
    # Use asyncio.create_task so the endpoint returns immediately.
    # BackgroundTasks is NOT used here because httpx's ASGITransport
    # awaits BackgroundTasks inline, making POST /runs block in tests.
    import asyncio
    asyncio.create_task(
        job_store.launch_worker(receipt.job_id, scenario, _DB_PATH)
    )
    return receipt


# ---------------------------------------------------------------------------
# GET /runs  — list all jobs
# ---------------------------------------------------------------------------

@app.get(
    "/runs",
    response_model=List[JobSummary],
    tags=["runs"],
    summary="List all computation runs (newest first)",
)
async def list_runs(
    limit:  int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0,  ge=0),
) -> List[JobSummary]:
    return await job_store.list_jobs(limit=limit, offset=offset, db_path=_DB_PATH)


# ---------------------------------------------------------------------------
# GET /runs/{job_id}  — job detail
# ---------------------------------------------------------------------------

@app.get(
    "/runs/{job_id}",
    response_model=JobDetail,
    tags=["runs"],
    summary="Get full detail and results for a specific run",
)
async def get_run(job_id: str) -> JobDetail:
    detail = await job_store.get_job(job_id, _DB_PATH)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")
    return detail


# ---------------------------------------------------------------------------
# DELETE /runs/{job_id}  — cancel
# ---------------------------------------------------------------------------

@app.delete(
    "/runs/{job_id}",
    status_code=200,
    tags=["runs"],
    summary="Cancel a queued or running job",
)
async def cancel_run(job_id: str) -> dict:
    ok = await job_store.cancel_job(job_id, _DB_PATH)
    if not ok:
        detail = await job_store.get_job(job_id, _DB_PATH)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id!r} is already {detail.status.value} and cannot be cancelled.",
        )
    return {"job_id": job_id, "cancelled": True}


# ---------------------------------------------------------------------------
# GET /runs/{job_id}/export  — download results
# ---------------------------------------------------------------------------

@app.get(
    "/runs/{job_id}/export",
    tags=["runs"],
    summary="Export results as JSON or CSV",
)
async def export_run(
    job_id: str,
    format: ExportFormat = Query(default=ExportFormat.JSON),
) -> PlainTextResponse:
    detail = await job_store.get_job(job_id, _DB_PATH)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")
    if detail.status not in (JobStatus.COMPLETED,):
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id!r} is {detail.status.value}; export is only available for completed jobs.",
        )

    if format == ExportFormat.JSON:
        content  = job_store.build_json_export(detail)
        filename = f"qlarity_{job_id[:8]}.json"
        media    = "application/json"
    else:
        content  = job_store.build_csv_export(detail)
        filename = f"qlarity_{job_id[:8]}.csv"
        media    = "text/csv"

    return PlainTextResponse(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
