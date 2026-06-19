"""Metrics dataclasses for pipeline stage tracking.

This module defines the data structures for collecting metrics at each stage
of the quantum compilation pipeline. Dataclasses validate physical constraints
(non-negative counts, fidelities and rates in [0, 1], T2 <= 2*T1) in
__post_init__.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class StageMetrics:
    """Metrics for a single stage of the pipeline.

    Attributes:
        gates: Total gate count.
        depth: Circuit depth (longest path through DAG).
        qubits: Number of qubits used.
        two_qubit_gates: Count of two-qubit gates (CZ, CNOT, etc.).
    """

    gates: int
    depth: int
    qubits: int
    two_qubit_gates: int

    def __post_init__(self) -> None:
        """Validate metrics are non-negative."""
        if self.gates < 0:
            raise ValueError(f"gates must be non-negative, got {self.gates}")
        if self.depth < 0:
            raise ValueError(f"depth must be non-negative, got {self.depth}")
        if self.qubits < 0:
            raise ValueError(f"qubits must be non-negative, got {self.qubits}")
        if self.two_qubit_gates < 0:
            raise ValueError(
                f"two_qubit_gates must be non-negative, got {self.two_qubit_gates}"
            )


@dataclass(frozen=True)
class PassMetrics:
    """Metrics for a single optimization pass.

    Attributes:
        name: Name of the optimization pass (e.g., "CancellationPass").
        input_metrics: Circuit metrics before this pass.
        output_metrics: Circuit metrics after this pass.
        gates_removed: Number of gates removed by this pass.
        gates_added: Number of gates added by this pass (e.g., for decomposition).
        execution_time_ms: Time taken by this pass in milliseconds.
    """

    name: str
    input_metrics: StageMetrics
    output_metrics: StageMetrics
    gates_removed: int
    gates_added: int
    execution_time_ms: float


@dataclass(frozen=True)
class RoutingMetrics:
    """Metrics for the routing stage.

    Attributes:
        topology: Target topology name (e.g., "iqm-garnet").
        swaps_inserted: Number of SWAP gates inserted.
        depth_increase: Increase in circuit depth due to routing.
        final_gates: Total gates after routing.
        final_depth: Circuit depth after routing.
    """

    topology: str
    swaps_inserted: int
    depth_increase: int
    final_gates: int
    final_depth: int


@dataclass(frozen=True)
class PulseMetrics:
    """Metrics for pulse compilation.

    Attributes:
        total_duration_ns: Total pulse sequence duration in nanoseconds.
        pulse_count: Number of individual pulse segments.
        max_amplitude: Maximum pulse amplitude (normalized).
    """

    total_duration_ns: float
    pulse_count: int
    max_amplitude: float

    def __post_init__(self) -> None:
        """Validate pulse metrics."""
        if self.total_duration_ns < 0:
            raise ValueError(
                f"total_duration_ns must be non-negative, got {self.total_duration_ns}"
            )
        if self.pulse_count < 0:
            raise ValueError(f"pulse_count must be non-negative, got {self.pulse_count}")
        if not 0 <= self.max_amplitude <= 1:
            raise ValueError(
                f"max_amplitude must be in [0, 1], got {self.max_amplitude}"
            )


@dataclass(frozen=True)
class NoiseParams:
    """Noise model parameters.

    Attributes:
        t1_ns: T1 relaxation time in nanoseconds.
        t2_ns: T2 dephasing time in nanoseconds.
        single_qubit_error: Single-qubit gate error rate.
        two_qubit_error: Two-qubit gate error rate.
    """

    t1_ns: float
    t2_ns: float
    single_qubit_error: float
    two_qubit_error: float

    def __post_init__(self) -> None:
        """Validate noise parameters are physical."""
        if self.t1_ns <= 0:
            raise ValueError(f"t1_ns must be positive, got {self.t1_ns}")
        if self.t2_ns <= 0:
            raise ValueError(f"t2_ns must be positive, got {self.t2_ns}")
        if self.t2_ns > 2 * self.t1_ns:
            raise ValueError(
                f"t2_ns cannot exceed 2*t1_ns (physical constraint), "
                f"got t2={self.t2_ns}, 2*t1={2 * self.t1_ns}"
            )
        if not 0 <= self.single_qubit_error <= 1:
            raise ValueError(
                f"single_qubit_error must be in [0, 1], got {self.single_qubit_error}"
            )
        if not 0 <= self.two_qubit_error <= 1:
            raise ValueError(
                f"two_qubit_error must be in [0, 1], got {self.two_qubit_error}"
            )


@dataclass
class EndToEndResult:
    """Complete results from an end-to-end pipeline run.

    Attributes:
        circuit_name: Identifier for the input circuit.
        input_metrics: Metrics for the original circuit.
        optimization_passes: Per-pass metrics from optimization stage.
        post_optimization: Metrics after all optimization passes.
        routing_metrics: Metrics from routing stage (optional if no routing).
        pulse_metrics: Metrics from pulse compilation stage.
        process_fidelity: Process fidelity from noise simulation.
        state_fidelity: State fidelity from noise simulation.
        noise_params: Noise model parameters used.
        topology: Target topology name.
        timestamp: When this result was generated.
    """

    circuit_name: str
    input_metrics: StageMetrics
    optimization_passes: list[PassMetrics]
    post_optimization: StageMetrics
    routing_metrics: RoutingMetrics | None
    pulse_metrics: PulseMetrics
    process_fidelity: float
    state_fidelity: float
    noise_params: NoiseParams
    topology: str
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Validate fidelity values are in [0, 1]."""
        if not 0 <= self.process_fidelity <= 1:
            raise ValueError(
                f"process_fidelity must be in [0, 1], got {self.process_fidelity}"
            )
        if not 0 <= self.state_fidelity <= 1:
            raise ValueError(
                f"state_fidelity must be in [0, 1], got {self.state_fidelity}"
            )
