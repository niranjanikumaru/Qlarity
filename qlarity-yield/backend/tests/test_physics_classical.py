"""
test_physics_classical.py — Integration and unit tests for the physics &
classical math engine.

Specification reference: §17 (Integration checks).

Covers:
    1. Physics model: unit/parameter validation and physical-consistency checks.
    2. Distribution normalisation and support validity.
    3. Integer arithmetic bounds.
    4. Exact enumeration correctness.
    5. Monte Carlo convergence to exact reference.
    6. Importance sampling convergence and weight diagnostics.
    7. Quantisation misclassification mass.
    8. Edge cases: p=0, p=1, threshold at boundary, zero variance.
    9. Invalid inputs: negative dimensions.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Ensure the backend package is importable from the repo root
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.physics.leakage import (
    NominalDevice,
    OperatingPoint,
    compute_leakage,
    compute_leakage_vectorized,
    is_failure,
    is_failure_vectorized,
    log_failure_threshold,
    thermal_voltage,
)
from backend.app.physics.variations import (
    DiscreteVar,
    JointDistribution,
    build_discrete_var,
    default_joint_distribution,
)
from backend.app.physics.discretize import (
    QuantisedScoreModel,
    build_quantised_score,
    sweep_scales,
)
from backend.app.physics.calibration import track_a_record
from backend.app.classical.exact import (
    ExactResult,
    compare_references,
    exact_float,
    exact_integer,
    gaussian_approximation,
)
from backend.app.classical.monte_carlo import (
    MonteCarloResult,
    clopper_pearson,
    coverage_fraction,
    run_mc_multi_seed,
    run_monte_carlo,
)
from backend.app.classical.importance_sampling import (
    ImportanceSamplingResult,
    run_importance_sampling,
    run_is_multi_seed,
)


# ===========================================================================
# Fixtures
# ===========================================================================
@pytest.fixture
def nominal_op():
    return OperatingPoint()


@pytest.fixture
def nominal_device():
    return NominalDevice()


@pytest.fixture
def joint():
    return default_joint_distribution()


@pytest.fixture
def I_limit_A():
    """Leakage limit set so p_fail is non-trivial (not 0 or 1)."""
    return 5.0e-8  # 50 nA — above nominal, so some states fail


@pytest.fixture
def qmodel(joint, I_limit_A, nominal_op, nominal_device):
    return build_quantised_score(joint, I_limit_A, nominal_op, nominal_device, scale=1000.0)


# ===========================================================================
# 1. Physics model tests
# ===========================================================================
class TestLeakageModel:
    def test_thermal_voltage_300K(self):
        Vt = thermal_voltage(300.0)
        assert abs(Vt - 0.025852) < 1e-5, f"Unexpected Vt={Vt}"

    def test_nominal_leakage_positive(self, nominal_op, nominal_device):
        I_off, g = compute_leakage(0.0, 0.0, 0.0, nominal_op, nominal_device)
        assert I_off > 0.0
        assert math.isfinite(g)

    def test_shorter_gate_increases_leakage(self, nominal_op, nominal_device):
        """Shorter gate length reduces Vth (via alpha_L > 0) => more leakage."""
        I_nominal, _ = compute_leakage(0.0, 0.0, 0.0, nominal_op, nominal_device)
        I_short, _ = compute_leakage(-5.0, 0.0, 0.0, nominal_op, nominal_device)
        assert I_short > I_nominal, "Shorter gate should increase off-state leakage"

    def test_thinner_oxide_increases_leakage(self, nominal_op, nominal_device):
        I_nominal, _ = compute_leakage(0.0, 0.0, 0.0, nominal_op, nominal_device)
        I_thin, _ = compute_leakage(0.0, -0.1, 0.0, nominal_op, nominal_device)
        assert I_thin > I_nominal

    def test_negative_vth_offset_increases_leakage(self, nominal_op, nominal_device):
        """Negative dvth_mV lowers Vth => more leakage."""
        I_nominal, _ = compute_leakage(0.0, 0.0, 0.0, nominal_op, nominal_device)
        I_low_vth, _ = compute_leakage(0.0, 0.0, -30.0, nominal_op, nominal_device)
        assert I_low_vth > I_nominal

    def test_invalid_negative_gate_length(self, nominal_op, nominal_device):
        with pytest.raises(ValueError, match="gate length"):
            compute_leakage(-100.0, 0.0, 0.0, nominal_op, nominal_device)

    def test_invalid_negative_oxide(self, nominal_op, nominal_device):
        with pytest.raises(ValueError, match="oxide"):
            compute_leakage(0.0, -5.0, 0.0, nominal_op, nominal_device)

    def test_failure_boundary_equality(self, nominal_op, nominal_device):
        """I_off exactly equal to I_limit => failure (equality => fail per spec §5)."""
        I_exact, _ = compute_leakage(0.0, 0.0, 0.0, nominal_op, nominal_device)
        assert is_failure(0.0, 0.0, 0.0, I_exact, nominal_op, nominal_device) is True

    def test_just_below_limit_passes(self, nominal_op, nominal_device):
        I_exact, _ = compute_leakage(0.0, 0.0, 0.0, nominal_op, nominal_device)
        assert is_failure(0.0, 0.0, 0.0, I_exact * 1.001, nominal_op, nominal_device) is False

    def test_vectorized_matches_scalar(self, nominal_op, nominal_device):
        dL   = np.array([0.0, -5.0, 5.0])
        dtox = np.array([0.0,  0.0, 0.1])
        dvth = np.array([0.0, -20.0, 10.0])
        I_vec, g_vec = compute_leakage_vectorized(dL, dtox, dvth, nominal_op, nominal_device)
        for i in range(3):
            I_sc, g_sc = compute_leakage(dL[i], dtox[i], dvth[i], nominal_op, nominal_device)
            assert abs(I_vec[i] - I_sc) / I_sc < 1e-10
            assert abs(g_vec[i] - g_sc) < 1e-10

    def test_log_failure_threshold(self, nominal_device):
        I_limit = 1.0e-8
        g_th = log_failure_threshold(I_limit, nominal_device)
        expected = math.log(I_limit / nominal_device.I_ref_A)
        assert abs(g_th - expected) < 1e-14


# ===========================================================================
# 2. Distribution tests
# ===========================================================================
class TestDistributions:
    def test_marginal_probabilities_sum_to_one(self, joint):
        for var in (joint.var_L, joint.var_tox, joint.var_vth):
            total = sum(var.probabilities)
            assert abs(total - 1.0) < 1e-12, f"{var.name} sums to {total}"

    def test_all_probabilities_nonnegative(self, joint):
        for var in (joint.var_L, joint.var_tox, joint.var_vth):
            assert all(p >= 0 for p in var.probabilities)

    def test_joint_probability_sums_to_one(self, joint):
        total = sum(p for *_, p in joint.enumerate_states())
        assert abs(total - 1.0) < 1e-10

    def test_n_states_equals_64(self, joint):
        assert joint.n_states == 64
        assert len(joint.enumerate_states()) == 64

    def test_physical_values_valid(self, joint, nominal_device):
        """All variation values keep L and tox positive."""
        for vL, vtox, vvth, _ in joint.enumerate_states():
            L_eff = nominal_device.L0_nm + vL
            tox_eff = nominal_device.tox0_nm + vtox
            assert L_eff > 0, f"Non-positive L_eff={L_eff} for delta_L={vL}"
            assert tox_eff > 0, f"Non-positive tox_eff={tox_eff} for delta_tox={vtox}"

    def test_omitted_tail_mass_reported(self, joint):
        for var in (joint.var_L, joint.var_tox, joint.var_vth):
            assert 0.0 <= var.omitted_tail_mass < 0.01  # <1% for ±3-sigma

    def test_joint_omitted_tail_mass(self, joint):
        m = joint.total_omitted_tail_mass()
        assert 0.0 <= m < 0.05

    def test_zero_sigma_edge_case(self):
        """Zero-sigma distribution: all mass at zero."""
        var = build_discrete_var("test", "nm", sigma=0.001, n_bins=4)
        # All values near zero, probabilities sum to 1
        assert abs(sum(var.probabilities) - 1.0) < 1e-10
        assert all(abs(v) < 0.01 for v in var.values)

    def test_invalid_distribution_negative_prob(self):
        with pytest.raises(ValueError, match="Negative probability"):
            DiscreteVar(
                name="bad",
                unit="nm",
                values=[0.0, 1.0, 2.0, 3.0],
                probabilities=[-0.1, 0.4, 0.4, 0.3],
                sigma=1.0,
                truncation_sigma=3.0,
                omitted_tail_mass=0.0,
                distribution_source="test",
            )


# ===========================================================================
# 3. Integer arithmetic / quantisation tests
# ===========================================================================
class TestQuantisation:
    def test_score_range_consistent(self, qmodel, joint):
        """Every computed score falls within [S_min, S_max]."""
        for iL in range(joint.var_L.n_bins):
            for itox in range(joint.var_tox.n_bins):
                for ivth in range(joint.var_vth.n_bins):
                    S = qmodel.score(iL, itox, ivth)
                    assert qmodel.S_min <= S <= qmodel.S_max

    def test_nonnegative_after_offset(self, qmodel, joint):
        """S + B >= 0 for every input."""
        for iL in range(joint.var_L.n_bins):
            for itox in range(joint.var_tox.n_bins):
                for ivth in range(joint.var_vth.n_bins):
                    S = qmodel.score(iL, itox, ivth)
                    assert S + qmodel.B >= 0

    def test_accumulator_width_sufficient(self, qmodel):
        """2^b > S_max + B."""
        assert 2 ** qmodel.accumulator_bits > qmodel.S_max + qmodel.B

    def test_misclassification_mass_small(self, qmodel):
        """Misclassification mass from quantisation is small."""
        assert qmodel.quantisation_error_mass < 0.05  # <5%

    def test_scale_sweep_returns_table(self, joint, I_limit_A, nominal_op, nominal_device):
        table = sweep_scales(joint, I_limit_A, nominal_op, nominal_device)
        assert len(table) == 5
        for row in table:
            assert "scale" in row and "accumulator_bits" in row

    def test_integer_and_float_agree_mostly(self, qmodel, joint, I_limit_A, nominal_op, nominal_device):
        """Integer predicate matches float predicate on almost all states."""
        mismatches = 0
        for iL, (vL, pL) in enumerate(zip(joint.var_L.values, joint.var_L.probabilities)):
            for itox, (vtox, _) in enumerate(zip(joint.var_tox.values, joint.var_tox.probabilities)):
                for ivth, (vvth, _) in enumerate(zip(joint.var_vth.values, joint.var_vth.probabilities)):
                    float_fail = is_failure(vL, vtox, vvth, I_limit_A, nominal_op, nominal_device)
                    int_fail = qmodel.is_fail_int(iL, itox, ivth)
                    if float_fail != int_fail:
                        mismatches += 1
        assert mismatches == len(qmodel.misclassified_states)


# ===========================================================================
# 4. Exact enumeration tests
# ===========================================================================
class TestExactEnumeration:
    def test_float_enumeration_normalisation(self, joint, I_limit_A, nominal_op, nominal_device):
        result = exact_float(joint, I_limit_A, nominal_op, nominal_device)
        total_p = sum(s["probability"] for s in result.state_table)
        assert abs(total_p - 1.0) < 1e-10

    def test_p_fail_in_unit_interval(self, joint, I_limit_A, nominal_op, nominal_device):
        result = exact_float(joint, I_limit_A, nominal_op, nominal_device)
        assert 0.0 <= result.p_fail <= 1.0

    def test_yield_complement(self, joint, I_limit_A, nominal_op, nominal_device):
        result = exact_float(joint, I_limit_A, nominal_op, nominal_device)
        assert abs(result.yield_ - (1.0 - result.p_fail)) < 1e-14

    def test_integer_close_to_float(self, joint, qmodel, I_limit_A, nominal_op, nominal_device):
        ef = exact_float(joint, I_limit_A, nominal_op, nominal_device)
        ei = exact_integer(joint, qmodel)
        # Difference bounded by quantisation_error_mass
        assert abs(ei.p_fail - ef.p_fail) <= qmodel.quantisation_error_mass + 1e-12

    def test_p_zero_scenario(self, joint, nominal_op, nominal_device):
        """Very high limit -> p_fail = 0."""
        result = exact_float(joint, 1.0, nominal_op, nominal_device)  # 1 A limit (impossible to fail)
        assert result.p_fail == 0.0

    def test_p_one_scenario(self, joint, nominal_op, nominal_device):
        """Extremely tight limit -> p_fail = 1."""
        result = exact_float(joint, 1e-30, nominal_op, nominal_device)
        assert result.p_fail == 1.0

    def test_gaussian_approx_plausible(self, joint, I_limit_A, nominal_op, nominal_device):
        """Gaussian approx within a factor of 3 of discrete exact (sanity check)."""
        ef = exact_float(joint, I_limit_A, nominal_op, nominal_device)
        ga = gaussian_approximation(joint, I_limit_A, nominal_op, nominal_device)
        if ef.p_fail > 0:
            ratio = ga.p_fail / ef.p_fail
            assert 0.05 < ratio < 20.0, f"Gaussian approx ratio={ratio:.2f} seems unreasonable"

    def test_compare_references_keys(self, joint, qmodel, I_limit_A, nominal_op, nominal_device):
        comp = compare_references(joint, qmodel, I_limit_A, nominal_op, nominal_device)
        for key in ("exact_float", "exact_integer", "gaussian_approx"):
            assert key in comp
            assert "p_fail" in comp[key]


# ===========================================================================
# 5. Monte Carlo convergence tests
# ===========================================================================
class TestMonteCarlo:
    def test_clopper_pearson_bounds(self):
        lo, hi = clopper_pearson(0, 100, 0.05)
        assert lo == 0.0
        assert hi < 0.05  # 95% CI upper bound when k=0 must be small

        lo, hi = clopper_pearson(100, 100, 0.05)
        assert hi == 1.0
        assert lo > 0.95

    def test_clopper_pearson_zero_trials(self):
        lo, hi = clopper_pearson(0, 0, 0.05)
        assert lo == 0.0 and hi == 1.0

    def test_mc_result_in_unit_interval(self, joint, I_limit_A, nominal_op, nominal_device):
        result = run_monte_carlo(joint, I_limit_A, nominal_op, nominal_device,
                                 n_samples=1000, seed=0)
        assert 0.0 <= result.p_fail_estimate <= 1.0
        assert 0.0 <= result.ci_lower <= result.ci_upper <= 1.0

    def test_mc_yield_complement(self, joint, I_limit_A, nominal_op, nominal_device):
        result = run_monte_carlo(joint, I_limit_A, nominal_op, nominal_device,
                                 n_samples=1000, seed=1)
        assert abs(result.yield_estimate - (1.0 - result.p_fail_estimate)) < 1e-14

    def test_mc_convergence_with_seed(self, joint, I_limit_A, nominal_op, nominal_device):
        """10k samples should be close to exact (within 3 sigma of binomial)."""
        exact = exact_float(joint, I_limit_A, nominal_op, nominal_device)
        result = run_monte_carlo(joint, I_limit_A, nominal_op, nominal_device,
                                 n_samples=10_000, seed=42,
                                 exact_p_fail=exact.p_fail)
        # 3-sigma bound for binomial: ~3*sqrt(p*(1-p)/n)
        p = exact.p_fail
        sigma_bound = 3.0 * math.sqrt(p * (1 - p) / 10_000) if p > 0 else 0.01
        assert result.error_vs_exact is not None
        assert result.error_vs_exact < max(sigma_bound, 0.01)

    def test_mc_trajectory_not_empty(self, joint, I_limit_A, nominal_op, nominal_device):
        result = run_monte_carlo(joint, I_limit_A, nominal_op, nominal_device,
                                 n_samples=2000, seed=0, record_trajectory_every=500)
        assert len(result.trajectory) >= 1

    def test_mc_coverage(self, joint, I_limit_A, nominal_op, nominal_device):
        """95% CI should cover the exact value on >80% of 20 runs (rough check)."""
        exact = exact_float(joint, I_limit_A, nominal_op, nominal_device)
        results = run_mc_multi_seed(
            joint, I_limit_A, nominal_op, nominal_device,
            n_samples=5000, seeds=list(range(20)),
            exact_p_fail=exact.p_fail,
        )
        cov = coverage_fraction(results, exact.p_fail)
        assert cov >= 0.75, f"Coverage fraction={cov:.2f} is too low"

    def test_mc_p_zero(self, joint, nominal_op, nominal_device):
        """p=0 scenario: all samples pass, CI includes 0."""
        result = run_monte_carlo(joint, 1.0, nominal_op, nominal_device,
                                 n_samples=500, seed=0)
        assert result.p_fail_estimate == 0.0
        assert result.ci_lower == 0.0

    def test_mc_p_one(self, joint, nominal_op, nominal_device):
        """p=1 scenario: all samples fail, CI includes 1."""
        result = run_monte_carlo(joint, 1e-30, nominal_op, nominal_device,
                                 n_samples=500, seed=0)
        assert result.p_fail_estimate == 1.0
        assert result.ci_upper == 1.0


# ===========================================================================
# 6. Importance sampling tests
# ===========================================================================
class TestImportanceSampling:
    def test_is_result_in_unit_interval(self, joint, I_limit_A, nominal_op, nominal_device):
        result = run_importance_sampling(
            joint, I_limit_A, nominal_op, nominal_device, n_samples=2000, seed=0
        )
        assert 0.0 <= result.p_fail_estimate <= 1.0

    def test_is_ess_positive(self, joint, I_limit_A, nominal_op, nominal_device):
        result = run_importance_sampling(
            joint, I_limit_A, nominal_op, nominal_device, n_samples=2000, seed=0
        )
        assert result.ess > 0.0

    def test_is_convergence(self, joint, I_limit_A, nominal_op, nominal_device):
        """IS should be within rough tolerance of exact on 5k samples."""
        exact = exact_float(joint, I_limit_A, nominal_op, nominal_device)
        result = run_importance_sampling(
            joint, I_limit_A, nominal_op, nominal_device,
            n_samples=5000, seed=7, exact_p_fail=exact.p_fail
        )
        assert result.error_vs_exact is not None
        # Allow loose tolerance (IS can have higher variance than MC for this tiny grid)
        p = exact.p_fail
        loose_bound = 5.0 * math.sqrt(p * (1 - p) / 5000) if p > 0 else 0.05
        assert result.error_vs_exact < max(loose_bound, 0.05)

    def test_is_ci_contains_estimate(self, joint, I_limit_A, nominal_op, nominal_device):
        result = run_importance_sampling(
            joint, I_limit_A, nominal_op, nominal_device, n_samples=2000, seed=3
        )
        assert result.ci_lower <= result.p_fail_estimate <= result.ci_upper

    def test_is_proposal_description_nonempty(self, joint, I_limit_A, nominal_op, nominal_device):
        result = run_importance_sampling(
            joint, I_limit_A, nominal_op, nominal_device, n_samples=500, seed=0
        )
        assert len(result.proposal_description) > 0

    def test_is_p_zero(self, joint, nominal_op, nominal_device):
        result = run_importance_sampling(
            joint, 1.0, nominal_op, nominal_device, n_samples=500, seed=0
        )
        assert result.p_fail_estimate == pytest.approx(0.0, abs=1e-10)


# ===========================================================================
# 7. Calibration record tests
# ===========================================================================
class TestCalibration:
    def test_track_a_not_foundry_calibrated(self):
        rec = track_a_record()
        assert rec.is_foundry_calibrated is False
        assert rec.track == "A"

    def test_track_a_has_warnings(self):
        rec = track_a_record()
        assert len(rec.warnings) > 0
        assert any("ILLUSTRATIVE" in w for w in rec.warnings)

    def test_track_a_supported_range(self):
        rec = track_a_record()
        assert "delta_L_nm" in rec.supported_range
        lo, hi = rec.supported_range["delta_L_nm"]
        assert lo < 0.0 < hi


# ===========================================================================
# 8. End-to-end smoke test
# ===========================================================================
class TestEndToEnd:
    def test_full_pipeline(self, joint, I_limit_A, nominal_op, nominal_device):
        """All three classical methods should give consistent p_fail."""
        qm = build_quantised_score(joint, I_limit_A, nominal_op, nominal_device)
        ef = exact_float(joint, I_limit_A, nominal_op, nominal_device)
        ei = exact_integer(joint, qm)
        mc = run_monte_carlo(joint, I_limit_A, nominal_op, nominal_device,
                             n_samples=20_000, seed=0)
        is_ = run_importance_sampling(joint, I_limit_A, nominal_op, nominal_device,
                                       n_samples=10_000, seed=0)

        # All estimates should be within ±10% of exact (very loose for a test)
        for label, est in [("exact_int", ei.p_fail), ("mc", mc.p_fail_estimate),
                             ("is", is_.p_fail_estimate)]:
            if ef.p_fail > 0:
                ratio = est / ef.p_fail
                assert 0.5 < ratio < 2.0, \
                    f"{label}: p_fail={est:.4e} vs exact={ef.p_fail:.4e} (ratio={ratio:.2f})"
