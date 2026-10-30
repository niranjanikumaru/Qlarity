"""
arithmetic.py  — Reversible integer arithmetic primitives.

Specification reference: §8, §9 (reversible adders, comparator).

Purpose
-------
Provide tested, clean reversible arithmetic gates used by the oracle:
    1. _qft_add_constant_gate  — adds a non-negative integer constant c
       to an n-bit quantum register (no controls, no ancilla).
    2. controlled_constant_adder — same, conditioned on n_controls control qubits.
    3. comparator_gate  — sets flag qubit to 1 iff register >= T
       (equality counts as failure, per spec §5).

Design: QFT-based (Draper/Beauregard) constant adder
------------------------------------------------------
References:
    T. Draper, "Addition on a Quantum Computer", arXiv:quant-ph/0008033 (2000).
    S. Beauregard, "Circuit for Shor's algorithm using 2n+3 qubits",
    arXiv:quant-ph/0205095 (2002).

Convention
----------
Qiskit uses little-endian bit ordering: qubit 0 is the LSB of the integer
register index.  The QFT gates must include their SWAP reversal (do_swaps=True
for the deprecated QFT class, or use QFTGate which is correct by default)
so that the computational basis integer ordering matches Statevector indexing.

Concretely: QFTGate(n)|j⟩ = (1/√2^n) Σ_k exp(2πi*j*k/2^n)|k⟩
applied in the standard Qiskit little-endian convention.  Adding constant c
then amounts to phase rotation Rz(2π*c*2^k/2^n) on qubit k in the Fourier
basis, followed by inverse QFT.

Correctness guarantee
---------------------
Both the adder and comparator include exhaustive basis-state test functions
(verify_adder, verify_comparator) that the test suite calls for n=2 and n=3.
"""

from __future__ import annotations

import math
from typing import List

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFTGate   # non-deprecated in Qiskit 2.x


# ---------------------------------------------------------------------------
# QFT-based constant adder  (no ancilla, no controls)
# ---------------------------------------------------------------------------

def _qft_add_constant_gate(n_bits: int, c: int, name: str = "ADD") -> QuantumCircuit:
    """Return an n-qubit circuit: |r⟩ → |(r + c) mod 2^n⟩.

    Uses the Draper phase-rotation adder.  Zero ancilla qubits.

    Qubit convention: qubit 0 = LSB of the integer (Qiskit little-endian).
    QFTGate is used (replaces deprecated QFT class) and its built-in swap
    layer handles the bit-reversal so arithmetic respects the integer ordering.

    Parameters
    ----------
    n_bits : register width (bits)
    c      : non-negative integer constant; taken mod 2^n_bits
    name   : gate label

    Returns
    -------
    QuantumCircuit on n_bits qubits.
    """
    c = int(c) % (2 ** n_bits)
    qc = QuantumCircuit(n_bits, name=f"{name}({c})")
    if c == 0:
        return qc  # identity

    # QFTGate includes swap layer by default (correct integer convention)
    qc.append(QFTGate(n_bits), range(n_bits))

    # Phase rotations: for qubit k, phase is 2π * c * 2^k / 2^n
    # In the QFT basis (with swaps) qubit k carries weight 2^k.
    for k in range(n_bits):
        angle = 2.0 * math.pi * c * (2 ** k) / (2 ** n_bits)
        if abs(angle % (2 * math.pi)) > 1e-12:
            qc.p(angle, k)

    # Inverse QFT (includes inverse swap layer)
    qc.append(QFTGate(n_bits).inverse(), range(n_bits))

    return qc


# ---------------------------------------------------------------------------
# Controlled constant adder  (n_controls control qubits + n_bits register)
# ---------------------------------------------------------------------------

