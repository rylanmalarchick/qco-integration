"""CircuitCorpus: Benchmark circuit generation and management.

This module provides utilities for generating and managing a diverse set
of benchmark circuits for experimental analysis.

Circuit types (per SCOPE_OF_WORK.md Phase 2):
- VQE circuits (extracted from QuantumVQE)
- QFT (various sizes: 4, 8, 12, 16, 20 qubits)
- QAOA (MaxCut, various graph sizes)
- GHZ states
- Random circuits (controlled depth/gate density)

Following AgentBible principles:
- Type hints on all functions
- Clear documentation with references
- Reproducible circuit generation (fixed seeds)
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CircuitType(Enum):
    """Types of benchmark circuits available."""

    VQE = "vqe"
    QFT = "qft"
    QAOA = "qaoa"
    GHZ = "ghz"
    RANDOM = "random"


@dataclass(frozen=True)
class CircuitSpec:
    """Specification for a benchmark circuit.

    Attributes:
        circuit_type: Type of circuit (QFT, QAOA, etc.).
        num_qubits: Number of qubits.
        depth: Target depth (for random circuits).
        seed: Random seed for reproducibility.
        params: Additional parameters (circuit-type specific).
    """

    circuit_type: CircuitType
    num_qubits: int
    depth: int | None = None
    seed: int = 42
    params: tuple[tuple[str, Any], ...] | None = None

    @property
    def name(self) -> str:
        """Generate a unique name for this circuit."""
        parts = [self.circuit_type.value, f"{self.num_qubits}q"]
        if self.depth is not None:
            parts.append(f"d{self.depth}")
        if self.params:
            for key, value in self.params:
                parts.append(f"{key}{value}")
        return "_".join(parts)


@dataclass
class BenchmarkCircuit:
    """A benchmark circuit with metadata.

    Attributes:
        spec: Circuit specification.
        qasm: OpenQASM 3.0 circuit string.
        metadata: Additional metadata about the circuit.
    """

    spec: CircuitSpec
    qasm: str
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Circuit Generators
# =============================================================================


def generate_ghz_circuit(num_qubits: int) -> str:
    """Generate a GHZ state preparation circuit.

    The GHZ state |GHZ_n> = (|0...0> + |1...1>) / sqrt(2) is created by:
    1. Apply H to qubit 0
    2. Apply CX from qubit i to qubit i+1 for i = 0, 1, ..., n-2

    Args:
        num_qubits: Number of qubits (must be >= 2).

    Returns:
        OpenQASM 3.0 circuit string.

    Raises:
        ValueError: If num_qubits < 2.
    """
    if num_qubits < 2:
        raise ValueError(f"GHZ requires at least 2 qubits, got {num_qubits}")

    lines = [
        "OPENQASM 3.0;",
        f"qubit[{num_qubits}] q;",
        "",
        "// GHZ state preparation",
        "h q[0];",
    ]

    for i in range(num_qubits - 1):
        lines.append(f"cx q[{i}], q[{i + 1}];")

    return "\n".join(lines)


def generate_qft_circuit(num_qubits: int) -> str:
    """Generate a Quantum Fourier Transform circuit.

    The QFT applies:
    1. Hadamard on each qubit
    2. Controlled phase rotations between qubit pairs
    3. SWAP gates to reverse qubit order (optional, included here)

    Note: CRZ gates are decomposed into RZ + CNOT for compatibility with
    the C++ optimizer which doesn't support crz directly.

    Args:
        num_qubits: Number of qubits (must be >= 1).

    Returns:
        OpenQASM 3.0 circuit string.

    Raises:
        ValueError: If num_qubits < 1.
    """
    if num_qubits < 1:
        raise ValueError(f"QFT requires at least 1 qubit, got {num_qubits}")

    lines = [
        "OPENQASM 3.0;",
        f"qubit[{num_qubits}] q;",
        "",
        "// Quantum Fourier Transform",
    ]

    # QFT core
    for i in range(num_qubits):
        lines.append(f"h q[{i}];")

        # Controlled phase rotations (decomposed crz)
        for j in range(i + 1, num_qubits):
            k = j - i + 1
            # Phase angle = pi / 2^k
            angle = 3.14159265358979 / (2**k)
            # Decompose crz(angle) control=q[j], target=q[i] as:
            #   rz(angle/2) q[i]
            #   cx q[j], q[i]
            #   rz(-angle/2) q[i]
            #   cx q[j], q[i]
            half_angle = angle / 2
            lines.append(f"rz({half_angle:.10f}) q[{i}];")
            lines.append(f"cx q[{j}], q[{i}];")
            lines.append(f"rz({-half_angle:.10f}) q[{i}];")
            lines.append(f"cx q[{j}], q[{i}];")

    # Swap to reverse qubit order
    lines.append("")
    lines.append("// Reverse qubit order")
    for i in range(num_qubits // 2):
        j = num_qubits - i - 1
        lines.append(f"swap q[{i}], q[{j}];")

    return "\n".join(lines)


def generate_qaoa_circuit(
    num_qubits: int,
    edges: list[tuple[int, int]],
    gamma: float = 0.5,
    beta: float = 0.5,
    layers: int = 1,
) -> str:
    """Generate a QAOA circuit for MaxCut.

    QAOA for MaxCut consists of:
    1. Initial superposition (H on all qubits)
    2. Cost layer: exp(-i * gamma * C) using ZZ interactions on edges
    3. Mixer layer: exp(-i * beta * B) using X rotations

    Args:
        num_qubits: Number of qubits (= graph nodes).
        edges: List of (i, j) tuples representing graph edges.
        gamma: Cost layer angle.
        beta: Mixer layer angle.
        layers: Number of QAOA layers (p).

    Returns:
        OpenQASM 3.0 circuit string.

    Raises:
        ValueError: If num_qubits < 2 or edges reference invalid qubits.
    """
    if num_qubits < 2:
        raise ValueError(f"QAOA requires at least 2 qubits, got {num_qubits}")

    # Validate edges
    for i, j in edges:
        if not (0 <= i < num_qubits and 0 <= j < num_qubits):
            raise ValueError(f"Edge ({i}, {j}) references invalid qubit for {num_qubits} qubits")
        if i == j:
            raise ValueError(f"Self-loop edge ({i}, {j}) is not allowed")

    lines = [
        "OPENQASM 3.0;",
        f"qubit[{num_qubits}] q;",
        "",
        "// QAOA MaxCut circuit",
        "// Initial superposition",
    ]

    for i in range(num_qubits):
        lines.append(f"h q[{i}];")

    for layer in range(layers):
        lines.append("")
        lines.append(f"// Layer {layer + 1} - Cost")

        # Cost layer: ZZ interactions
        # exp(-i * gamma * Z_i Z_j) = CNOT - RZ(2*gamma) - CNOT
        for i, j in edges:
            lines.append(f"cx q[{i}], q[{j}];")
            lines.append(f"rz({2 * gamma:.10f}) q[{j}];")
            lines.append(f"cx q[{i}], q[{j}];")

        lines.append("")
        lines.append(f"// Layer {layer + 1} - Mixer")

        # Mixer layer: X rotations
        for i in range(num_qubits):
            lines.append(f"rx({2 * beta:.10f}) q[{i}];")

    return "\n".join(lines)


def generate_random_graph_edges(
    num_nodes: int,
    edge_probability: float = 0.5,
    seed: int = 42,
) -> list[tuple[int, int]]:
    """Generate random graph edges for QAOA.

    Args:
        num_nodes: Number of nodes in the graph.
        edge_probability: Probability of edge between any two nodes.
        seed: Random seed for reproducibility.

    Returns:
        List of (i, j) edge tuples where i < j.
    """
    rng = random.Random(seed)
    edges = []

    for i in range(num_nodes):
        for j in range(i + 1, num_nodes):
            if rng.random() < edge_probability:
                edges.append((i, j))

    # Ensure at least one edge
    if not edges and num_nodes >= 2:
        edges.append((0, 1))

    return edges


def generate_random_circuit(
    num_qubits: int,
    depth: int,
    two_qubit_gate_density: float = 0.3,
    seed: int = 42,
) -> str:
    """Generate a random quantum circuit.

    The circuit is generated layer by layer:
    1. Each layer targets all qubits
    2. Some fraction of gates are two-qubit (CX/CZ)
    3. Single-qubit gates are randomly chosen from {H, X, Y, Z, S, T}

    Args:
        num_qubits: Number of qubits (must be >= 1).
        depth: Number of layers.
        two_qubit_gate_density: Fraction of layers with 2Q gates.
        seed: Random seed for reproducibility.

    Returns:
        OpenQASM 3.0 circuit string.

    Raises:
        ValueError: If num_qubits < 1 or depth < 1.
    """
    if num_qubits < 1:
        raise ValueError(f"Random circuit requires at least 1 qubit, got {num_qubits}")
    if depth < 1:
        raise ValueError(f"Random circuit requires at least depth 1, got {depth}")

    rng = random.Random(seed)
    single_qubit_gates = ["h", "x", "y", "z", "s", "t"]
    two_qubit_gates = ["cx", "cz"]

    lines = [
        "OPENQASM 3.0;",
        f"qubit[{num_qubits}] q;",
        "",
        f"// Random circuit (depth={depth}, 2q_density={two_qubit_gate_density})",
    ]

    for layer in range(depth):
        lines.append(f"// Layer {layer + 1}")

        # Decide if this layer has 2Q gates
        has_two_qubit = num_qubits >= 2 and rng.random() < two_qubit_gate_density

        if has_two_qubit:
            # Pick a random pair for 2Q gate
            qubits = list(range(num_qubits))
            rng.shuffle(qubits)
            pairs = [(qubits[i], qubits[i + 1]) for i in range(0, len(qubits) - 1, 2)]

            for q0, q1 in pairs:
                gate = rng.choice(two_qubit_gates)
                lines.append(f"{gate} q[{q0}], q[{q1}];")

            # Apply single-qubit gates to unpaired qubits
            if num_qubits % 2 == 1:
                gate = rng.choice(single_qubit_gates)
                lines.append(f"{gate} q[{qubits[-1]}];")
        else:
            # All single-qubit gates
            for qubit in range(num_qubits):
                gate = rng.choice(single_qubit_gates)
                lines.append(f"{gate} q[{qubit}];")

    return "\n".join(lines)


# =============================================================================
# CircuitCorpus Class
# =============================================================================


class CircuitCorpus:
    """Collection of benchmark circuits for experimental analysis.

    This class generates and manages a diverse set of circuits for
    benchmarking the compilation pipeline.

    Example:
        >>> corpus = CircuitCorpus()
        >>> corpus.add_qft_circuits([4, 8, 12])
        >>> corpus.add_ghz_circuits([4, 8, 12, 16, 20])
        >>> for circuit in corpus:
        ...     result = pipeline.run(circuit.qasm)
    """

    def __init__(self) -> None:
        """Initialize an empty circuit corpus."""
        self._circuits: list[BenchmarkCircuit] = []

    def __iter__(self) -> Iterator[BenchmarkCircuit]:
        """Iterate over circuits in the corpus."""
        return iter(self._circuits)

    def __len__(self) -> int:
        """Return number of circuits in the corpus."""
        return len(self._circuits)

    def add_circuit(self, circuit: BenchmarkCircuit) -> None:
        """Add a single circuit to the corpus.

        Args:
            circuit: BenchmarkCircuit to add.
        """
        self._circuits.append(circuit)

    def add_ghz_circuits(self, qubit_counts: list[int]) -> None:
        """Add GHZ state preparation circuits.

        Args:
            qubit_counts: List of qubit counts to generate.
        """
        for n in qubit_counts:
            spec = CircuitSpec(
                circuit_type=CircuitType.GHZ,
                num_qubits=n,
            )
            qasm = generate_ghz_circuit(n)
            self._circuits.append(BenchmarkCircuit(spec=spec, qasm=qasm))

    def add_qft_circuits(self, qubit_counts: list[int], seed: int = 42) -> None:
        """Add QFT circuits for various qubit counts.

        Args:
            qubit_counts: List of qubit counts to generate.
            seed: Random seed (unused for QFT, kept for API consistency).
        """
        for n in qubit_counts:
            spec = CircuitSpec(
                circuit_type=CircuitType.QFT,
                num_qubits=n,
                seed=seed,
            )
            qasm = generate_qft_circuit(n)
            self._circuits.append(BenchmarkCircuit(spec=spec, qasm=qasm))

    def add_qaoa_circuits(
        self,
        qubit_counts: list[int],
        graph_type: str = "random",
        edge_probability: float = 0.5,
        gamma: float = 0.5,
        beta: float = 0.5,
        layers: int = 1,
        seed: int = 42,
    ) -> None:
        """Add QAOA MaxCut circuits.

        Args:
            qubit_counts: List of qubit counts (= graph nodes).
            graph_type: Type of graph ("random" supported).
            edge_probability: Edge probability for random graphs.
            gamma: QAOA cost layer angle.
            beta: QAOA mixer layer angle.
            layers: Number of QAOA layers.
            seed: Random seed for graph generation.
        """
        for i, n in enumerate(qubit_counts):
            # Use different seed for each circuit size
            circuit_seed = seed + i

            if graph_type == "random":
                edges = generate_random_graph_edges(n, edge_probability, circuit_seed)
            else:
                raise ValueError(f"Unsupported graph type: {graph_type}")

            spec = CircuitSpec(
                circuit_type=CircuitType.QAOA,
                num_qubits=n,
                seed=circuit_seed,
                params=(
                    ("p", layers),
                    ("g", f"{gamma:.2f}"),
                    ("b", f"{beta:.2f}"),
                ),
            )
            qasm = generate_qaoa_circuit(n, edges, gamma, beta, layers)
            self._circuits.append(
                BenchmarkCircuit(
                    spec=spec,
                    qasm=qasm,
                    metadata={"edges": edges, "graph_type": graph_type},
                )
            )

    def add_random_circuits(
        self,
        qubit_counts: list[int],
        depths: list[int],
        two_qubit_gate_density: float = 0.3,
        seed: int = 42,
    ) -> None:
        """Add random circuits with controlled properties.

        Creates circuits for all combinations of qubit_counts and depths.

        Args:
            qubit_counts: List of qubit counts.
            depths: List of circuit depths.
            two_qubit_gate_density: Fraction of layers with two-qubit gates.
            seed: Base random seed for reproducibility.
        """
        circuit_index = 0
        for n in qubit_counts:
            for d in depths:
                # Use different seed for each circuit
                circuit_seed = seed + circuit_index
                circuit_index += 1

                spec = CircuitSpec(
                    circuit_type=CircuitType.RANDOM,
                    num_qubits=n,
                    depth=d,
                    seed=circuit_seed,
                    params=(("density", f"{two_qubit_gate_density:.1f}"),),
                )
                qasm = generate_random_circuit(n, d, two_qubit_gate_density, circuit_seed)
                self._circuits.append(BenchmarkCircuit(spec=spec, qasm=qasm))

    def add_vqe_circuits(self, vqe_path: str) -> None:
        """Import VQE circuits from QuantumVQE project.

        Args:
            vqe_path: Path to QuantumVQE project directory.

        Note:
            This requires the QuantumVQE project to be available.
            Implementation is deferred until VQE integration is needed.
        """
        raise NotImplementedError(
            "VQE circuit import requires QuantumVQE project. "
            "Set vqe_path to the project directory."
        )

    def filter_by_type(self, circuit_type: CircuitType) -> list[BenchmarkCircuit]:
        """Filter circuits by type.

        Args:
            circuit_type: Type to filter by.

        Returns:
            List of matching circuits.
        """
        return [c for c in self._circuits if c.spec.circuit_type == circuit_type]

    def filter_by_qubits(
        self,
        min_qubits: int = 0,
        max_qubits: int = 100,
    ) -> list[BenchmarkCircuit]:
        """Filter circuits by qubit count.

        Args:
            min_qubits: Minimum qubit count (inclusive).
            max_qubits: Maximum qubit count (inclusive).

        Returns:
            List of matching circuits.
        """
        return [
            c
            for c in self._circuits
            if min_qubits <= c.spec.num_qubits <= max_qubits
        ]

    def get_by_name(self, name: str) -> BenchmarkCircuit | None:
        """Get a circuit by its name.

        Args:
            name: Circuit name to find.

        Returns:
            Matching circuit or None if not found.
        """
        for c in self._circuits:
            if c.spec.name == name:
                return c
        return None

    def summary(self) -> dict[str, int]:
        """Get a summary of circuits by type.

        Returns:
            Dictionary mapping circuit type to count.
        """
        counts: dict[str, int] = {}
        for c in self._circuits:
            key = c.spec.circuit_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts


# =============================================================================
# Predefined Corpus Factories
# =============================================================================


def create_standard_corpus(seed: int = 42) -> CircuitCorpus:
    """Create a standard benchmark corpus with common circuit sizes.

    Includes:
    - GHZ: 4, 8, 12, 16, 20 qubits
    - QFT: 4, 8, 12, 16, 20 qubits
    - QAOA: 4, 8, 12 qubits (1-layer)
    - Random: 4, 8 qubits x depths 5, 10, 20

    Args:
        seed: Random seed for reproducibility.

    Returns:
        Populated CircuitCorpus.
    """
    corpus = CircuitCorpus()

    # GHZ states
    corpus.add_ghz_circuits([4, 8, 12, 16, 20])

    # QFT circuits
    corpus.add_qft_circuits([4, 8, 12, 16, 20], seed=seed)

    # QAOA circuits
    corpus.add_qaoa_circuits([4, 8, 12], seed=seed)

    # Random circuits
    corpus.add_random_circuits([4, 8], [5, 10, 20], seed=seed)

    return corpus


def create_small_corpus(seed: int = 42) -> CircuitCorpus:
    """Create a small corpus for quick testing.

    Includes:
    - GHZ: 4, 8 qubits
    - QFT: 4 qubits
    - Random: 4 qubits x depth 5

    Args:
        seed: Random seed for reproducibility.

    Returns:
        Populated CircuitCorpus.
    """
    corpus = CircuitCorpus()

    corpus.add_ghz_circuits([4, 8])
    corpus.add_qft_circuits([4], seed=seed)
    corpus.add_random_circuits([4], [5], seed=seed)

    return corpus
