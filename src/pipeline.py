"""EndToEndPipeline: Orchestrates the full compilation and simulation flow.

This module provides the main pipeline class that coordinates:
1. Circuit parsing and validation
2. C++ optimizer (via CircuitOptimizerBridge)
3. Routing for target topology
4. Pulse compilation (via QubitPulseOpt)
5. Noise simulation

Following AgentBible principles:
- Clear stage-by-stage metrics collection
- Fail fast with context
- Type hints on all interfaces

Reference: ARCHITECTURE.md for data flow specification.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from src.bridge import CircuitOptimizerBridge, OptimizationResult
from src.metrics import (
    EndToEndResult,
    NoiseParams,
    PulseMetrics,
    RoutingMetrics,
    StageMetrics,
)
from src.qasm import QASMParseError, extract_metrics, validate_qasm

if TYPE_CHECKING:
    pass


# =============================================================================
# Protocols for External Dependencies
# =============================================================================


class OptimizerBridgeProtocol(Protocol):
    """Protocol for circuit optimizer bridges (real or mock)."""

    def optimize(
        self,
        qasm: str,
        passes: list[str],
        topology: str | None = None,
        route: bool = False,
        timeout: int = 60,
    ) -> OptimizationResult:
        """Optimize a quantum circuit.

        Args:
            qasm: OpenQASM 3.0 circuit string.
            passes: List of optimization passes to apply.
            topology: Target topology (e.g., "iqm-garnet").
            route: Whether to apply routing.
            timeout: Timeout in seconds.

        Returns:
            OptimizationResult with metrics and optimized circuit.
        """
        ...


class GateCompilerProtocol(Protocol):
    """Protocol for pulse gate compilers (e.g., QubitPulseOpt GateCompiler)."""

    def compile_gate_sequence(self, gate_sequence: list[dict[str, Any]]) -> Any:
        """Compile a sequence of gates to pulses.

        Args:
            gate_sequence: List of gate dictionaries with name and qubit info.

        Returns:
            Pulse sequence object.
        """
        ...

    def simulate_with_noise(
        self,
        pulses: Any,
        noise_model: dict[str, float],
    ) -> dict[str, float]:
        """Simulate pulses with noise model.

        Args:
            pulses: Pulse sequence to simulate.
            noise_model: Dictionary of noise parameters.

        Returns:
            Dictionary with process_fidelity and state_fidelity.
        """
        ...


# =============================================================================
# Stage Result Types
# =============================================================================


class Stage1Result:
    """Result from Stage 1: Parse and validate."""

    def __init__(self, input_metrics: StageMetrics, validated_qasm: str) -> None:
        self.input_metrics = input_metrics
        self.validated_qasm = validated_qasm


class Stage2Result:
    """Result from Stage 2: Optimize."""

    def __init__(
        self,
        optimization_result: OptimizationResult,
        optimized_qasm: str,
    ) -> None:
        self.optimization_result = optimization_result
        self.optimized_qasm = optimized_qasm


class Stage3Result:
    """Result from Stage 3: Route."""

    def __init__(
        self,
        routed_qasm: str,
        routing_metrics: RoutingMetrics | None,
        post_routing_metrics: StageMetrics,
    ) -> None:
        self.routed_qasm = routed_qasm
        self.routing_metrics = routing_metrics
        self.post_routing_metrics = post_routing_metrics


class Stage4Result:
    """Result from Stage 4: Pulse compilation."""

    def __init__(
        self,
        pulses: Any,
        pulse_metrics: PulseMetrics,
    ) -> None:
        self.pulses = pulses
        self.pulse_metrics = pulse_metrics


class Stage5Result:
    """Result from Stage 5: Noise simulation."""

    def __init__(
        self,
        process_fidelity: float,
        state_fidelity: float,
    ) -> None:
        self.process_fidelity = process_fidelity
        self.state_fidelity = state_fidelity


# =============================================================================
# Mock Gate Compiler for Testing
# =============================================================================


class MockGateCompiler:
    """Mock gate compiler for testing when QubitPulseOpt is not available.

    This provides reasonable mock values based on circuit structure.
    """

    def __init__(
        self,
        single_qubit_gate_duration_ns: float = 20.0,
        two_qubit_gate_duration_ns: float = 40.0,
    ) -> None:
        """Initialize mock compiler with gate durations.

        Args:
            single_qubit_gate_duration_ns: Duration for 1Q gates (IQM PRX = 20ns).
            two_qubit_gate_duration_ns: Duration for 2Q gates (IQM CZ = 40ns).
        """
        self.single_qubit_gate_duration_ns = single_qubit_gate_duration_ns
        self.two_qubit_gate_duration_ns = two_qubit_gate_duration_ns

    def compile_gate_sequence(
        self,
        gate_sequence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Mock compilation: calculate duration based on gate types.

        Args:
            gate_sequence: List of gate dictionaries.

        Returns:
            Mock pulse data with timing info.
        """
        total_duration = 0.0
        pulse_count = 0

        for gate in gate_sequence:
            num_qubits = gate.get("num_qubits", 1)
            if num_qubits >= 2:
                total_duration += self.two_qubit_gate_duration_ns
            else:
                total_duration += self.single_qubit_gate_duration_ns
            pulse_count += 1

        return {
            "total_duration_ns": total_duration,
            "pulse_count": pulse_count,
            "max_amplitude": 0.8,  # Typical value
            "gate_sequence": gate_sequence,
        }

    def simulate_with_noise(
        self,
        pulses: dict[str, Any],
        noise_model: dict[str, float],
    ) -> dict[str, float]:
        """Mock simulation: estimate fidelity based on noise and duration.

        Uses a simple exponential decay model for coherent errors.

        Args:
            pulses: Mock pulse data from compile_gate_sequence.
            noise_model: Dictionary with t1_ns, t2_ns, error rates.

        Returns:
            Dictionary with estimated fidelities.
        """
        total_duration = pulses.get("total_duration_ns", 0.0)
        pulse_count = pulses.get("pulse_count", 0)

        t1_ns = noise_model.get("t1_ns", 30000.0)
        t2_ns = noise_model.get("t2_ns", 10000.0)
        single_qubit_error = noise_model.get("single_qubit_error", 0.001)
        two_qubit_error = noise_model.get("two_qubit_error", 0.006)

        # Simple fidelity model:
        # 1. Decoherence contribution: exp(-t/T2)
        # 2. Gate error contribution: (1 - avg_error)^num_gates
        import math

        decoherence_fidelity = math.exp(-total_duration / t2_ns)

        # Rough estimate: half the gates are 2Q
        avg_error = (single_qubit_error + two_qubit_error) / 2
        gate_fidelity = (1 - avg_error) ** pulse_count

        # Combined process fidelity
        process_fidelity = min(1.0, max(0.0, decoherence_fidelity * gate_fidelity))

        # State fidelity is typically slightly higher than process fidelity
        # For a d-dimensional system: F_state >= (d * F_process + 1) / (d + 1)
        # For qubits, d=2, so F_state >= (2*F_process + 1) / 3
        state_fidelity = min(1.0, (2 * process_fidelity + 1) / 3)

        # Add some T1 contribution for relaxation
        t1_factor = math.exp(-total_duration / (2 * t1_ns))  # T1 affects state fidelity
        state_fidelity *= t1_factor

        return {
            "process_fidelity": process_fidelity,
            "state_fidelity": state_fidelity,
        }


