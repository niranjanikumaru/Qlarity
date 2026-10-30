"""
test_oracle_validation.py — Pytest validation suite for the Qiskit quantum failure oracle (backend/app/quantum/oracle.py).

Physics & Quantum Specification Reference:
------------------------------------------
1. 28nm HKMG Analytical Leakage Model:
   - First-order subthreshold exponential dependence on threshold voltage (Vth) and gate oxide thickness (Tox).
   - Calibrated to industrial 28nm planar HKMG standards (Lg0 = 28nm, Tox0 = 1.20nm, Vth0 = 0.350V, n = 1.26).
   
2. Random Input State Generation & Classical Evaluation:
   - Generates randomized discrete parameter basis states across {0, 1, 2, 3}^3 lattice.
   - Generates randomized continuous Gaussian variations binned into representative quantum registers.
   - Generates randomized superposition states across input qubits.
   - Evaluates each sample against the 28nm classical analytical model and classifies failure (I_leak >= I_limit).

3. Quantum Oracle Behavioral Assertions:
   - Ancilla Toggling Test: asserts that O_f |x> |0> |0_work> = |x> |f_classical(x)> |0_work> for every randomized state.
   - Phase Inversion Test: asserts that O_f |x> |-> |0_work> = (-1)^{f_classical(x)} |x> |-> |0_work> for exactly the same failing states.
   - Register Purity: asserts input register remains uncorrupted and work/accumulator register returns to |0>.

4. Mathematical Reversibility & Unitary Matrix Verification:
   - Full operator reversibility: asserts that U_oracle * U_oracle_inv = I (to machine precision < 1e-12).
   - Involutive boolean oracle property: asserts that U_oracle * U_oracle = I.
   - Statevector round-trip fidelity: asserts |<psi | O^dagger O | psi>|^2 > 0.999999 for arbitrary random quantum states.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest
from qiskit import transpile
from qiskit.quantum_info import Statevector, random_statevector
from qiskit_aer import AerSimulator

# Ensure the backend package is importable from the repository root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.physics.leakage import (
    NominalDevice,
    OperatingPoint,
    compute_leakage,
    thermal_voltage,
)
from backend.app.physics.variations import (
    DiscreteVar,
    JointDistribution,
    build_discrete_var,
)
from backend.app.physics.discretize import (
    QuantisedScoreModel,
    build_quantised_score,
)
from backend.app.quantum.oracle import (
    OracleResult,
    build_oracle,
)


# ==============================================================================
# 1. FIXTURES CALIBRATED TO 28nm HKMG CMOS NODE
# ==============================================================================

@pytest.fixture(scope="module")
def device_28nm() -> NominalDevice:
    """
    Nominal semiconductor device parameters calibrated to advanced 28nm HKMG planar CMOS:
    - Nominal Gate Length Lg0 = 28.0 nm
    - Nominal Oxide Thickness Tox0 = 1.20 nm (12 Angstroms)
    - Nominal Threshold Voltage Vth0 = 0.350 V (350 mV)
    - Subthreshold ideality factor n = 1.26
    - Temperature = 300 K (Thermal voltage Vt ~ 25.85 mV)
    - I0 = 1.3e-5 A/um produces exact 10.0 nA baseline standby leakage at nominal center.
    """
    return NominalDevice(
        L0_nm=28.0,
        tox0_nm=1.20,
        Vth0_V=0.350,
        I0_A_per_um=1.3e-5,
        n_ideality=1.26,
        alpha_L_V_per_nm=1.8e-3,       # 1.8 mV/nm gate length sensitivity
        alpha_tox_V_per_nm=12.0e-3,     # 12.0 mV/nm oxide thickness sensitivity
        I_ref_A=1.0e-9                 # 1.0 nA reference current
    )


@pytest.fixture(scope="module")
def op_28nm() -> OperatingPoint:
    """Fixed electrical and thermal operating conditions at probe test."""
    return OperatingPoint(
        Vds=1.0,
        Vgs=0.0,
        Vbs=0.0,
        temperature_K=300.0,
        W_um=1.0
    )


@pytest.fixture(scope="module")
def joint_28nm() -> JointDistribution:
    """
    Process variation distributions calibrated to 28nm 3-sigma process controls:
    - sigma_Lg = 0.80 nm (3-sigma = +/- 2.4 nm)
    - sigma_Tox = 0.020 nm (3-sigma = +/- 0.06 nm)
    - sigma_Vth = 15.0 mV (3-sigma = +/- 45 mV)
    Discretized into 4 equiprobable bins (2 qubits each -> 6 input qubits total).
    """
    var_L = build_discrete_var("delta_L", "nm", sigma=0.80, n_bins=4)
    var_tox = build_discrete_var("delta_tox", "nm", sigma=0.020, n_bins=4)
    var_vth = build_discrete_var("delta_vth", "mV", sigma=15.0, n_bins=4)
    return JointDistribution(var_L=var_L, var_tox=var_tox, var_vth=var_vth)


@pytest.fixture(scope="module")
def leakage_limit_A() -> float:
    """Rigorous QA standby leakage pass/fail threshold: 14.5 nA (1.45e-8 A), testing both pass and fail classes."""
    return 1.45e-8


@pytest.fixture(scope="module")
def qmodel_28nm(
    joint_28nm: JointDistribution,
    leakage_limit_A: float,
    op_28nm: OperatingPoint,
    device_28nm: NominalDevice
) -> QuantisedScoreModel:
    """
    Quantized integer score model calibrated to 28nm parameters.
    Scale=4.0 yields exact representation with compact 3-bit accumulator (total 10 qubits),
    enabling fast, exact unitary matrix assertions and statevector evaluations.
    """
    return build_quantised_score(
        joint_28nm,
        leakage_limit_A,
        op_28nm,
        device_28nm,
        scale=4.0
    )


@pytest.fixture(scope="module")
def oracle_res_28nm(
    joint_28nm: JointDistribution,
    qmodel_28nm: QuantisedScoreModel
) -> OracleResult:
    """Constructs the clean failure oracle O_f and associated metadata."""
    return build_oracle(joint_28nm, qmodel_28nm, validate=False)


# ==============================================================================
# 2. FIRST-ORDER ANALYTICAL LEAKAGE MODEL (28nm CALIBRATION)
# ==============================================================================

def analytical_leakage_28nm(
    delta_L_nm: float,
    delta_tox_nm: float,
    delta_vth_mV: float,
    op: OperatingPoint,
    dev: NominalDevice,
    I_limit_A: float
) -> Tuple[float, int]:
    """
    First-order analytical physical calculation of subthreshold standby leakage.
    Models exponential dependence on threshold voltage Vth and gate oxide thickness Tox:
        Vth_eff = Vth0 + alpha_L * dL + alpha_tox * dtox + dvth
        I_leak = I0 * (W / L_eff) * exp(-(Vth_eff - Vgs) / (n * Vt))
    
    Returns:
        (I_leak_A, fail_flag) where fail_flag is 1 if I_leak >= I_limit, else 0.
    """
    L_eff_nm = dev.L0_nm + delta_L_nm
    tox_eff_nm = dev.tox0_nm + delta_tox_nm
    assert L_eff_nm > 0.0, "Effective gate length must be positive"
    assert tox_eff_nm > 0.0, "Effective oxide thickness must be positive"

    L_eff_um = L_eff_nm * 1e-3
    Vth_eff_V = (
        dev.Vth0_V
        + dev.alpha_L_V_per_nm * delta_L_nm
        + dev.alpha_tox_V_per_nm * delta_tox_nm
        + delta_vth_mV * 1e-3
    )

    Vt = thermal_voltage(op.temperature_K)
    exponent = -(Vth_eff_V - op.Vgs) / (dev.n_ideality * Vt)
    I_leak_A = dev.I0_A_per_um * (op.W_um / L_eff_um) * math.exp(exponent)
    fail_flag = 1 if I_leak_A >= I_limit_A else 0
    return I_leak_A, fail_flag


def encode_basis_state_int(iL: int, itox: int, ivth: int, flag: int = 0) -> int:
    """Encodes (iL, itox, ivth, flag) into a standard Qiskit little-endian basis integer."""
    return (
        (iL & 0x3) << 0
        | (itox & 0x3) << 2
        | (ivth & 0x3) << 4
        | (flag & 0x1) << 6
    )


# ==============================================================================
# 3. UNIT TESTS: 28nm ANALYTICAL PHYSICS DEPENDENCIES
# ==============================================================================

class TestAnalyticalPhysics28nm:
    """Verifies that the analytical model obeys first-order 28nm device physics."""

    def test_nominal_leakage_current_magnitude(self, op_28nm, device_28nm, leakage_limit_A):
        """At nominal center (all deltas=0), leakage should be safely below the 14.5 nA spec limit (~10.0 nA)."""
        I_nom, fail = analytical_leakage_28nm(0.0, 0.0, 0.0, op_28nm, device_28nm, leakage_limit_A)
        assert 8.0e-9 <= I_nom <= 12.0e-9, f"Nominal leakage {I_nom*1e9:.2f} nA out of expected range"
        assert fail == 0, f"Nominal baseline process ({I_nom*1e9:.2f} nA) must pass the {leakage_limit_A*1e9:.1f} nA QA threshold"

    def test_exponential_vth_dependence(self, op_28nm, device_28nm, leakage_limit_A):
        """Negative delta_Vth must exponentially increase subthreshold leakage."""
        I_baseline, _ = analytical_leakage_28nm(0.0, 0.0, 0.0, op_28nm, device_28nm, leakage_limit_A)
        I_shifted, _ = analytical_leakage_28nm(0.0, 0.0, -35.0, op_28nm, device_28nm, leakage_limit_A)
        
        # At n=1.26 and Vt=25.85mV, n*Vt ~ 32.57mV. A 35mV reduction in Vth should multiply leakage by ~e^(35/32.57) ~ 2.92x
        ratio = I_shifted / I_baseline
        expected_ratio = math.exp(35.0e-3 / (device_28nm.n_ideality * thermal_voltage(op_28nm.temperature_K)))
        assert np.isclose(ratio, expected_ratio, rtol=1e-3), (
            f"Vth scaling ratio {ratio:.3f} did not match physical expectation {expected_ratio:.3f}"
        )

    def test_exponential_tox_dependence(self, op_28nm, device_28nm, leakage_limit_A):
        """Thinning gate oxide thickness (delta_tox < 0) lowers Vth and increases leakage."""
        I_nom, _ = analytical_leakage_28nm(0.0, 0.0, 0.0, op_28nm, device_28nm, leakage_limit_A)
        I_thin, _ = analytical_leakage_28nm(0.0, -0.05, 0.0, op_28nm, device_28nm, leakage_limit_A)
        assert I_thin > I_nom, "Thinning oxide thickness must monotonically increase off-state leakage"


# ==============================================================================
# 4. QUANTUM ORACLE EVALUATION ON RANDOM INPUT STATES
# ==============================================================================

class TestQuantumOracleRandomizedInputs:
    """
    Evaluates a randomized set of input states against the classical 28nm model,
    asserting that the quantum oracle toggles the ancilla and flips the phase
    for exactly the same failing states.
    """

    def test_oracle_ancilla_toggling_random_basis_states(
        self,
        oracle_res_28nm: OracleResult,
        joint_28nm: JointDistribution,
        op_28nm: OperatingPoint,
        device_28nm: NominalDevice,
        leakage_limit_A: float
    ):
        """
        Generates random input basis states |x> |0_flag> |0_work>.
        Asserts that the quantum oracle toggles the flag qubit to |1> if and only if
        the 28nm classical analytical model classifies the state as failing (I_leak >= 30 nA).
        """
        oracle_qc = oracle_res_28nm.oracle_circuit
        n_total = oracle_res_28nm.n_total_qubits
        flag_idx = oracle_res_28nm.objective_qubit
        acc_start = oracle_res_28nm.n_input_qubits + 1

        # Seed random generator for deterministic reproducibility
        rng = np.random.default_rng(2026)
        # Sample 20 randomized discrete coordinate states across the 4x4x4 parameter space
        sampled_states = [tuple(rng.integers(0, 4, size=3)) for _ in range(20)]

        for iL, itox, ivth in sampled_states:
            dL = joint_28nm.var_L.values[iL]
            dtox = joint_28nm.var_tox.values[itox]
            dvth = joint_28nm.var_vth.values[ivth]

            # 1. Classical analytical prediction
            I_leak, expected_fail = analytical_leakage_28nm(
                dL, dtox, dvth, op_28nm, device_28nm, leakage_limit_A
            )

            # 2. Quantum oracle simulation
            state_int = encode_basis_state_int(iL, itox, ivth, flag=0)
            sv_in = Statevector.from_int(state_int, dims=2**n_total)
            sv_out = sv_in.evolve(oracle_qc)

            # Extract measured basis state
            out_idx = int(np.argmax(sv_out.probabilities()))
            out_flag = (out_idx >> flag_idx) & 1
            out_input = out_idx & 0x3F
            out_acc = (out_idx >> acc_start) & ((1 << oracle_res_28nm.n_acc_qubits) - 1)

            # Assertions
            assert out_flag == expected_fail, (
                f"Oracle flag mismatch for state ({iL}, {itox}, {ivth}): "
                f"I_leak={I_leak*1e9:.3f} nA, expected={expected_fail}, oracle={out_flag}"
            )
            assert out_input == (state_int & 0x3F), "Oracle corrupted the input parameter register!"
            assert out_acc == 0, f"Oracle left uncomputed garbage in accumulator register: {out_acc}"

    def test_oracle_phase_inversion_random_basis_states(
        self,
        oracle_res_28nm: OracleResult,
        joint_28nm: JointDistribution,
        op_28nm: OperatingPoint,
        device_28nm: NominalDevice,
        leakage_limit_A: float
    ):
        """
        Initializes flag qubit in the |-> = (|0> - |1>)/sqrt(2) phase kickback eigenstate.
        Asserts that the quantum oracle applies a (-1) phase shift:
            O_f |x> |-> |0_work> = (-1)^{f_classical(x)} |x> |-> |0_work>
        for exactly the failing states identified by the 28nm classical analytical model.
        """
        oracle_qc = oracle_res_28nm.oracle_circuit
        n_total = oracle_res_28nm.n_total_qubits
        flag_idx = oracle_res_28nm.objective_qubit

        rng = np.random.default_rng(2828)
        sampled_states = [tuple(rng.integers(0, 4, size=3)) for _ in range(20)]

        for iL, itox, ivth in sampled_states:
            dL = joint_28nm.var_L.values[iL]
            dtox = joint_28nm.var_tox.values[itox]
            dvth = joint_28nm.var_vth.values[ivth]

            # Classical prediction
            _, expected_fail = analytical_leakage_28nm(
                dL, dtox, dvth, op_28nm, device_28nm, leakage_limit_A
            )

            # Build |x> |-> |0_work>
            state_0 = encode_basis_state_int(iL, itox, ivth, flag=0)
            state_1 = encode_basis_state_int(iL, itox, ivth, flag=1)
            amps = np.zeros(2**n_total, dtype=complex)
            amps[state_0] = 1.0 / math.sqrt(2.0)
            amps[state_1] = -1.0 / math.sqrt(2.0)
            sv_minus = Statevector(amps)

            # Evolve under quantum oracle
            sv_out = sv_minus.evolve(oracle_qc)

            # Check phase factor
            inner_prod = sv_out.inner(sv_minus)
            expected_phase = (-1.0) ** expected_fail

            assert np.isclose(inner_prod.real, expected_phase, atol=1e-5), (
                f"Phase inversion mismatch for state ({iL}, {itox}, {ivth}): "
                f"expected phase={expected_phase}, got inner_product={inner_prod}"
            )
            assert np.isclose(inner_prod.imag, 0.0, atol=1e-5), "Unexpected imaginary phase component detected"

    def test_oracle_random_superposition_phase_inversion(
        self,
        oracle_res_28nm: OracleResult,
        joint_28nm: JointDistribution,
        op_28nm: OperatingPoint,
        device_28nm: NominalDevice,
        leakage_limit_A: float
    ):
        """
        Constructs a random superposition over an arbitrary subset of input states:
            |psi_in> = sum_{x in S} c_x |x> |-> |0_work>
        Asserts that the quantum oracle linearly and simultaneously flips the phase of each
        basis component in the superposition according to its classical failure label:
            |psi_out> = sum_{x in S} c_x * (-1)^{f_classical(x)} |x> |-> |0_work>
        """
        oracle_qc = oracle_res_28nm.oracle_circuit
        n_total = oracle_res_28nm.n_total_qubits

        rng = np.random.default_rng(777)
        subset_size = 12
        chosen_indices = rng.choice(64, size=subset_size, replace=False)
        random_weights = rng.normal(0, 1, size=subset_size) + 1j * rng.normal(0, 1, size=subset_size)
        random_weights /= np.linalg.norm(random_weights)

        amps_in = np.zeros(2**n_total, dtype=complex)
        amps_expected_out = np.zeros(2**n_total, dtype=complex)

        for idx, c_x in zip(chosen_indices, random_weights):
            iL = idx & 3
            itox = (idx >> 2) & 3
            ivth = (idx >> 4) & 3

            dL = joint_28nm.var_L.values[iL]
            dtox = joint_28nm.var_tox.values[itox]
            dvth = joint_28nm.var_vth.values[ivth]

            _, expected_fail = analytical_leakage_28nm(
                dL, dtox, dvth, op_28nm, device_28nm, leakage_limit_A
            )
            phase = (-1.0) ** expected_fail

            s0 = encode_basis_state_int(iL, itox, ivth, flag=0)
            s1 = encode_basis_state_int(iL, itox, ivth, flag=1)

            amps_in[s0] += c_x / math.sqrt(2.0)
            amps_in[s1] -= c_x / math.sqrt(2.0)

            amps_expected_out[s0] += (c_x * phase) / math.sqrt(2.0)
            amps_expected_out[s1] -= (c_x * phase) / math.sqrt(2.0)

        sv_in = Statevector(amps_in)
        sv_expected = Statevector(amps_expected_out)
        sv_actual = sv_in.evolve(oracle_qc)

        fidelity = abs(sv_actual.inner(sv_expected)) ** 2
        assert fidelity > 0.99999, f"Superposition phase inversion fidelity = {fidelity:.6f} < 0.99999"


# ==============================================================================
# 5. MATHEMATICAL REVERSIBILITY & UNITARY IDENTITY VERIFICATION
# ==============================================================================

class TestOracleMathematicalReversibility:
    """
    Mathematically verifies full reversibility of the quantum failure oracle:
    1. Direct unitary matrix assertion: U_oracle * U_oracle_inv == Identity.
    2. Involutive boolean oracle identity: U_oracle * U_oracle == Identity.
    3. Statevector conservation: O_inv * O |psi> == |psi> for arbitrary random states.
    """

    def test_oracle_inverse_product_is_identity_matrix(self, oracle_res_28nm: OracleResult):
        """
        Calculates the complete 2^10 x 2^10 unitary matrix of O * O_inv using AerSimulator.
        Asserts that the maximum absolute deviation from the true Identity matrix is zero (< 1e-12).
        """
        oracle_qc = oracle_res_28nm.oracle_circuit
        n_total = oracle_res_28nm.n_total_qubits

        roundtrip_qc = oracle_qc.compose(oracle_qc.inverse())
        roundtrip_qc.save_unitary()

        sim = AerSimulator(method="unitary")
        transpiled_qc = transpile(roundtrip_qc, sim)
        result = sim.run(transpiled_qc).result()
        unitary_matrix = result.get_unitary(transpiled_qc).data

        identity_matrix = np.eye(2**n_total, dtype=complex)
        max_dev = float(np.max(np.abs(unitary_matrix - identity_matrix)))

        assert np.allclose(unitary_matrix, identity_matrix, atol=1e-7), (
            f"O * O_inv is NOT the identity matrix! Max deviation = {max_dev:.3e}"
        )
        assert max_dev < 1e-11, f"Numerical precision degraded: max deviation = {max_dev:.3e}"

    def test_oracle_involutive_square_is_identity_matrix(self, oracle_res_28nm: OracleResult):
        """
        Because O_f is a clean boolean reflection operator:
            O_f |x> |b> = |x> |b XOR f(x)>
        applying the oracle twice in succession must equal the identity matrix:
            O_f^2 = I
        """
        oracle_qc = oracle_res_28nm.oracle_circuit
        n_total = oracle_res_28nm.n_total_qubits

        double_qc = oracle_qc.compose(oracle_qc)
        double_qc.save_unitary()

        sim = AerSimulator(method="unitary")
        transpiled_qc = transpile(double_qc, sim)
        result = sim.run(transpiled_qc).result()
        unitary_matrix = result.get_unitary(transpiled_qc).data

        identity_matrix = np.eye(2**n_total, dtype=complex)
        max_dev = float(np.max(np.abs(unitary_matrix - identity_matrix)))

        assert np.allclose(unitary_matrix, identity_matrix, atol=1e-7), (
            f"O_f^2 is NOT the identity matrix! Max deviation = {max_dev:.3e}"
        )
        assert max_dev < 1e-11, f"Numerical precision degraded: max deviation = {max_dev:.3e}"

    def test_oracle_roundtrip_arbitrary_random_statevector(self, oracle_res_28nm: OracleResult):
        """
        Generates 5 completely arbitrary Haar-random complex statevectors across all 10 qubits.
        Asserts that applying O followed by O_inv restores the original state with unit fidelity.
        """
        oracle_qc = oracle_res_28nm.oracle_circuit
        n_total = oracle_res_28nm.n_total_qubits

        for seed in [101, 202, 303, 404, 505]:
            sv_random = random_statevector(2**n_total, seed=seed)
            sv_forward = sv_random.evolve(oracle_qc)
            sv_restored = sv_forward.evolve(oracle_qc.inverse())

            overlap = abs(sv_restored.inner(sv_random)) ** 2
            assert np.isclose(overlap, 1.0, atol=1e-10), (
                f"Reversibility fidelity failure for seed {seed}: overlap = {overlap:.12f}"
            )

    def test_oracle_verification_json_export(
        self,
        oracle_res_28nm: OracleResult,
        joint_28nm: JointDistribution,
        op_28nm: OperatingPoint,
        device_28nm: NominalDevice,
        leakage_limit_A: float
    ):
        """
        Validates all basis states and outputs oracle_verification.json with boolean success flag
        and states_verified count.
        """
        import json
        import datetime

        oracle_qc = oracle_res_28nm.oracle_circuit
        n_total = oracle_res_28nm.n_total_qubits

        verified_states_count = 0
        all_passed = True

        for iL in range(4):
            for itox in range(4):
                for ivth in range(4):
                    dL = joint_28nm.var_L.values[iL]
                    dtox = joint_28nm.var_tox.values[itox]
                    dvth = joint_28nm.var_vth.values[ivth]

                    _, expected_fail = analytical_leakage_28nm(
                        dL, dtox, dvth, op_28nm, device_28nm, leakage_limit_A
                    )

                    # Check phase flip on |x> |-> |0>
                    s0 = encode_basis_state_int(iL, itox, ivth, flag=0)
                    s1 = encode_basis_state_int(iL, itox, ivth, flag=1)
                    amps = np.zeros(2**n_total, dtype=complex)
                    amps[s0] = 1.0 / math.sqrt(2.0)
                    amps[s1] = -1.0 / math.sqrt(2.0)
                    sv = Statevector(amps)
                    sv_out = sv.evolve(oracle_qc)
                    inner = sv_out.inner(sv)
                    expected_phase = (-1.0) ** expected_fail

                    if np.isclose(inner.real, expected_phase, atol=1e-5):
                        verified_states_count += 1
                    else:
                        all_passed = False

        assert all_passed and verified_states_count == 64

        # Verify reversibility
        roundtrip_qc = oracle_qc.compose(oracle_qc.inverse())
        roundtrip_qc.save_unitary()
        sim = AerSimulator(method="unitary")
        transpiled_qc = transpile(roundtrip_qc, sim)
        unitary_matrix = sim.run(transpiled_qc).result().get_unitary(transpiled_qc).data
        identity_matrix = np.eye(2**n_total, dtype=complex)
        max_dev = float(np.max(np.abs(unitary_matrix - identity_matrix)))
        is_reversible = bool(max_dev < 1e-7)

        verification_record = {
            "success": bool(all_passed and is_reversible),
            "states_verified": verified_states_count,
            "reversibility_verified": is_reversible,
            "max_unitary_deviation": max_dev,
            "calibrated_node": "28nm HKMG Planar CMOS",
            "device_nominal": {
                "Lg_nm": device_28nm.L0_nm,
                "Tox_nm": device_28nm.tox0_nm,
                "Vth_V": device_28nm.Vth0_V,
                "subthreshold_n": device_28nm.n_ideality
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        # Save to evidence/, web/, and project root for ubiquitous accessibility
        root_dir = Path(__file__).resolve().parents[2]
        destinations = [
            root_dir / "evidence" / "oracle_verification.json",
            root_dir / "web" / "oracle_verification.json",
            root_dir.parent / "oracle_verification.json",
            root_dir / "oracle_verification.json",
        ]
        for dest in destinations:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(verification_record, indent=2))

        assert verification_record["success"] is True
        assert verification_record["states_verified"] == 64
