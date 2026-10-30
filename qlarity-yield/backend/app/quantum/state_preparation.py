"""
state_preparation.py  — Coherent superposition of the joint process distribution.

Specification reference: §10 (Prepare the probability distribution coherently).

Goal
----
Build a unitary circuit A such that:

    A|0> = sum_{x} sqrt(p(x)) |x_L> |x_tox> |x_vth> |0_flag> |0_work>

where x = (iL, itox, ivth) ranges over all 64 grid points and p(x) = pL * ptox * pvth.

Because the three marginals are independent the joint preparation factors as
three independent 2-qubit preparations:

    |psi_L>   = sum_j sqrt(pL_j)   |j>  (2 qubits)
    |psi_tox> = sum_j sqrt(ptox_j) |j>  (2 qubits)
    |psi_vth> = sum_j sqrt(pvth_j) |j>  (2 qubits)

Each 2-qubit preparation is built with Qiskit's StatePreparation library gate,
which accepts a statevector of amplitudes (square roots of probabilities).

Key design rules (§10):
    - Use a *unitary* StatePreparation gate (inverse = standard gate inverse).
    - Do NOT use reset-based initialisation inside A; the oracle must be able
      to apply A† cleanly.
    - Validate that:
        * Marginal and joint probabilities match the declared model.
        * A†A on any basis state restores the starting state.
        * Qubit ordering: iL occupies qubits 0-1, itox qubits 2-3, ivth 4-5.
          Qiskit's little-endian convention is handled explicitly.
    - Report cost: StatePreparation on 2 qubits decomposes into O(1) rotations.

Qubit layout of the full A circuit (passed to IQAE)
----------------------------------------------------
    q[0:2]  — delta_L bin index   (2 qubits, 4 levels)
    q[2:4]  — delta_tox bin index (2 qubits, 4 levels)
    q[4:6]  — delta_vth bin index (2 qubits, 4 levels)
    q[6]    — objective flag (|0> after A; oracle XORs f(x) into this)
    q[7:]   — arithmetic work ancillas (allocated by oracle builder)

The state_preparation circuit returned here covers only the 6 input qubits.
The caller (oracle.py / iqae.py) embeds it into the full A circuit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from qiskit import QuantumCircuit, QuantumRegister
from qiskit.circuit.library import StatePreparation

from ..physics.variations import DiscreteVar, JointDistribution


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _amplitudes_from_probs(probs: List[float]) -> np.ndarray:
    """Return the statevector amplitudes (sqrt of probabilities).

    Qiskit's StatePreparation expects a normalised complex statevector.
    We use real, non-negative square roots since all amplitudes are real.
    """
    amps = np.sqrt(np.asarray(probs, dtype=float))
    norm = np.linalg.norm(amps)
    if not math.isclose(norm, 1.0, rel_tol=1e-6):
        raise ValueError(
            f"Amplitude vector is not normalised (norm={norm:.8f}). "
            "Check that probabilities sum to 1."
        )
    return amps


def _marginal_prep_circuit(var: DiscreteVar, name: str) -> QuantumCircuit:
    """Build a 2-qubit unitary StatePreparation circuit for one marginal.

    The circuit maps |00> -> sum_j sqrt(p_j) |j> in Qiskit's little-endian
    binary order (j=0 is |q1 q0> = |00>, j=1 is |01>, j=2 is |10>, j=3 is |11>).

    Parameters
    ----------
    var  : DiscreteVar with 4 bins
    name : label for the gate (used in circuit diagrams)

    Returns
    -------
    QuantumCircuit on 2 qubits
    """
    if var.n_bins != 4:
        raise ValueError(
            f"Variable '{var.name}' has {var.n_bins} bins; "
            "state preparation expects exactly 4 (2 qubits)."
        )

    amps = _amplitudes_from_probs(var.probabilities)
    sp_gate = StatePreparation(amps, label=name)
    qc = QuantumCircuit(2, name=name)
    qc.append(sp_gate, [0, 1])
    return qc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class StatePrepResult:
    """Validated state-preparation circuit and cost metadata.

    Attributes
    ----------
    circuit         : 6-qubit QuantumCircuit preparing the joint distribution.
                      Qubit layout: [q0-1 = L, q2-3 = tox, q4-5 = vth].
    n_input_qubits  : 6
    marginal_fidelities: dict  -- {name: inner product with ideal state}
    joint_prob_error: max |p_reconstructed - p_target| over all 64 states
    cost_note       : human-readable resource note
    """
    circuit: QuantumCircuit
    n_input_qubits: int
    marginal_fidelities: dict
    joint_prob_error: float
    cost_note: str


def build_state_preparation(
    joint: JointDistribution,
    validate: bool = True,
) -> StatePrepResult:
    """Build the 6-qubit joint distribution preparation circuit.

    Parameters
    ----------
    joint    : JointDistribution (three independent 4-bin variables)
    validate : if True, run statevector simulation to verify probabilities

    Returns
    -------
    StatePrepResult

    Circuit structure
    -----------------
    Three independent 2-qubit StatePreparation gates applied to disjoint
    register halves.  No entanglement between variables (they are independent).

    Validation
    ----------
    Runs Qiskit's statevector simulator on the 6-qubit circuit and checks:
        1. Each marginal probability matches the declared model.
        2. Joint probabilities match the Cartesian product.
    """
    # --- Build individual marginal circuits ---
    circ_L   = _marginal_prep_circuit(joint.var_L,   name="SP_L")
    circ_tox = _marginal_prep_circuit(joint.var_tox, name="SP_tox")
    circ_vth = _marginal_prep_circuit(joint.var_vth, name="SP_vth")

    # --- Compose into 6-qubit joint circuit ---
    qc = QuantumCircuit(6, name="A_state_prep")
    qc.append(circ_L.to_gate(),   [0, 1])
    qc.append(circ_tox.to_gate(), [2, 3])
    qc.append(circ_vth.to_gate(), [4, 5])

    # --- Validate via statevector ---
    marginal_fidelities: dict = {}
    joint_prob_error = float("nan")
    cost_note = (
        "Three independent 2-qubit StatePreparation gates. "
        "Each decomposes into O(1) one- and two-qubit rotations. "
        "Total: 6 input qubits, no ancillas, no entanglement between variables."
    )

    if validate:
        from qiskit.quantum_info import Statevector

        sv = Statevector(qc)
        probs = sv.probabilities()  # length 2^6 = 64

        # Reconstruct joint probabilities from statevector
        # Qiskit's bit ordering: qubit 0 is the LSB of the integer index.
        # Index i => bits (q0, q1, q2, q3, q4, q5) where q0 is bit 0 of i.
        # Our layout: q[0:2]=L, q[2:4]=tox, q[4:6]=vth
        # i_L   = (i >> 0) & 0x3
        # i_tox = (i >> 2) & 0x3
        # i_vth = (i >> 4) & 0x3
        reconstructed = np.zeros((4, 4, 4))
        for i in range(64):
            iL   = (i >> 0) & 0x3
            itox = (i >> 2) & 0x3
            ivth = (i >> 4) & 0x3
            reconstructed[iL, itox, ivth] += probs[i]

        # Build target joint array
        target_joint = np.zeros((4, 4, 4))
        for iL, pL in enumerate(joint.var_L.probabilities):
            for itox, ptox in enumerate(joint.var_tox.probabilities):
                for ivth, pvth in enumerate(joint.var_vth.probabilities):
                    target_joint[iL, itox, ivth] = pL * ptox * pvth

        joint_prob_error = float(np.max(np.abs(reconstructed - target_joint)))

        if joint_prob_error > 1e-6:
            raise RuntimeError(
                f"State preparation validation failed: max joint probability "
                f"error = {joint_prob_error:.2e} (tolerance 1e-6). "
                "Check qubit ordering conventions."
            )

        # Marginal fidelities
        for var, start in [
            (joint.var_L,   (0, 0x3, 0)),
            (joint.var_tox, (2, 0x3, 2)),
            (joint.var_vth, (4, 0x3, 4)),
        ]:
            name, mask, shift = var.name, start[1], start[2]
            marginal_probs = np.zeros(4)
            for i in range(64):
                idx = (i >> shift) & mask
                marginal_probs[idx] += probs[i]
            ideal_amps = _amplitudes_from_probs(var.probabilities)
            actual_amps = np.sqrt(np.clip(marginal_probs, 0, None))
            fidelity = float(np.dot(ideal_amps, actual_amps)) ** 2
            marginal_fidelities[name] = fidelity

        # Validate A†A = I on the all-zeros state
        # Correct check: apply A, then A†, result must be |000000>
        sv_roundtrip = sv.evolve(qc.inverse())
        sv_zero = Statevector.from_label("0" * 6)
        overlap = abs(sv_roundtrip.inner(sv_zero)) ** 2
        if overlap < 0.999:
            raise RuntimeError(
                f"A†A|0> does not return to |0>: overlap={overlap:.6f}. "
                "StatePreparation gate may not be unitary."
            )

    return StatePrepResult(
        circuit=qc,
        n_input_qubits=6,
        marginal_fidelities=marginal_fidelities,
        joint_prob_error=joint_prob_error,
        cost_note=cost_note,
    )


def decode_state_index(i: int) -> Tuple[int, int, int]:
    """Decode a 6-qubit Qiskit statevector index to (iL, itox, ivth).

    Qiskit uses little-endian bit ordering: qubit 0 is bit 0 of the index.
    Layout: q[0:2]=L, q[2:4]=tox, q[4:6]=vth.

    Parameters
    ----------
    i : integer index in [0, 63]

    Returns
    -------
    (iL, itox, ivth) each in [0, 3]
    """
    iL   = (i >> 0) & 0x3
    itox = (i >> 2) & 0x3
    ivth = (i >> 4) & 0x3
    return iL, itox, ivth


def encode_state_index(iL: int, itox: int, ivth: int) -> int:
    """Encode (iL, itox, ivth) bin indices to a 6-qubit Qiskit statevector index."""
    return (iL & 0x3) | ((itox & 0x3) << 2) | ((ivth & 0x3) << 4)