# =============================================================================
# EndToEndPipeline
# =============================================================================


class EndToEndPipeline:
    """Orchestrates the full compilation and simulation flow.

    This class coordinates all stages of quantum circuit compilation:
    Stage 1: Parse input circuit
    Stage 2: Run C++ optimizer (configurable passes)
    Stage 3: Route for target topology
    Stage 4: Compile to pulses via QubitPulseOpt GateCompiler
    Stage 5: Simulate with noise model

    Metrics are collected at each stage for analysis.

    Attributes:
        optimizer_bridge: Bridge to C++ optimizer.
        noise_params: Default noise model parameters.
        default_topology: Default target topology.
        gate_compiler: Pulse compiler (QubitPulseOpt or mock).

    Example:
        >>> bridge = CircuitOptimizerBridge("/path/to/optimizer")
        >>> noise = NoiseParams(t1_ns=30000, t2_ns=10000, ...)
        >>> pipeline = EndToEndPipeline(bridge, noise_params=noise)
        >>> result = pipeline.run(circuit_qasm, passes=["cancel", "commute"])
    """

    def __init__(
        self,
        optimizer_bridge: OptimizerBridgeProtocol,
        noise_params: NoiseParams,
        default_topology: str = "iqm-garnet",
        gate_compiler: GateCompilerProtocol | None = None,
    ) -> None:
        """Initialize the pipeline.

        Args:
            optimizer_bridge: Bridge to circuit optimizer (real or mock).
            noise_params: Noise model parameters for simulation.
            default_topology: Default target topology for routing.
            gate_compiler: Optional pulse compiler. If None, uses MockGateCompiler.
        """
        self.optimizer_bridge = optimizer_bridge
        self.noise_params = noise_params
        self.default_topology = default_topology
        self.gate_compiler: GateCompilerProtocol = (
            gate_compiler if gate_compiler is not None else MockGateCompiler()
        )

    def run(
        self,
        circuit: str,
        passes: list[str],
        topology: str | None = None,
        noise_params: NoiseParams | None = None,
        circuit_name: str | None = None,
        route: bool = True,
    ) -> EndToEndResult:
        """Execute full pipeline and collect metrics.

        Args:
            circuit: OpenQASM 3.0 circuit string.
            passes: List of optimization passes to apply.
            topology: Target topology (defaults to self.default_topology).
            noise_params: Override noise parameters for this run.
            circuit_name: Identifier for this circuit (for results tracking).
            route: Whether to apply routing (default True).

        Returns:
            EndToEndResult with metrics from all stages.

        Raises:
            ValueError: If circuit is invalid or passes are unknown.
            RuntimeError: If any pipeline stage fails.
        """
        # Resolve defaults
        effective_topology = topology or self.default_topology
        effective_noise = noise_params or self.noise_params
        effective_name = circuit_name or "unnamed_circuit"

        # Stage 1: Parse and validate
        stage1 = self._stage1_parse(circuit)

        # Stage 2: Optimize (includes routing if enabled)
        stage2 = self._stage2_optimize(
            circuit=stage1.validated_qasm,
            passes=passes,
            topology=effective_topology if route else None,
            route=route,
        )

        # Stage 3: Extract routing info (from optimizer result)
        stage3 = self._stage3_extract_routing(stage2)

        # Stage 4: Pulse compilation
        stage4 = self._stage4_pulse_compile(stage3.routed_qasm)

        # Stage 5: Noise simulation
        stage5 = self._stage5_simulate(stage4.pulses, effective_noise)

        # Build and return result
        return EndToEndResult(
            circuit_name=effective_name,
            input_metrics=stage1.input_metrics,
            optimization_passes=stage2.optimization_result.passes,
            post_optimization=stage2.optimization_result.post_optimization,
            routing_metrics=stage3.routing_metrics,
            pulse_metrics=stage4.pulse_metrics,
            process_fidelity=stage5.process_fidelity,
            state_fidelity=stage5.state_fidelity,
            noise_params=effective_noise,
            topology=effective_topology,
            timestamp=datetime.now(),
        )

    def _stage1_parse(self, circuit: str) -> Stage1Result:
        """Stage 1: Parse and validate input circuit.

        Args:
            circuit: OpenQASM 3.0 circuit string.

        Returns:
            Stage1Result with input metrics and validated QASM.

        Raises:
            ValueError: If circuit is invalid.
        """
        # Validate QASM
        is_valid, errors = validate_qasm(circuit)
        if not is_valid:
            raise ValueError(
                "Invalid OpenQASM circuit:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        # Extract metrics
        try:
            input_metrics = extract_metrics(circuit)
        except QASMParseError as e:
            raise ValueError(f"Failed to parse circuit metrics: {e}") from e

        return Stage1Result(
            input_metrics=input_metrics,
            validated_qasm=circuit,
        )

    def _stage2_optimize(
        self,
        circuit: str,
        passes: list[str],
        topology: str | None,
        route: bool,
    ) -> Stage2Result:
        """Stage 2: Run C++ optimizer.

        Args:
            circuit: OpenQASM 3.0 circuit string.
            passes: List of optimization passes.
            topology: Target topology (for routing).
            route: Whether to enable routing.

        Returns:
            Stage2Result with optimization result and output QASM.

        Raises:
            RuntimeError: If optimizer fails.
        """
        result = self.optimizer_bridge.optimize(
            qasm=circuit,
            passes=passes,
            topology=topology,
            route=route,
        )

        return Stage2Result(
            optimization_result=result,
            optimized_qasm=result.output_qasm,
        )

    def _stage3_extract_routing(self, stage2: Stage2Result) -> Stage3Result:
        """Stage 3: Extract routing information from optimizer result.

        The C++ optimizer performs routing as part of optimization,
        so this stage extracts the routing metrics from that result.

        Args:
            stage2: Result from stage 2 optimization.

        Returns:
            Stage3Result with routed QASM and routing metrics.
        """
        opt_result = stage2.optimization_result

        # If routing was performed, use the routing metrics
        if opt_result.routing_metrics is not None:
            post_routing_metrics = StageMetrics(
                gates=opt_result.routing_metrics.final_gates,
                depth=opt_result.routing_metrics.final_depth,
                qubits=opt_result.post_optimization.qubits,
                two_qubit_gates=opt_result.post_optimization.two_qubit_gates
                + opt_result.routing_metrics.swaps_inserted,  # SWAPs add 2Q gates
            )
        else:
            post_routing_metrics = opt_result.post_optimization

        return Stage3Result(
            routed_qasm=stage2.optimized_qasm,
            routing_metrics=opt_result.routing_metrics,
            post_routing_metrics=post_routing_metrics,
        )

    def _stage4_pulse_compile(self, circuit: str) -> Stage4Result:
        """Stage 4: Compile gates to pulses via GateCompiler.

        Args:
            circuit: OpenQASM 3.0 circuit string.

        Returns:
            Stage4Result with pulses and pulse metrics.
        """
        # Convert QASM to gate sequence
        gate_sequence = self._qasm_to_gate_sequence(circuit)

        # Compile to pulses
        pulses = self.gate_compiler.compile_gate_sequence(gate_sequence)

        # Extract pulse metrics
        if isinstance(pulses, dict):
            pulse_metrics = PulseMetrics(
                total_duration_ns=pulses.get("total_duration_ns", 0.0),
                pulse_count=pulses.get("pulse_count", 0),
                max_amplitude=pulses.get("max_amplitude", 0.0),
            )
        else:
            # For real QubitPulseOpt, extract from pulse object
            pulse_metrics = PulseMetrics(
                total_duration_ns=getattr(pulses, "total_duration_ns", 0.0),
                pulse_count=getattr(pulses, "pulse_count", 0),
                max_amplitude=getattr(pulses, "max_amplitude", 0.0),
            )

        return Stage4Result(pulses=pulses, pulse_metrics=pulse_metrics)

    def _stage5_simulate(
        self,
        pulses: Any,
        noise_params: NoiseParams,
    ) -> Stage5Result:
        """Stage 5: Simulate with noise model.

        Args:
            pulses: Pulse sequence from Stage 4.
            noise_params: Noise model parameters.

        Returns:
            Stage5Result with fidelity values.
        """
        # Convert NoiseParams to dict for compiler interface
        noise_model = {
            "t1_ns": noise_params.t1_ns,
            "t2_ns": noise_params.t2_ns,
            "single_qubit_error": noise_params.single_qubit_error,
            "two_qubit_error": noise_params.two_qubit_error,
        }

        # Run simulation
        fidelities = self.gate_compiler.simulate_with_noise(pulses, noise_model)

        return Stage5Result(
            process_fidelity=fidelities["process_fidelity"],
            state_fidelity=fidelities["state_fidelity"],
        )

    def _qasm_to_gate_sequence(self, circuit: str) -> list[dict[str, Any]]:
        """Convert OpenQASM circuit to gate sequence for pulse compilation.

        Args:
            circuit: OpenQASM 3.0 circuit string.

        Returns:
            List of gate dictionaries with name and qubit info.
        """
        from src.qasm import parse_qasm

        parsed = parse_qasm(circuit)
        gate_sequence = []

        for gate in parsed.gates:
            gate_sequence.append({
                "name": gate.name,
                "qubits": list(gate.qubits),
                "parameters": list(gate.parameters),
                "num_qubits": gate.num_qubits,
            })

        return gate_sequence


# =============================================================================
# Utility Functions
# =============================================================================


def create_pipeline_with_mock(
    optimizer_binary_path: str,
    noise_params: NoiseParams | None = None,
    default_topology: str = "iqm-garnet",
) -> EndToEndPipeline:
    """Create a pipeline with mock gate compiler for testing.

    Args:
        optimizer_binary_path: Path to C++ optimizer binary.
        noise_params: Noise parameters (defaults to IQM Garnet medians).
        default_topology: Default topology for routing.

    Returns:
        Configured EndToEndPipeline instance.
    """
    bridge = CircuitOptimizerBridge(optimizer_binary_path)

    if noise_params is None:
        # IQM Garnet median values from IQM_GARNET_SPEC.md
        noise_params = NoiseParams(
            t1_ns=37000.0,
            t2_ns=9600.0,
            single_qubit_error=0.001,
            two_qubit_error=0.006,
        )

    return EndToEndPipeline(
        optimizer_bridge=bridge,
        noise_params=noise_params,
        default_topology=default_topology,
        gate_compiler=MockGateCompiler(),
    )


# =============================================================================
# Real Pipeline with Lindblad Simulation
# =============================================================================


class RealPulseGateCompiler:
    """Adapter for RealGateCompiler to match GateCompilerProtocol.

    Uses qiskit-dynamics based Lindblad simulation for realistic fidelity.
    """

    def __init__(self, noise_params: NoiseParams) -> None:
        """Initialize with noise parameters.

        Args:
            noise_params: IQM Garnet noise parameters.
        """
        from src.pulse import RealGateCompiler

        self.noise_params = noise_params
        self._compiler = RealGateCompiler(noise_params)
        self._last_metrics: dict[str, Any] | None = None

    def _parse_qubit_index(self, qubit: int | str) -> int:
        """Extract numeric qubit index from various formats.

        Args:
            qubit: Qubit identifier (int, 'q[0]', '0', etc.)

        Returns:
            Integer qubit index.
        """
        if isinstance(qubit, int):
            return qubit
        # Handle 'q[0]' format
        if isinstance(qubit, str):
            if "[" in qubit and "]" in qubit:
                # Extract number from q[N] format
                import re

                match = re.search(r"\[(\d+)\]", qubit)
                if match:
                    return int(match.group(1))
            # Try direct int conversion
            try:
                return int(qubit)
            except ValueError:
                return 0
        return 0

    def compile_gate_sequence(
        self,
        gate_sequence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compile gate sequence and cache metrics for simulation.

        Args:
            gate_sequence: List of gate dictionaries.

        Returns:
            Pulse data dictionary with metrics.
        """
        # Count gate types
        num_gates = len(gate_sequence)
        num_two_qubit = sum(1 for g in gate_sequence if g.get("num_qubits", 1) >= 2)

        # Extract num_qubits from gate sequence
        max_qubit = 0
        for g in gate_sequence:
            qubits = g.get("qubits", [0])
            for q in qubits:
                q_int = self._parse_qubit_index(q)
                max_qubit = max(max_qubit, q_int)
        num_qubits = max(1, max_qubit + 1)

        # Use real compiler
        proc_f, state_f, metrics = self._compiler.compile_and_simulate(
            qasm="",  # Not needed, using gate stats
            num_qubits=num_qubits,
            num_gates=num_gates,
            num_two_qubit_gates=num_two_qubit,
        )

        # Cache for simulate_with_noise
        self._last_metrics = {
            "total_duration_ns": metrics.total_duration_ns,
            "pulse_count": metrics.pulse_count,
            "max_amplitude": metrics.max_amplitude,
            "process_fidelity": proc_f,
            "state_fidelity": state_f,
        }

        return self._last_metrics

    def simulate_with_noise(
        self,
        pulses: dict[str, Any],
        noise_model: dict[str, float],  # noqa: ARG002
    ) -> dict[str, float]:
        """Return cached fidelities from compilation.

        Args:
            pulses: Pulse data from compile_gate_sequence.
            noise_model: Noise parameters (already included in compilation).

        Returns:
            Dictionary with fidelities.
        """
        # Fidelity was computed during compilation
        return {
            "process_fidelity": pulses.get("process_fidelity", 0.9),
            "state_fidelity": pulses.get("state_fidelity", 0.9),
        }


def create_real_pipeline(
    noise_params: NoiseParams | None = None,
    default_topology: str = "iqm-garnet",
    use_mock_optimizer: bool = False,
) -> EndToEndPipeline:
    """Create a pipeline with real C++ optimizer and Lindblad pulse simulation.

    Args:
        noise_params: Noise parameters (defaults to IQM Garnet medians).
        default_topology: Default topology for routing.
        use_mock_optimizer: If True, use mock optimizer (for testing).

    Returns:
        Configured EndToEndPipeline with real components.
    """
    from pathlib import Path

    from src.bridge import MockCircuitOptimizerBridge

    # Default noise parameters
    if noise_params is None:
        noise_params = NoiseParams(
            t1_ns=37000.0,
            t2_ns=9600.0,
            single_qubit_error=0.001,
            two_qubit_error=0.006,
        )

    # Setup optimizer bridge
    if use_mock_optimizer:
        bridge: OptimizerBridgeProtocol = MockCircuitOptimizerBridge()
    else:
        # Path to real C++ optimizer
        optimizer_path = Path(
            "/home/rylan/dev/research/"
            "quantum-circuit-optimizer/build/quantum_circuit_optimizer"
        )
        if not optimizer_path.exists():
            raise FileNotFoundError(
                f"C++ optimizer not found at {optimizer_path}. "
                "Build it or set use_mock_optimizer=True."
            )
        bridge = CircuitOptimizerBridge(optimizer_path)

    # Real pulse compiler with Lindblad simulation
    gate_compiler = RealPulseGateCompiler(noise_params)

    return EndToEndPipeline(
        optimizer_bridge=bridge,
        noise_params=noise_params,
        default_topology=default_topology,
        gate_compiler=gate_compiler,
    )
