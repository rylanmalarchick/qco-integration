"""Tests for EndToEndPipeline.

Tests cover:
- Pipeline initialization
- Stage 1: Parsing and validation
- Stage 2: Optimization (mocked)
- Stage 3: Routing extraction
- Stage 4: Pulse compilation (mock)
- Stage 5: Noise simulation (mock)
- Full pipeline integration

Following AgentBible testing principles:
- Specification Before Code
- Mock external dependencies
- Clear test names describing expected behavior
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.bridge import OptimizationResult
from src.metrics import (
    EndToEndResult,
    NoiseParams,
    PassMetrics,
    PulseMetrics,
    RoutingMetrics,
    StageMetrics,
)
from src.pipeline import (
    EndToEndPipeline,
    MockGateCompiler,
    Stage1Result,
    Stage2Result,
    Stage3Result,
    Stage4Result,
    Stage5Result,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_bridge() -> MagicMock:
    """Create a mock CircuitOptimizerBridge."""
    bridge = MagicMock()

    # Default optimization result
    input_metrics = StageMetrics(gates=10, depth=5, qubits=2, two_qubit_gates=3)
    output_metrics = StageMetrics(gates=8, depth=4, qubits=2, two_qubit_gates=2)

    bridge.optimize.return_value = OptimizationResult(
        input_metrics=input_metrics,
        passes=[
            PassMetrics(
                name="CancellationPass",
                input_metrics=input_metrics,
                output_metrics=output_metrics,
                gates_removed=2,
                gates_added=0,
                execution_time_ms=1.5,
            )
        ],
        post_optimization=output_metrics,
        routing_metrics=None,
        output_qasm="OPENQASM 3.0;\nqubit[2] q;\nh q[0];\ncx q[0], q[1];",
    )

    return bridge


@pytest.fixture
def mock_bridge_with_routing() -> MagicMock:
    """Create a mock CircuitOptimizerBridge that returns routing metrics."""
    bridge = MagicMock()

    input_metrics = StageMetrics(gates=10, depth=5, qubits=2, two_qubit_gates=3)
    output_metrics = StageMetrics(gates=8, depth=4, qubits=2, two_qubit_gates=2)

    routing_metrics = RoutingMetrics(
        topology="iqm-garnet",
        swaps_inserted=2,
        depth_increase=3,
        final_gates=14,
        final_depth=7,
    )

    bridge.optimize.return_value = OptimizationResult(
        input_metrics=input_metrics,
        passes=[
            PassMetrics(
                name="CancellationPass",
                input_metrics=input_metrics,
                output_metrics=output_metrics,
                gates_removed=2,
                gates_added=0,
                execution_time_ms=1.5,
            )
        ],
        post_optimization=output_metrics,
        routing_metrics=routing_metrics,
        output_qasm="OPENQASM 3.0;\nqubit[2] q;\nh q[0];\ncx q[0], q[1];",
    )

    return bridge


@pytest.fixture
def noise_params() -> NoiseParams:
    """IQM Garnet median noise parameters."""
    return NoiseParams(
        t1_ns=37000.0,
        t2_ns=9600.0,
        single_qubit_error=0.001,
        two_qubit_error=0.006,
    )


@pytest.fixture
def pipeline(mock_bridge: MagicMock, noise_params: NoiseParams) -> EndToEndPipeline:
    """Create a pipeline with mock bridge."""
    return EndToEndPipeline(
        optimizer_bridge=mock_bridge,
        noise_params=noise_params,
        default_topology="iqm-garnet",
    )


@pytest.fixture
def pipeline_with_routing(
    mock_bridge_with_routing: MagicMock,
    noise_params: NoiseParams,
) -> EndToEndPipeline:
    """Create a pipeline with mock bridge that returns routing."""
    return EndToEndPipeline(
        optimizer_bridge=mock_bridge_with_routing,
        noise_params=noise_params,
        default_topology="iqm-garnet",
    )


# =============================================================================
# MockGateCompiler Tests
# =============================================================================


class TestMockGateCompiler:
    """Tests for MockGateCompiler."""

    def test_compile_gate_sequence_single_qubit(self) -> None:
        """Single-qubit gates use correct duration."""
        compiler = MockGateCompiler(
            single_qubit_gate_duration_ns=20.0,
            two_qubit_gate_duration_ns=40.0,
        )

        gate_sequence = [
            {"name": "h", "qubits": ["q[0]"], "num_qubits": 1},
            {"name": "x", "qubits": ["q[0]"], "num_qubits": 1},
        ]

        result = compiler.compile_gate_sequence(gate_sequence)

        assert result["total_duration_ns"] == 40.0  # 2 * 20ns
        assert result["pulse_count"] == 2

    def test_compile_gate_sequence_two_qubit(self) -> None:
        """Two-qubit gates use correct duration."""
        compiler = MockGateCompiler(
            single_qubit_gate_duration_ns=20.0,
            two_qubit_gate_duration_ns=40.0,
        )

        gate_sequence = [
            {"name": "cx", "qubits": ["q[0]", "q[1]"], "num_qubits": 2},
        ]

        result = compiler.compile_gate_sequence(gate_sequence)

        assert result["total_duration_ns"] == 40.0  # 1 * 40ns
        assert result["pulse_count"] == 1

    def test_compile_gate_sequence_mixed(self) -> None:
        """Mixed gate types calculate correct total."""
        compiler = MockGateCompiler(
            single_qubit_gate_duration_ns=20.0,
            two_qubit_gate_duration_ns=40.0,
        )

        gate_sequence = [
            {"name": "h", "qubits": ["q[0]"], "num_qubits": 1},
            {"name": "cx", "qubits": ["q[0]", "q[1]"], "num_qubits": 2},
            {"name": "x", "qubits": ["q[1]"], "num_qubits": 1},
        ]

        result = compiler.compile_gate_sequence(gate_sequence)

        assert result["total_duration_ns"] == 80.0  # 2*20 + 1*40
        assert result["pulse_count"] == 3

    def test_simulate_with_noise_returns_fidelities(self) -> None:
        """Simulation returns process and state fidelities."""
        compiler = MockGateCompiler()

        pulses = {
            "total_duration_ns": 100.0,
            "pulse_count": 5,
            "max_amplitude": 0.8,
        }

        noise_model = {
            "t1_ns": 30000.0,
            "t2_ns": 10000.0,
            "single_qubit_error": 0.001,
            "two_qubit_error": 0.006,
        }

        result = compiler.simulate_with_noise(pulses, noise_model)

        assert "process_fidelity" in result
        assert "state_fidelity" in result
        assert 0 <= result["process_fidelity"] <= 1
        assert 0 <= result["state_fidelity"] <= 1

    def test_simulate_longer_duration_lower_fidelity(self) -> None:
        """Longer duration results in lower fidelity."""
        compiler = MockGateCompiler()

        noise_model = {
            "t1_ns": 30000.0,
            "t2_ns": 10000.0,
            "single_qubit_error": 0.001,
            "two_qubit_error": 0.006,
        }

        short_pulses = {"total_duration_ns": 100.0, "pulse_count": 5}
        long_pulses = {"total_duration_ns": 5000.0, "pulse_count": 5}

        short_result = compiler.simulate_with_noise(short_pulses, noise_model)
        long_result = compiler.simulate_with_noise(long_pulses, noise_model)

        assert short_result["process_fidelity"] > long_result["process_fidelity"]

    def test_simulate_more_gates_lower_fidelity(self) -> None:
        """More gates result in lower fidelity."""
        compiler = MockGateCompiler()

        noise_model = {
            "t1_ns": 30000.0,
            "t2_ns": 10000.0,
            "single_qubit_error": 0.001,
            "two_qubit_error": 0.006,
        }

        few_gates = {"total_duration_ns": 100.0, "pulse_count": 2}
        many_gates = {"total_duration_ns": 100.0, "pulse_count": 50}

        few_result = compiler.simulate_with_noise(few_gates, noise_model)
        many_result = compiler.simulate_with_noise(many_gates, noise_model)

        assert few_result["process_fidelity"] > many_result["process_fidelity"]


# =============================================================================
# Pipeline Initialization Tests
# =============================================================================


class TestEndToEndPipelineInit:
    """Tests for EndToEndPipeline initialization."""

    def test_init_with_mock_bridge(
        self,
        mock_bridge: MagicMock,
        noise_params: NoiseParams,
    ) -> None:
        """Pipeline initializes with mock bridge."""
        pipeline = EndToEndPipeline(
            optimizer_bridge=mock_bridge,
            noise_params=noise_params,
        )

        assert pipeline.optimizer_bridge is mock_bridge
        assert pipeline.noise_params == noise_params
        assert pipeline.default_topology == "iqm-garnet"

    def test_init_default_gate_compiler(
        self,
        mock_bridge: MagicMock,
        noise_params: NoiseParams,
    ) -> None:
        """Pipeline uses MockGateCompiler by default."""
        pipeline = EndToEndPipeline(
            optimizer_bridge=mock_bridge,
            noise_params=noise_params,
        )

        assert isinstance(pipeline.gate_compiler, MockGateCompiler)

    def test_init_custom_topology(
        self,
        mock_bridge: MagicMock,
        noise_params: NoiseParams,
    ) -> None:
        """Pipeline accepts custom default topology."""
        pipeline = EndToEndPipeline(
            optimizer_bridge=mock_bridge,
            noise_params=noise_params,
            default_topology="linear-8",
        )

        assert pipeline.default_topology == "linear-8"


# =============================================================================
# Stage 1 Tests
# =============================================================================


class TestStage1Parse:
    """Tests for Stage 1: Parse and validate."""

    def test_stage1_valid_circuit(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Valid circuit passes stage 1."""
        result = pipeline._stage1_parse(bell_qasm)

        assert isinstance(result, Stage1Result)
        assert result.input_metrics.gates == 2
        assert result.input_metrics.qubits == 2
        assert result.validated_qasm == bell_qasm

    def test_stage1_empty_circuit_raises(self, pipeline: EndToEndPipeline) -> None:
        """Empty circuit raises ValueError."""
        with pytest.raises(ValueError, match="Invalid OpenQASM"):
            pipeline._stage1_parse("")

    def test_stage1_no_version_raises(self, pipeline: EndToEndPipeline) -> None:
        """Circuit without version raises ValueError."""
        with pytest.raises(ValueError, match="Invalid OpenQASM"):
            pipeline._stage1_parse("qubit q; h q;")


