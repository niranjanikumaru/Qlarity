"""
iqae.py  — IQAE wrapper, resource accounting, and comparison utilities.

Specification reference: §11 (Connect IQAE), §12 (accuracy & confidence),
§13 (resource accounting).

This module:
    1. Wraps the verified A circuit into an EstimationProblem.
    2. Runs IterativeAmplitudeEstimation using StatevectorSampler.
    3. Converts the returned amplitude interval to a failure-probability
       interval and a yield interval.
    4. Records every resource-accounting field required by §13.
    5. Provides a multi-run comparison utility for classical vs quantum.

IQAE interface (qiskit-algorithms 0.4.0, Qiskit 2.x):
    EstimationProblem(state_preparation, objective_qubits, ...)
    IterativeAmplitudeEstimation(epsilon_target, alpha, sampler=sampler)
    sampler = StatevectorSampler(default_shots=..., seed=...)

Note on the confidence parameter alpha:
    alpha is the *allowed failure probability* of the confidence-interval
    guarantee under the algorithm's statistical model.  alpha=0.05 gives a
    nominal 95% CI.  This does NOT include model error, quantisation error,
    or surrogate approximation error.

Note on epsilon_target:
    Absolute error on failure probability p, NOT on sqrt(p).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from qiskit.primitives import StatevectorSampler
from qiskit import transpile, qasm3
from qiskit_algorithms import EstimationProblem, IterativeAmplitudeEstimation
from qiskit_algorithms import IterativeAmplitudeEstimationResult

from ..physics.discretize import QuantisedScoreModel
from ..physics.variations import JointDistribution
from .oracle import OracleResult, build_oracle, build_grover_operator, validate_grover_power_identity
from .state_preparation import build_state_preparation


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class IQAERunResult:
    """Complete result from one IQAE run.

    Attributes
    ----------
    p_fail_estimate     : estimated failure probability (amplitude^2)
    yield_estimate      : 1 - p_fail_estimate
    p_fail_ci_lower     : lower bound of the failure probability CI
    p_fail_ci_upper     : upper bound of the failure probability CI
    yield_ci_lower      : 1 - p_fail_ci_upper
    yield_ci_upper      : 1 - p_fail_ci_lower
    amplitude_estimate  : raw amplitude estimate (sqrt of p_fail)
    amplitude_ci        : (lower, upper) amplitude CI derived from the IQAE probability interval
    epsilon_target      : absolute probability epsilon target passed to IQAE
    alpha               : confidence level parameter (e.g. 0.05 = 95% CI)
    confint_method      : CI method used (e.g. 'beta')

    Resource accounting (§13):
    powers              : list of amplification powers k used
    shots_per_circuit   : list of shots at each power
    num_oracle_queries  : library-reported Grover iteration count (k per shot)
    NA_our_count        : our own count: sum_k shots_k * (2k+1)
    n_total_qubits      : circuit width (input + flag + accumulator)
    circuit_depth_raw   : depth of A circuit before transpilation
    n_acc_qubits        : accumulator bit-width
    elapsed_s           : wall-clock time for IQAE run
    seed                : RNG seed used
    backend             : description of backend (e.g. 'StatevectorSampler')
    exact_p_fail        : reference value if provided (for error reporting)
    error_vs_exact      : |estimate - exact| if exact provided
    interval_contains_exact : bool — whether CI contains exact value

    Grover validation:
    grover_power_notes  : list of PASS/FAIL strings from power identity test
    """
    p_fail_estimate: float
    yield_estimate: float
    p_fail_ci_lower: float
    p_fail_ci_upper: float
    yield_ci_lower: float
    yield_ci_upper: float
    amplitude_estimate: float
    amplitude_ci: Tuple[float, float]
    epsilon_target: float
    alpha: float
    confint_method: str
    powers: List[int]
    shots_per_circuit: List[int]
    num_oracle_queries: int
    NA_our_count: int
    n_total_qubits: int
    circuit_depth_raw: int
    n_acc_qubits: int
    elapsed_s: float
    seed: int
    backend: str
    exact_p_fail: Optional[float] = None
    error_vs_exact: Optional[float] = None
    interval_contains_exact: Optional[bool] = None
    grover_power_notes: List[str] = field(default_factory=list)
    executed_rounds: List[dict] = field(default_factory=list)
    resources: dict = field(default_factory=dict)
    circuits: dict = field(default_factory=dict)

    def summary(self) -> str:
        ci_pct = int(round((1.0 - self.alpha) * 100))
        return (
            f"[IQAE] "
            f"p_fail={self.p_fail_estimate:.4e}  "
            f"{ci_pct}%CI=[{self.p_fail_ci_lower:.4e}, {self.p_fail_ci_upper:.4e}]  "
            f"yield={self.yield_estimate:.6f}  "
            f"NA={self.NA_our_count}  "
            f"qubits={self.n_total_qubits}  "
            f"t={self.elapsed_s:.2f}s"
        )


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run_iqae(
    oracle_result: OracleResult,
    epsilon_target: float = 0.02,
    alpha: float = 0.05,
    default_shots: int = 1024,
    seed: int = 42,
    confint_method: str = "beta",
    exact_p_fail: Optional[float] = None,
    run_grover_validation: bool = False,
    grover_max_k: int = 3,
) -> IQAERunResult:
    """Run IQAE on the verified oracle and return full results.

    Parameters
    ----------
    oracle_result       : OracleResult from build_oracle()
    epsilon_target      : absolute failure-probability error target.
                          epsilon=0.02 is a debugging setting; use smaller
                          values for production (e.g. 0.005 for ~1% in prob).
    alpha               : confidence level (0.05 -> 95% nominal CI).
    default_shots       : shots per circuit in the sampler.
    seed                : RNG seed for the sampler.
    confint_method      : 'beta' (default) or 'chernoff'.
    exact_p_fail        : optional exact reference for error and coverage check.
    run_grover_validation: if True, verify Grover-power identity before IQAE.
    grover_max_k        : maximum k for Grover validation.

    Returns
    -------
    IQAERunResult
    """
    A = oracle_result.A_circuit
    obj_qubit = oracle_result.objective_qubit

    # --- Grover validation (§11) ---
    grover_notes: List[str] = []
    if run_grover_validation and exact_p_fail is not None:
        grover_notes = validate_grover_power_identity(
            oracle_result, exact_p_fail, max_k=grover_max_k
        )

    # --- Set up IQAE ---
    captured = []
    class RecordingSampler(StatevectorSampler):
        def run(self, pubs, *, shots=None):
            pubs = list(pubs)
            job = super().run(pubs, shots=shots)
            measured = job.result()
            for pub, item in zip(pubs, measured):
                circuit = pub if hasattr(pub, 'num_qubits') else pub[0]
                counts = next(iter(item.data.values())).get_counts()
                captured.append((circuit, counts))
            class Completed:
                def result(self): return measured
            return Completed()
    sampler = RecordingSampler(default_shots=default_shots, seed=np.random.default_rng(seed))

    problem = EstimationProblem(
        state_preparation=A,
        objective_qubits=[obj_qubit],
    )

    iqae = IterativeAmplitudeEstimation(
        epsilon_target=epsilon_target,
        alpha=alpha,
        confint_method=confint_method,
        sampler=sampler,
    )

    # --- Run ---
    t0 = time.perf_counter()
    result: IterativeAmplitudeEstimationResult = iqae.estimate(problem)
    elapsed = time.perf_counter() - t0

    # --- Extract raw IQAE outputs ---
    amp_est: float = float(result.estimation)             # probability estimate (post-processed)
    amp_ci = result.confidence_interval                   # probability CI
    # Qiskit 0.4 begins with an unexecuted bookkeeping k=0.
    powers = list(result.powers)[1:]
    if len(powers) != len(captured):
        raise RuntimeError("IQAE executed-round ledger disagrees with algorithm history")
    shots_list = [sum(counts.values()) for _,counts in captured]
    num_oracle_queries: int = int(result.num_oracle_queries)

    # --- Probability estimate and CI ---
    # result.estimation and confidence_interval are already in probability space
    p_fail_est = float(np.clip(amp_est, 0.0, 1.0))
    p_ci = result.confidence_interval
    p_ci_lo = float(np.clip(p_ci[0], 0.0, 1.0))
    p_ci_hi = float(np.clip(p_ci[1], 0.0, 1.0))

    # Amplitude (sqrt(p)) for reporting
    amplitude_est = math.sqrt(max(p_fail_est, 0.0))
    amp_ci_lo = math.sqrt(max(p_ci_lo, 0.0))
    amp_ci_hi = math.sqrt(max(p_ci_hi, 0.0))

    # Yield
    yield_est  = 1.0 - p_fail_est
    yield_lo   = 1.0 - p_ci_hi
    yield_hi   = 1.0 - p_ci_lo

    # --- Our own query count (§13) ---
    # NA = sum_k shots_k * (2k + 1)
    # The powers list gives the k values used.
    NA = sum(s * (2 * k + 1) for k, s in zip(powers, shots_list))

    # --- Circuit metrics ---
    n_total = A.num_qubits
    try:
        depth_raw = A.depth()
    except Exception:
        depth_raw = -1

    # --- Error vs exact ---
    err = abs(p_fail_est - exact_p_fail) if exact_p_fail is not None else None
    contains = (
        p_ci_lo <= exact_p_fail <= p_ci_hi
        if exact_p_fail is not None else None
    )

    compiled_at = time.perf_counter()
    basis = ['cx', 'rz', 'sx', 'x']
    def metrics(circuit):
        compiled = transpile(circuit, basis_gates=basis, optimization_level=1, seed_transpiler=seed)
        return compiled, dict(qubits=compiled.num_qubits, depth=compiled.depth(),
            two_qubit_gates=sum(i.operation.num_qubits==2 for i in compiled.data))
    _, a_metrics = metrics(A)
    _, prep_metrics = metrics(A.data[0].operation.definition)
    intervals = list(result.estimate_intervals)[1:]
    ledger=[]; exported={}
    for n, ((circuit, counts),k,shots) in enumerate(zip(captured,powers,shots_list)):
        compiled, costs=metrics(circuit)
        cid=f'round_{n+1}_k{k}'
        exported[cid]=qasm3.dumps(compiled)
        ledger.append(dict(circuit_id=cid,k=int(k),shots=shots,counts=counts,
            probability_interval=[float(x) for x in intervals[n]],
            A_calls=shots*(int(k)+1),A_inverse_calls=shots*int(k),
            predicate_calls=shots*(2*int(k)+1),seed=seed,**costs))
    compiled_a, _=metrics(A)
    exported['A']=qasm3.dumps(compiled_a)
    resources=dict(A=a_metrics,state_preparation=prep_metrics,basis_gates=basis,optimization_level=1,
        hardware_connectivity='All-to-all abstract basis; no physical-device routing',
        compilation_s=time.perf_counter()-compiled_at,total_shots=sum(shots_list),
        total_two_qubit_gate_executions=sum(x['shots']*x['two_qubit_gates'] for x in ledger),
        max_executed_depth=max((x['depth'] for x in ledger),default=0),
        state_preparation_note='Included inside every A/A-inverse; not a free oracle',
        query_convention='A and A-inverse each contain one failure predicate; sum shots*(2k+1)',
        library_query_convention='sum shots*k Grover iterations, excluding initial A')

    return IQAERunResult(
        p_fail_estimate=p_fail_est,
        yield_estimate=yield_est,
        p_fail_ci_lower=p_ci_lo,
        p_fail_ci_upper=p_ci_hi,
        yield_ci_lower=yield_lo,
        yield_ci_upper=yield_hi,
        amplitude_estimate=amplitude_est,
        amplitude_ci=(amp_ci_lo, amp_ci_hi),
        epsilon_target=epsilon_target,
        alpha=alpha,
        confint_method=confint_method,
        powers=powers,
        shots_per_circuit=shots_list,
        num_oracle_queries=num_oracle_queries,
        NA_our_count=NA,
        n_total_qubits=n_total,
        circuit_depth_raw=depth_raw,
        n_acc_qubits=oracle_result.n_acc_qubits,
        elapsed_s=elapsed,
        seed=seed,
        backend="StatevectorSampler (ideal, finite-shot)",
        exact_p_fail=exact_p_fail,
        error_vs_exact=err,
        interval_contains_exact=contains,
        grover_power_notes=grover_notes,
        executed_rounds=ledger, resources=resources, circuits=exported,
    )


# ---------------------------------------------------------------------------
# Multi-seed coverage runner
# ---------------------------------------------------------------------------

def run_iqae_multi_seed(
    oracle_result: OracleResult,
    epsilon_target: float = 0.02,
    alpha: float = 0.05,
    default_shots: int = 1024,
    seeds: Optional[List[int]] = None,
    exact_p_fail: Optional[float] = None,
) -> List[IQAERunResult]:
    """Run IQAE over multiple seeds for coverage assessment.

    Note: StatevectorSampler randomness comes from the seed parameter.
    Each run is independent with a different seed.
    """
    if seeds is None:
        seeds = list(range(10))
    results = []
    for s in seeds:
        r = run_iqae(
            oracle_result,
            epsilon_target=epsilon_target,
            alpha=alpha,
            default_shots=default_shots,
            seed=s,
            exact_p_fail=exact_p_fail,
        )
        results.append(r)
    return results


def iqae_coverage_fraction(
    results: List[IQAERunResult],
    exact_p_fail: float,
) -> float:
    """Fraction of IQAE runs whose CI contains the exact value."""
    covered = sum(
        1 for r in results
        if r.p_fail_ci_lower <= exact_p_fail <= r.p_fail_ci_upper
    )
    return covered / len(results) if results else float("nan")


# ---------------------------------------------------------------------------
# Classical vs quantum comparison (§13)
# ---------------------------------------------------------------------------

@dataclass
class MethodComparison:
    """Side-by-side comparison of IQAE vs classical methods.

    All comparisons use the *same* underlying model and distribution.
    Query counts are oracle-evaluation equivalents (§13: fair comparison).
    """
    p_fail_exact: float
    iqae: IQAERunResult
    mc_result: Optional[object] = None    # MonteCarloResult
    is_result: Optional[object] = None   # ImportanceSamplingResult
    exact_int_result: Optional[object] = None  # ExactResult

    def comparison_table(self) -> List[Dict]:
        """Return list of dicts for each method, suitable for JSON/display."""
        rows = []

        rows.append({
            "method": "Exact (integer)",
            "p_fail": self.exact_int_result.p_fail if self.exact_int_result else None,
            "ci_lower": None,
            "ci_upper": None,
            "oracle_queries": self.exact_int_result.n_states if self.exact_int_result else None,
            "elapsed_s": self.exact_int_result.elapsed_s if self.exact_int_result else None,
            "error_vs_exact": 0.0,
        })

        if self.mc_result:
            err_mc = abs(self.mc_result.p_fail_estimate - self.p_fail_exact)
            rows.append({
                "method": "Monte Carlo",
                "p_fail": self.mc_result.p_fail_estimate,
                "ci_lower": self.mc_result.ci_lower,
                "ci_upper": self.mc_result.ci_upper,
                "oracle_queries": self.mc_result.n_samples,
                "elapsed_s": self.mc_result.elapsed_s,
                "error_vs_exact": err_mc,
            })

        if self.is_result:
            err_is = abs(self.is_result.p_fail_estimate - self.p_fail_exact)
            rows.append({
                "method": "Importance Sampling",
                "p_fail": self.is_result.p_fail_estimate,
                "ci_lower": self.is_result.ci_lower,
                "ci_upper": self.is_result.ci_upper,
                "oracle_queries": self.is_result.n_samples + self.is_result.n_pilot,
                "elapsed_s": self.is_result.elapsed_s,
                "error_vs_exact": err_is,
            })

        err_iqae = self.iqae.error_vs_exact or 0.0
        rows.append({
            "method": "IQAE (quantum)",
            "p_fail": self.iqae.p_fail_estimate,
            "ci_lower": self.iqae.p_fail_ci_lower,
            "ci_upper": self.iqae.p_fail_ci_upper,
            "oracle_queries": self.iqae.NA_our_count,
            "elapsed_s": self.iqae.elapsed_s,
            "error_vs_exact": err_iqae,
        })

        return rows


# ---------------------------------------------------------------------------
# Full end-to-end runner (convenience)
# ---------------------------------------------------------------------------

def run_full_quantum_pipeline(
    joint: JointDistribution,
    qmodel: QuantisedScoreModel,
    epsilon_target: float = 0.02,
    alpha: float = 0.05,
    default_shots: int = 1024,
    seed: int = 42,
    exact_p_fail: Optional[float] = None,
    validate_oracle: bool = True,
    run_grover_validation: bool = True,
) -> Tuple[OracleResult, IQAERunResult]:
    """Build oracle and run IQAE end-to-end.

    Parameters
    ----------
    joint           : JointDistribution
    qmodel          : QuantisedScoreModel
    epsilon_target  : IQAE amplitude epsilon (absolute)
    alpha           : CI significance level
    default_shots   : shots per circuit
    seed            : RNG seed
    exact_p_fail    : reference for validation
    validate_oracle : run exhaustive oracle tests
    run_grover_validation : run Grover-power identity check

    Returns
    -------
    (OracleResult, IQAERunResult)
    """
    oracle_result = build_oracle(joint, qmodel, validate=validate_oracle)

    iqae_result = run_iqae(
        oracle_result,
        epsilon_target=epsilon_target,
        alpha=alpha,
        default_shots=default_shots,
        seed=seed,
        exact_p_fail=exact_p_fail,
        run_grover_validation=run_grover_validation,
        grover_max_k=3,
    )

    return oracle_result, iqae_result
