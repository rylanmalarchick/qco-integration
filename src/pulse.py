"""Pulse-level fidelity via per-gate Lindblad master-equation simulation.

Each gate is modelled as a constant generator ``H = i log(U)/tau`` acting for the
gate's calibrated duration ``tau`` while T1/T2 decoherence and a calibrated
depolarizing channel act concurrently. We integrate the Lindblad master equation

    drho/dt = -i[H, rho] + sum_k ( L_k rho L_k^dag - 1/2 {L_k^dag L_k, rho} )

on the gate's 1- or 2-qubit subspace by exponentiating the (time-independent)
Liouvillian superoperator, then compose a depolarizing channel calibrated to the
hardware gate-error spec. Per-gate average/entanglement gate fidelities are
computed from the channel's Choi state and composed multiplicatively across the
circuit.

This is an approximation: it ignores inter-gate correlations, crosstalk, and
leakage to non-computational states. The per-gate evolution is cross-validated
against ``qiskit-dynamics`` (see tests/test_pulse.py).

Conventions (validated against qiskit-dynamics):
- Relaxation operator L1 = sqrt(1/T1) * sigma_minus gives excited-population
  decay exp(-t/T1).
- Pure-dephasing operator Lphi = sqrt(gamma_phi/2) * sigma_z with
  gamma_phi = 1/T2 - 1/(2 T1) gives total coherence decay exp(-t/T2).
- Vectorization is column-stacking: vec(rho)[a + d*b] = rho[a, b], so the
  superoperator for ``A rho B`` is ``B^T (x) A``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.linalg import expm, logm

from src.metrics import NoiseParams, PulseMetrics

# =============================================================================
# Physical Constants for IQM Garnet
# =============================================================================

# Gate durations in nanoseconds (from IQM Garnet hardware parameters).
SINGLE_QUBIT_GATE_NS = 20.0
TWO_QUBIT_GATE_NS = 40.0

# =============================================================================
# Pauli Matrices and Operators
# =============================================================================

SIGMA_X = np.array([[0, 1], [1, 0]], dtype=complex)
SIGMA_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
SIGMA_Z = np.array([[1, 0], [0, -1]], dtype=complex)
SIGMA_MINUS = np.array([[0, 1], [0, 0]], dtype=complex)  # |0><1|, lowers |1>->|0>
IDENTITY_2 = np.eye(2, dtype=complex)


# =============================================================================
# Decoherence rates and Lindblad operators
# =============================================================================


def compute_t1_rate(t1_ns: float) -> float:
    """Return the relaxation rate gamma_1 = 1/T1 in 1/ns."""
    if t1_ns <= 0:
        raise ValueError(f"T1 must be positive, got {t1_ns}")
    return 1.0 / t1_ns


def compute_dephasing_rate(t1_ns: float, t2_ns: float) -> float:
    """Return the pure-dephasing rate gamma_phi = 1/T2 - 1/(2 T1) in 1/ns.

    Raises:
        ValueError: If T2 > 2*T1 (physically impossible) or T2 <= 0.
    """
    if t2_ns <= 0:
        raise ValueError(f"T2 must be positive, got {t2_ns}")
    if t2_ns > 2 * t1_ns:
        raise ValueError(
            f"T2 ({t2_ns} ns) cannot exceed 2*T1 ({2 * t1_ns} ns) - physically impossible"
        )
    return 1.0 / t2_ns - 1.0 / (2 * t1_ns)


def single_qubit_collapse_ops(noise: NoiseParams) -> list[np.ndarray]:
    """Lindblad collapse operators for one qubit: [relaxation, pure dephasing]."""
    gamma_1 = compute_t1_rate(noise.t1_ns)
    gamma_phi = compute_dephasing_rate(noise.t1_ns, noise.t2_ns)
    l_relax = np.sqrt(gamma_1) * SIGMA_MINUS
    l_dephase = np.sqrt(gamma_phi / 2.0) * SIGMA_Z
    return [l_relax, l_dephase]


def multi_qubit_collapse_ops(noise: NoiseParams, num_qubits: int) -> list[np.ndarray]:
    """Collapse operators for ``num_qubits`` qubits, each with its own T1/T2.

    Each single-qubit operator is embedded into the full 2**num_qubits space.
    """
    single = single_qubit_collapse_ops(noise)
    ops: list[np.ndarray] = []
    for q in range(num_qubits):
        for op in single:
            factors = [op if i == q else IDENTITY_2 for i in range(num_qubits)]
            embedded = factors[0]
            for f in factors[1:]:
                embedded = np.kron(embedded, f)
            ops.append(embedded)
    return ops


# =============================================================================
# Gate unitaries
# =============================================================================


def single_qubit_gate_unitary(name: str, angle: float = 0.0) -> np.ndarray:
    """Return the 2x2 unitary for a single-qubit gate, or identity if unknown."""
    gates: dict[str, np.ndarray] = {
        "h": np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2),
        "x": SIGMA_X,
        "y": SIGMA_Y,
        "z": SIGMA_Z,
        "s": np.array([[1, 0], [0, 1j]], dtype=complex),
        "sdg": np.array([[1, 0], [0, -1j]], dtype=complex),
        "t": np.array([[1, 0], [0, np.exp(1j * np.pi / 4)]], dtype=complex),
        "tdg": np.array([[1, 0], [0, np.exp(-1j * np.pi / 4)]], dtype=complex),
        "id": IDENTITY_2,
    }
    if name in gates:
        return gates[name]
    if name == "rx":
        c, s = np.cos(angle / 2), np.sin(angle / 2)
        return np.array([[c, -1j * s], [-1j * s, c]], dtype=complex)
    if name == "ry":
        c, s = np.cos(angle / 2), np.sin(angle / 2)
        return np.array([[c, -s], [s, c]], dtype=complex)
    if name in ("rz", "u1", "p"):
        return np.array(
            [[np.exp(-1j * angle / 2), 0], [0, np.exp(1j * angle / 2)]], dtype=complex
        )
    # Unknown single-qubit gate: fall back to identity. The decoherence channel
    # fidelity is U-independent to leading order in gamma*tau (~1e-4 here), so the
    # reported fidelity is unaffected to well below 1e-6.
    return IDENTITY_2


def two_qubit_gate_unitary(name: str) -> np.ndarray:
    """Return the 4x4 unitary for a two-qubit gate, or identity if unknown."""
    if name in ("cx", "cnot"):
        return np.array(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=complex
        )
    if name == "cz":
        return np.array(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, -1]], dtype=complex
        )
    if name == "swap":
        return np.array(
            [[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=complex
        )
    # Unknown two-qubit gate: fall back to identity (see note in the 1q case).
    return np.eye(4, dtype=complex)


def gate_unitary(name: str, params: Sequence[float], num_qubits: int) -> np.ndarray:
    """Return the ideal unitary for a gate given its name, params, and arity."""
    if num_qubits == 1:
        angle = float(params[0]) if params else 0.0
        return single_qubit_gate_unitary(name, angle)
    if num_qubits == 2:
        return two_qubit_gate_unitary(name)
    raise ValueError(f"Unsupported gate arity: {num_qubits} qubits ({name})")


# =============================================================================
# Superoperators (column-stacking vectorization)
# =============================================================================


def liouvillian(hamiltonian: np.ndarray, collapse_ops: Sequence[np.ndarray]) -> np.ndarray:
    """Build the Lindblad Liouvillian superoperator for column-stacked vec(rho)."""
    d = hamiltonian.shape[0]
    ident = np.eye(d, dtype=complex)
    lab = -1j * (np.kron(ident, hamiltonian) - np.kron(hamiltonian.T, ident))
    for c in collapse_ops:
        cdag_c = c.conj().T @ c
        lab += np.kron(c.conj(), c)
        lab -= 0.5 * (np.kron(ident, cdag_c) + np.kron(cdag_c.T, ident))
    return lab


def gate_channel_superop(
    unitary: np.ndarray,
    duration_ns: float,
    collapse_ops: Sequence[np.ndarray],
) -> np.ndarray:
    """Channel superoperator for a gate: constant generator H = i log(U)/tau plus
    concurrent decoherence, integrated over the gate duration."""
    if duration_ns <= 0:
        raise ValueError(f"Gate duration must be positive, got {duration_ns}")
    hamiltonian = 1j * logm(unitary) / duration_ns
    # Re-Hermitize to remove logm round-off (log of a unitary is anti-Hermitian).
    hamiltonian = 0.5 * (hamiltonian + hamiltonian.conj().T)
    return expm(liouvillian(hamiltonian, collapse_ops) * duration_ns)


def depolarizing_superop(d: int, p: float) -> np.ndarray:
    """Superoperator for the depolarizing channel rho -> (1-p) rho + p Tr(rho) I/d."""
    vec_identity = np.eye(d, dtype=complex).reshape(-1, order="F")
    completely_mixing = np.outer(vec_identity, vec_identity.conj()) / d
    return (1.0 - p) * np.eye(d * d, dtype=complex) + p * completely_mixing


def depolarizing_p_for_error(gate_error: float, d: int) -> float:
    """Depolarizing strength p giving average gate error ``gate_error`` in dim d.

    From F_avg = 1 - gate_error and the depolarizing channel's average gate
    fidelity, p = gate_error * d / (d - 1).
    """
    if d < 2:
        raise ValueError(f"dimension must be >= 2, got {d}")
    return gate_error * d / (d - 1)


# =============================================================================
# Fidelity
# =============================================================================


def _maximally_entangled(d: int) -> np.ndarray:
    """Return |Omega> = (1/sqrt(d)) sum_i |i>|i> (system (x) ancilla)."""
    vec = np.zeros(d * d, dtype=complex)
    for i in range(d):
        vec[i * d + i] = 1.0
    normalized: np.ndarray = vec / np.sqrt(d)
    return normalized


def _apply_superop(superop: np.ndarray, rho: np.ndarray) -> np.ndarray:
    """Apply a channel superoperator to a density matrix (column-stacking)."""
    d = rho.shape[0]
    out: np.ndarray = (superop @ rho.reshape(-1, order="F")).reshape((d, d), order="F")
    return out


def entanglement_fidelity(
    channel_superop: np.ndarray, target_unitary: np.ndarray, d: int
) -> float:
    """Entanglement (process) fidelity F_e between a channel and a target unitary.

    F_e = <Omega_U| (channel (x) I)(|Omega><Omega|) |Omega_U>, with
    |Omega_U> = (U (x) I)|Omega>.
    """
    choi = np.zeros((d * d, d * d), dtype=complex)
    basis = np.zeros((d, d), dtype=complex)
    for i in range(d):
        for j in range(d):
            basis[i, j] = 1.0
            anc = np.zeros((d, d), dtype=complex)
            anc[i, j] = 1.0
            choi += np.kron(_apply_superop(channel_superop, basis), anc)
            basis[i, j] = 0.0
    choi /= d
    omega_u = np.kron(target_unitary, np.eye(d, dtype=complex)) @ _maximally_entangled(d)
    return float(np.real(omega_u.conj() @ choi @ omega_u))


def average_gate_fidelity(entanglement_fid: float, d: int) -> float:
    """Average gate fidelity from entanglement fidelity: (d*F_e + 1)/(d + 1)."""
    return (d * entanglement_fid + 1.0) / (d + 1.0)


# =============================================================================
# Pulse simulator
# =============================================================================


@dataclass(frozen=True)
class GateFidelity:
    """Per-gate fidelities under the noise model."""

    process_fidelity: float  # entanglement fidelity F_e
    state_fidelity: float  # average gate fidelity F_avg (>= F_e)


class PulseSimulator:
    """Per-gate Lindblad simulator with a calibrated depolarizing channel.

    Per-gate fidelities are memoized on (name, params, arity) for a fixed noise
    model, so repeated identical gates are solved once.
    """

    def __init__(self, noise_params: NoiseParams) -> None:
        self.noise_params = noise_params
        self._single_collapse = multi_qubit_collapse_ops(noise_params, 1)
        self._two_collapse = multi_qubit_collapse_ops(noise_params, 2)
        self._cache: dict[tuple[str, tuple[float, ...], int], GateFidelity] = {}

    def gate_fidelity(
        self, name: str, qubits: tuple[int, ...], params: Sequence[float]
    ) -> GateFidelity:
        """Return (process, state) fidelity for a single gate, memoized."""
        num_qubits = len(qubits)
        if num_qubits not in (1, 2):
            raise ValueError(f"Unsupported gate size: {num_qubits} qubits ({name})")
        key = (name, tuple(round(float(p), 12) for p in params), num_qubits)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        if num_qubits == 1:
            duration = SINGLE_QUBIT_GATE_NS
            collapse = self._single_collapse
            gate_error = self.noise_params.single_qubit_error
            d = 2
        else:
            duration = TWO_QUBIT_GATE_NS
            collapse = self._two_collapse
            gate_error = self.noise_params.two_qubit_error
            d = 4

        unitary = gate_unitary(name, params, num_qubits)
        decoherence = gate_channel_superop(unitary, duration, collapse)
        depol = depolarizing_superop(d, depolarizing_p_for_error(gate_error, d))
        channel = depol @ decoherence

        f_e = entanglement_fidelity(channel, unitary, d)
        # Clamp tiny numerical overshoot above 1 (e.g. 1 + 1e-15) into range.
        f_e = min(1.0, max(0.0, f_e))
        fidelity = GateFidelity(
            process_fidelity=f_e,
            state_fidelity=average_gate_fidelity(f_e, d),
        )
        self._cache[key] = fidelity
        return fidelity

    def idle_fidelity(self, idle_ns: float) -> GateFidelity:
        """Fidelity of a single qubit decohering (H=0) while idle for idle_ns."""
        if idle_ns <= 1e-9:
            return GateFidelity(1.0, 1.0)
        key = ("__idle__", (round(idle_ns, 3),), 1)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        superop = gate_channel_superop(IDENTITY_2, idle_ns, self._single_collapse)
        f_e = min(1.0, max(0.0, entanglement_fidelity(superop, IDENTITY_2, 2)))
        fidelity = GateFidelity(f_e, average_gate_fidelity(f_e, 2))
        self._cache[key] = fidelity
        return fidelity

    def simulate_gate_sequence(
        self,
        gates: Sequence[tuple[str, tuple[int, ...], Sequence[float]]],
        idle_aware: bool = True,
    ) -> tuple[float, float, PulseMetrics]:
        """Simulate a gate sequence and return (process_fid, state_fid, metrics).

        Gates are ASAP-scheduled (gates on disjoint qubits run concurrently).
        Per-gate fidelities compose multiplicatively; when ``idle_aware`` (the
        physical model), each qubit additionally accrues idle decoherence over
        the gap between its active time and the circuit makespan. The reported
        duration is the makespan, not the serial sum of gate durations.
        """
        process_fidelity = 1.0
        state_fidelity = 1.0
        free: dict[int, float] = {}
        active: dict[int, float] = {}
        makespan = 0.0
        pulse_count = 0

        for name, qubits, params in gates:
            fid = self.gate_fidelity(name, qubits, params)
            process_fidelity *= fid.process_fidelity
            state_fidelity *= fid.state_fidelity
            duration = SINGLE_QUBIT_GATE_NS if len(qubits) == 1 else TWO_QUBIT_GATE_NS
            start = max((free.get(q, 0.0) for q in qubits), default=0.0)
            end = start + duration
            for q in qubits:
                free[q] = end
                active[q] = active.get(q, 0.0) + duration
            makespan = max(makespan, end)
            pulse_count += 1

        if idle_aware:
            for active_ns in active.values():
                idle = self.idle_fidelity(makespan - active_ns)
                process_fidelity *= idle.process_fidelity
                state_fidelity *= idle.state_fidelity

        metrics = PulseMetrics(
            total_duration_ns=makespan,
            pulse_count=pulse_count,
            max_amplitude=1.0,
        )
        return process_fidelity, state_fidelity, metrics


# =============================================================================
# Gate compiler interface
# =============================================================================


class RealGateCompiler:
    """Gate compiler using per-gate Lindblad simulation for fidelity estimation."""

    def __init__(self, noise_params: NoiseParams) -> None:
        self.noise_params = noise_params
        self.simulator = PulseSimulator(noise_params)

    def simulate_gates(
        self,
        gates: Sequence[tuple[str, tuple[int, ...], Sequence[float]]],
    ) -> tuple[float, float, PulseMetrics]:
        """Simulate an explicit gate sequence (name, qubit indices, params)."""
        return self.simulator.simulate_gate_sequence(gates)
