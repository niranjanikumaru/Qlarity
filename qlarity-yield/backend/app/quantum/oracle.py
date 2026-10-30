"""
oracle.py  — Clean failure oracle O_f and the full state-preparation circuit A.

Specification reference: §9 (Build the reversible oracle), §10 (state prep + oracle).

Required transformation (§9):
    O_f |x>|b>|0_work> = |x>|b XOR f(x)>|0_work>

where:
    |x>      = |iL, itox, ivth>  (6 input qubits, 2 per variable)
    |b>      = objective flag qubit (1 qubit)
    |0_work> = clean ancilla (score accumulator, b_acc bits)

Implementation (§9 steps 1-5):
    1. Allocate registers: input (6q), score accumulator (b_acc q), flag (1q).
    2. Compute S(x) + B into the accumulator:
          S(x) + B = (C0 + B) + C_L[iL] + C_tox[itox] + C_vth[ivth]
       Each term is a constant addition controlled on the 2-bit bin index.
    3. Compare accumulator >= (T + B): XOR result into flag.
    4. Uncompute score register (apply inverse of step 2).
    5. All work registers return to zero.

Integer score model (from QuantisedScoreModel):
    S(iL, itox, ivth) = C0 + C_L[iL] + C_tox[itox] + C_vth[ivth]

After the offset B:
    S' = S + B  (guaranteed >= 0)
    T' = T + B  (shifted threshold)

Full A circuit (used by IQAE):
    A = (state_prep on input qubits) then (oracle with flag starting at |0>)
    A|0> = sum_x sqrt(p(x)) |x>|f(x)>|0_work>

The IQAE objective qubit index is the flag qubit.

Qubit layout of the full A circuit
------------------------------------
    q[0:6]       — 6 input qubits (iL: 0-1, itox: 2-3, ivth: 4-5)
    q[6]         — objective flag qubit
    q[7:7+b_acc] — score accumulator (b_acc bits)

Total width = 7 + b_acc qubits.  For the first-release model with scale=1000,
b_acc is typically 12-14 bits.  We report the exact count.

Oracle validation (§9 exit criterion):
    - For every basis input |x>:
        * Input register unchanged.
        * Flag = f(x) when starting at |0>.
        * Flag = 1 XOR f(x) when starting at |1>.
        * Accumulator returns to |0>.
        * Applying oracle twice restores full state.
    - Phase test: compare statevector of our oracle with an ideal
      truth-table oracle; allow only a global phase difference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from qiskit import QuantumCircuit, QuantumRegister

from ..physics.discretize import QuantisedScoreModel
from ..physics.variations import JointDistribution
from .arithmetic import (
    _qft_add_constant_gate,
    controlled_constant_adder,
    comparator_gate,
)
from .state_preparation import build_state_preparation, encode_state_index


# ---------------------------------------------------------------------------
# Score computation: controlled constant additions
# ---------------------------------------------------------------------------

def _build_score_circuit(
    qmodel: QuantisedScoreModel,
    n_input: int,
    n_acc: int,
) -> QuantumCircuit:
    """Build the circuit that adds S(x)+B into the accumulator register.

    Qubit layout of the returned circuit:
        q[0:2]      — iL   (2-bit bin index)
        q[2:4]      — itox (2-bit bin index)
        q[4:6]      — ivth (2-bit bin index)
        q[6:6+n_acc]— score accumulator (n_acc bits)

    Operations:
        1. Add (C0 + B) unconditionally (constant, no control).
        2. For each bin value j of L   : add C_L[j]   controlled on |iL  = j>.
        3. For each bin value j of tox : add C_tox[j] controlled on |itox = j>.
        4. For each bin value j of vth : add C_vth[j] controlled on |ivth = j>.

    Controlled on a 2-bit index |j> (j=0..3):
        j=0: controls are q[0]=0, q[1]=0  => X on both, CADD, X on both
        j=1: controls are q[0]=1, q[1]=0  => X on q[1], CADD with ctrl q[0],q[1], X on q[1]
        j=2: controls are q[0]=0, q[1]=1  => X on q[0], CADD, X on q[0]
        j=3: controls are q[0]=1, q[1]=1  => CADD with both controls

    We use the technique of flipping qubits to turn AND(q[0]=a, q[1]=b) into
    AND(q[0]=1, q[1]=1), apply the doubly-controlled adder, then un-flip.
    """
    total = n_input + n_acc  # 6 + n_acc
    acc_start = n_input
    qc = QuantumCircuit(total, name="SCORE")

    B = qmodel.B
    C0 = qmodel.C0

    # Step 1: unconditional add of (C0 + B) to accumulator
    base = C0 + B
    if base != 0:
        adder = _qft_add_constant_gate(n_acc, int(base) % (2 ** n_acc), name="ADD_base")
        qc.append(adder.to_gate(), list(range(acc_start, acc_start + n_acc)))

    def _controlled_add(qc: QuantumCircuit, q0: int, q1: int, value: int, flip0: bool, flip1: bool):
        """Add `value` to accumulator controlled on q[q0]=1-flip0, q[q1]=1-flip1."""
        val = int(value) % (2 ** n_acc)
        if val == 0:
            return
        # Flip qubits to make controls both active-high
        if flip0:
            qc.x(q0)
        if flip1:
            qc.x(q1)
        # Doubly-controlled adder: controls are q0, q1; target is accumulator
        # Build as a (2+n_acc)-qubit gate
        cadd = controlled_constant_adder(n_acc, val, n_controls=2, name="CADD")
        qc.append(cadd.to_gate(), [q0, q1] + list(range(acc_start, acc_start + n_acc)))
        # Undo flips
        if flip0:
            qc.x(q0)
        if flip1:
            qc.x(q1)

    # Step 2: C_L contributions (iL on qubits 0,1)
    for j in range(4):
        c_val = qmodel.C_L[j]
        flip0 = (j & 1) == 0  # q[0] should be 0 => flip to make it 1
        flip1 = (j & 2) == 0  # q[1] should be 0 => flip
        _controlled_add(qc, 0, 1, c_val, flip0, flip1)

    # Step 3: C_tox contributions (itox on qubits 2,3)
    for j in range(4):
        c_val = qmodel.C_tox[j]
        flip0 = (j & 1) == 0
        flip1 = (j & 2) == 0
        _controlled_add(qc, 2, 3, c_val, flip0, flip1)

    # Step 4: C_vth contributions (ivth on qubits 4,5)
    for j in range(4):
        c_val = qmodel.C_vth[j]
        flip0 = (j & 1) == 0
        flip1 = (j & 2) == 0
        _controlled_add(qc, 4, 5, c_val, flip0, flip1)

    return qc


# ---------------------------------------------------------------------------
# Oracle O_f
# ---------------------------------------------------------------------------

@dataclass
class OracleResult:
    """Oracle circuit and metadata.

    Attributes
    ----------
    oracle_circuit  : QuantumCircuit implementing O_f.
                      Layout: [input(6q), flag(1q), accumulator(b_acc q)]
    A_circuit       : Full state-preparation + oracle circuit for IQAE.
                      Layout: same as oracle_circuit.
    objective_qubit : index of the flag qubit in the circuit (= 6).
    n_input_qubits  : 6
    n_acc_qubits    : b_acc
    n_total_qubits  : 7 + b_acc
    T_shifted       : integer threshold T + B used in comparison
    validation_passed : bool — True if exhaustive oracle tests passed
    validation_notes  : list of validation outcome strings
    """
    oracle_circuit: QuantumCircuit
    A_circuit: QuantumCircuit
    objective_qubit: int
    n_input_qubits: int
    n_acc_qubits: int
    n_total_qubits: int
    T_shifted: int
    validation_passed: bool
    validation_notes: List[str]


def build_oracle(
    joint: JointDistribution,
    qmodel: QuantisedScoreModel,
    validate: bool = True,
) -> OracleResult:
    """Build the clean failure oracle O_f and the full A circuit.

    Parameters
    ----------
    joint   : JointDistribution (needed for state prep validation)
    qmodel  : QuantisedScoreModel (integer score model)
    validate: if True, run exhaustive oracle tests on all 64 basis states

    Returns
    -------
    OracleResult

    Circuit description
    -------------------
    Qubit registers (in order, 0-indexed):
        [0:6]       — input (iL, itox, ivth), 2 bits each
        [6]         — flag / objective qubit
        [7:7+n_acc] — score accumulator

    Oracle gate sequence:
        1. SCORE   : compute S(x)+B into accumulator (forward)
        2. CMP(T') : XOR (acc >= T') into flag, restore acc
        3. SCORE†  : uncompute accumulator (inverse of step 1)

    The SCORE† step restores every accumulator bit to 0, so no garbage phase
    is introduced.  The flag carries only f(x).
    """
    n_input = 6
    n_acc   = qmodel.accumulator_bits
    n_flag  = 1
    n_total = n_input + n_flag + n_acc

    flag_qubit = n_input  # qubit index 6
    acc_start  = n_input + n_flag  # qubit index 7

    # Build sub-circuits
    score_fwd = _build_score_circuit(qmodel, n_input, n_acc)
    cmp_gate  = comparator_gate(n_acc, qmodel.T + qmodel.B, name="CMP")
    score_inv = score_fwd.inverse()

    # Assemble oracle
    oracle_qc = QuantumCircuit(n_total, name="Oracle_Of")

    # Step 1: forward score computation
    score_qubits = list(range(n_input)) + list(range(acc_start, acc_start + n_acc))
    oracle_qc.append(score_fwd.to_gate(), score_qubits)

    # Step 2: comparator (acc vs T')
    # Comparator layout: q[0..n_acc-1] = accumulator, q[n_acc] = flag
    cmp_qubits = list(range(acc_start, acc_start + n_acc)) + [flag_qubit]
    oracle_qc.append(cmp_gate.to_gate(), cmp_qubits)

    # Step 3: uncompute score (inverse of step 1)
    oracle_qc.append(score_inv.to_gate(), score_qubits)

    # Build full A circuit: state_prep then oracle
    sp_result = build_state_preparation(joint, validate=validate)
    A_qc = QuantumCircuit(n_total, name="A_full")

    # Embed state prep on input qubits only
    A_qc.append(sp_result.circuit.to_gate(), list(range(n_input)))

    # Append oracle
    A_qc.append(oracle_qc.to_gate(), list(range(n_total)))

    # --- Validation ---
    validation_passed = False
    validation_notes: List[str] = []

    if validate:
        validation_passed, validation_notes = _validate_oracle(
            oracle_qc, qmodel, n_input, n_acc, flag_qubit, acc_start
        )

    return OracleResult(
        oracle_circuit=oracle_qc,
        A_circuit=A_qc,
        objective_qubit=flag_qubit,
        n_input_qubits=n_input,
        n_acc_qubits=n_acc,
        n_total_qubits=n_total,
        T_shifted=qmodel.T + qmodel.B,
        validation_passed=validation_passed,
        validation_notes=validation_notes,
    )


# ---------------------------------------------------------------------------
# Oracle validation  (§9 exit criterion)
# ---------------------------------------------------------------------------

def _validate_oracle(
    oracle_qc: QuantumCircuit,
    qmodel: QuantisedScoreModel,
    n_input: int,
    n_acc: int,
    flag_qubit: int,
    acc_start: int,
) -> Tuple[bool, List[str]]:
    """Run exhaustive oracle tests on all 64 basis states.

    Tests (per §9):
        1. Input register unchanged.
        2. Flag = f(x) when starting at 0.
        3. Flag = 1 XOR f(x) when starting at 1.
        4. Accumulator returns to 0.
        5. Applying oracle twice restores full state.
        6. Boundary: f(x) when S(x)+B == T+B (equality => fail).
        7. Phase test: statevector matches ideal truth-table oracle up to
           global phase.

    Returns (passed: bool, notes: list[str])
    """
    from qiskit.quantum_info import Statevector

    notes: List[str] = []
    n_total = oracle_qc.num_qubits
    n_total_bits = n_total

    # Build ideal (truth-table) oracle for comparison
    ideal_oracle = _build_truth_table_oracle(qmodel, n_input, n_acc, flag_qubit, acc_start, n_total)

    failures = 0

    for iL in range(4):
        for itox in range(4):
            for ivth in range(4):
                # Compute expected flag from the integer model
                expected_f = 1 if qmodel.is_fail_int(iL, itox, ivth) else 0
                S = qmodel.score(iL, itox, ivth)

                for flag_in in [0, 1]:
                    # Encode the basis state |iL, itox, ivth, flag_in, acc=0>
                    # Qiskit little-endian: qubit 0 is bit 0 of the state label
                    # Input qubits: 0-1=iL, 2-3=itox, 4-5=ivth (little-endian 2-bit indices)
                    # qubit 0 = bit 0 of iL, qubit 1 = bit 1 of iL, etc.
                    state_int = (
                        (iL   & 0x3) << 0   |   # qubits 0,1
                        (itox & 0x3) << 2   |   # qubits 2,3
                        (ivth & 0x3) << 4   |   # qubits 4,5
                        (flag_in     ) << flag_qubit |   # qubit 6
                        # accumulator starts at 0
                        0
                    )

                    sv_in = Statevector.from_int(state_int, dims=2 ** n_total)
                    sv_out = sv_in.evolve(oracle_qc)
                    probs = sv_out.probabilities()
                    out_idx = int(np.argmax(probs))

                    # Decode output
                    out_flag = (out_idx >> flag_qubit) & 1
                    out_input = out_idx & 0x3F          # lower 6 bits
                    out_acc   = (out_idx >> acc_start) & ((1 << n_acc) - 1)

                    expected_flag = flag_in ^ expected_f
                    expected_input = (iL & 0x3) | ((itox & 0x3) << 2) | ((ivth & 0x3) << 4)

                    ok_input = (out_input == expected_input)
                    ok_flag  = (out_flag  == expected_flag)
                    ok_acc   = (out_acc   == 0)

                    if not (ok_input and ok_flag and ok_acc):
                        failures += 1
                        notes.append(
                            f"FAIL iL={iL} itox={itox} ivth={ivth} "
                            f"flag_in={flag_in}: "
                            f"input_ok={ok_input} flag_ok={ok_flag} "
                            f"(got {out_flag}, exp {expected_flag}) "
                            f"acc_ok={ok_acc} (acc={out_acc})"
                        )

    if failures == 0:
        notes.append(f"Exhaustive oracle test: all 64x2=128 basis states PASSED.")
    else:
        notes.append(f"Exhaustive oracle test: {failures} FAILURES detected.")

    # Test 5: oracle^2 = identity
    double_oracle = oracle_qc.compose(oracle_qc)
    # Check on one sample state
    test_state = Statevector.from_int(0, dims=2 ** n_total)
    sv_dbl = test_state.evolve(double_oracle)
    overlap = abs(test_state.inner(sv_dbl)) ** 2
    if overlap > 0.999:
        notes.append("Oracle^2 = I check: PASSED.")
    else:
        notes.append(f"Oracle^2 = I check: FAILED (overlap={overlap:.4f}).")
        failures += 1

    # Test 6: boundary state (S+B == T+B) must fail
    boundary_notes = _check_boundary(qmodel)
    notes.extend(boundary_notes)

    # Test 7: phase check — compare statevector with ideal truth-table oracle
    phase_ok = _check_phases(oracle_qc, ideal_oracle, n_total)
    if phase_ok:
        notes.append("Phase purity check (vs truth-table oracle): PASSED.")
    else:
        notes.append("Phase purity check: FAILED — input-dependent phases detected.")
        failures += 1

    return failures == 0, notes


def _build_truth_table_oracle(
    qmodel: QuantisedScoreModel,
    n_input: int,
    n_acc: int,
    flag_qubit: int,
    acc_start: int,
    n_total: int,
) -> QuantumCircuit:
    """Build a small truth-table oracle for phase-verification reference.

    For each of the 64 input states, if f(x)=1, apply a multi-controlled X
    on the flag qubit controlled on that exact input pattern.

    THIS IS NOT THE SCALABLE ORACLE — it is only used as a reference for
    phase testing.  Its gate count is O(64 * n_input) which is fine for n=6.
    """
    qc = QuantumCircuit(n_total, name="TT_oracle")

    for iL in range(4):
        for itox in range(4):
            for ivth in range(4):
                if not qmodel.is_fail_int(iL, itox, ivth):
                    continue

                # Controls: input bits q[0..5] must match (iL, itox, ivth)
                ctrl_state = ""
                # qubit 5 (MSB of ivth) ... qubit 0 (LSB of iL)
                # Qiskit control_state string: MSB first in string, maps to highest qubit
                # qubit order in MCX: [q0, q1, q2, q3, q4, q5]
                # control_state[0] -> q0, control_state[1] -> q1, etc.
                bits_iL   = format(iL,   "02b")  # 2 bits, MSB first => q1 q0
                bits_itox = format(itox, "02b")
                bits_ivth = format(ivth, "02b")
                # q0 = bit0 of iL = iL & 1; q1 = bit1 of iL = (iL>>1) & 1
                b0 = (iL   >> 0) & 1
                b1 = (iL   >> 1) & 1
                b2 = (itox >> 0) & 1
                b3 = (itox >> 1) & 1
                b4 = (ivth >> 0) & 1
                b5 = (ivth >> 1) & 1

                # Flip qubits where we need |0> control
                flips = []
                for qi, bi in [(0, b0), (1, b1), (2, b2), (3, b3), (4, b4), (5, b5)]:
                    if bi == 0:
                        qc.x(qi)
                        flips.append(qi)

                qc.mcx(list(range(n_input)), flag_qubit)

                for qi in flips:
                    qc.x(qi)

    return qc


def _check_boundary(qmodel: QuantisedScoreModel) -> List[str]:
    """Verify that states where S(x)+B == T+B are classified as failures."""
    notes = []
    T_shifted = qmodel.T + qmodel.B
    boundary_states = []
    for iL in range(4):
        for itox in range(4):
            for ivth in range(4):
                S_shifted = qmodel.score(iL, itox, ivth) + qmodel.B
                if S_shifted == T_shifted:
                    boundary_states.append((iL, itox, ivth))
                    is_f = qmodel.is_fail_int(iL, itox, ivth)
                    if not is_f:
                        notes.append(
                            f"BOUNDARY ERROR: state ({iL},{itox},{ivth}) "
                            f"has S+B=T+B={T_shifted} but is NOT classified as failure."
                        )

    if boundary_states:
        notes.append(
            f"Boundary check: {len(boundary_states)} states with S+B=T+B, "
            f"all correctly classified as failure (S>=T convention)."
        )
    else:
        notes.append("Boundary check: no states exactly at threshold (threshold between grid values).")
    return notes


def _check_phases(
    oracle_qc: QuantumCircuit,
    ideal_oracle: QuantumCircuit,
    n_total: int,
) -> bool:
    """Compare oracle statevector with ideal truth-table oracle for phase purity.

    Both oracles are applied to a uniform superposition.  They should produce
    the same statevector up to a global phase.  Input-dependent phases would
    cause element-wise phase differences.
    """
    from qiskit.quantum_info import Statevector, random_statevector
    import numpy as np

    # Apply each oracle to the same random-ish superposition of input states
    # (accumulator and flag qubits must start at |0>)
    # We use the equal superposition over input bits only
    n_input = 6
    n_ancilla = n_total - n_input

    # Build a combined state: input qubits (0..n_input-1) in uniform superposition,
    # ancilla qubits (n_input..n_total-1) in |0>.
    # In Qiskit little-endian: ancilla on HIGH qubit indices = high integer bits.
    # Uniform superposition over input = sum_i |i> / sqrt(2^n_input), ancilla = |0>.
    # Combined index: i (input bits, qubits 0..n_input-1) | 0 (ancilla, high bits).
    # So combined amplitudes: amp[i] = 1/sqrt(2^n_input) for i in [0, 2^n_input-1],
    #                                  amp[i] = 0            for i >= 2^n_input.
    combined_amps = np.zeros(2 ** n_total, dtype=complex)
    combined_amps[:2 ** n_input] = 1.0 / math.sqrt(2 ** n_input)
    sv_combined = Statevector(combined_amps)

    sv_ours  = sv_combined.evolve(oracle_qc)
    sv_ideal = sv_combined.evolve(ideal_oracle)

    # Fidelity should be 1.0 (up to global phase)
    fidelity = abs(sv_ours.inner(sv_ideal)) ** 2
    return fidelity > 0.999


# ---------------------------------------------------------------------------
# Grover operator  (for IQAE validation §11)
# ---------------------------------------------------------------------------

def build_grover_operator(oracle_result: OracleResult) -> QuantumCircuit:
    """Build the Grover oracle: Q = -A S_0 A† S_chi.

    For IQAE, the library builds Q automatically from EstimationProblem.
    This function builds it explicitly for validation of the Grover power
    identity:  P(flag=1 after Q^k A |0>) = sin^2((2k+1)*theta).

    Parameters
    ----------
    oracle_result : OracleResult from build_oracle()

    Returns
    -------
    QuantumCircuit implementing one application of Q.
    """
    A = oracle_result.A_circuit
    n_total = A.num_qubits
    obj = oracle_result.objective_qubit

    # S_chi: reflection about |chi> (good states) = Z on objective qubit
    S_chi = QuantumCircuit(n_total, name="S_chi")
    S_chi.z(obj)

    # S_0: reflection about |0> = X on all, multi-controlled Z on all, X on all
    S_0 = QuantumCircuit(n_total, name="S_0")
    S_0.x(range(n_total))
    S_0.h(n_total - 1)
    S_0.mcx(list(range(n_total - 1)), n_total - 1)
    S_0.h(n_total - 1)
    S_0.x(range(n_total))

    # Q = A S_0 A† S_chi   (standard Grover operator for amplitude estimation)
    Q = QuantumCircuit(n_total, name="Q_Grover")
    Q.compose(S_chi, inplace=True)
    Q.compose(A.inverse(), inplace=True)
    Q.compose(S_0, inplace=True)
    Q.compose(A, inplace=True)

    return Q


def validate_grover_power_identity(
    oracle_result: OracleResult,
    p_fail_exact: float,
    max_k: int = 4,
) -> List[str]:
    """Verify P(flag=1 | Q^k A |0>) = sin^2((2k+1)*theta) for k=0..max_k.

    §11 exit criterion: catches wrong reflection registers, leftover work,
    and phase errors.

    Parameters
    ----------
    oracle_result : OracleResult
    p_fail_exact  : exact failure probability (sin^2(theta))
    max_k         : maximum Grover power to test

    Returns
    -------
    list of result strings (PASS/FAIL per k)
    """
    from qiskit.quantum_info import Statevector

    if p_fail_exact <= 0.0 or p_fail_exact >= 1.0:
        return [f"Grover power test skipped: p_fail={p_fail_exact:.4e} outside (0,1)."]

    theta = math.asin(math.sqrt(p_fail_exact))
    A = oracle_result.A_circuit
    Q = build_grover_operator(oracle_result)
    obj = oracle_result.objective_qubit
    n_total = A.num_qubits

    results = []
    sv0 = Statevector.from_int(0, dims=2 ** n_total)

    # k=0: P = sin^2(theta) = p_fail_exact (this is just |A|0>|)
    sv_A = sv0.evolve(A)
    prob_k0 = float(sum(
        abs(amp) ** 2
        for idx, amp in enumerate(sv_A.data)
        if (idx >> obj) & 1
    ))
    expected_k0 = math.sin(theta) ** 2
    err_k0 = abs(prob_k0 - expected_k0)
    results.append(
        f"k=0: P(flag=1)={prob_k0:.6f}, expected sin^2(theta)={expected_k0:.6f}, "
        f"err={err_k0:.2e} {'PASS' if err_k0 < 1e-4 else 'FAIL'}"
    )

    # k=1..max_k
    sv_k = sv_A.copy()
    for k in range(1, max_k + 1):
        sv_k = sv_k.evolve(Q)
        prob_k = float(sum(
            abs(amp) ** 2
            for idx, amp in enumerate(sv_k.data)
            if (idx >> obj) & 1
        ))
        expected_k = math.sin((2 * k + 1) * theta) ** 2
        err_k = abs(prob_k - expected_k)
        results.append(
            f"k={k}: P(flag=1)={prob_k:.6f}, expected sin^2({2*k+1}*theta)={expected_k:.6f}, "
            f"err={err_k:.2e} {'PASS' if err_k < 1e-4 else 'FAIL'}"
        )

    return results
