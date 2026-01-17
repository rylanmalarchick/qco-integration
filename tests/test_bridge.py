"""Tests for CircuitOptimizerBridge.

Following AgentBible principles:
- Tests written BEFORE implementation
- Each test specifies expected behavior clearly
- Edge cases enumerated in test names

These tests use a mock subprocess when the real binary is unavailable,
and can optionally run against the real binary with --run-integration.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.bridge import CircuitOptimizerBridge, OptimizationResult
from src.metrics import PassMetrics, RoutingMetrics, StageMetrics

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_binary_path(tmp_path: Path) -> Path:
    """Create a mock binary path for testing."""
    binary = tmp_path / "quantum_circuit_optimizer"
    binary.touch()
    binary.chmod(0o755)
    return binary


@pytest.fixture
def sample_optimizer_json_output() -> dict[str, Any]:
    """Sample JSON output matching SCOPE_OF_WORK.md specification."""
    return {
        "input": {
            "gates": 50,
            "depth": 20,
            "qubits": 8,
            "two_qubit_gates": 15,
        },
        "passes": [
            {
                "name": "CancellationPass",
                "gates_removed": 5,
                "gates_added": 0,
                "output_gates": 45,
                "output_depth": 18,
            },
            {
                "name": "CommutationPass",
                "gates_removed": 3,
                "gates_added": 0,
                "output_gates": 42,
                "output_depth": 17,
            },
        ],
        "post_optimization": {
            "gates": 42,
            "depth": 17,
            "qubits": 8,
            "two_qubit_gates": 12,
        },
        "routing": {
            "topology": "iqm-garnet",
            "swaps_inserted": 6,
            "final_gates": 54,
            "final_depth": 23,
        },
        "output_qasm": "OPENQASM 3.0;\nqubit[8] q;\nh q[0];\n",
    }


@pytest.fixture
def sample_optimizer_json_no_routing() -> dict[str, Any]:
    """Sample JSON output without routing."""
    return {
        "input": {
            "gates": 10,
            "depth": 5,
            "qubits": 2,
            "two_qubit_gates": 2,
        },
        "passes": [
            {
                "name": "CancellationPass",
                "gates_removed": 2,
                "gates_added": 0,
                "output_gates": 8,
                "output_depth": 4,
            },
        ],
        "post_optimization": {
            "gates": 8,
            "depth": 4,
            "qubits": 2,
            "two_qubit_gates": 2,
        },
        "output_qasm": "OPENQASM 3.0;\nqubit[2] q;\nh q[0];\ncx q[0], q[1];\n",
    }


# =============================================================================
# Initialization Tests
# =============================================================================


class TestCircuitOptimizerBridgeInit:
    """Tests for CircuitOptimizerBridge initialization."""

    def test_init_with_valid_path(self, mock_binary_path: Path) -> None:
        """Bridge initializes successfully with valid binary path."""
        bridge = CircuitOptimizerBridge(mock_binary_path)
        assert bridge.binary_path == mock_binary_path

    def test_init_with_string_path(self, mock_binary_path: Path) -> None:
        """Bridge accepts string path and converts to Path."""
        bridge = CircuitOptimizerBridge(str(mock_binary_path))
        assert bridge.binary_path == mock_binary_path

    def test_init_raises_file_not_found_for_missing_binary(
        self, tmp_path: Path
    ) -> None:
        """Bridge raises FileNotFoundError if binary doesn't exist."""
        missing_path = tmp_path / "nonexistent_binary"
        with pytest.raises(FileNotFoundError) as exc_info:
            CircuitOptimizerBridge(missing_path)
        assert "not found" in str(exc_info.value).lower()

    def test_init_raises_file_not_found_for_directory(self, tmp_path: Path) -> None:
        """Bridge raises FileNotFoundError if path is a directory."""
        with pytest.raises(FileNotFoundError) as exc_info:
            CircuitOptimizerBridge(tmp_path)
        assert "not a file" in str(exc_info.value).lower()


# =============================================================================
# Optimization Tests (with mocked subprocess)
# =============================================================================


