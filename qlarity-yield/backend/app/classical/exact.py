"""
exact.py — Exact weighted enumeration of the 64-state discrete grid.

Specification reference: §7 (Build the classical ground truth first).

This module provides three reference calculations on the same discrete model:
    1. Float reference  — floating-point failure predicate g >= g_threshold.
    2. Integer reference — integer predicate S >= T (same arithmetic as oracle).
    3. Continuous Gaussian approximation — analytic integral for comparison.

The exact enumeration is:
    p_fail = sum_x p(x) * failure(x)
    yield  = 1 - p_fail

It is not an estimator. For 64 states it is trivially exact.

Keeping three distinct references (continuous, discrete-float, discrete-int)
separates model error, grid error, and integer arithmetic quantisation.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from scipy import stats

from ..physics.leakage import (
    NominalDevice,
    OperatingPoint,
    compute_leakage,
    log_failure_threshold,
    thermal_voltage,
)
from ..physics.discretize import QuantisedScoreModel
from ..physics.variations import JointDistribution


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class ExactResult:
    """Result from exact weighted enumeration.

    Attributes
    ----------
    method              : 'exact_float' | 'exact_integer' | 'gaussian_approx'
    p_fail              : failure probability (float in [0,1])
    yield_              : manufacturing yield = 1 - p_fail
    n_states            : number of states enumerated
    elapsed_s           : wall-clock time in seconds
    state_table         : list of per-state dicts for inspection
    notes               : any warnings or approximation notes
    """
    method: str
    p_fail: float
    yield_: float
    n_states: int
    elapsed_s: float
    state_table: List[dict]
    notes: List[str]

    def summary(self) -> str:
        return (
            f"[{self.method}] "
            f"p_fail={self.p_fail:.6e}  yield={self.yield_:.6f}  "
            f"n_states={self.n_states}  t={self.elapsed_s*1e3:.2f} ms"
        )


# ---------------------------------------------------------------------------
# Float exact enumeration
# ---------------------------------------------------------------------------
def exact_float(
    joint: JointDistribution,
    I_limit_A: float,
    op: OperatingPoint,
    device: NominalDevice,
) -> ExactResult:
    """Exact weighted enumeration using the floating-point failure predicate.

    failure(x) = 1  iff  I_off(x) >= I_limit  (equality => fail per spec §5)

    Parameters
    ----------
    joint     : JointDistribution
    I_limit_A : leakage limit (A)
    op, device: operating conditions and device parameters

    Returns
    -------
    ExactResult
    """
    t0 = time.perf_counter()
    g_threshold = log_failure_threshold(I_limit_A, device)
    p_fail = 0.0
    state_table = []

    for vL, pL in zip(joint.var_L.values, joint.var_L.probabilities):
        for vtox, ptox in zip(joint.var_tox.values, joint.var_tox.probabilities):
            for vvth, pvth in zip(joint.var_vth.values, joint.var_vth.probabilities):
                prob = pL * ptox * pvth
                I_off, g = compute_leakage(vL, vtox, vvth, op, device)
                fail = g >= g_threshold
                if fail:
                    p_fail += prob
                state_table.append(
                    {
                        "delta_L_nm": vL,
                        "delta_tox_nm": vtox,
                        "delta_vth_mV": vvth,
                        "probability": prob,
                        "I_off_A": I_off,
                        "g": g,
                        "fail": fail,
                    }
                )

    elapsed = time.perf_counter() - t0
    return ExactResult(
        method="exact_float",
        p_fail=p_fail,
        yield_=1.0 - p_fail,
        n_states=len(state_table),
        elapsed_s=elapsed,
        state_table=state_table,
        notes=[
            "Exact enumeration; no statistical error.",
            f"g_threshold = {g_threshold:.6f}",
            f"Omitted tail mass (all vars combined): "
            f"{joint.total_omitted_tail_mass():.4e}",
        ],
    )


# ---------------------------------------------------------------------------
# Integer exact enumeration (same arithmetic as oracle)
# ---------------------------------------------------------------------------
def exact_integer(
    joint: JointDistribution,
    qmodel: QuantisedScoreModel,
) -> ExactResult:
    """Exact enumeration using the integer score model (matches oracle).

    Parameters
    ----------
    joint   : JointDistribution
    qmodel  : QuantisedScoreModel from build_quantised_score()

    Returns
    -------
    ExactResult
    """
    t0 = time.perf_counter()
    p_fail = 0.0
    state_table = []

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
                S = qmodel.score(iL, itox, ivth)
                fail = S >= qmodel.T
                if fail:
                    p_fail += prob
                state_table.append(
                    {
                        "iL": iL,
                        "itox": itox,
                        "ivth": ivth,
                        "delta_L_nm": vL,
                        "delta_tox_nm": vtox,
                        "delta_vth_mV": vvth,
                        "probability": prob,
                        "S_int": S,
                        "T_int": qmodel.T,
                        "fail": fail,
                    }
                )

    elapsed = time.perf_counter() - t0
    return ExactResult(
        method="exact_integer",
        p_fail=p_fail,
        yield_=1.0 - p_fail,
        n_states=len(state_table),
        elapsed_s=elapsed,
        state_table=state_table,
        notes=[
            "Integer arithmetic matches quantum oracle exactly.",
            f"T = {qmodel.T}, B = {qmodel.B}, "
            f"accumulator_bits = {qmodel.accumulator_bits}",
            f"Quantisation misclassification mass: "
            f"{qmodel.quantisation_error_mass:.4e}",
            qmodel.provenance,
        ],
    )


# ---------------------------------------------------------------------------
# Continuous Gaussian approximation
# ---------------------------------------------------------------------------
def gaussian_approximation(
    joint: JointDistribution,
    I_limit_A: float,
    op: OperatingPoint,
    device: NominalDevice,
) -> ExactResult:
    """Analytic failure probability under a Gaussian approximation.

    Linearises g around nominal and propagates the continuous Gaussian
    distributions analytically:
        g ~ N(g0, sigma_g^2)
    where sigma_g^2 = c_L^2 * sigma_L^2 + c_tox^2 * sigma_tox^2 + c_vth^2 * sigma_vth^2

    This is a continuous-distribution result, useful as a sanity check and
    to quantify discretisation error.

    Returns
    -------
    ExactResult (state_table is empty; p_fail from analytic integral)

    Notes
    -----
    - Ignores truncation of the continuous distribution.
    - Valid only for small variations (linearisation assumption).
    - Not the same as the discrete grid model.
    """
    from ..physics.discretize import derive_linear_coefficients

    t0 = time.perf_counter()
    g_threshold = log_failure_threshold(I_limit_A, device)
    coeffs = derive_linear_coefficients(op, device)

    # Continuous sigma of each variable (use the var's stored sigma)
    sigma_g_sq = (
        coeffs["c_L"] ** 2 * joint.var_L.sigma ** 2
        + coeffs["c_tox"] ** 2 * joint.var_tox.sigma ** 2
        + coeffs["c_vth"] ** 2 * joint.var_vth.sigma ** 2
    )
    sigma_g = math.sqrt(sigma_g_sq)
    g0 = coeffs["g0"]

    # p_fail = P(g >= g_threshold) = 1 - Phi((g_threshold - g0) / sigma_g)
    z = (g_threshold - g0) / sigma_g
    p_fail = float(stats.norm.sf(z))  # survival function = 1 - CDF

    elapsed = time.perf_counter() - t0
    return ExactResult(
        method="gaussian_approx",
        p_fail=p_fail,
        yield_=1.0 - p_fail,
        n_states=0,
        elapsed_s=elapsed,
        state_table=[],
        notes=[
            "Continuous Gaussian approximation (analytic integral).",
            f"g0={g0:.6f}, sigma_g={sigma_g:.6f}, z={z:.4f}",
            "Truncation effects not included.",
            "Linearisation valid for small sigma; check against discrete exact.",
        ],
    )


# ---------------------------------------------------------------------------
# Compare all three references
# ---------------------------------------------------------------------------
def compare_references(
    joint: JointDistribution,
    qmodel: QuantisedScoreModel,
    I_limit_A: float,
    op: OperatingPoint,
    device: NominalDevice,
) -> dict:
    """Run all three reference methods and return a comparison dict."""
    ef = exact_float(joint, I_limit_A, op, device)
    ei = exact_integer(joint, qmodel)
    ga = gaussian_approximation(joint, I_limit_A, op, device)

    return {
        "exact_float": {
            "p_fail": ef.p_fail,
            "yield": ef.yield_,
            "elapsed_s": ef.elapsed_s,
        },
        "exact_integer": {
            "p_fail": ei.p_fail,
            "yield": ei.yield_,
            "elapsed_s": ei.elapsed_s,
            "delta_from_float": ei.p_fail - ef.p_fail,
        },
        "gaussian_approx": {
            "p_fail": ga.p_fail,
            "yield": ga.yield_,
            "elapsed_s": ga.elapsed_s,
            "delta_from_float": ga.p_fail - ef.p_fail,
        },
    }