def controlled_constant_adder(
    n_bits: int,
    c: int,
    n_controls: int = 1,
    name: str = "CADD",
) -> QuantumCircuit:
    """Return a (n_controls + n_bits)-qubit circuit.

    When ALL control qubits are |1⟩, adds c to the register.
    Otherwise, leaves everything unchanged.

    Qubit layout:
        q[0 .. n_controls-1]        : control qubits (unchanged)
        q[n_controls .. total-1]    : n_bits-wide register

    Method: apply QFTGate to register, then condition each phase rotation
    on all control qubits (multi-controlled P), then inverse QFTGate.

    For n_controls=2 the controlled-P gates are doubly-controlled.
    Qiskit decomposes these natively.
    """
    c = int(c) % (2 ** n_bits)
    total = n_controls + n_bits
    qc = QuantumCircuit(total, name=f"{name}({c})")
    if c == 0:
        return qc

    ctrl_qubits = list(range(n_controls))
    reg_qubits  = list(range(n_controls, total))

    # QFT on register
    qc.append(QFTGate(n_bits), reg_qubits)

    # Multi-controlled phase rotations
    for k in range(n_bits):
        angle = 2.0 * math.pi * c * (2 ** k) / (2 ** n_bits)
        if abs(angle % (2 * math.pi)) < 1e-12:
            continue

        # Build a (1+n_controls)-qubit circuit with one P gate, then control it
        # Use Qiskit's built-in gate.control() method
        target_idx = reg_qubits[k]
        if n_controls == 1:
            qc.cp(angle, ctrl_qubits[0], target_idx)
        elif n_controls == 2:
            # Doubly-controlled P: decompose as CCP
            # Qiskit 2.x: use PhaseGate.control(2)
            from qiskit.circuit.library import PhaseGate
            ccp = PhaseGate(angle).control(2)
            qc.append(ccp, ctrl_qubits + [target_idx])
        else:
            # General multi-controlled P via gate.control()
            from qiskit.circuit.library import PhaseGate
            mcp = PhaseGate(angle).control(n_controls)
            qc.append(mcp, ctrl_qubits + [target_idx])

    # Inverse QFT on register
    qc.append(QFTGate(n_bits).inverse(), reg_qubits)

    return qc


# ---------------------------------------------------------------------------
# Comparator:  |r⟩|flag⟩ → |r⟩|flag XOR (r >= T)⟩
# ---------------------------------------------------------------------------

def comparator_gate(n_bits: int, T: int, name: str = "CMP") -> QuantumCircuit:
    """Return a (n_bits + 1)-qubit circuit: |r⟩|flag⟩ → |r⟩|flag XOR (r >= T)⟩.

    The register is restored exactly after the comparison.
    Equality (r == T) produces flag XOR 1 (failure, per spec §5).

    Qubit layout:
        q[0 .. n_bits-1] : register r   (unchanged after gate)
        q[n_bits]        : flag qubit   (XOR'd with (r >= T))

    Method (carry-overflow comparator):
    ------------------------------------
    To test r >= T without ancilla, we use the fact that in n-bit arithmetic:

        r >= T   iff   (r + (2^n - T)) mod 2^n produces carry-out

    We detect the carry-out by treating the flag qubit as an extra MSB
    (extending the register to n+1 bits):

        1. Let extended_reg = [r_bits, flag_bit]  (flag_bit = bit n, weight 2^n).
        2. Add (2^n - T) mod 2^(n+1) to the (n+1)-wide extended register.
           When flag starts at |0⟩, the carry into position n sets flag to 1
           iff r + (2^n - T) >= 2^n, i.e. iff r >= T.
        3. Now flag = (r >= T) XOR flag_original.
        4. Restore the lower n bits: add T mod 2^n to only the lower register.
           This undoes step 2 on the lower bits (since (2^n - T) + T = 2^n ≡ 0 mod 2^n).
           The flag bit is left as-is (it now holds the comparison result XOR'd with flag_in).

    Correctness: extensively verified in test suite (verify_comparator).

    Note on qubit ordering
    ----------------------
    For the (n+1)-bit addition in step 2, we treat:
        qubit 0..n-1 = lower register bits (weight 2^0 .. 2^(n-1))
        qubit n      = flag bit (weight 2^n)
    This matches Qiskit's little-endian convention, so the (n+1)-qubit
    _qft_add_constant_gate operates correctly.
    """
    T = int(T)
    n = n_bits
    total = n + 1

    # Handle edge cases where T is outside the representable range.
    # An n-bit register holds r in [0, 2^n-1].
    if T >= 2 ** n:
        # r < 2^n <= T always  =>  comparison is always False  =>  no-op
        return QuantumCircuit(total, name=f"{name}(>={T})")
    if T <= 0:
        # r >= 0 always  =>  comparison is always True  =>  flip flag unconditionally
        qc = QuantumCircuit(total, name=f"{name}(>=0)")
        qc.x(n)   # flag qubit = qubit index n
        return qc

    # The complement to add in (n+1)-bit space: (2^n - T) as an (n+1)-bit integer
    complement_n1 = 2 ** n - T          # in [1, 2^n - 1], fits in (n+1) bits
    # What to add back to restore lower n bits after the (n+1)-bit addition
    restore_c = T                        # in [1, 2^n - 1]

    qc = QuantumCircuit(total, name=f"{name}(>={T})")

    reg_qubits  = list(range(n))
    flag_qubit  = n

    # Step 1: add (2^n - T) to the full (n+1)-qubit extended register [r, flag]
    adder_full = _qft_add_constant_gate(n + 1, complement_n1, name="ADD_comp")
    qc.append(adder_full.to_gate(), list(range(n + 1)))

    # Step 2: restore lower n bits by adding T mod 2^n to the register only
    if restore_c != 0:
        adder_restore = _qft_add_constant_gate(n, restore_c, name="ADD_T")
        qc.append(adder_restore.to_gate(), reg_qubits)

    return qc