class TestCircuitOptimizerBridgeOptimize:
    """Tests for the optimize() method."""

    def test_optimize_returns_optimization_result(
        self,
        mock_binary_path: Path,
        sample_optimizer_json_output: dict[str, Any],
    ) -> None:
        """optimize() returns OptimizationResult with correct structure."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with patch.object(bridge, "_run_optimizer") as mock_run:
            mock_run.return_value = sample_optimizer_json_output
            result = bridge.optimize(
                qasm="OPENQASM 3.0;\nqubit q;\nh q;\n",
                passes=["cancel", "commute"],
                topology="iqm-garnet",
                route=True,
            )

        assert isinstance(result, OptimizationResult)
        assert isinstance(result.input_metrics, StageMetrics)
        assert isinstance(result.post_optimization, StageMetrics)
        assert len(result.passes) == 2
        assert all(isinstance(p, PassMetrics) for p in result.passes)

    def test_optimize_parses_input_metrics_correctly(
        self,
        mock_binary_path: Path,
        sample_optimizer_json_output: dict[str, Any],
    ) -> None:
        """Input metrics are correctly parsed from JSON."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with patch.object(bridge, "_run_optimizer") as mock_run:
            mock_run.return_value = sample_optimizer_json_output
            result = bridge.optimize(
                qasm="OPENQASM 3.0;\nqubit q;\n",
                passes=["cancel"],
            )

        assert result.input_metrics.gates == 50
        assert result.input_metrics.depth == 20
        assert result.input_metrics.qubits == 8
        assert result.input_metrics.two_qubit_gates == 15

    def test_optimize_parses_pass_metrics_correctly(
        self,
        mock_binary_path: Path,
        sample_optimizer_json_output: dict[str, Any],
    ) -> None:
        """Per-pass metrics are correctly parsed."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with patch.object(bridge, "_run_optimizer") as mock_run:
            mock_run.return_value = sample_optimizer_json_output
            result = bridge.optimize(
                qasm="OPENQASM 3.0;\nqubit q;\n",
                passes=["cancel", "commute"],
            )

        assert len(result.passes) == 2
        assert result.passes[0].name == "CancellationPass"
        assert result.passes[0].gates_removed == 5
        assert result.passes[1].name == "CommutationPass"
        assert result.passes[1].gates_removed == 3

    def test_optimize_parses_routing_metrics_when_present(
        self,
        mock_binary_path: Path,
        sample_optimizer_json_output: dict[str, Any],
    ) -> None:
        """Routing metrics are parsed when routing is enabled."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with patch.object(bridge, "_run_optimizer") as mock_run:
            mock_run.return_value = sample_optimizer_json_output
            result = bridge.optimize(
                qasm="OPENQASM 3.0;\nqubit q;\n",
                passes=["cancel"],
                topology="iqm-garnet",
                route=True,
            )

        assert result.routing_metrics is not None
        assert isinstance(result.routing_metrics, RoutingMetrics)
        assert result.routing_metrics.topology == "iqm-garnet"
        assert result.routing_metrics.swaps_inserted == 6

    def test_optimize_routing_metrics_none_when_not_routing(
        self,
        mock_binary_path: Path,
        sample_optimizer_json_no_routing: dict[str, Any],
    ) -> None:
        """Routing metrics are None when routing is disabled."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with patch.object(bridge, "_run_optimizer") as mock_run:
            mock_run.return_value = sample_optimizer_json_no_routing
            result = bridge.optimize(
                qasm="OPENQASM 3.0;\nqubit q;\n",
                passes=["cancel"],
                route=False,
            )

        assert result.routing_metrics is None

    def test_optimize_returns_output_qasm(
        self,
        mock_binary_path: Path,
        sample_optimizer_json_output: dict[str, Any],
    ) -> None:
        """Output QASM is included in result."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with patch.object(bridge, "_run_optimizer") as mock_run:
            mock_run.return_value = sample_optimizer_json_output
            result = bridge.optimize(
                qasm="OPENQASM 3.0;\nqubit q;\n",
                passes=["cancel"],
            )

        assert result.output_qasm.startswith("OPENQASM 3.0")


# =============================================================================
# Input Validation Tests
# =============================================================================


class TestCircuitOptimizerBridgeValidation:
    """Tests for input validation."""

    def test_optimize_raises_for_empty_qasm(self, mock_binary_path: Path) -> None:
        """optimize() raises ValueError for empty QASM input."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with pytest.raises(ValueError) as exc_info:
            bridge.optimize(qasm="", passes=["cancel"])
        assert "empty" in str(exc_info.value).lower()

    def test_optimize_raises_for_invalid_pass_name(
        self, mock_binary_path: Path
    ) -> None:
        """optimize() raises ValueError for unknown pass name."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with pytest.raises(ValueError) as exc_info:
            bridge.optimize(
                qasm="OPENQASM 3.0;\nqubit q;\n",
                passes=["invalid_pass"],
            )
        assert "invalid" in str(exc_info.value).lower() or "unknown" in str(
            exc_info.value
        ).lower()

    def test_optimize_raises_for_empty_passes_list(
        self, mock_binary_path: Path
    ) -> None:
        """optimize() raises ValueError for empty passes list."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with pytest.raises(ValueError) as exc_info:
            bridge.optimize(
                qasm="OPENQASM 3.0;\nqubit q;\n",
                passes=[],
            )
        assert "pass" in str(exc_info.value).lower()

    def test_optimize_requires_topology_when_routing(
        self, mock_binary_path: Path
    ) -> None:
        """optimize() raises ValueError if route=True but no topology."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with pytest.raises(ValueError) as exc_info:
            bridge.optimize(
                qasm="OPENQASM 3.0;\nqubit q;\n",
                passes=["cancel"],
                route=True,
                topology=None,
            )
        assert "topology" in str(exc_info.value).lower()


