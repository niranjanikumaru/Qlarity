"""
schemas.py — Pydantic v2 data models for the Qlarity API.

All request/response bodies are defined here so that:
  - FastAPI can auto-generate OpenAPI docs from them.
  - Business logic (jobs.py, main.py) stays schema-agnostic.
  - Tests can import and construct schemas independently.

Design notes
------------
- All models use strict mode where values should never be coerced silently.
- Numerical ranges are validated with Annotated / Field(ge=, le=, gt=).
- Enum strings are the single source of truth for job states / estimator names.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    QUEUED    = "queued"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class Estimator(str, Enum):
    EXACT               = "exact"
    MONTE_CARLO         = "monte_carlo"
    IMPORTANCE_SAMPLING = "importance_sampling"
    IQAE                = "iqae"


class ExportFormat(str, Enum):
    JSON = "json"
    CSV  = "csv"


# ---------------------------------------------------------------------------
# Scenario input schemas
# ---------------------------------------------------------------------------

from .physics.leakage import NominalDevice, OperatingPoint

class DeviceParams(BaseModel):
    """Nominal transistor device parameters. All values are illustrative."""
    L0_nm:              float = Field(default=NominalDevice().L0_nm,  gt=0,   description="Nominal gate length (nm)")
    tox0_nm:            float = Field(default=NominalDevice().tox0_nm,   gt=0,   description="Nominal oxide thickness (nm)")
    Vth0_V:             float = Field(default=NominalDevice().Vth0_V,   gt=0,   description="Nominal threshold voltage (V)")
    I0_A_per_um:        float = Field(default=NominalDevice().I0_A_per_um,  gt=0,   description="Pre-exponential current scale (A/µm)")
    n_ideality:         float = Field(default=NominalDevice().n_ideality,   ge=1.0, le=2.0, description="Sub-threshold ideality factor")
    alpha_L_V_per_nm:   float = Field(default=NominalDevice().alpha_L_V_per_nm, description="Vth sensitivity to gate length (V/nm)")
    alpha_tox_V_per_nm: float = Field(default=NominalDevice().alpha_tox_V_per_nm,  description="Vth sensitivity to oxide thickness (V/nm)")
    I_ref_A:            float = Field(default=NominalDevice().I_ref_A, gt=0,   description="Reference current for log scaling (A)")


class OperatingParams(BaseModel):
    """Operating-point parameters at which leakage is evaluated."""
    Vds:           float = Field(default=1.0,   description="Drain-source voltage (V)")
    Vgs:           float = Field(default=0.0,   description="Gate-source voltage (V), 0 = off-state")
    Vbs:           float = Field(default=0.0,   description="Body-source voltage (V)")
    temperature_K: float = Field(default=300.0, gt=0, description="Temperature (K)")
    W_um:          float = Field(default=1.0,   gt=0, description="Channel width (µm)")


class VariationParams(BaseModel):
    """Standard deviations for the three process-variation Gaussians."""
    sigma_L_nm:   float = Field(default=3.0,  gt=0, description="Gate-length variation σ (nm)")
    sigma_tox_nm: float = Field(default=0.1,  gt=0, description="Oxide-thickness variation σ (nm)")
    sigma_vth_mV: float = Field(default=15.0, gt=0, description="Threshold-voltage offset σ (mV)")


class ClassicalParams(BaseModel):
    """Options for classical estimators (MC, IS)."""
    n_samples: int   = Field(default=10_000, ge=100, le=1_000_000)
    seed:      int   = Field(default=42,     ge=0)
    alpha:     float = Field(default=0.05,   gt=0.0, lt=1.0,
                             description="Significance level for confidence intervals")


class IQAEParams(BaseModel):
    """Options for Iterative Quantum Amplitude Estimation."""
    epsilon_target: float = Field(default=0.02, gt=0.0, lt=0.5,
                                  description="Target half-width of probability CI")
    alpha:          float = Field(default=0.05, gt=0.0, lt=1.0)
    default_shots:  int   = Field(default=1024, ge=64, le=65536)
    seed:           int   = Field(default=42,   ge=0)
    confint_method: str   = Field(default="beta",
                                  description="CI method: 'beta' or 'likelihood_ratio'")


class ScenarioRequest(BaseModel):
    """Full scenario specification submitted to POST /runs."""
    label:      str             = Field(default="", max_length=128)
    I_limit_A:  float           = Field(..., gt=0,
                                        description="Leakage failure threshold (A). Fail if I_off >= I_limit.")
    device:     DeviceParams    = Field(default_factory=DeviceParams)
    operating:  OperatingParams = Field(default_factory=OperatingParams)
    variations: VariationParams = Field(default_factory=VariationParams)
    estimators: List[Estimator] = Field(
        default=[Estimator.EXACT, Estimator.MONTE_CARLO],
        min_length=1,
        description="Estimators to run (exact runs first to provide ground-truth p_fail).",
    )
    classical:  ClassicalParams = Field(default_factory=ClassicalParams)
    iqae:       IQAEParams      = Field(default_factory=IQAEParams)
    qae_scale:  float           = Field(default=1000.0, gt=0,
                                        description="Integer quantisation scale for oracle")

    @field_validator("estimators")
    @classmethod
    def no_duplicate_estimators(cls, v: List[Estimator]) -> List[Estimator]:
        seen: set = set()
        for e in v:
            if e in seen:
                raise ValueError(f"Duplicate estimator: {e}")
            seen.add(e)
        return v

    model_config = {"json_schema_extra": {
        "examples": [{
            "label": "Nominal 65 nm node",
            "I_limit_A": 5e-8,
            "estimators": ["exact", "monte_carlo", "iqae"],
        }]
    }}


# ---------------------------------------------------------------------------
# Validation-only response
# ---------------------------------------------------------------------------

class ValidationResponse(BaseModel):
    valid:    bool
    warnings: List[str]         = Field(default_factory=list)
    errors:   List[str]         = Field(default_factory=list)
    derived:  Dict[str, Any]    = Field(default_factory=dict,
                                        description="Derived quantities (exact p_fail, qmodel summary)")


# ---------------------------------------------------------------------------
# Estimator result schemas (mirror computation dataclass fields)
# ---------------------------------------------------------------------------

class ExactResultSchema(BaseModel):
    method:    str
    p_fail:    float
    yield_:    float
    n_states:  int
    elapsed_s: float
    notes:     List[str] = Field(default_factory=list)


class TrajectoryPoint(BaseModel):
    sample_index:   int
    p_fail_running: float


class MonteCarloResultSchema(BaseModel):
    p_fail_estimate: float
    yield_estimate:  float
    ci_lower:        float
    ci_upper:        float
    ci_alpha:        float
    n_samples:       int
    n_failures:      int
    elapsed_s:       float
    seed:            int
    error_vs_exact:  Optional[float] = None
    relative_error:  Optional[float] = None
    trajectory:      List[TrajectoryPoint] = Field(default_factory=list)


class ISResultSchema(BaseModel):
    p_fail_estimate:      float
    yield_estimate:       float
    ci_lower:             float
    ci_upper:             float
    ci_alpha:             float
    n_samples:            int
    n_pilot:              int
    ess:                  float
    max_weight:           float
    weight_cv:            float
    elapsed_s:            float
    seed:                 int
    proposal_description: str
    error_vs_exact:       Optional[float] = None
    relative_error:       Optional[float] = None


class IQAEResultSchema(BaseModel):
    p_fail_estimate:         float
    yield_estimate:          float
    p_fail_ci_lower:         float
    p_fail_ci_upper:         float
    yield_ci_lower:          float
    yield_ci_upper:          float
    amplitude_estimate:      float
    amplitude_ci:            Tuple[float, float]
    epsilon_target:          float
    alpha:                   float
    confint_method:          str
    powers:                  List[int]
    shots_per_circuit:       List[int]
    num_oracle_queries:      int
    NA_our_count:            int
    n_total_qubits:          int
    circuit_depth_raw:       int
    n_acc_qubits:            int
    elapsed_s:               float
    seed:                    int
    backend:                 str
    error_vs_exact:          Optional[float] = None
    interval_contains_exact: Optional[bool]  = None
    grover_power_notes:      List[str]       = Field(default_factory=list)


class RunResults(BaseModel):
    """Aggregated results for all requested estimators."""
    exact:               Optional[ExactResultSchema]      = None
    monte_carlo:         Optional[MonteCarloResultSchema] = None
    importance_sampling: Optional[ISResultSchema]         = None
    iqae:                Optional[IQAEResultSchema]        = None
    exact_p_fail: Optional[float] = Field(
        None, description="Ground-truth p_fail from exact enumerator (if run)"
    )


# ---------------------------------------------------------------------------
# Job lifecycle schemas
# ---------------------------------------------------------------------------

class JobCreate(BaseModel):
    job_id:    str
    status:    JobStatus
    queued_at: datetime
    label:     str


class JobSummary(BaseModel):
    job_id:      str
    status:      JobStatus
    label:       str
    queued_at:   datetime
    started_at:  Optional[datetime] = None
    finished_at: Optional[datetime] = None
    estimators:  List[str]
    I_limit_A:   float
    error_msg:   Optional[str] = None


class JobDetail(JobSummary):
    """Full detail returned by GET /runs/{id}."""
    scenario:  ScenarioRequest
    results:   Optional[RunResults] = None
    progress:  Optional[str]        = None


class ExportResponse(BaseModel):
    """Returned by GET /runs/{id}/export."""
    job_id:   str
    format:   ExportFormat
    filename: str
    content:  str   # raw JSON or CSV text


# ---------------------------------------------------------------------------
# GET /models response
# ---------------------------------------------------------------------------

class ModelInfo(BaseModel):
    name:                  str
    description:           str
    device_defaults:       DeviceParams
    operating_defaults:    OperatingParams
    variation_defaults:    VariationParams
    estimators_available:  List[str]
    notes:                 List[str] = Field(default_factory=list)