# ---------------------------------------------------------------------------
# Exhaustive correctness verification
# ---------------------------------------------------------------------------

def verify_adder(n_bits: int, c: int) -> bool:
    """Exhaustive test: |r⟩ → |(r+c) mod 2^n⟩ for every r in [0, 2^n-1].

    Returns True or raises AssertionError with details.
    """
    from qiskit.quantum_info import Statevector

    gate = _qft_add_constant_gate(n_bits, c)
    mod = 2 ** n_bits

    for r in range(mod):
        sv = Statevector.from_int(r, dims=mod)
        sv_out = sv.evolve(gate)
        measured = int(np.argmax(sv_out.probabilities()))
        expected = (r + c) % mod
        if measured != expected:
            raise AssertionError(
                f"Adder(n={n_bits}, c={c}): input {r} -> {measured} "
                f"(expected {expected})"
            )
    return True


def verify_comparator(n_bits: int, T: int) -> bool:
    """Exhaustive test of the comparator on all inputs.

    Tests:
        |r⟩|0⟩ → |r⟩|(r >= T)⟩
        |r⟩|1⟩ → |r⟩|NOT(r >= T)⟩   (XOR semantics)
        Register is unchanged.
        Equality r == T gives flag = 1.

    Returns True or raises AssertionError.
    """
    from qiskit.quantum_info import Statevector

    gate = comparator_gate(n_bits, T)
    mod = 2 ** n_bits
    total = 2 ** (n_bits + 1)

    for r in range(mod):
        for flag_in in [0, 1]:
            # State |r, flag_in⟩ in little-endian:
            # qubit 0 = bit 0 of r, ..., qubit n_bits-1 = bit n_bits-1 of r,
            # qubit n_bits = flag_in
            # Integer index: r | (flag_in << n_bits)
            state_idx = r | (flag_in << n_bits)
            sv = Statevector.from_int(state_idx, dims=total)
            sv_out = sv.evolve(gate)
            measured_idx = int(np.argmax(sv_out.probabilities()))

            out_reg  = measured_idx & (mod - 1)          # lower n bits
            out_flag = (measured_idx >> n_bits) & 1      # bit n

            expected_flag = flag_in ^ (1 if r >= T else 0)

            if out_reg != r or out_flag != expected_flag:
                raise AssertionError(
                    f"Comparator(n={n_bits}, T={T}): "
                    f"input r={r}, flag_in={flag_in} -> "
                    f"reg={out_reg} (expected {r}), "
                    f"flag={out_flag} (expected {expected_flag})"
                )
    return True
