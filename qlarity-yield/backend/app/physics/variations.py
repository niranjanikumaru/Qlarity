"""
variations.py — Manufacturing variation distributions.

Specification reference: §6 (Specify the manufacturing distribution).

Each variable has exactly 4 representative values and their probability masses,
built from defined bins of a declared distribution.

Variables:
    1. delta_L_nm    — gate-length deviation from nominal   (nm)
    2. delta_tox_nm  — oxide-thickness deviation from nominal (nm)
    3. delta_vth_mV  — residual threshold-voltage offset    (mV)

For the first release the three variables are treated as independent, so the
joint distribution is the Cartesian product:
    p(x1, x2, x3) = p1(x1) * p2(x2) * p3(x3)

Distribution source:
    The discrete distributions are constructed by binning truncated Gaussians.
    For each variable we:
        1. Define a Gaussian N(0, sigma).
        2. Truncate to a ±3-sigma support range.
        3. Divide into 4 equiprobable-mass bins whose representative
           values are the bin conditional means.
        4. Record the *renormalised* probability mass of each bin AND
           the omitted tail mass from truncation.

    The truncated Gaussian is a common model for process variation in
    the absence of proprietary foundry data.  It is documented as the
    distribution model, not a foundry measurement.

Illustrative sigma values (NOT foundry-calibrated):
    sigma_L   = 3.0 nm
    sigma_tox = 0.1 nm
    sigma_vth = 15.0 mV
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np
from scipy import stats


# ---------------------------------------------------------------------------
# Single-variable discrete distribution
# ---------------------------------------------------------------------------
@dataclass
class DiscreteVar:
    """One process-variation variable discretised to n_bins representative values.

    Attributes
    ----------
    name          : human-readable name for display / serialisation
    unit          : physical unit string (e.g. 'nm', 'mV')
    values        : representative values in physical units (length n_bins)
    probabilities : non-negative weights summing to 1.0   (length n_bins)
    sigma         : sigma of the underlying continuous Gaussian (same unit)
    truncation_sigma : truncation point in units of sigma
    omitted_tail_mass: total probability mass discarded by truncation
                       (= 2 * (1 - Phi(truncation_sigma)) for symmetric case)
    distribution_source: free-text provenance description
    """
    name: str
    unit: str
    values: List[float]
    probabilities: List[float]
    sigma: float
    truncation_sigma: float
    omitted_tail_mass: float
    distribution_source: str

    def __post_init__(self) -> None:
        self.values = list(self.values)
        self.probabilities = list(self.probabilities)
        self._validate()

    def _validate(self) -> None:
        if len(self.values) != len(self.probabilities):
            raise ValueError("values and probabilities must have the same length.")
        if any(p < 0.0 for p in self.probabilities):
            raise ValueError(f"[{self.name}] Negative probability detected.")
        total = sum(self.probabilities)
        if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError(
                f"[{self.name}] Probabilities sum to {total:.15f}, not 1.0."
            )

    @property
    def n_bins(self) -> int:
        return len(self.values)

    def expected_value(self) -> float:
        return float(np.dot(self.values, self.probabilities))

    def variance(self) -> float:
        mu = self.expected_value()
        return float(np.dot([(v - mu) ** 2 for v in self.values], self.probabilities))


import math  # kept here so module-level docstring stays at top


# ---------------------------------------------------------------------------
# Builder: truncated-Gaussian bins -> DiscreteVar
# ---------------------------------------------------------------------------
def _bin_conditional_mean(
    lo: float, hi: float, sigma: float
) -> float:
    """Conditional mean of N(0, sigma) truncated to [lo, hi]."""
    # E[X | lo < X < hi] = sigma * (phi(lo/sigma) - phi(hi/sigma)) /
    #                       (Phi(hi/sigma) - Phi(lo/sigma))
    norm = stats.norm(loc=0.0, scale=sigma)
    phi_lo = norm.pdf(lo)
    phi_hi = norm.pdf(hi)
    prob_mass = norm.cdf(hi) - norm.cdf(lo)
    if prob_mass < 1e-300:
        return 0.5 * (lo + hi)  # degenerate bin
    return sigma**2 * (phi_lo - phi_hi) / prob_mass


def build_discrete_var(
    name: str,
    unit: str,
    sigma: float,
    n_bins: int = 4,
    truncation_sigma: float = 3.0,
    distribution_source: str = "Truncated Gaussian, illustrative sigma",
) -> DiscreteVar:
    """Build a DiscreteVar from a truncated-Gaussian by equiprobable binning.

    Parameters
    ----------
    name             : variable name
    unit             : physical unit
    sigma            : standard deviation of the Gaussian (same unit)
    n_bins           : number of discrete levels (default 4 per spec §2)
    truncation_sigma : truncation at ±truncation_sigma * sigma
    distribution_source : provenance string

    Returns
    -------
    DiscreteVar with n_bins values of equal probability 1/n_bins.

    Notes
    -----
    Equiprobable bins: divide the [−3σ, +3σ] range using quantiles of
    the untruncated Gaussian (within the truncated support), then use the
    conditional mean of each bin as the representative value.
    The renormalised probability of each bin is exactly 1/n_bins by
    construction, and the omitted tail mass is reported explicitly.
    """
    norm = stats.norm(loc=0.0, scale=sigma)
    lo_abs = -truncation_sigma * sigma
    hi_abs = +truncation_sigma * sigma

    # Omitted tail mass (both tails combined)
    omitted_tail_mass = 1.0 - (norm.cdf(hi_abs) - norm.cdf(lo_abs))

    # Quantile boundaries within the truncated support
    # Map [lo_abs, hi_abs] to quantile range within the full Gaussian
    p_lo = norm.cdf(lo_abs)
    p_hi = norm.cdf(hi_abs)
    quantiles = np.linspace(p_lo, p_hi, n_bins + 1)
    boundaries = norm.ppf(quantiles)

    # Representative value = conditional mean of each bin
    values = []
    for i in range(n_bins):
        cm = _bin_conditional_mean(boundaries[i], boundaries[i + 1], sigma)
        values.append(float(cm))

    # Equal probability masses (renormalised within truncated support)
    prob = 1.0 / n_bins
    probabilities = [prob] * n_bins

    return DiscreteVar(
        name=name,
        unit=unit,
        values=values,
        probabilities=probabilities,
        sigma=sigma,
        truncation_sigma=truncation_sigma,
        omitted_tail_mass=float(omitted_tail_mass),
        distribution_source=distribution_source,
    )


# ---------------------------------------------------------------------------
# Default scenario distributions (illustrative)
# ---------------------------------------------------------------------------
SIGMA_L_NM = 3.0      # nm
SIGMA_TOX_NM = 0.10   # nm
SIGMA_VTH_MV = 15.0   # mV

_DEFAULT_SOURCE = (
    "Truncated Gaussian N(0, sigma) with ±3-sigma truncation, "
    "4 equiprobable bins, conditional mean as representative value. "
    "Sigma values are ILLUSTRATIVE, NOT foundry-calibrated."
)


def default_delta_L() -> DiscreteVar:
    """Default gate-length variation distribution."""
    return build_discrete_var(
        name="delta_L",
        unit="nm",
        sigma=SIGMA_L_NM,
        distribution_source=_DEFAULT_SOURCE,
    )


def default_delta_tox() -> DiscreteVar:
    """Default oxide-thickness variation distribution."""
    return build_discrete_var(
        name="delta_tox",
        unit="nm",
        sigma=SIGMA_TOX_NM,
        distribution_source=_DEFAULT_SOURCE,
    )


def default_delta_vth() -> DiscreteVar:
    """Default residual threshold-voltage offset distribution."""
    return build_discrete_var(
        name="delta_vth",
        unit="mV",
        sigma=SIGMA_VTH_MV,
        distribution_source=_DEFAULT_SOURCE,
    )


# ---------------------------------------------------------------------------
# Joint independent distribution
# ---------------------------------------------------------------------------
@dataclass
class JointDistribution:
    """Independent joint distribution over three process variables.

    Attributes
    ----------
    var_L   : gate-length deviation distribution
    var_tox : oxide-thickness deviation distribution
    var_vth : threshold-voltage offset distribution
    """
    var_L: DiscreteVar
    var_tox: DiscreteVar
    var_vth: DiscreteVar

    @property
    def n_states(self) -> int:
        """Total number of joint states (Cartesian product)."""
        return self.var_L.n_bins * self.var_tox.n_bins * self.var_vth.n_bins

    def enumerate_states(self) -> List[Tuple[float, float, float, float]]:
        """Enumerate all joint states.

        Returns
        -------
        List of (delta_L_nm, delta_tox_nm, delta_vth_mV, probability) tuples.
        Total probability should be 1.0 (verified by validate()).
        """
        states = []
        for i, (vL, pL) in enumerate(
            zip(self.var_L.values, self.var_L.probabilities)
        ):
            for j, (vtox, ptox) in enumerate(
                zip(self.var_tox.values, self.var_tox.probabilities)
            ):
                for k, (vvth, pvth) in enumerate(
                    zip(self.var_vth.values, self.var_vth.probabilities)
                ):
                    prob = pL * ptox * pvth
                    states.append((vL, vtox, vvth, prob))
        return states

    def validate(self) -> None:
        """Check normalisation, support validity, and consistency."""
        # Each marginal
        for var in (self.var_L, self.var_tox, self.var_vth):
            var._validate()

        # Joint total probability
        total = sum(p for *_, p in self.enumerate_states())
        if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError(f"Joint probability sums to {total:.15f}, not 1.0.")

    def total_omitted_tail_mass(self) -> float:
        """Upper bound on omitted probability mass from all truncations.

        For independent variables the joint omitted mass satisfies:
            1 - prod_i(1 - m_i) <= sum_i m_i   (union-bound upper bound)
        We report the exact complement:
            1 - (1 - m_L)(1 - m_tox)(1 - m_vth)
        """
        retained = (
            (1.0 - self.var_L.omitted_tail_mass)
            * (1.0 - self.var_tox.omitted_tail_mass)
            * (1.0 - self.var_vth.omitted_tail_mass)
        )
        return 1.0 - retained


def default_joint_distribution() -> JointDistribution:
    """Return the default first-release joint distribution."""
    return JointDistribution(
        var_L=default_delta_L(),
        var_tox=default_delta_tox(),
        var_vth=default_delta_vth(),
    )
