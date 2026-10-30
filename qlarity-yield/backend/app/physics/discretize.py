"""
discretize.py — Integer quantisation of the leakage score.

Specification reference: §8 (Convert the failure predicate to bounded integer
arithmetic).

Purpose
-------
The quantum oracle operates on integers, not floating-point values.  This
module converts the log-leakage score g(x) = ln(I_off/I_ref) into a bounded
non-negative integer score S(x) so that the failure predicate

    g(x) >= g_threshold

becomes

    S(x) >= T

with no floating-point arithmetic required inside the oracle.

Approach
--------
The leakage model in log space is:

    g(x) = g0 + c_L * delta_L + c_tox * delta_tox + c_vth * delta_vth

where the coefficients come from linearising the full model around the
nominal point (see derive_linear_coefficients()).

A scale factor s converts floating-point coefficients to integers:

    C_i = round(s * c_i)

and the integer score is:

    S(x) = C0 + C_L * xi_L + C_tox * xi_tox + C_vth * xi_vth

where xi_L, xi_tox, xi_vth are the 2-bit indices (0..3) of the discrete
variation values.

The integer failure threshold is:

    T = ceil(s * g_threshold - S_at_nominal_indices + S_at_nominal_values)

handled consistently; see integer_threshold() for the exact derivation.

Quantisation error
------------------
The module reports the set of states where the integer predicate disagrees
with the floating-point predicate (classification changes) and the total
probability mass of those states.  This is the key exit criterion of §8.

Accumulator width
-----------------
b = ceil(log2(S_max + B + 1))
where B is the offset to ensure S + B >= 0 for all inputs, and S_max is the
maximum possible score over all input combinations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .leakage import (
    NominalDevice,
    OperatingPoint,
    compute_leakage,
    log_failure_threshold,
    thermal_voltage,
)
from .variations import JointDistribution


# ---------------------------------------------------------------------------
# Linear coefficient derivation in log-current space
# ---------------------------------------------------------------------------
def _g_nominal(op: OperatingPoint, device: NominalDevice) -> float:
    """Log-ratio g at the nominal process point (all deltas = 0)."""
    _, g = compute_leakage(0.0, 0.0, 0.0, op, device)
    return g


def derive_linear_coefficients(
    op: OperatingPoint,
    device: NominalDevice,
) -> Dict[str, float]:
    """Derive first-order linear coefficients for g(x) around nominal.

    g(x) ~ g0 + c_L * delta_L + c_tox * delta_tox + c_vth * delta_vth

    Coefficients are derived analytically from the leakage formula:

        g(x) = ln(I0*W/I_ref) - ln(L/1um) - (Vth0 + alpha_L*dL
                + alpha_tox*dtox + dvth/1000 - Vgs) / (n * Vt)

    Partial derivatives:
        dg/d(dL)   = -1/(L0+dL)|_{dL=0} - alpha_L / (n*Vt)
                   = -1/L0_um - alpha_L / (n*Vt)
        dg/d(dtox) = -alpha_tox / (n*Vt)
        dg/d(dvth) = -1e-3 / (n*Vt)        [mV -> V conversion]

    Returns
    -------
    dict with keys:
        'g0'    : nominal log-ratio (float)
        'c_L'   : dg/d(delta_L_nm)   (float, per nm)
        'c_tox' : dg/d(delta_tox_nm) (float, per nm)
        'c_vth' : dg/d(delta_vth_mV) (float, per mV)
    """
    Vt = thermal_voltage(op.temperature_K)
    nVt = device.n_ideality * Vt
    L0_um = device.L0_nm * 1e-3

    g0 = _g_nominal(op, device)
    c_L = -1.0 / L0_um * 1e-3 - device.alpha_L_V_per_nm / nVt  # per nm
    c_tox = -device.alpha_tox_V_per_nm / nVt                     # per nm
    c_vth = -1.0e-3 / nVt                                        # per mV

    return {"g0": g0, "c_L": c_L, "c_tox": c_tox, "c_vth": c_vth}


# ---------------------------------------------------------------------------
# Quantised score dataclass
# ---------------------------------------------------------------------------
@dataclass
class QuantisedScoreModel:
    """Integer score model used by the quantum oracle.

    Attributes
    ----------
    scale              : float — scaling factor s
    C0                 : int   — constant term (scaled + rounded g0)
    C_L                : list[int]  — per-state integer contributions for delta_L
    C_tox              : list[int]  — per-state for delta_tox
    C_vth              : list[int]  — per-state for delta_vth
    T                  : int   — integer failure threshold (S >= T => fail)
    B                  : int   — non-negativity offset (S + B >= 0 always)
    accumulator_bits   : int   — b = ceil(log2(S_max + B + 1))
    S_min              : int   — minimum score over all input combinations
    S_max              : int   — maximum score over all input combinations
    float_g_threshold  : float — floating-point g threshold for reference
    quantisation_error_mass : float — total prob mass of misclassified states
    misclassified_states    : list of (dL_idx, dtox_idx, dvth_idx, prob)
    provenance         : str   — textual description of derivation
    """
    scale: float
    C0: int
    C_L: List[int]
    C_tox: List[int]
    C_vth: List[int]
    T: int
    B: int
    accumulator_bits: int
    S_min: int
    S_max: int
    float_g_threshold: float
    quantisation_error_mass: float
    misclassified_states: List[Tuple[int, int, int, float]]
    provenance: str = ""

    def score(self, iL: int, itox: int, ivth: int) -> int:
        """Integer score S for bin indices iL, itox, ivth."""
        return self.C0 + self.C_L[iL] + self.C_tox[itox] + self.C_vth[ivth]

    def is_fail_int(self, iL: int, itox: int, ivth: int) -> bool:
        """Integer failure predicate: S(x) >= T."""
        return self.score(iL, itox, ivth) >= self.T


# ---------------------------------------------------------------------------
# Main quantisation builder
# ---------------------------------------------------------------------------
def build_quantised_score(
    joint: JointDistribution,
    I_limit_A: float,
    op: OperatingPoint,
    device: NominalDevice,
    scale: float = 1000.0,
) -> QuantisedScoreModel:
    """Build the integer score model from the continuous physics model.

    Parameters
    ----------
    joint     : JointDistribution — the discrete variation model
    I_limit_A : leakage limit (A)
    op        : OperatingPoint
    device    : NominalDevice
    scale     : float — multiplier converting float g-values to integers.
                Larger scale = finer resolution but wider accumulator.

    Returns
    -------
    QuantisedScoreModel

    Algorithm
    ---------
    1. For each bin value in each variable, compute the exact (float)
       g evaluated at (delta_val, 0, 0) minus g0, scaled, and rounded.
       This gives integer contributions C_L[i], C_tox[j], C_vth[k].
    2. C0 = round(scale * g0).
    3. T  = ceil(scale * g_threshold).
    4. Enumerate all 64 joint states; compute float g and integer score.
    5. Compare float predicate with integer predicate, record mismatches.
    6. Compute B = max(0, -S_min), accumulator bits from S_max + B.
    """
    # Step 1 & 2: scaled integer contributions per bin
    g0 = _g_nominal(op, device)
    g_threshold = log_failure_threshold(I_limit_A, device)
    C0 = round(scale * g0)

    def _delta_contributions(vals: List[float], axis: str) -> List[int]:
        contribs = []
        for v in vals:
            if axis == "L":
                _, g = compute_leakage(v, 0.0, 0.0, op, device)
            elif axis == "tox":
                _, g = compute_leakage(0.0, v, 0.0, op, device)
            else:  # vth
                _, g = compute_leakage(0.0, 0.0, v, op, device)
            delta_g = g - g0
            contribs.append(round(scale * delta_g))
        return contribs

    C_L = _delta_contributions(joint.var_L.values, "L")
    C_tox = _delta_contributions(joint.var_tox.values, "tox")
    C_vth = _delta_contributions(joint.var_vth.values, "vth")

    # Step 3: integer threshold
    T = math.ceil(scale * g_threshold)

    # Step 4 & 5: enumerate all 64 states
    all_scores_int = []
    misclassified = []

    for iL, (vL, pL) in enumerate(
        zip(joint.var_L.values, joint.var_L.probabilities)
    ):
        for itox, (vtox, ptox) in enumerate(
            zip(joint.var_tox.values, joint.var_tox.probabilities)
        ):
            for ivth, (vvth, pvth) in enumerate(
                zip(joint.var_vth.values, joint.var_vth.probabilities)
            ):
                prob = pL * ptox * pvth

                # Float predicate
                _, g_val = compute_leakage(vL, vtox, vvth, op, device)
                float_fail = g_val >= g_threshold

                # Integer predicate
                S_int = C0 + C_L[iL] + C_tox[itox] + C_vth[ivth]
                int_fail = S_int >= T

                all_scores_int.append(S_int)

                if float_fail != int_fail:
                    misclassified.append((iL, itox, ivth, prob))

    S_min = min(all_scores_int)
    S_max = max(all_scores_int)
    B = max(0, -S_min)

    acc_val = S_max + B + 1
    accumulator_bits = max(1, math.ceil(math.log2(acc_val)) if acc_val > 1 else 1)

    q_err_mass = sum(p for *_, p in misclassified)

    provenance = (
        f"Separable log-current quantisation (exact per-axis contributions). scale={scale}. "
        f"g0={g0:.6f}, g_threshold={g_threshold:.6f}. "
        f"C0={C0}, T={T}. "
        f"S_min={S_min}, S_max={S_max}, B={B}, bits={accumulator_bits}. "
        f"Misclassified states: {len(misclassified)}, "
        f"total misclassification mass: {q_err_mass:.4e}."
    )

    return QuantisedScoreModel(
        scale=scale,
        C0=C0,
        C_L=C_L,
        C_tox=C_tox,
        C_vth=C_vth,
        T=T,
        B=B,
        accumulator_bits=accumulator_bits,
        S_min=S_min,
        S_max=S_max,
        float_g_threshold=g_threshold,
        quantisation_error_mass=q_err_mass,
        misclassified_states=misclassified,
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# Scale sweep utility
# ---------------------------------------------------------------------------
def sweep_scales(
    joint: JointDistribution,
    I_limit_A: float,
    op: OperatingPoint,
    device: NominalDevice,
    scales: Optional[List[float]] = None,
) -> List[Dict]:
    """Sweep quantisation scales and report the accuracy/width trade-off.

    Returns
    -------
    List of dicts with keys:
        scale, accumulator_bits, n_misclassified, misclassification_mass
    """
    if scales is None:
        scales = [100.0, 500.0, 1000.0, 2000.0, 5000.0]
    results = []
    for s in scales:
        m = build_quantised_score(joint, I_limit_A, op, device, scale=s)
        results.append(
            {
                "scale": s,
                "accumulator_bits": m.accumulator_bits,
                "n_misclassified": len(m.misclassified_states),
                "misclassification_mass": m.quantisation_error_mass,
            }
        )
    return results