# =============================================================================
# CLI Argument Construction Tests
# =============================================================================


class TestCircuitOptimizerBridgeCLI:
    """Tests for CLI argument construction."""

    def test_build_cli_args_basic(self, mock_binary_path: Path) -> None:
        """CLI args are correctly constructed for basic optimization."""
        bridge = CircuitOptimizerBridge(mock_binary_path)
        args = bridge._build_cli_args(
            input_file=Path("/tmp/input.qasm"),
            output_file=Path("/tmp/output.json"),
            passes=["cancel", "commute"],
            topology=None,
            route=False,
        )

        assert str(mock_binary_path) in args
        assert "--input" in args
        assert "/tmp/input.qasm" in args
        assert "--output" in args
        assert "/tmp/output.json" in args
        assert "--passes" in args
        assert "cancel,commute" in args
        assert "--output-format" in args
        assert "json" in args

    def test_build_cli_args_with_routing(self, mock_binary_path: Path) -> None:
        """CLI args include routing options when enabled."""
        bridge = CircuitOptimizerBridge(mock_binary_path)
        args = bridge._build_cli_args(
            input_file=Path("/tmp/input.qasm"),
            output_file=Path("/tmp/output.json"),
            passes=["cancel"],
            topology="iqm-garnet",
            route=True,
        )

        assert "--topology" in args
        assert "iqm-garnet" in args
        assert "--route" in args


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestCircuitOptimizerBridgeErrorHandling:
    """Tests for error handling."""

    def test_optimize_raises_runtime_error_on_subprocess_failure(
        self, mock_binary_path: Path
    ) -> None:
        """RuntimeError raised when subprocess returns non-zero exit code."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="Error: Invalid QASM syntax",
            )
            with pytest.raises(RuntimeError) as exc_info:
                bridge.optimize(
                    qasm="OPENQASM 3.0;\ninvalid syntax;\n",
                    passes=["cancel"],
                )
            assert "failed" in str(exc_info.value).lower()

    def test_optimize_raises_runtime_error_on_invalid_json(
        self, mock_binary_path: Path
    ) -> None:
        """RuntimeError raised when subprocess returns invalid JSON."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="not valid json",
                stderr="",
            )
            with pytest.raises(RuntimeError) as exc_info:
                bridge.optimize(
                    qasm="OPENQASM 3.0;\nqubit q;\n",
                    passes=["cancel"],
                )
            assert "json" in str(exc_info.value).lower()

    def test_optimize_handles_timeout(self, mock_binary_path: Path) -> None:
        """TimeoutError is propagated when subprocess times out."""
        bridge = CircuitOptimizerBridge(mock_binary_path)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=60)
            with pytest.raises(subprocess.TimeoutExpired):
                bridge.optimize(
                    qasm="OPENQASM 3.0;\nqubit q;\n",
                    passes=["cancel"],
                )


# =============================================================================
# Integration Tests (require real binary)
# =============================================================================


@pytest.mark.integration
@pytest.mark.requires_optimizer
class TestCircuitOptimizerBridgeIntegration:
    """Integration tests requiring the real optimizer binary.

    Run with: pytest -m requires_optimizer
    """

    @pytest.fixture
    def real_binary_path(self) -> Path:
        """Get path to real optimizer binary from environment."""
        import os

        path = os.environ.get(
            "QCO_OPTIMIZER_BINARY",
            "/home/rylan/Documents/career/code_bases/quantum/compilers/"
            "quantum-circuit-optimizer/build/quantum_circuit_optimizer",
        )
        binary = Path(path)
        if not binary.exists():
            pytest.skip(f"Optimizer binary not found at {binary}")
        return binary

    def test_real_optimization_simple_circuit(self, real_binary_path: Path) -> None:
        """Real optimizer works on a simple circuit."""
        bridge = CircuitOptimizerBridge(real_binary_path)
        qasm = """OPENQASM 3.0;
qubit[2] q;
h q[0];
h q[0];
cx q[0], q[1];
"""
        result = bridge.optimize(qasm=qasm, passes=["cancel"])

        assert result.input_metrics.gates >= 2
        assert result.output_qasm.startswith("OPENQASM")
