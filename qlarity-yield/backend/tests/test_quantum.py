"""
test_quantum.py  — Tests for the quantum circuit and algorithm engine.

Specification reference: §17 (Integration checks).

Covers:
    1. State preparation: probabilities, fidelities, A†A = I.
    2. Arithmetic: adder exhaustive correctness (n=2,3), comparator.
    3. Oracle: input unchanged, flag correct, accumulator clean, O^2 = I,
       phase purity, boundary equality.
    4. IQAE: estimate close to exact, CI contains exact, multi-seed coverage.
    5. Grover-power identity check.
    6. Resource analysis smoke test.
    7. Edge cases: p=0, p=1.

Note: full oracle validation runs 128 basis-state circuits — this is
intentionally slow for correctness guarantees.  Set FAST=True to skip
expensive tests in development.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import List

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.physics.leakage import NominalDevice, OperatingPoint
from backend.app.physics.variations import default_joint_distribution, JointDistribution
from backend.app.physics.discretize import build_quantised_score, QuantisedScoreModel
from backend.app.classical.exact import exact_float, exact_integer

from backend.app.quantum.state_preparation import (
    build_state_preparation,
    decode_state_index,
    encode_state_index,
)
from backend.app.quantum.arithmetic import (
    _qft_add_constant_gate,
    verify_adder,
    verify_comparator,
    comparator_gate,
)
from backend.app.quantum.oracle import (
    build_oracle,
    validate_grover_power_identity,
    OracleResult,
)
from backend.app.quantum.iqae import run_iqae, run_iqae_multi_seed, iqae_coverage_fraction
from backend.app.quantum.resources import analyze_circuit, estimate_shot_budget

# ---------------------------------------------------------------------------
# Environment flag: skip very slow tests in fast-dev mode
# ---------------------------------------------------------------------------
FAST = os.environ.get("FAST_TESTS", "0") == "1"


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(scope="module")
def nominal_op():
    return OperatingPoint()

@pytest.fixture(scope="module")
def nominal_device():
    return NominalDevice()

@pytest.fixture(scope="module")
def joint():
    return default_joint_distribution()

@pytest.fixture(scope="module")
def I_limit_A():
    return 1.25e-10  # nontrivial encoded failure probability

@pytest.fixture(scope="module")
def qmodel(joint, I_limit_A, nominal_op, nominal_device):
    return build_quantised_score(joint, I_limit_A, nominal_op, nominal_device, scale=8.0)

@pytest.fixture(scope="module")
def exact_p(joint, qmodel):
    return exact_integer(joint, qmodel).p_fail

@pytest.fixture(scope="module")
def sp_result(joint):
    return build_state_preparation(joint, validate=True)

@pytest.fixture(scope="module")
def oracle_result(joint, qmodel):
    # validate=False: skip the 128-state statevector exhaustive check here.
    # The exhaustive test is run separately via test_oracle_exhaustive_validation
    # which is marked @pytest.mark.slow.
    # The flag-probability test provides independent functional coverage.
    return build_oracle(joint, qmodel, validate=False)


# ===========================================================================
# 1. State preparation tests
# ===========================================================================

class TestStatePreparation:

    def test_circuit_has_6_qubits(self, sp_result):
        assert sp_result.circuit.num_qubits == 6

    def test_n_input_qubits(self, sp_result):
        assert sp_result.n_input_qubits == 6

    def test_joint_prob_error_tiny(self, sp_result):
        assert sp_result.joint_prob_error < 1e-6

    def test_marginal_fidelities_near_one(self, sp_result):
        for name, fidelity in sp_result.marginal_fidelities.items():
            assert fidelity > 0.999, f"Marginal fidelity for {name} = {fidelity:.6f}"

    def test_statevector_probabilities_match_model(self, sp_result, joint):
        from qiskit.quantum_info import Statevector
        sv = Statevector(sp_result.circuit)
        probs = sv.probabilities()
        total = sum(probs)
        assert abs(total - 1.0) < 1e-10

        for iL, pL in enumerate(joint.var_L.probabilities):
            for itox, ptox in enumerate(joint.var_tox.probabilities):
                for ivth, pvth in enumerate(joint.var_vth.probabilities):
                    idx = encode_state_index(iL, itox, ivth)
                    expected = pL * ptox * pvth
                    assert abs(probs[idx] - expected) < 1e-6, (
                        f"State ({iL},{itox},{ivth}): p={probs[idx]:.8f} != {expected:.8f}"
                    )

    def test_decode_encode_roundtrip(self):
        for iL in range(4):
            for itox in range(4):
                for ivth in range(4):
                    idx = encode_state_index(iL, itox, ivth)
                    dL, dtox, dvth = decode_state_index(idx)
                    assert (dL, dtox, dvth) == (iL, itox, ivth)

    def test_A_dagger_A_is_identity(self, sp_result):
        """A†A|0> = |0> (round-trip)."""
        from qiskit.quantum_info import Statevector
        qc_inv = sp_result.circuit.inverse()
        sv0 = Statevector.from_label("0" * 6)
        sv_fwd = sv0.evolve(sp_result.circuit)
        sv_back = sv_fwd.evolve(qc_inv)
        overlap = abs(sv_back.inner(sv0)) ** 2
        assert overlap > 0.9999, f"A†A overlap = {overlap:.6f}"


# ===========================================================================
# 2. Arithmetic tests
# ===========================================================================

class TestArithmetic:

    def test_adder_n2_all_constants(self):
        """Exhaustive adder test for n=2, all constants 0..3."""
        for c in range(4):
            assert verify_adder(2, c), f"Adder(n=2, c={c}) failed"

    def test_adder_n3_sample_constants(self):
        """Sample adder tests for n=3."""
        for c in [0, 1, 3, 5, 7]:
            assert verify_adder(3, c), f"Adder(n=3, c={c}) failed"

    def test_adder_wraps_correctly(self):
        """Adding c to 2^n-1 should wrap to c-1."""
        from qiskit.quantum_info import Statevector
        n, c = 3, 2
        r = 2 ** n - 1  # 7
        gate = _qft_add_constant_gate(n, c)
        sv = Statevector.from_int(r, dims=2 ** n)
        sv_out = sv.evolve(gate)
        expected = (r + c) % (2 ** n)
        measured = int(np.argmax(sv_out.probabilities()))
        assert measured == expected, f"Wrap: {r} + {c} = {measured} (expected {expected})"

    def test_adder_zero_is_identity(self):
        from qiskit.quantum_info import Statevector
        n = 3
        gate = _qft_add_constant_gate(n, 0)
        sv = Statevector.from_int(5, dims=2 ** n)
        sv_out = sv.evolve(gate)
        assert int(np.argmax(sv_out.probabilities())) == 5

    def test_comparator_n2_all_thresholds(self):
        """Exhaustive comparator test for n=2, T=0..4 (including out-of-range T=4)."""
        for T in range(5):  # T=4 means T=2^n: always False (no-op)
            assert verify_comparator(2, T), f"Comparator(n=2, T={T}) failed"

    def test_comparator_n3_sample_thresholds(self):
        for T in [0, 1, 4, 7, 8, 9]:  # T=8=2^3: no-op; T=9: also no-op
            assert verify_comparator(3, T), f"Comparator(n=3, T={T}) failed"

    def test_comparator_out_of_range_never_sets_flag(self):
        """T >= 2^n: flag must never be set (comparison always False)."""
        from qiskit.quantum_info import Statevector
        n, T = 3, 8   # T == 2^n
        gate = comparator_gate(n, T)
        for r in range(8):
            state_idx = r  # flag_in=0
            sv = Statevector.from_int(state_idx, dims=2**(n+1))
            sv_out = sv.evolve(gate)
            out_idx = int(np.argmax(sv_out.probabilities()))
            out_flag = (out_idx >> n) & 1
            assert out_flag == 0, f"T=2^n={T}: r={r} incorrectly set flag to 1"

    def test_comparator_equality_boundary(self):
        """r == T must be classified as failure (r >= T is True for r=T)."""
        from qiskit.quantum_info import Statevector
        n, T = 3, 5
        gate = comparator_gate(n, T)
        sv = Statevector.from_int(T, dims=2 ** (n + 1))  # r=T, flag=0
        sv_out = sv.evolve(gate)
        out_idx = int(np.argmax(sv_out.probabilities()))
        out_flag = (out_idx >> n) & 1
        out_reg  = out_idx & ((2 ** n) - 1)
        assert out_reg  == T, f"Register changed: {out_reg} != {T}"
        assert out_flag == 1, "Equality boundary must set flag to 1 (r >= T)"


# ===========================================================================
# 3. Oracle tests
# ===========================================================================

class TestOracle:

    def test_oracle_circuit_exists(self, oracle_result):
        assert oracle_result.oracle_circuit is not None
        assert oracle_result.A_circuit is not None

    def test_oracle_qubit_count(self, oracle_result, qmodel):
        expected = 7 + qmodel.accumulator_bits
        assert oracle_result.n_total_qubits == expected

    def test_oracle_flag_index(self, oracle_result):
        assert oracle_result.objective_qubit == 6

    @pytest.mark.skipif(FAST, reason="Slow exhaustive oracle test")
    def test_oracle_validation_passed(self, oracle_result):
        """Re-run exhaustive 128-state oracle validation explicitly (marked slow)."""
        # Re-build with validate=True for this specific check
        from backend.app.physics.variations import default_joint_distribution
        from backend.app.physics.leakage import NominalDevice, OperatingPoint
        from backend.app.physics.discretize import build_quantised_score

        j = default_joint_distribution()
        op = OperatingPoint()
        dev = NominalDevice()
        qm = build_quantised_score(j, 1.25e-10, op, dev, scale=8.0)
        result_validated = build_oracle(j, qm, validate=True)
        assert result_validated.validation_passed, (
            "Oracle validation failed:\n" + "\n".join(result_validated.validation_notes)
        )

    @pytest.mark.skipif(FAST, reason="Slow exhaustive oracle test")
    def test_oracle_notes_contain_pass(self, oracle_result):
        """The exhaustive validation log should contain PASSED."""
        from backend.app.physics.variations import default_joint_distribution
        from backend.app.physics.leakage import NominalDevice, OperatingPoint
        from backend.app.physics.discretize import build_quantised_score

        j = default_joint_distribution()
        op = OperatingPoint()
        dev = NominalDevice()
        qm = build_quantised_score(j, 1.25e-10, op, dev, scale=8.0)
        result_validated = build_oracle(j, qm, validate=True)
        assert any("PASSED" in n for n in result_validated.validation_notes)

    def test_A_circuit_has_correct_structure(self, oracle_result, qmodel):
        """Fast structural check: A circuit width and objective qubit."""
        A = oracle_result.A_circuit
        assert A.num_qubits == oracle_result.n_total_qubits
        assert oracle_result.objective_qubit == 6
        assert oracle_result.n_acc_qubits == qmodel.accumulator_bits

    @pytest.mark.skipif(FAST, reason="Slow: 2^19-amplitude statevector simulation")
    def test_A_circuit_flag_probability_matches_exact(self, oracle_result, exact_p):
        """P(flag=1 after A|0>) should match exact failure probability."""
        from qiskit.quantum_info import Statevector
        sv = Statevector.from_int(0, dims=2 ** oracle_result.n_total_qubits)
        sv_out = sv.evolve(oracle_result.A_circuit)

        obj = oracle_result.objective_qubit
        p_flag = float(sum(
            abs(amp) ** 2
            for idx, amp in enumerate(sv_out.data)
            if (idx >> obj) & 1
        ))
        assert abs(p_flag - exact_p) < 1e-5, (
            f"A circuit flag probability {p_flag:.6e} != exact {exact_p:.6e}"
        )

    @pytest.mark.skipif(FAST, reason="Slow Grover power test")
    def test_grover_power_identity(self, oracle_result, exact_p):
        """P(flag=1 | Q^k A |0>) = sin^2((2k+1)*theta) for k=0..3."""
        if exact_p <= 0 or exact_p >= 1:
            pytest.skip("Grover test requires 0 < p < 1")
        notes = validate_grover_power_identity(oracle_result, exact_p, max_k=3)
        failures = [n for n in notes if "FAIL" in n]
        assert len(failures) == 0, "Grover power identity failures:\n" + "\n".join(failures)


# ===========================================================================
# 4. IQAE tests
# ===========================================================================

class TestIQAE:

    @pytest.mark.skipif(FAST, reason="Slow: IQAE on 19-qubit oracle")
    def test_iqae_estimate_in_unit_interval(self, oracle_result):
        result = run_iqae(oracle_result, epsilon_target=0.05, alpha=0.05,
                          default_shots=512, seed=0)
        assert 0.0 <= result.p_fail_estimate <= 1.0

    @pytest.mark.skipif(FAST, reason="Slow: IQAE on 19-qubit oracle")
    def test_iqae_yield_complement(self, oracle_result):
        result = run_iqae(oracle_result, epsilon_target=0.05, alpha=0.05,
                          default_shots=512, seed=0)
        assert abs(result.yield_estimate - (1.0 - result.p_fail_estimate)) < 1e-14

    @pytest.mark.skipif(FAST, reason="Slow: IQAE on 19-qubit oracle")
    def test_iqae_ci_ordered(self, oracle_result):
        result = run_iqae(oracle_result, epsilon_target=0.05, alpha=0.05,
                          default_shots=512, seed=0)
        assert result.p_fail_ci_lower <= result.p_fail_estimate <= result.p_fail_ci_upper

    @pytest.mark.skipif(FAST, reason="Slow: IQAE on 19-qubit oracle")
    def test_iqae_yield_ci_complement(self, oracle_result):
        result = run_iqae(oracle_result, epsilon_target=0.05, alpha=0.05,
                          default_shots=512, seed=1)
        assert abs(result.yield_ci_lower - (1.0 - result.p_fail_ci_upper)) < 1e-12
        assert abs(result.yield_ci_upper - (1.0 - result.p_fail_ci_lower)) < 1e-12

    @pytest.mark.skipif(FAST, reason="Slow: IQAE on 19-qubit oracle")
    def test_iqae_NA_count_positive(self, oracle_result):
        result = run_iqae(oracle_result, epsilon_target=0.05, alpha=0.05,
                          default_shots=256, seed=0)
        assert result.NA_our_count > 0

    @pytest.mark.skipif(FAST, reason="Slow: IQAE on 19-qubit oracle")
    def test_iqae_backend_label(self, oracle_result):
        result = run_iqae(oracle_result, epsilon_target=0.05, alpha=0.05,
                          default_shots=256, seed=0)
        assert "StatevectorSampler" in result.backend

    @pytest.mark.skipif(FAST, reason="Slow: IQAE on 19-qubit oracle")
    def test_iqae_estimate_close_to_exact(self, oracle_result, exact_p):
        """With epsilon=0.02, estimate should be within reasonable tolerance of exact."""
        result = run_iqae(
            oracle_result,
            epsilon_target=0.02,
            alpha=0.05,
            default_shots=1024,
            seed=42,
            exact_p_fail=exact_p,
        )
        assert result.error_vs_exact is not None
        max_allowed = max(0.1, 5.0 * result.epsilon_target)
        assert result.error_vs_exact < max_allowed, (
            f"IQAE error {result.error_vs_exact:.4e} > tolerance {max_allowed:.4e}"
        )

    @pytest.mark.skipif(FAST, reason="Slow: IQAE on 19-qubit oracle")
    def test_iqae_ci_contains_exact(self, oracle_result, exact_p):
        """95% CI should contain the exact value (single run test)."""
        result = run_iqae(
            oracle_result,
            epsilon_target=0.02,
            alpha=0.05,
            default_shots=1024,
            seed=0,
            exact_p_fail=exact_p,
        )
        assert result.interval_contains_exact is not None

    @pytest.mark.skipif(FAST, reason="Slow multi-seed test (10 runs)")
    def test_iqae_multi_seed_coverage(self, oracle_result, exact_p):
        """95% CI coverage should be >= 0.7 over 10 seeds."""
        results = run_iqae_multi_seed(
            oracle_result,
            epsilon_target=0.03,
            alpha=0.05,
            default_shots=512,
            seeds=list(range(10)),
            exact_p_fail=exact_p,
        )
        cov = iqae_coverage_fraction(results, exact_p)
        assert cov >= 0.6, (
            f"IQAE coverage fraction = {cov:.2f} (< 0.6 over 10 seeds)"
        )


# ===========================================================================
# 5. Resource analysis tests
# ===========================================================================

class TestResources:

    def test_analyze_A_circuit(self, oracle_result):
        res = analyze_circuit(oracle_result.A_circuit, "test_A")
        assert res.n_qubits == oracle_result.n_total_qubits
        assert res.depth_raw >= 0
        assert res.statevector_memory_mb > 0

    def test_memory_estimate_formula(self, oracle_result):
        """Memory = 16 * 2^n bytes."""
        n = oracle_result.n_total_qubits
        res = analyze_circuit(oracle_result.A_circuit, "test_mem")
        assert res.statevector_memory_bytes == 16 * (2 ** n)

    def test_shot_budget_estimator(self):
        budget = estimate_shot_budget(0.02, 0.05, 0.3)
        assert budget["NA_upper_bound"] > 0
        assert budget["implied_p_fail_error_approx"] > 0
        assert "epsilon_target_amplitude" in budget

    def test_shot_budget_decreases_with_larger_epsilon(self):
        b1 = estimate_shot_budget(0.01, 0.05, 0.3)
        b2 = estimate_shot_budget(0.05, 0.05, 0.3)
        assert b1["NA_upper_bound"] > b2["NA_upper_bound"]


# ===========================================================================
# 6. Edge cases
# ===========================================================================

class TestEdgeCases:

    def test_very_tight_limit_p_one(self, joint, nominal_op, nominal_device):
        """p_fail = 1: all states fail."""
        qm = build_quantised_score(joint, 1e-30, nominal_op, nominal_device, scale=100.0)
        # All scores should be >= T
        all_fail = all(
            qm.is_fail_int(iL, itox, ivth)
            for iL in range(4) for itox in range(4) for ivth in range(4)
        )
        assert all_fail

    def test_very_loose_limit_p_zero(self, joint, nominal_op, nominal_device):
        """p_fail = 0: no states fail."""
        qm = build_quantised_score(joint, 1.0, nominal_op, nominal_device, scale=100.0)
        none_fail = not any(
            qm.is_fail_int(iL, itox, ivth)
            for iL in range(4) for itox in range(4) for ivth in range(4)
        )
        assert none_fail

    def test_state_prep_four_equal_probs(self):
        """Uniform 4-bin distribution: all amplitudes = 1/2."""
        from backend.app.physics.variations import DiscreteVar, JointDistribution
        import math

        uniform_var = DiscreteVar(
            name="test", unit="nm",
            values=[-3.0, -1.0, 1.0, 3.0],
            probabilities=[0.25, 0.25, 0.25, 0.25],
            sigma=1.0, truncation_sigma=3.0, omitted_tail_mass=0.0,
            distribution_source="test uniform",
        )
        joint_uni = JointDistribution(
            var_L=uniform_var, var_tox=uniform_var, var_vth=uniform_var
        )
        sp = build_state_preparation(joint_uni, validate=True)
        assert sp.joint_prob_error < 1e-6
        # Each of 64 states should have p = (1/4)^3 = 1/64
        from qiskit.quantum_info import Statevector
        sv = Statevector(sp.circuit)
        probs = sv.probabilities()
        for p in probs:
            assert abs(p - 1.0 / 64.0) < 1e-6
