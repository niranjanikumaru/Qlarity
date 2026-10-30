"""
calibration.py — Model calibration utilities (Track A illustrative; Track B stub).

Specification reference: §5 Track A & B.

Track A (default): Clearly labelled illustrative model.
    No SPICE runs required.  All parameters are set from documented physics
    with explicit ILLUSTRATIVE labels.

Track B (optional): SPICE-calibrated surrogate.
    Provides the infrastructure for fitting a polynomial surrogate to
    SPICE-generated leakage data.  Requires the user to supply a dataset
    (e.g., from ngspice).  Will not run without data.

The surrogate family for Track B is:
    g(z) = c0 + sum_i ci*zi + sum_{i<=j} cij*zi*zj

where z are normalised variation variables:
    z_L   = delta_L_nm / sigma_L
    z_tox = delta_tox_nm / sigma_tox
    z_vth = delta_vth_mV / sigma_vth
"""

from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats
from scipy.optimize import least_squares


# ---------------------------------------------------------------------------
# Calibration record
# ---------------------------------------------------------------------------
@dataclass
class CalibrationRecord:
    """Provenance record for a fitted or illustrative model.

    Attributes
    ----------
    track               : 'A' (illustrative) or 'B' (SPICE-calibrated)
    model_description   : human-readable description
    provenance          : citable source or data file reference
    is_foundry_calibrated: False for Track A; True only after validated fit
    coefficients        : dict of coefficient name -> value (for surrogate)
    training_rmse_log_I : root-mean-square error in log-current on training set
    validation_rmse_log_I: RMSE on held-out validation set
    misclassification_rate: fraction of validation states with flipped pass/fail
    supported_range     : dict var_name -> (min, max) in physical units
    warnings            : list of human-readable warnings about model limits
    """
    track: str  # 'A' or 'B'
    model_description: str
    provenance: str
    is_foundry_calibrated: bool = False
    coefficients: Dict[str, float] = field(default_factory=dict)
    training_rmse_log_I: Optional[float] = None
    validation_rmse_log_I: Optional[float] = None
    misclassification_rate: Optional[float] = None
    supported_range: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "track": self.track,
            "model_description": self.model_description,
            "provenance": self.provenance,
            "is_foundry_calibrated": self.is_foundry_calibrated,
            "coefficients": self.coefficients,
            "training_rmse_log_I": self.training_rmse_log_I,
            "validation_rmse_log_I": self.validation_rmse_log_I,
            "misclassification_rate": self.misclassification_rate,
            "supported_range": {k: list(v) for k, v in self.supported_range.items()},
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Track A: illustrative model record
# ---------------------------------------------------------------------------
def track_a_record() -> CalibrationRecord:
    """Return the provenance record for the Track A illustrative model."""
    return CalibrationRecord(
        track="A",
        model_description=(
            "Illustrative bulk n-MOSFET sub-threshold leakage model. "
            "Functional form from Taur & Ning (2009) §3.2. "
            "Coefficients are NOT foundry-calibrated; for educational use only."
        ),
        provenance=(
            "Taur & Ning, 'Fundamentals of Modern VLSI Devices', 2nd ed., "
            "Cambridge University Press, 2009. "
            "BSIM4 reference manual, https://bsim.berkeley.edu/models/bsim4/"
        ),
        is_foundry_calibrated=False,
        supported_range={
            "delta_L_nm": (-20.0, 20.0),
            "delta_tox_nm": (-0.5, 0.5),
            "delta_vth_mV": (-60.0, 60.0),
        },
        warnings=[
            "All coefficient values are ILLUSTRATIVE. "
            "Do not interpret as foundry measurements.",
            "The linear Vth sensitivity model (alpha_L, alpha_tox) is a "
            "first-order approximation; short-channel effects are not modelled.",
            "No DIBL, drain-induced barrier lowering, or body-effect terms included.",
        ],
    )


# ---------------------------------------------------------------------------
# Track B: polynomial surrogate fitting (stub, requires SPICE data)
# ---------------------------------------------------------------------------
def _feature_matrix(
    delta_L: np.ndarray,
    delta_tox: np.ndarray,
    delta_vth: np.ndarray,
    sigma_L: float,
    sigma_tox: float,
    sigma_vth: float,
    order: int = 2,
) -> np.ndarray:
    """Build the feature matrix for the polynomial surrogate.

    Normalised inputs:
        z0 = delta_L / sigma_L
        z1 = delta_tox / sigma_tox
        z2 = delta_vth / sigma_vth

    Features (order <= 2):
        [1, z0, z1, z2, z0*z0, z0*z1, z0*z2, z1*z1, z1*z2, z2*z2]
        (upper-triangular including diagonal for cross-terms)
    """
    z0 = delta_L / sigma_L
    z1 = delta_tox / sigma_tox
    z2 = delta_vth / sigma_vth
    zs = [z0, z1, z2]

    cols = [np.ones_like(z0), z0, z1, z2]
    if order >= 2:
        for i in range(3):
            for j in range(i, 3):
                cols.append(zs[i] * zs[j])

    return np.column_stack(cols)


FEATURE_NAMES_ORDER2 = [
    "const", "z_L", "z_tox", "z_vth",
    "z_L^2", "z_L*z_tox", "z_L*z_vth",
    "z_tox^2", "z_tox*z_vth",
    "z_vth^2",
]