# =============================================================================
# Stage 2 Tests
# =============================================================================


class TestStage2Optimize:
    """Tests for Stage 2: Optimize."""

    def test_stage2_calls_bridge(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Stage 2 calls optimizer bridge with correct args."""
        pipeline._stage2_optimize(
            circuit=bell_qasm,
            passes=["cancel", "commute"],
            topology="iqm-garnet",
            route=True,
        )

        pipeline.optimizer_bridge.optimize.assert_called_once_with(  # type: ignore[attr-defined]
            qasm=bell_qasm,
            passes=["cancel", "commute"],
            topology="iqm-garnet",
            route=True,
        )

    def test_stage2_returns_result(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Stage 2 returns Stage2Result with optimization data."""
        result = pipeline._stage2_optimize(
            circuit=bell_qasm,
            passes=["cancel"],
            topology=None,
            route=False,
        )

        assert isinstance(result, Stage2Result)
        assert result.optimization_result is not None
        assert "OPENQASM" in result.optimized_qasm


# =============================================================================
# Stage 3 Tests
# =============================================================================


class TestStage3ExtractRouting:
    """Tests for Stage 3: Extract routing."""

    def test_stage3_without_routing(self, pipeline: EndToEndPipeline) -> None:
        """Stage 3 handles missing routing metrics."""
        # Create a Stage2Result without routing
        opt_result = OptimizationResult(
            input_metrics=StageMetrics(gates=10, depth=5, qubits=2, two_qubit_gates=3),
            passes=[],
            post_optimization=StageMetrics(
                gates=8, depth=4, qubits=2, two_qubit_gates=2
            ),
            routing_metrics=None,
            output_qasm="OPENQASM 3.0; qubit q; h q;",
        )
        stage2 = Stage2Result(
            optimization_result=opt_result,
            optimized_qasm=opt_result.output_qasm,
        )

        result = pipeline._stage3_extract_routing(stage2)

        assert isinstance(result, Stage3Result)
        assert result.routing_metrics is None
        assert result.post_routing_metrics.gates == 8

    def test_stage3_with_routing(
        self, pipeline_with_routing: EndToEndPipeline
    ) -> None:
        """Stage 3 extracts routing metrics when present."""
        # Run stage 2 to get result with routing
        stage2 = pipeline_with_routing._stage2_optimize(
            circuit="OPENQASM 3.0;\nqubit[2] q;\nh q[0];",
            passes=["cancel"],
            topology="iqm-garnet",
            route=True,
        )

        result = pipeline_with_routing._stage3_extract_routing(stage2)

        assert result.routing_metrics is not None
        assert result.routing_metrics.swaps_inserted == 2
        assert result.routing_metrics.topology == "iqm-garnet"


# =============================================================================
# Stage 4 Tests
# =============================================================================


class TestStage4PulseCompile:
    """Tests for Stage 4: Pulse compilation."""

    def test_stage4_returns_pulse_metrics(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Stage 4 returns pulse metrics."""
        result = pipeline._stage4_pulse_compile(bell_qasm)

        assert isinstance(result, Stage4Result)
        assert isinstance(result.pulse_metrics, PulseMetrics)
        assert result.pulse_metrics.pulse_count > 0
        assert result.pulse_metrics.total_duration_ns > 0

    def test_stage4_duration_scales_with_gates(
        self, pipeline: EndToEndPipeline
    ) -> None:
        """Pulse duration scales with number of gates."""
        small_circuit = "OPENQASM 3.0;\nqubit q;\nh q;"
        large_circuit = """OPENQASM 3.0;
qubit[4] q;
h q[0];
cx q[0], q[1];
cx q[1], q[2];
cx q[2], q[3];
"""

        small_result = pipeline._stage4_pulse_compile(small_circuit)
        large_result = pipeline._stage4_pulse_compile(large_circuit)

        assert large_result.pulse_metrics.total_duration_ns > (
            small_result.pulse_metrics.total_duration_ns
        )


# =============================================================================
# Stage 5 Tests
# =============================================================================


class TestStage5Simulate:
    """Tests for Stage 5: Noise simulation."""

    def test_stage5_returns_fidelities(
        self,
        pipeline: EndToEndPipeline,
        noise_params: NoiseParams,
    ) -> None:
        """Stage 5 returns fidelity values."""
        pulses = {
            "total_duration_ns": 100.0,
            "pulse_count": 5,
            "max_amplitude": 0.8,
        }

        result = pipeline._stage5_simulate(pulses, noise_params)

        assert isinstance(result, Stage5Result)
        assert 0 <= result.process_fidelity <= 1
        assert 0 <= result.state_fidelity <= 1

    def test_stage5_uses_provided_noise_params(
        self, pipeline: EndToEndPipeline
    ) -> None:
        """Stage 5 uses the provided noise parameters."""
        pulses = {"total_duration_ns": 100.0, "pulse_count": 5}

        high_noise = NoiseParams(
            t1_ns=1000.0,  # Very short T1
            t2_ns=500.0,
            single_qubit_error=0.1,
            two_qubit_error=0.2,
        )

        low_noise = NoiseParams(
            t1_ns=100000.0,  # Very long T1
            t2_ns=50000.0,
            single_qubit_error=0.0001,
            two_qubit_error=0.001,
        )

        high_result = pipeline._stage5_simulate(pulses, high_noise)
        low_result = pipeline._stage5_simulate(pulses, low_noise)

        # Lower noise should give higher fidelity
        assert low_result.process_fidelity > high_result.process_fidelity


# =============================================================================
# Full Pipeline Tests
# =============================================================================


class TestEndToEndPipelineRun:
    """Tests for full pipeline run."""

    def test_run_returns_end_to_end_result(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Full pipeline run returns EndToEndResult."""
        result = pipeline.run(
            circuit=bell_qasm,
            passes=["cancel"],
            circuit_name="test_bell",
        )

        assert isinstance(result, EndToEndResult)
        assert result.circuit_name == "test_bell"

    def test_run_collects_input_metrics(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Pipeline collects input metrics from parsing."""
        result = pipeline.run(
            circuit=bell_qasm,
            passes=["cancel"],
        )

        assert result.input_metrics.gates == 2
        assert result.input_metrics.qubits == 2

    def test_run_collects_optimization_passes(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Pipeline collects optimization pass metrics."""
        result = pipeline.run(
            circuit=bell_qasm,
            passes=["cancel"],
        )

        assert len(result.optimization_passes) == 1
        assert result.optimization_passes[0].name == "CancellationPass"

    def test_run_includes_pulse_metrics(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Pipeline includes pulse metrics."""
        result = pipeline.run(
            circuit=bell_qasm,
            passes=["cancel"],
        )

        assert result.pulse_metrics.pulse_count > 0
        assert result.pulse_metrics.total_duration_ns > 0

    def test_run_includes_fidelities(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Pipeline includes fidelity values."""
        result = pipeline.run(
            circuit=bell_qasm,
            passes=["cancel"],
        )

        assert 0 <= result.process_fidelity <= 1
        assert 0 <= result.state_fidelity <= 1

    def test_run_uses_default_topology(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Pipeline uses default topology when not specified."""
        result = pipeline.run(
            circuit=bell_qasm,
            passes=["cancel"],
        )

        assert result.topology == "iqm-garnet"

    def test_run_uses_custom_topology(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Pipeline uses custom topology when specified."""
        result = pipeline.run(
            circuit=bell_qasm,
            passes=["cancel"],
            topology="linear-8",
        )

        assert result.topology == "linear-8"

    def test_run_uses_default_noise_params(
        self,
        pipeline: EndToEndPipeline,
        noise_params: NoiseParams,
        bell_qasm: str,
    ) -> None:
        """Pipeline uses default noise params when not overridden."""
        result = pipeline.run(
            circuit=bell_qasm,
            passes=["cancel"],
        )

        assert result.noise_params == noise_params

    def test_run_uses_custom_noise_params(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Pipeline uses custom noise params when specified."""
        custom_noise = NoiseParams(
            t1_ns=50000.0,
            t2_ns=20000.0,
            single_qubit_error=0.0005,
            two_qubit_error=0.003,
        )

        result = pipeline.run(
            circuit=bell_qasm,
            passes=["cancel"],
            noise_params=custom_noise,
        )

        assert result.noise_params == custom_noise

    def test_run_includes_timestamp(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Pipeline includes timestamp."""
        before = datetime.now()
        result = pipeline.run(
            circuit=bell_qasm,
            passes=["cancel"],
        )
        after = datetime.now()

        assert before <= result.timestamp <= after

    def test_run_with_routing_metrics(
        self,
        pipeline_with_routing: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Pipeline includes routing metrics when routing is enabled."""
        result = pipeline_with_routing.run(
            circuit=bell_qasm,
            passes=["cancel"],
            route=True,
        )

        assert result.routing_metrics is not None
        assert result.routing_metrics.swaps_inserted == 2

    def test_run_invalid_circuit_raises(
        self,
        pipeline: EndToEndPipeline,
    ) -> None:
        """Invalid circuit raises ValueError."""
        with pytest.raises(ValueError, match="Invalid OpenQASM"):
            pipeline.run(
                circuit="not valid qasm",
                passes=["cancel"],
            )

    def test_run_empty_circuit_raises(
        self,
        pipeline: EndToEndPipeline,
    ) -> None:
        """Empty circuit raises ValueError."""
        with pytest.raises(ValueError, match="Invalid OpenQASM"):
            pipeline.run(
                circuit="",
                passes=["cancel"],
            )

    def test_run_default_circuit_name(
        self,
        pipeline: EndToEndPipeline,
        bell_qasm: str,
    ) -> None:
        """Pipeline uses default circuit name when not specified."""
        result = pipeline.run(
            circuit=bell_qasm,
            passes=["cancel"],
        )

        assert result.circuit_name == "unnamed_circuit"
