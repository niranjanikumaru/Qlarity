"""
monte_carlo.py — Ordinary Monte Carlo estimator.

Specification reference: §7.

Samples from exactly the same discrete distribution and uses exactly the
same integer failure predicate as IQAE, enabling a like-for-like comparison
of query efficiency.

Statistical reporting:
    - Point estimate: sample mean of the failure indicator.
    - Binomial confidence interval (Clopper-Pearson exact).
    - Elapsed time, samples drawn, failures observed, seed.

Convergence diagnostics:
    - Running estimate trajectory (optional).
    - Relative and absolute error vs. the exact reference.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from scipy import stats

from ..physics.leakage import NominalDevice, OperatingPoint
from ..physics.variations import JointDistribution


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class MonteCarloResult:
    """Result from ordinary Monte Carlo estimation.

    Attributes
    ----------
    p_fail_estimate     : point estimate of failure probability
    yield_estimate      : 1 - p_fail_estimate
    ci_lower, ci_upper  : Clopper-Pearson 100*(1-alpha)% confidence interval
    ci_alpha            : significance level used (e.g. 0.05 for 95% CI)
    n_samples           : total samples drawn
    n_failures          : number of failures observed
    elapsed_s           : wall-clock time
    seed                : RNG seed used
    trajectory          : list of (n, p_estimate) checkpoints (optional)
    error_vs_exact      : |estimate - exact| if exact supplied, else None
    relative_error      : |estimate - exact| / exact if exact > 0, else None
    """
    p_fail_estimate: float
    yield_estimate: float
    ci_lower: float
    ci_upper: float
    ci_alpha: float
    n_samples: int
    n_failures: int
    elapsed_s: float
    seed: int
    trajectory: List[Tuple[int, float]] = field(default_factory=list)
    error_vs_exact: Optional[float] = None
    relative_error: Optional[float] = None

    def summary(self) -> str:
        ci_pct = int(round((1 - self.ci_alpha) * 100))
        return (
            f"[monte_carlo] "
            f"p_fail={self.p_fail_estimate:.4e}  "
            f"{ci_pct}%CI=[{self.ci_lower:.4e}, {self.ci_upper:.4e}]  "
            f"n={self.n_samples}  failures={self.n_failures}  "
            f"t={self.elapsed_s*1e3:.1f}ms"
        )


# ---------------------------------------------------------------------------
# Clopper-Pearson exact confidence interval
# ---------------------------------------------------------------------------
def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> Tuple[float, float]:
    """Exact Clopper-Pearson binomial confidence interval.

    Parameters
    ----------
    k     : number of successes (failures observed)
    n     : total trials
    alpha : significance level (CI = 100*(1-alpha)%)

    Returns
    -------
    (lower, upper) confidence interval for the true proportion p.

    Notes
    -----
    - k=0: lower bound is 0.
    - k=n: upper bound is 1.
    - Based on the Beta distribution quantiles.
    """
    if n == 0:
        return 0.0, 1.0
    lower = 0.0 if k == 0 else float(stats.beta.ppf(alpha / 2, k, n - k + 1))
    upper = 1.0 if k == n else float(stats.beta.ppf(1 - alpha / 2, k + 1, n - k))
    return lower, upper


# ---------------------------------------------------------------------------
# Sampler from the discrete joint distribution
# ---------------------------------------------------------------------------
def _build_joint_pmf(joint: JointDistribution):
    """Build flat arrays for efficient vectorised sampling.

    Returns
    -------
    states : list of (iL, itox, ivth) — bin index tuples
    probs  : 1-D array of joint probabilities
    values : list of (delta_L_nm, delta_tox_nm, delta_vth_mV) per state
    """
    states = []
    probs = []
    values = []
    for iL, (vL, pL) in enumerate(zip(joint.var_L.values, joint.var_L.probabilities)):
        for itox, (vtox, ptox) in enumerate(
            zip(joint.var_tox.values, joint.var_tox.probabilities)
        ):
            for ivth, (vvth, pvth) in enumerate(
                zip(joint.var_vth.values, joint.var_vth.probabilities)
            ):
                states.append((iL, itox, ivth))
                probs.append(pL * ptox * pvth)
                values.append((vL, vtox, vvth))
    probs = np.array(probs, dtype=float)
    probs /= probs.sum()  # renormalise for floating-point safety
    return states, probs, values


# ---------------------------------------------------------------------------
# Main MC estimator
# ---------------------------------------------------------------------------
def run_monte_carlo(
    joint: JointDistribution,
    I_limit_A: float,
    op: OperatingPoint,
    device: NominalDevice,
    n_samples: int = 10_000,
    seed: int = 42,
    alpha: float = 0.05,
    record_trajectory_every: int = 500,
    exact_p_fail: Optional[float] = None,
    use_integer_predicate: bool = False,
    qmodel=None,
) -> MonteCarloResult:
    """Ordinary Monte Carlo failure probability estimator.

    Uses the same discrete distribution and float failure predicate.

    Parameters
    ----------
    joint              : JointDistribution
    I_limit_A          : leakage specification limit (A)
    op, device         : operating point and device
    n_samples          : total samples to draw
    seed               : RNG seed
    alpha              : CI significance level
    record_trajectory_every: record running estimate every N samples
    exact_p_fail       : optional exact reference for error reporting
    use_integer_predicate: use explicitly supplied qmodel when True

    Returns
    -------
    MonteCarloResult
    """
    from ..physics.leakage import is_failure_vectorized

    states, probs, values = _build_joint_pmf(joint)
    n_states_total = len(states)

    rng = np.random.default_rng(seed)
    t0 = time.perf_counter()

    indices = rng.choice(n_states_total, size=n_samples, replace=True, p=probs)
    sampled_values = np.array([values[i] for i in indices])

    dL   = sampled_values[:, 0]
    dtox = sampled_values[:, 1]
    dvth = sampled_values[:, 2]

    if use_integer_predicate:
        if qmodel is None:
            raise ValueError("Integer sampling requires the explicit shared quantised model")
        fail_flags = np.array([qmodel.is_fail_int(*states[i]) for i in indices], dtype=int)
    else:
        fail_flags = is_failure_vectorized(dL, dtox, dvth, I_limit_A, op, device).astype(int)

    trajectory: List[Tuple[int, float]] = []
    for cp in range(record_trajectory_every, n_samples + 1, record_trajectory_every):
        trajectory.append((cp, float(fail_flags[:cp].mean())))

    elapsed = time.perf_counter() - t0

    n_failures = int(fail_flags.sum())
    p_estimate = float(fail_flags.mean())
    ci_lo, ci_hi = clopper_pearson(n_failures, n_samples, alpha)

    err = abs(p_estimate - exact_p_fail) if exact_p_fail is not None else None
    rel_err = (err / exact_p_fail) if (err is not None and exact_p_fail > 0) else None

    return MonteCarloResult(
        p_fail_estimate=p_estimate,
        yield_estimate=1.0 - p_estimate,
        ci_lower=ci_lo,
        ci_upper=ci_hi,
        ci_alpha=alpha,
        n_samples=n_samples,
        n_failures=n_failures,
        elapsed_s=elapsed,
        seed=seed,
        trajectory=trajectory,
        error_vs_exact=err,
        relative_error=rel_err,
    )


# ---------------------------------------------------------------------------
# Convenience: run multiple seeds for coverage analysis
# ---------------------------------------------------------------------------
def run_mc_multi_seed(
    joint: JointDistribution,
    I_limit_A: float,
    op: OperatingPoint,
    device: NominalDevice,
    n_samples: int = 10_000,
    seeds: List[int] = None,
    alpha: float = 0.05,
    exact_p_fail: Optional[float] = None,
) -> List[MonteCarloResult]:
    """Run MC over multiple seeds for interval coverage assessment."""
    if seeds is None:
        seeds = list(range(10))
    return [
        run_monte_carlo(
            joint, I_limit_A, op, device,
            n_samples=n_samples, seed=s, alpha=alpha,
            exact_p_fail=exact_p_fail,
        )
        for s in seeds
    ]


def coverage_fraction(results: List[MonteCarloResult], exact_p_fail: float) -> float:
    """Fraction of runs whose CI contains the exact value."""
    covered = sum(
        1 for r in results if r.ci_lower <= exact_p_fail <= r.ci_upper
    )
    return covered / len(results) if results else float("nan")