class SpiceSurrogate:
    """Polynomial surrogate fitted to SPICE-generated leakage data.

    Usage
    -----
    1. Generate a design matrix from ngspice runs: (delta_L, delta_tox,
       delta_vth) -> I_off_A.
    2. Split into training (80%) and validation (20%).
    3. Call SpiceSurrogate.fit(X_train, y_train, ...).
    4. Validate with SpiceSurrogate.validate(X_val, y_val, I_limit_A).
    5. Access .record for the CalibrationRecord.
    """

    def __init__(
        self,
        sigma_L: float,
        sigma_tox: float,
        sigma_vth: float,
        order: int = 2,
    ) -> None:
        self.sigma_L = sigma_L
        self.sigma_tox = sigma_tox
        self.sigma_vth = sigma_vth
        self.order = order
        self._coef: Optional[np.ndarray] = None
        self.record: Optional[CalibrationRecord] = None

    def fit(
        self,
        delta_L: np.ndarray,
        delta_tox: np.ndarray,
        delta_vth: np.ndarray,
        I_off_A: np.ndarray,
        data_source: str = "user-supplied SPICE dataset",
    ) -> "SpiceSurrogate":
        """Fit the polynomial surrogate to log-current data.

        Parameters
        ----------
        delta_L, delta_tox, delta_vth : 1-D arrays — training inputs
        I_off_A    : 1-D array — SPICE off-state leakage currents (A)
        data_source: provenance string for the training data
        """
        g_train = np.log(I_off_A)  # ln(I_off); I_ref absorbed into const
        X = _feature_matrix(
            delta_L, delta_tox, delta_vth,
            self.sigma_L, self.sigma_tox, self.sigma_vth,
            self.order,
        )
        self._coef = np.linalg.lstsq(X, g_train, rcond=None)[0]
        g_pred = X @ self._coef
        rmse = float(np.sqrt(np.mean((g_pred - g_train) ** 2)))

        coef_dict = {
            name: float(v)
            for name, v in zip(FEATURE_NAMES_ORDER2, self._coef)
        }

        self.record = CalibrationRecord(
            track="B",
            model_description=(
                f"Polynomial surrogate g(z) of order {self.order} "
                "fitted to SPICE-generated leakage data."
            ),
            provenance=data_source,
            is_foundry_calibrated=False,  # True only after independent validation
            coefficients=coef_dict,
            training_rmse_log_I=rmse,
            supported_range={},
            warnings=[
                "Validation has not yet been performed.  "
                "Call validate() before using for probability estimation.",
                "is_foundry_calibrated remains False until "
                "independently validated against a held-out dataset.",
            ],
        )
        return self

    def predict_log(
        self,
        delta_L: np.ndarray,
        delta_tox: np.ndarray,
        delta_vth: np.ndarray,
    ) -> np.ndarray:
        """Predict ln(I_off) using the fitted surrogate."""
        if self._coef is None:
            raise RuntimeError("Call fit() before predict_log().")
        X = _feature_matrix(
            delta_L, delta_tox, delta_vth,
            self.sigma_L, self.sigma_tox, self.sigma_vth,
            self.order,
        )
        return X @ self._coef

    def validate(
        self,
        delta_L: np.ndarray,
        delta_tox: np.ndarray,
        delta_vth: np.ndarray,
        I_off_A: np.ndarray,
        I_limit_A: float,
    ) -> Dict:
        """Evaluate surrogate on a held-out validation set.

        Records validation RMSE and classification error rate into self.record.

        Returns
        -------
        dict with 'validation_rmse_log_I' and 'misclassification_rate'.
        """
        if self._coef is None or self.record is None:
            raise RuntimeError("Call fit() before validate().")

        g_true = np.log(I_off_A)
        g_pred = self.predict_log(delta_L, delta_tox, delta_vth)
        rmse = float(np.sqrt(np.mean((g_pred - g_true) ** 2)))

        g_limit = math.log(I_limit_A)
        true_fail = g_true >= g_limit
        pred_fail = g_pred >= g_limit
        misclass_rate = float(np.mean(true_fail != pred_fail))

        self.record.validation_rmse_log_I = rmse
        self.record.misclassification_rate = misclass_rate

        if misclass_rate > 0.01:
            self.record.warnings.append(
                f"Surrogate misclassifies {misclass_rate*100:.1f}% of "
                "validation states near the failure boundary. "
                "Probability estimates may be inaccurate."
            )

        return {
            "validation_rmse_log_I": rmse,
            "misclassification_rate": misclass_rate,
        }

    def save(self, path: Path) -> None:
        """Persist calibration record to JSON."""
        if self.record is None:
            raise RuntimeError("Nothing to save; call fit() first.")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.record.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path, sigma_L: float, sigma_tox: float, sigma_vth: float) -> "SpiceSurrogate":
        """Load a previously saved surrogate from its JSON record."""
        with open(path) as f:
            d = json.load(f)
        obj = cls(sigma_L=sigma_L, sigma_tox=sigma_tox, sigma_vth=sigma_vth)
        names = FEATURE_NAMES_ORDER2
        obj._coef = np.array([d["coefficients"].get(n, 0.0) for n in names])
        obj.record = CalibrationRecord(
            track=d["track"],
            model_description=d["model_description"],
            provenance=d["provenance"],
            is_foundry_calibrated=d["is_foundry_calibrated"],
            coefficients=d["coefficients"],
            training_rmse_log_I=d.get("training_rmse_log_I"),
            validation_rmse_log_I=d.get("validation_rmse_log_I"),
            misclassification_rate=d.get("misclassification_rate"),
            supported_range={k: tuple(v) for k, v in d.get("supported_range", {}).items()},
            warnings=d.get("warnings", []),
        )
        return obj
