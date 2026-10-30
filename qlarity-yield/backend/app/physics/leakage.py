"""
leakage.py — MOSFET off-state leakage model.

Model family: Illustrative compact sub-threshold leakage expression.
Source / provenance:
    The functional form is adapted from the widely cited bulk-CMOS
    sub-threshold leakage formula described in:
        Taur & Ning, "Fundamentals of Modern VLSI Devices", 2nd ed.
        Cambridge University Press, 2009. §3.2
    and the BSIM4 compact model reference manual (public documentation):
        https://bsim.berkeley.edu/models/bsim4/
    Coefficient values below are ILLUSTRATIVE for educational use.
    They are NOT foundry-calibrated.  Label them as such in any output.

Physics:
    For a long-channel n-MOSFET biased below threshold (Vgs < Vth):

        I_off(x) = I0 * (W/L(x)) * exp(-(Vth(x) - Vgs) / (n * Vt))

    where:
        I0    — pre-exponential current scale (technology constant), A/um
        W     — effective channel width, um
        L(x)  — effective gate length, um  (varies with process)
        Vth(x)— effective threshold voltage, V
        Vgs   — gate-to-source voltage at operating point (= 0 V off-state)
        n     — sub-threshold slope factor (1 < n < 2, dimensionless)
        Vt    — thermal voltage kT/q approx 0.02585 V at 300 K

    Vth depends on gate length and oxide thickness through:
        Vth(x) = Vth0 + alpha_L * (L(x) - L0) + alpha_tox * (tox(x) - tox0)
                 + delta_vth   (residual offset)

    We work in log-current space:
        g(x) = ln(I_off(x) / I_ref)

    Failure condition (equality => fail, per spec §5):
        I_off(x) >= I_limit

Units:
    Gate length   L    : nm
    Oxide thickness tox: nm
    Threshold offset   : mV
    Leakage current    : A
    Voltages           : V
    Temperature        : K
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
_K_BOLTZMANN = 1.380649e-23  # J/K
_Q_ELECTRON = 1.602176634e-19  # C


def thermal_voltage(temperature_K: float) -> float:
    """Thermal voltage Vt = kT/q in volts."""
    return _K_BOLTZMANN * temperature_K / _Q_ELECTRON


# ---------------------------------------------------------------------------
# Nominal operating point and model parameters
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OperatingPoint:
    """Fixed electrical and thermal operating conditions."""
    Vds: float = 1.0            # Drain-source voltage, V (off-state: Vds = Vdd)
    Vgs: float = 0.0            # Gate-source voltage, V  (off-state: Vgs = 0)
    Vbs: float = 0.0            # Bulk-source voltage, V
    temperature_K: float = 300.0  # Absolute temperature, K
    W_um: float = 1.0           # Channel width, um


@dataclass(frozen=True)
class NominalDevice:
    """Nominal (process-center) device geometry and electrical parameters.

    Provenance: illustrative bulk n-MOSFET, 65 nm node class.
    NOT calibrated to a specific foundry PDK.

    Coefficients:
        I0_A_per_um  — pre-exponential leakage per unit width (A/um).
                       Illustrative scale, not fitted to measurements.
        n_ideality   — sub-threshold ideality factor.
        Vth0         — nominal threshold voltage at L0, tox0, delta_vth=0 (V).
        L0_nm        — nominal effective gate length (nm).
        tox0_nm      — nominal gate oxide thickness (nm).
        alpha_L      — dVth/dL (V/nm): longer gate => slightly higher Vth.
                       Illustrative: +1.5 mV/nm.
        alpha_tox    — dVth/dtox (V/nm): thicker oxide => higher Vth.
                       Illustrative: +8 mV/nm.
        I_ref_A      — reference current for log ratio (1 nA).
    """
    L0_nm: float = 65.0
    tox0_nm: float = 1.8
    Vth0_V: float = 0.35
    I0_A_per_um: float = 1.0e-7
    n_ideality: float = 1.4
    alpha_L_V_per_nm: float = 1.5e-3
    alpha_tox_V_per_nm: float = 8.0e-3
    I_ref_A: float = 1.0e-9


# ---------------------------------------------------------------------------
# Scalar computation
# ---------------------------------------------------------------------------
def compute_leakage(
    delta_L_nm: float,
    delta_tox_nm: float,
    delta_vth_mV: float,
    op: OperatingPoint,
    device: NominalDevice,
) -> Tuple[float, float]:
    """Compute off-state leakage current and log-current ratio.

    Parameters
    ----------
    delta_L_nm    : deviation from nominal gate length  (nm)
    delta_tox_nm  : deviation from nominal oxide thickness  (nm)
    delta_vth_mV  : residual threshold-voltage offset  (mV)
                    Independent of delta_L and delta_tox in first-release model.
    op            : OperatingPoint (fixed)
    device        : NominalDevice parameters

    Returns
    -------
    I_off_A : float  — off-state leakage current in amperes
    g       : float  — log-ratio  ln(I_off / I_ref)

    Raises
    ------
    ValueError if geometry becomes non-positive.
    """
    L_eff_nm = device.L0_nm + delta_L_nm
    if L_eff_nm <= 0.0:
        raise ValueError(
            f"Effective gate length must be positive; got {L_eff_nm:.3f} nm."
        )
    L_eff_um = L_eff_nm * 1e-3

    tox_eff_nm = device.tox0_nm + delta_tox_nm
    if tox_eff_nm <= 0.0:
        raise ValueError(
            f"Effective oxide thickness must be positive; got {tox_eff_nm:.3f} nm."
        )

    Vth_V = (
        device.Vth0_V
        + device.alpha_L_V_per_nm * delta_L_nm
        + device.alpha_tox_V_per_nm * delta_tox_nm
        + delta_vth_mV * 1e-3
    )

    Vt = thermal_voltage(op.temperature_K)
    exponent = -(Vth_V - op.Vgs) / (device.n_ideality * Vt)
    I_off_A = device.I0_A_per_um * (op.W_um / L_eff_um) * math.exp(exponent)
    g = math.log(I_off_A / device.I_ref_A)

    return I_off_A, g


def is_failure(
    delta_L_nm: float,
    delta_tox_nm: float,
    delta_vth_mV: float,
    I_limit_A: float,
    op: OperatingPoint,
    device: NominalDevice,
) -> bool:
    """Return True iff I_off >= I_limit (equality => fail per spec §5)."""
    I_off_A, _ = compute_leakage(delta_L_nm, delta_tox_nm, delta_vth_mV, op, device)
    return I_off_A >= I_limit_A


def log_failure_threshold(I_limit_A: float, device: NominalDevice) -> float:
    """Return ln(I_limit / I_ref) — the failure boundary in log-ratio space."""
    return math.log(I_limit_A / device.I_ref_A)


# ---------------------------------------------------------------------------
# Vectorised NumPy interface
# ---------------------------------------------------------------------------
def compute_leakage_vectorized(
    delta_L_nm: np.ndarray,
    delta_tox_nm: np.ndarray,
    delta_vth_mV: np.ndarray,
    op: OperatingPoint,
    device: NominalDevice,
) -> Tuple[np.ndarray, np.ndarray]:
    """Vectorised leakage computation over arrays of variation inputs.

    Parameters
    ----------
    delta_L_nm, delta_tox_nm, delta_vth_mV : arrays of the same shape

    Returns
    -------
    I_off_A : ndarray  — leakage currents (A)
    g       : ndarray  — log-ratios ln(I_off / I_ref)
    """
    dL = np.asarray(delta_L_nm, dtype=float)
    dtox = np.asarray(delta_tox_nm, dtype=float)
    dvth = np.asarray(delta_vth_mV, dtype=float)

    L_eff_nm = device.L0_nm + dL
    if np.any(L_eff_nm <= 0.0):
        raise ValueError("One or more effective gate lengths are non-positive.")

    tox_eff_nm = device.tox0_nm + dtox
    if np.any(tox_eff_nm <= 0.0):
        raise ValueError("One or more effective oxide thicknesses are non-positive.")

    L_eff_um = L_eff_nm * 1e-3
    Vth_V = (
        device.Vth0_V
        + device.alpha_L_V_per_nm * dL
        + device.alpha_tox_V_per_nm * dtox
        + dvth * 1e-3
    )

    Vt = thermal_voltage(op.temperature_K)
    exponent = -(Vth_V - op.Vgs) / (device.n_ideality * Vt)
    I_off_A = device.I0_A_per_um * (op.W_um / L_eff_um) * np.exp(exponent)
    g = np.log(I_off_A / device.I_ref_A)

    return I_off_A, g


def is_failure_vectorized(
    delta_L_nm: np.ndarray,
    delta_tox_nm: np.ndarray,
    delta_vth_mV: np.ndarray,
    I_limit_A: float,
    op: OperatingPoint,
    device: NominalDevice,
) -> np.ndarray:
    """Vectorised failure predicate. Returns boolean array."""
    I_off_A, _ = compute_leakage_vectorized(
        delta_L_nm, delta_tox_nm, delta_vth_mV, op, device
    )
    return I_off_A >= I_limit_A
