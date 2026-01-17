"""Pytest configuration and shared fixtures for qco-integration.

This file is automatically loaded by pytest and provides:
- Reproducibility: Fixed random seeds for deterministic tests
- Common fixtures: Quantum states, gates, noise parameters
- Custom markers: @pytest.mark.slow, @pytest.mark.integration, etc.

Following AgentBible principles:
- All seeds documented
- Physics-aware fixtures with validation
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.metrics import NoiseParams, StageMetrics


# =============================================================================
# Reproducibility: Set seeds before each test
# =============================================================================
@pytest.fixture(autouse=True)
def set_random_seeds() -> None:
    """Set random seeds for reproducibility in all tests.

    This fixture runs automatically before every test to ensure
    deterministic behavior. Document any seed changes.

    Seeds:
        numpy: 42
        python random: 42 (if using random module)
    """
    np.random.seed(42)


# =============================================================================
# Path Fixtures
# =============================================================================
@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def test_data_dir(project_root: Path) -> Path:
    """Return the test data directory."""
    return project_root / "tests" / "data"


# =============================================================================
# Quantum State Fixtures
# =============================================================================
@pytest.fixture
def zero_state() -> np.ndarray:
    """Qubit |0> state."""
    return np.array([1, 0], dtype=complex)


@pytest.fixture
def one_state() -> np.ndarray:
    """Qubit |1> state."""
    return np.array([0, 1], dtype=complex)


@pytest.fixture
def plus_state() -> np.ndarray:
    """Qubit |+> = (|0> + |1>)/sqrt(2) state."""
    return np.array([1, 1], dtype=complex) / np.sqrt(2)


@pytest.fixture
def minus_state() -> np.ndarray:
    """Qubit |-> = (|0> - |1>)/sqrt(2) state."""
    return np.array([1, -1], dtype=complex) / np.sqrt(2)


@pytest.fixture
def bell_state() -> np.ndarray:
    """Bell state |Phi+> = (|00> + |11>)/sqrt(2)."""
    return np.array([1, 0, 0, 1], dtype=complex) / np.sqrt(2)


# =============================================================================
# Quantum Gate Fixtures
# =============================================================================
@pytest.fixture
def pauli_x() -> np.ndarray:
    """Pauli X gate matrix."""
    return np.array([[0, 1], [1, 0]], dtype=complex)


@pytest.fixture
def pauli_y() -> np.ndarray:
    """Pauli Y gate matrix."""
    return np.array([[0, -1j], [1j, 0]], dtype=complex)


@pytest.fixture
def pauli_z() -> np.ndarray:
    """Pauli Z gate matrix."""
    return np.array([[1, 0], [0, -1]], dtype=complex)


@pytest.fixture
def hadamard() -> np.ndarray:
    """Hadamard gate matrix."""
    return np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)


@pytest.fixture
def identity_2x2() -> np.ndarray:
    """2x2 identity matrix."""
    return np.eye(2, dtype=complex)


@pytest.fixture
def cnot() -> np.ndarray:
    """CNOT (CX) gate matrix."""
    return np.array(
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=complex
    )


@pytest.fixture
def cz() -> np.ndarray:
    """CZ gate matrix (native IQM Garnet two-qubit gate)."""
    return np.array(
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, -1]], dtype=complex
    )


# =============================================================================
# Noise Parameter Fixtures
# =============================================================================
@pytest.fixture
def iqm_garnet_noise() -> NoiseParams:
    """IQM Garnet median noise parameters.

    Source: IQM_GARNET_SPEC.md
    """
    return NoiseParams(
        t1_ns=37000.0,  # Median T1
        t2_ns=9600.0,  # Median T2
        single_qubit_error=0.001,  # Median 1Q error
        two_qubit_error=0.006,  # Median 2Q error
    )


@pytest.fixture
def low_noise_params() -> NoiseParams:
    """Low noise parameters for testing (high fidelity regime)."""
    return NoiseParams(
        t1_ns=100000.0,
        t2_ns=50000.0,
        single_qubit_error=0.0001,
        two_qubit_error=0.001,
    )


@pytest.fixture
def high_noise_params() -> NoiseParams:
    """High noise parameters for testing (low fidelity regime)."""
    return NoiseParams(
        t1_ns=10000.0,
        t2_ns=5000.0,
        single_qubit_error=0.01,
        two_qubit_error=0.05,
    )


# =============================================================================
# Metrics Fixtures
# =============================================================================
@pytest.fixture
def sample_stage_metrics() -> StageMetrics:
    """Sample stage metrics for testing."""
    return StageMetrics(
        gates=50,
        depth=20,
        qubits=8,
        two_qubit_gates=15,
    )


# =============================================================================
# OpenQASM Fixtures
# =============================================================================
@pytest.fixture
def simple_qasm() -> str:
    """Simple single-qubit OpenQASM circuit."""
    return """OPENQASM 3.0;
qubit q;
h q;
"""


@pytest.fixture
def bell_qasm() -> str:
    """Bell state preparation circuit."""
    return """OPENQASM 3.0;
qubit[2] q;
h q[0];
cx q[0], q[1];
"""


@pytest.fixture
def ghz_4_qasm() -> str:
    """4-qubit GHZ state preparation circuit."""
    return """OPENQASM 3.0;
qubit[4] q;
h q[0];
cx q[0], q[1];
cx q[1], q[2];
cx q[2], q[3];
"""


# =============================================================================
# Tolerance Constants
# =============================================================================
@pytest.fixture
def tolerance() -> float:
    """Default numerical tolerance for floating-point comparisons.

    Source: Machine epsilon for float64 is ~2.2e-16; 1e-10 provides
    margin for accumulated numerical error in typical operations.
    """
    return 1e-10


@pytest.fixture
def loose_tolerance() -> float:
    """Looser tolerance for operations with more numerical error."""
    return 1e-6
