"""CircuitOptimizerBridge: Subprocess wrapper for C++ quantum-circuit-optimizer.

This module provides a Python interface to the quantum-circuit-optimizer C++ binary,
handling JSON I/O and result parsing.

Following AgentBible principles:
- Fail fast with clear error messages
- Validate inputs at boundaries
- Type hints on all functions

Reference: SCOPE_OF_WORK.md for CLI interface specification.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.metrics import PassMetrics, RoutingMetrics, StageMetrics

# Valid optimization passes (from SCOPE_OF_WORK.md)
VALID_PASSES = frozenset({"cancel", "commute", "rotate", "identity"})

# Default subprocess timeout in seconds
DEFAULT_TIMEOUT = 60


@dataclass
class OptimizationResult:
    """Result from a circuit optimization run.

    Attributes:
        input_metrics: Metrics for the input circuit.
        passes: Per-pass metrics for each optimization pass.
        post_optimization: Metrics after all passes complete.
        routing_metrics: Routing metrics (if routing was enabled).
        output_qasm: The optimized OpenQASM 3.0 circuit.
    """

    input_metrics: StageMetrics
    passes: list[PassMetrics]
    post_optimization: StageMetrics
    routing_metrics: RoutingMetrics | None
    output_qasm: str


class CircuitOptimizerBridge:
    """Subprocess wrapper for quantum-circuit-optimizer C++ binary.

    This class provides a Python interface to call the quantum-circuit-optimizer
    CLI via subprocess, parsing JSON output into typed dataclasses.

    Attributes:
        binary_path: Path to the quantum_circuit_optimizer executable.

    Example:
        >>> bridge = CircuitOptimizerBridge("/path/to/quantum_circuit_optimizer")
        >>> result = bridge.optimize(
        ...     qasm='OPENQASM 3.0; qubit q; h q;',
        ...     passes=["cancel", "commute"],
        ...     topology="iqm-garnet",
        ...     route=True,
        ... )
        >>> print(result.post_optimization.gates)
    """

    def __init__(self, binary_path: str | Path) -> None:
        """Initialize the bridge with path to optimizer binary.

        Args:
            binary_path: Path to the quantum_circuit_optimizer executable.

        Raises:
            FileNotFoundError: If binary does not exist or is not a file.
        """
        self.binary_path = Path(binary_path)
        self._validate_binary()

    def _validate_binary(self) -> None:
        """Validate that the binary exists and is a file.

        Raises:
            FileNotFoundError: If binary does not exist or is not a file.
        """
        if not self.binary_path.exists():
            raise FileNotFoundError(
                f"Optimizer binary not found: {self.binary_path}\n"
                f"Expected location from PROJECT_CONTEXT.md: "
                f"/home/rylan/Documents/career/code_bases/quantum/compilers/"
                f"quantum-circuit-optimizer/build/quantum_circuit_optimizer"
            )
        if not self.binary_path.is_file():
            raise FileNotFoundError(
                f"Optimizer path is not a file: {self.binary_path}"
            )

    def _validate_inputs(
        self,
        qasm: str,
        passes: list[str],
        topology: str | None,
        route: bool,
    ) -> None:
        """Validate optimization inputs.

        Args:
            qasm: OpenQASM circuit string.
            passes: List of pass names.
            topology: Target topology.
            route: Whether routing is enabled.

        Raises:
            ValueError: If any input is invalid.
        """
        # Check QASM is not empty
        if not qasm or not qasm.strip():
            raise ValueError(
                "QASM input is empty. Provide a valid OpenQASM 3.0 circuit."
            )

        # Check passes list is not empty
        if not passes:
            raise ValueError(
                "Passes list is empty. Provide at least one pass: "
                f"{sorted(VALID_PASSES)}"
            )

        # Check all passes are valid
        invalid_passes = set(passes) - VALID_PASSES
        if invalid_passes:
            raise ValueError(
                f"Invalid pass name(s): {sorted(invalid_passes)}. "
                f"Valid passes are: {sorted(VALID_PASSES)}"
            )

        # Check topology is provided if routing is enabled
        if route and not topology:
            raise ValueError(
                "Topology must be specified when route=True. "
                "Example topologies: 'iqm-garnet', 'linear-8', 'grid-3x3'"
            )

    def _build_cli_args(
        self,
        input_file: Path,
        output_file: Path,
        passes: list[str],
        topology: str | None,
        route: bool,
    ) -> list[str]:
        """Build CLI arguments for the optimizer.

        Args:
            input_file: Path to input QASM file.
            output_file: Path to output JSON file.
            passes: List of optimization passes.
            topology: Target topology (optional).
            route: Whether to enable routing.

        Returns:
            List of CLI arguments.
        """
        args = [
            str(self.binary_path),
            "--input",
            str(input_file),
            "--output",
            str(output_file),
            "--passes",
            ",".join(passes),
            "--output-format",
            "json",
        ]

        if topology:
            args.extend(["--topology", topology])

        if route:
            args.append("--route")

        return args

    def _run_optimizer(
        self,
        qasm: str,
        passes: list[str],
        topology: str | None,
        route: bool,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        """Run the optimizer subprocess and return parsed JSON.

        Args:
            qasm: OpenQASM circuit string.
            passes: List of optimization passes.
            topology: Target topology.
            route: Whether to enable routing.
            timeout: Subprocess timeout in seconds.

        Returns:
            Parsed JSON output from optimizer.

        Raises:
            RuntimeError: If subprocess fails or returns invalid JSON.
            subprocess.TimeoutExpired: If subprocess times out.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            input_file = tmpdir_path / "input.qasm"
            output_file = tmpdir_path / "output.json"

            # Write input QASM to temp file
            input_file.write_text(qasm)

            # Build CLI arguments
            args = self._build_cli_args(
                input_file=input_file,
                output_file=output_file,
                passes=passes,
                topology=topology,
                route=route,
            )

            # Run subprocess
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            self._check_subprocess_result(result)
            return self._read_json_output(output_file, result.stdout)

    def _check_subprocess_result(self, result: subprocess.CompletedProcess[str]) -> None:
        """Check subprocess result and raise if failed."""
        if result.returncode != 0:
            raise RuntimeError(
                f"Optimizer failed with exit code {result.returncode}.\n"
                f"stderr: {result.stderr}\n"
                f"stdout: {result.stdout}"
            )

    def _read_json_output(
        self, output_file: Path, fallback_stdout: str
    ) -> dict[str, Any]:
        """Read and parse JSON output from file or stdout fallback."""
        output_text = (
            output_file.read_text() if output_file.exists() else fallback_stdout
        )
        try:
            result_data: dict[str, Any] = json.loads(output_text)
            return result_data
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Optimizer returned invalid JSON: {e}\n"
                f"Output was: {output_text[:500]}"
            ) from e

    def _parse_stage_metrics(self, data: dict[str, Any]) -> StageMetrics:
        """Parse stage metrics from JSON data.

        Args:
            data: Dictionary with gates, depth, qubits, two_qubit_gates.

        Returns:
            StageMetrics dataclass.
        """
        return StageMetrics(
            gates=data["gates"],
            depth=data["depth"],
            qubits=data["qubits"],
            two_qubit_gates=data["two_qubit_gates"],
        )

    def _parse_pass_metrics(
        self,
        pass_data: dict[str, Any],
        prev_metrics: StageMetrics,
    ) -> PassMetrics:
        """Parse pass metrics from JSON data.

        Args:
            pass_data: Dictionary with pass information.
            prev_metrics: Metrics from before this pass.

        Returns:
            PassMetrics dataclass.
        """
        # Build output metrics from the pass output
        output_metrics = StageMetrics(
            gates=pass_data["output_gates"],
            depth=pass_data["output_depth"],
            qubits=prev_metrics.qubits,  # Qubits don't change
            two_qubit_gates=prev_metrics.two_qubit_gates - pass_data.get(
                "two_qubit_gates_removed", 0
            ),
        )

        return PassMetrics(
            name=pass_data["name"],
            input_metrics=prev_metrics,
            output_metrics=output_metrics,
            gates_removed=pass_data["gates_removed"],
            gates_added=pass_data["gates_added"],
            execution_time_ms=pass_data.get("execution_time_ms", 0.0),
        )

    def _parse_routing_metrics(
        self,
        routing_data: dict[str, Any],
        post_opt_metrics: StageMetrics,
    ) -> RoutingMetrics:
        """Parse routing metrics from JSON data.

        Args:
            routing_data: Dictionary with routing information.
            post_opt_metrics: Metrics after optimization (before routing).

        Returns:
            RoutingMetrics dataclass.
        """
        return RoutingMetrics(
            topology=routing_data["topology"],
            swaps_inserted=routing_data["swaps_inserted"],
            depth_increase=routing_data["final_depth"] - post_opt_metrics.depth,
            final_gates=routing_data["final_gates"],
            final_depth=routing_data["final_depth"],
        )

    def _parse_result(self, json_output: dict[str, Any]) -> OptimizationResult:
        """Parse optimizer JSON output into OptimizationResult.

        Args:
            json_output: Parsed JSON from optimizer.

        Returns:
            OptimizationResult dataclass.
        """
        # Parse input metrics
        input_metrics = self._parse_stage_metrics(json_output["input"])

        # Parse per-pass metrics
        passes = []
        prev_metrics = input_metrics
        for pass_data in json_output.get("passes", []):
            pass_metrics = self._parse_pass_metrics(pass_data, prev_metrics)
            passes.append(pass_metrics)
            prev_metrics = pass_metrics.output_metrics

        # Parse post-optimization metrics
        post_optimization = self._parse_stage_metrics(json_output["post_optimization"])

        # Parse routing metrics if present
        routing_metrics = None
        routing_data = json_output.get("routing")
        if routing_data is not None:
            routing_metrics = self._parse_routing_metrics(
                routing_data,
                post_optimization,
            )

        return OptimizationResult(
            input_metrics=input_metrics,
            passes=passes,
            post_optimization=post_optimization,
            routing_metrics=routing_metrics,
            output_qasm=json_output["output_qasm"],
        )

    def optimize(
        self,
        qasm: str,
        passes: list[str],
        topology: str | None = None,
        route: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> OptimizationResult:
        """Run optimization on an OpenQASM circuit.

        Args:
            qasm: OpenQASM 3.0 circuit string.
            passes: List of optimization passes to apply.
                Valid values: "cancel", "commute", "rotate", "identity"
            topology: Target topology (e.g., "iqm-garnet", "linear-8").
                Required if route=True.
            route: Whether to apply SABRE routing after optimization.
            timeout: Subprocess timeout in seconds (default: 60).

        Returns:
            OptimizationResult with metrics and optimized circuit.

        Raises:
            ValueError: If invalid passes or topology specified.
            RuntimeError: If optimizer binary fails.
            subprocess.TimeoutExpired: If optimization takes too long.
        """
        # Validate inputs first (fail fast)
        self._validate_inputs(qasm, passes, topology, route)

        # Run optimizer and get JSON output
        json_output = self._run_optimizer(qasm, passes, topology, route, timeout)

        # Parse and return result
        return self._parse_result(json_output)


# =============================================================================
# Mock Bridge for Testing
# =============================================================================


class MockCircuitOptimizerBridge:
    """Mock bridge for testing when the C++ optimizer is not available.

    Simulates optimization by applying simple heuristic gate reductions
    based on the passes specified. Useful for integration testing and
    running experiments without the C++ binary.
    """

    # Simulated gate reduction rates per pass (percentage of gates removed)
    PASS_REDUCTION_RATES = {
        "cancel": 0.15,    # 15% gate reduction
        "commute": 0.10,   # 10% gate reduction
        "rotate": 0.05,    # 5% gate reduction
        "identity": 0.02,  # 2% gate reduction
    }

    def _simulate_pass(
        self,
        pass_name: str,
        prev_metrics: StageMetrics,
        input_qubits: int,
    ) -> tuple[PassMetrics, StageMetrics]:
        """Simulate a single optimization pass."""
        reduction_rate = self.PASS_REDUCTION_RATES.get(pass_name, 0.0)

        gates_removed = int(prev_metrics.gates * reduction_rate)
        depth_reduction = max(1, int(prev_metrics.depth * reduction_rate * 0.5))

        output_metrics = StageMetrics(
            gates=max(1, prev_metrics.gates - gates_removed),
            depth=max(1, prev_metrics.depth - depth_reduction),
            qubits=input_qubits,
            two_qubit_gates=max(0, prev_metrics.two_qubit_gates - int(prev_metrics.two_qubit_gates * reduction_rate * 0.8)),
        )

        pass_metrics = PassMetrics(
            name=pass_name,
            input_metrics=prev_metrics,
            output_metrics=output_metrics,
            gates_removed=gates_removed,
            gates_added=0,
            execution_time_ms=1.0,
        )

        return pass_metrics, output_metrics

    def _simulate_routing(self, post_opt: StageMetrics, topology: str) -> RoutingMetrics:
        """Simulate routing SWAP insertions."""
        swaps_inserted = max(0, (post_opt.qubits - 2) * 2)
        return RoutingMetrics(
            topology=topology,
            swaps_inserted=swaps_inserted,
            depth_increase=swaps_inserted,
            final_gates=post_opt.gates + swaps_inserted * 3,
            final_depth=post_opt.depth + swaps_inserted,
        )

    def optimize(
        self,
        qasm: str,
        passes: list[str],
        topology: str | None = None,
        route: bool = False,
        timeout: int = DEFAULT_TIMEOUT,  # noqa: ARG002
    ) -> OptimizationResult:
        """Mock optimization that simulates pass effects."""
        from src.qasm import extract_metrics

        input_metrics = extract_metrics(qasm)
        pass_results: list[PassMetrics] = []
        current_metrics = input_metrics

        for pass_name in passes:
            pass_metric, current_metrics = self._simulate_pass(pass_name, current_metrics, input_metrics.qubits)
            pass_results.append(pass_metric)

        routing_metrics = self._simulate_routing(current_metrics, topology) if route and topology else None

        return OptimizationResult(
            input_metrics=input_metrics,
            passes=pass_results,
            post_optimization=current_metrics,
            routing_metrics=routing_metrics,
            output_qasm=qasm,
        )
