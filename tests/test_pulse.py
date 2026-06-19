"""Tests for the per-gate Lindblad pulse simulator (src/pulse.py).

Two layers:
1. Deterministic physics pins (decay laws, trace/hermiticity, depolarizing
   calibration, fidelity relations) at tight tolerance.
2. Cross-validation of the per-gate evolution against qiskit-dynamics
   (@pytest.mark.crossval): an independent Lindblad ODE integrator must
   reproduce our matrix-exponential evolution to ~1e-8.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.metrics import NoiseParams
from src.pulse import (
    SIGMA_X,
    PulseSimulator,
    average_gate_fidelity,
    depolarizing_p_for_error,
    depolarizing_superop,
    entanglement_fidelity,
    gate_channel_superop,
    gate_unitary,
    liouvillian,
    multi_qubit_collapse_ops,
    single_qubit_collapse_ops,
)

GARNET = NoiseParams(
    t1_ns=37000.0, t2_ns=9600.0, single_qubit_error=0.001, two_qubit_error=0.006
)


def _evolve(rho0: np.ndarray, hamiltonian: np.ndarray, collapse, t: float) -> np.ndarray:
    """Evolve a density matrix under the Lindblad superoperator for time t."""
    from scipy.linalg import expm

    d = rho0.shape[0]
    superop = expm(liouvillian(hamiltonian, collapse) * t)
    return (superop @ rho0.reshape(-1, order="F")).reshape((d, d), order="F")


# =============================================================================
# Deterministic physics
# =============================================================================


def test_relaxation_population_decays_as_exp_t1() -> None:
    """Excited-state population of an idle qubit decays as exp(-t/T1)."""
    collapse = single_qubit_collapse_ops(GARNET)
    rho_excited = np.array([[0, 0], [0, 1]], dtype=complex)
    for t in (100.0, 1000.0, 9600.0):
        rho_t = _evolve(rho_excited, np.zeros((2, 2), dtype=complex), collapse, t)
        assert rho_t[1, 1].real == pytest.approx(np.exp(-t / GARNET.t1_ns), abs=1e-9)


def test_coherence_decays_as_exp_t2() -> None:
    """Off-diagonal coherence of an idle qubit decays as exp(-t/T2)."""
    collapse = single_qubit_collapse_ops(GARNET)
    plus = np.array([[0.5, 0.5], [0.5, 0.5]], dtype=complex)
    for t in (100.0, 1000.0, 5000.0):
        rho_t = _evolve(plus, np.zeros((2, 2), dtype=complex), collapse, t)
        assert abs(rho_t[0, 1]) == pytest.approx(0.5 * np.exp(-t / GARNET.t2_ns), abs=1e-9)


def test_channel_is_trace_preserving_and_hermitian() -> None:
    """A gate channel maps a valid state to a unit-trace Hermitian PSD state."""
    collapse = multi_qubit_collapse_ops(GARNET, 1)
    superop = gate_channel_superop(SIGMA_X, 20.0, collapse)
    rho0 = np.array([[0.7, 0.3 - 0.2j], [0.3 + 0.2j, 0.3]], dtype=complex)
    rho_t = (superop @ rho0.reshape(-1, order="F")).reshape((2, 2), order="F")
    assert np.trace(rho_t).real == pytest.approx(1.0, abs=1e-10)
    assert np.allclose(rho_t, rho_t.conj().T, atol=1e-10)
    assert np.linalg.eigvalsh(rho_t).min() > -1e-10


def test_depolarizing_calibration_recovers_gate_error() -> None:
    """depolarizing_p_for_error gives a channel with the target average gate error."""
    for gate_error, d in [(0.001, 2), (0.006, 4), (0.01, 2)]:
        p = depolarizing_p_for_error(gate_error, d)
        channel = depolarizing_superop(d, p)
        f_e = entanglement_fidelity(channel, np.eye(d, dtype=complex), d)
        # Closed form for depolarizing entanglement fidelity.
        assert f_e == pytest.approx((1 - p) + p / d**2, abs=1e-12)
        assert average_gate_fidelity(f_e, d) == pytest.approx(1 - gate_error, abs=1e-12)


def test_average_gate_fidelity_relation() -> None:
    """F_avg = (d*F_e + 1)/(d + 1)."""
    assert average_gate_fidelity(0.9, 2) == pytest.approx((2 * 0.9 + 1) / 3)
    assert average_gate_fidelity(0.9, 4) == pytest.approx((4 * 0.9 + 1) / 5)


def test_noiseless_gate_fidelity_is_one() -> None:
    """With negligible noise and zero gate error, every gate has fidelity ~1."""
    quiet = NoiseParams(
        t1_ns=1e15, t2_ns=1e15, single_qubit_error=0.0, two_qubit_error=0.0
    )
    sim = PulseSimulator(quiet)
    for name, qubits in [("h", (0,)), ("rz", (0,)), ("cz", (0, 1)), ("swap", (0, 1))]:
        params = (1.2345,) if name == "rz" else ()
        fid = sim.gate_fidelity(name, qubits, params)
        assert fid.process_fidelity > 1 - 1e-6
        assert fid.state_fidelity >= fid.process_fidelity


def test_two_qubit_gate_less_faithful_than_single() -> None:
    """A 2-qubit gate has lower fidelity than a 1-qubit gate under Garnet noise."""
    sim = PulseSimulator(GARNET)
    one_q = sim.gate_fidelity("h", (0,), ())
    two_q = sim.gate_fidelity("cz", (0, 1), ())
    assert two_q.process_fidelity < one_q.process_fidelity < 1.0


def test_higher_noise_lowers_fidelity() -> None:
    """Shorter coherence times produce lower per-gate fidelity."""
    low = PulseSimulator(
        NoiseParams(t1_ns=100000.0, t2_ns=50000.0, single_qubit_error=0.0, two_qubit_error=0.0)
    )
    high = PulseSimulator(
        NoiseParams(t1_ns=10000.0, t2_ns=2500.0, single_qubit_error=0.0, two_qubit_error=0.0)
    )
    assert (
        high.gate_fidelity("cz", (0, 1), ()).process_fidelity
        < low.gate_fidelity("cz", (0, 1), ()).process_fidelity
    )


def test_sequence_product_without_idle() -> None:
    """With idle_aware=False, circuit fidelity is the pure product of gate fidelities."""
    sim = PulseSimulator(GARNET)
    gates = [("h", (0,), ()), ("cz", (0, 1), ()), ("h", (1,), ())]
    proc, state, metrics = sim.simulate_gate_sequence(gates, idle_aware=False)
    expected_proc = 1.0
    expected_state = 1.0
    for name, qubits, params in gates:
        fid = sim.gate_fidelity(name, qubits, params)
        expected_proc *= fid.process_fidelity
        expected_state *= fid.state_fidelity
    assert proc == pytest.approx(expected_proc, abs=1e-12)
    assert state == pytest.approx(expected_state, abs=1e-12)
    assert metrics.pulse_count == 3


def test_sequence_makespan_uses_asap_schedule() -> None:
    """Disjoint-qubit gates run concurrently; makespan is ASAP, not the serial sum."""
    sim = PulseSimulator(GARNET)
    _, _, parallel = sim.simulate_gate_sequence([("h", (0,), ()), ("h", (1,), ())])
    assert parallel.total_duration_ns == pytest.approx(20.0)  # concurrent
    _, _, serial = sim.simulate_gate_sequence([("h", (0,), ()), ("x", (0,), ())])
    assert serial.total_duration_ns == pytest.approx(40.0)  # same qubit, serialized


def test_idle_fidelity_grows_worse_with_makespan() -> None:
    """A longer idle window means more decoherence loss."""
    sim = PulseSimulator(GARNET)
    short = sim.idle_fidelity(100.0)
    long = sim.idle_fidelity(5000.0)
    assert 1.0 > short.process_fidelity > long.process_fidelity
    assert short.state_fidelity >= short.process_fidelity


def test_idle_aware_below_schedule_blind() -> None:
    """Leaving a qubit idle during a long chain costs fidelity the blind model misses."""
    sim = PulseSimulator(GARNET)
    gates = [("h", (1,), ())] + [("x", (0,), ()) for _ in range(50)]
    blind, _, _ = sim.simulate_gate_sequence(gates, idle_aware=False)
    aware, _, metrics = sim.simulate_gate_sequence(gates, idle_aware=True)
    assert aware < blind
    assert metrics.total_duration_ns == pytest.approx(20.0 * 50)  # q0 chain sets makespan


# =============================================================================
# Cross-validation against qiskit-dynamics (independent Lindblad integrator)
# =============================================================================


def _qiskit_dynamics_final_state(
    hamiltonian: np.ndarray, collapse, rho0: np.ndarray, t: float
) -> np.ndarray:
    """Integrate the Lindblad ME with qiskit-dynamics; return rho(t)."""
    try:
        from qiskit.quantum_info import DensityMatrix
        from qiskit_dynamics import Solver
    except ImportError as exc:  # crossval must be RED if the oracle is absent
        pytest.fail(f"qiskit-dynamics required for cross-validation: {exc}")

    solver = Solver(static_hamiltonian=hamiltonian, static_dissipators=list(collapse))
    result = solver.solve(
        t_span=[0.0, t],
        y0=DensityMatrix(rho0),
        t_eval=[t],
        method="DOP853",
        atol=1e-12,
        rtol=1e-12,
    )
    return np.asarray(result.y[-1].data)


@pytest.mark.crossval
def test_crossval_single_qubit_evolution_matches_qiskit_dynamics() -> None:
    """Our expm Lindblad evolution matches qiskit-dynamics for 1-qubit gates."""
    collapse = multi_qubit_collapse_ops(GARNET, 1)
    states = {
        "ground": np.array([[1, 0], [0, 0]], dtype=complex),
        "excited": np.array([[0, 0], [0, 1]], dtype=complex),
        "plus": np.array([[0.5, 0.5], [0.5, 0.5]], dtype=complex),
    }
    from scipy.linalg import logm

    for gate in ("h", "x", "rz"):
        unitary = gate_unitary(gate, (0.7,) if gate == "rz" else (), 1)
        hamiltonian = 1j * logm(unitary) / 20.0
        hamiltonian = 0.5 * (hamiltonian + hamiltonian.conj().T)
        superop = gate_channel_superop(unitary, 20.0, collapse)
        for rho0 in states.values():
            ours = (superop @ rho0.reshape(-1, order="F")).reshape((2, 2), order="F")
            theirs = _qiskit_dynamics_final_state(hamiltonian, collapse, rho0, 20.0)
            assert np.allclose(ours, theirs, atol=1e-7), f"{gate} mismatch"


@pytest.mark.crossval
def test_crossval_two_qubit_evolution_matches_qiskit_dynamics() -> None:
    """Our expm Lindblad evolution matches qiskit-dynamics for a CZ gate."""
    collapse = multi_qubit_collapse_ops(GARNET, 2)
    unitary = gate_unitary("cz", (), 2)
    from scipy.linalg import logm

    hamiltonian = 1j * logm(unitary) / 40.0
    hamiltonian = 0.5 * (hamiltonian + hamiltonian.conj().T)
    superop = gate_channel_superop(unitary, 40.0, collapse)

    bell = np.zeros((4, 4), dtype=complex)
    psi = np.array([1, 0, 0, 1], dtype=complex) / np.sqrt(2)
    bell = np.outer(psi, psi.conj())
    for rho0 in (np.diag([1, 0, 0, 0]).astype(complex), bell):
        ours = (superop @ rho0.reshape(-1, order="F")).reshape((4, 4), order="F")
        theirs = _qiskit_dynamics_final_state(hamiltonian, collapse, rho0, 40.0)
        assert np.allclose(ours, theirs, atol=1e-7)


@pytest.mark.crossval
def test_crossval_gate_fidelity_matches_qiskit_quantum_info() -> None:
    """Per-gate average gate fidelity matches qiskit.quantum_info on the channel."""
    try:
        from qiskit.quantum_info import Operator, SuperOp
        from qiskit.quantum_info import average_gate_fidelity as qi_agf
    except ImportError as exc:
        pytest.fail(f"qiskit required for cross-validation: {exc}")

    collapse = multi_qubit_collapse_ops(GARNET, 1)
    unitary = gate_unitary("h", (), 1)
    depol = depolarizing_superop(2, depolarizing_p_for_error(GARNET.single_qubit_error, 2))
    channel = depol @ gate_channel_superop(unitary, 20.0, collapse)

    sim = PulseSimulator(GARNET)
    ours_avg = sim.gate_fidelity("h", (0,), ()).state_fidelity

    # qiskit SuperOp uses column-stacking, matching our convention.
    theirs_avg = qi_agf(SuperOp(channel), Operator(unitary))
    assert ours_avg == pytest.approx(theirs_avg, abs=1e-6)
