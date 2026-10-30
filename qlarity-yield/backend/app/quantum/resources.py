"""
resources.py  — Circuit resource analysis and transpilation summary.

Specification reference: §13 (Resource accounting and meaningful evaluation),
§14 (Noise and hardware stage — transpilation).

Reports for every circuit:
    - Width (total qubits)
    - Depth (gate layers)
    - Gate counts by type
    - Two-qubit gate count (CNOT/CX equivalent)
    - Transpiled versions for basis gate sets

This module is used by the API and UI to display circuit resource summaries
*before* launching expensive simulation runs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from qiskit import QuantumCircuit, transpile
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager


# ---------------------------------------------------------------------------
# Resource record
# ---------------------------------------------------------------------------

@dataclass
class CircuitResources:
    """Resource summary for a quantum circuit.

    Attributes
    ----------
    circuit_name        : label for the circuit
    n_qubits            : total qubit count
    depth_raw           : gate-layer depth before transpilation
    gate_counts_raw     : dict of {gate_name: count} before transpilation
    n_2q_raw            : two-qubit gate count before transpilation
    depth_transpiled    : depth after transpilation to basis gates
    gate_counts_transpiled: gate counts after transpilation
    n_2q_transpiled     : two-qubit gate count after transpilation
    basis_gates         : basis gate set used for transpilation
    statevector_memory_bytes: estimated memory for statevector simulation
    statevector_memory_mb   : same in MB
    notes               : list of advisory notes
    """
    circuit_name: str
    n_qubits: int
    depth_raw: int
    gate_counts_raw: Dict[str, int]
    n_2q_raw: int
    depth_transpiled: Optional[int] = None
    gate_counts_transpiled: Optional[Dict[str, int]] = None
    n_2q_transpiled: Optional[int] = None
    basis_gates: Optional[List[str]] = None
    statevector_memory_bytes: int = 0
    statevector_memory_mb: float = 0.0
    notes: List[str] = field(default_factory=list)

    def summary_dict(self) -> dict:
        return {
            "circuit_name": self.circuit_name,
            "n_qubits": self.n_qubits,
            "depth_raw": self.depth_raw,
            "n_2q_raw": self.n_2q_raw,
            "depth_transpiled": self.depth_transpiled,
            "n_2q_transpiled": self.n_2q_transpiled,
            "statevector_memory_mb": round(self.statevector_memory_mb, 2),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Two-qubit gate identification
# ---------------------------------------------------------------------------

_TWO_QUBIT_GATES = {
    "cx", "cz", "cy", "ch", "swap", "ecr", "rzz", "rxx", "ryy",
    "crx", "cry", "crz", "cp", "cu", "csx",
    "ccx", "mcx", "c3x", "c4x",  # multi-qubit (count as 2q for simplicity)
}


def _count_2q_gates(qc: QuantumCircuit) -> int:
    """Count two-qubit (and multi-qubit) gate operations in a circuit."""
    count = 0
    for instr in qc.data:
        if len(instr.qubits) >= 2:
            count += 1
    return count


def _gate_counts(qc: QuantumCircuit) -> Dict[str, int]:
    """Count gates by name in a decomposed circuit."""
    counts: Dict[str, int] = {}
    for instr in qc.data:
        name = instr.operation.name
        counts[name] = counts.get(name, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def analyze_circuit(
    qc: QuantumCircuit,
    circuit_name: str = "circuit",
    transpile_basis: Optional[List[str]] = None,
    transpile_optimization_level: int = 1,
) -> CircuitResources:
    """Analyze a QuantumCircuit and return its resource summary.

    Parameters
    ----------
    qc                          : the circuit to analyze
    circuit_name                : label for the summary
    transpile_basis             : basis gate set for transpilation.
                                  None => skip transpilation.
                                  Common choices:
                                    ['cx', 'rz', 'sx', 'x']  (IBM-like)
                                    ['ecr', 'rz', 'sx', 'x'] (IBM Eagle)
    transpile_optimization_level: 0-3 (passed to Qiskit transpiler)

    Returns
    -------
    CircuitResources
    """
    n_qubits = qc.num_qubits

    # Raw metrics (without decomposition of compound gates)
    try:
        depth_raw = qc.depth()
    except Exception:
        depth_raw = -1

    # Decompose to get primitive gate counts
    try:
        qc_decomposed = qc.decompose(reps=3)
        raw_counts = _gate_counts(qc_decomposed)
        n_2q_raw = _count_2q_gates(qc_decomposed)
    except Exception as e:
        raw_counts = {}
        n_2q_raw = -1

    # Memory estimate for statevector simulation
    # complex128: 16 bytes per amplitude, 2^n amplitudes
    mem_bytes = 16 * (2 ** n_qubits)
    mem_mb = mem_bytes / (1024 ** 2)

    notes = []
    if mem_mb > 1024:
        notes.append(
            f"WARNING: statevector simulation requires ~{mem_mb/1024:.1f} GB of RAM. "
            "Do not run on a small server."
        )
    elif mem_mb > 128:
        notes.append(
            f"CAUTION: statevector requires ~{mem_mb:.0f} MB RAM."
        )

    if n_qubits > 25:
        notes.append(
            f"Circuit has {n_qubits} qubits. Statevector simulation is infeasible "
            "on standard hardware. Consider AerSimulator with matrix_product_state method."
        )

    # Transpilation
    depth_t = None
    counts_t = None
    n_2q_t = None
    basis_used = transpile_basis

    if transpile_basis is not None:
        try:
            qc_t = transpile(
                qc,
                basis_gates=transpile_basis,
                optimization_level=transpile_optimization_level,
            )
            depth_t = qc_t.depth()
            counts_t = _gate_counts(qc_t)
            n_2q_t = _count_2q_gates(qc_t)
            notes.append(
                f"Transpiled to {transpile_basis} (opt level {transpile_optimization_level}): "
                f"depth={depth_t}, 2q gates={n_2q_t}."
            )
        except Exception as e:
            notes.append(f"Transpilation failed: {e}")

    return CircuitResources(
        circuit_name=circuit_name,
        n_qubits=n_qubits,
        depth_raw=depth_raw,
        gate_counts_raw=raw_counts,
        n_2q_raw=n_2q_raw,
        depth_transpiled=depth_t,
        gate_counts_transpiled=counts_t,
        n_2q_transpiled=n_2q_t,
        basis_gates=basis_used,
        statevector_memory_bytes=mem_bytes,
        statevector_memory_mb=mem_mb,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Full pipeline resource report
# ---------------------------------------------------------------------------

def build_resource_report(
    oracle_result,  # OracleResult (avoid circular import by using Any)
    transpile_basis: Optional[List[str]] = None,
) -> Dict:
    """Build a complete resource report for all circuits in the pipeline.

    Parameters
    ----------
    oracle_result   : OracleResult from oracle.py
    transpile_basis : optional basis gate set for transpilation analysis

    Returns
    -------
    dict with keys: 'oracle', 'A_circuit', 'summary', 'notes'
    """
    oracle_res = analyze_circuit(
        oracle_result.oracle_circuit,
        circuit_name="Oracle O_f",
        transpile_basis=transpile_basis,
    )
    A_res = analyze_circuit(
        oracle_result.A_circuit,
        circuit_name="Full A circuit",
        transpile_basis=transpile_basis,
    )

    # Grover circuit Q (one application)
    try:
        from .oracle import build_grover_operator
        Q = build_grover_operator(oracle_result)
        Q_res = analyze_circuit(Q, circuit_name="Grover Q", transpile_basis=transpile_basis)
    except Exception:
        Q_res = None

    report = {
        "oracle": oracle_res.summary_dict(),
        "A_circuit": A_res.summary_dict(),
        "grover_Q": Q_res.summary_dict() if Q_res else None,
        "layout": {
            "n_input_qubits": oracle_result.n_input_qubits,
            "n_acc_qubits": oracle_result.n_acc_qubits,
            "flag_qubit_index": oracle_result.objective_qubit,
            "n_total_qubits": oracle_result.n_total_qubits,
            "T_shifted": oracle_result.T_shifted,
        },
        "memory_budget": {
            "statevector_mb": round(A_res.statevector_memory_mb, 2),
            "statevector_gb": round(A_res.statevector_memory_mb / 1024, 3),
        },
        "notes": oracle_res.notes + A_res.notes,
    }
    return report


# ---------------------------------------------------------------------------
# Shot budget estimator
# ---------------------------------------------------------------------------

def estimate_shot_budget(
    epsilon_target: float,
    alpha: float,
    p_fail_guess: float,
) -> Dict:
    """Estimate IQAE shot budget before running.

    Uses the known IQAE complexity: total queries ~ O(1/epsilon * log(1/alpha)).
    This is a rough upper bound; actual count depends on the specific instance.

    Parameters
    ----------
    epsilon_target  : amplitude error target
    alpha           : confidence level
    p_fail_guess    : approximate failure probability (for context)

    Returns
    -------
    dict with estimated NA, notes
    """
    # IQAE theoretical query complexity
    # From Brassard et al.: O(1/epsilon * log(log(1/epsilon) / alpha))
    log_term = math.log(math.log(1.0 / epsilon_target + 1) / alpha + 1) + 1
    NA_upper = int(math.ceil(math.pi / (8 * epsilon_target) * log_term))

    # Implied probability error (approx)
    # For amplitude a = sqrt(p), delta_a = epsilon => delta_p ~ 2*sqrt(p)*epsilon
    p_error_implied = 2.0 * math.sqrt(max(p_fail_guess, 1e-6)) * epsilon_target

    return {
        "epsilon_target_amplitude": epsilon_target,
        "alpha": alpha,
        "p_fail_guess": p_fail_guess,
        "NA_upper_bound": NA_upper,
        "implied_p_fail_error_approx": p_error_implied,
        "note": (
            "NA is a theoretical upper bound; actual IQAE uses fewer queries "
            "when the estimate converges quickly."
        ),
    }
