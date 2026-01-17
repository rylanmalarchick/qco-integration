"""Tests for CircuitCorpus and circuit generators.

Tests cover:
- GHZ circuit generation
- QFT circuit generation
- QAOA circuit generation
- Random circuit generation
- CircuitCorpus management (add, filter, iterate)
- Reproducibility with seeds

Following AgentBible testing principles:
- Clear test names describing expected behavior
- Validate generated QASM is parseable
"""

from __future__ import annotations

import pytest

from src.corpus import (
    BenchmarkCircuit,
    CircuitCorpus,
    CircuitSpec,
    CircuitType,
    create_small_corpus,
    create_standard_corpus,
    generate_ghz_circuit,
    generate_qaoa_circuit,
    generate_qft_circuit,
    generate_random_circuit,
    generate_random_graph_edges,
)
from src.qasm import extract_metrics, validate_qasm

# =============================================================================
# GHZ Circuit Tests
# =============================================================================


class TestGenerateGHZCircuit:
    """Tests for GHZ circuit generation."""

    def test_ghz_2_qubits(self) -> None:
        """2-qubit GHZ circuit has correct structure."""
        qasm = generate_ghz_circuit(2)

        assert "OPENQASM 3.0" in qasm
        assert "qubit[2] q" in qasm
        assert "h q[0]" in qasm
        assert "cx q[0], q[1]" in qasm

    def test_ghz_4_qubits(self) -> None:
        """4-qubit GHZ circuit has 1 H and 3 CX gates."""
        qasm = generate_ghz_circuit(4)
        metrics = extract_metrics(qasm)

        assert metrics.qubits == 4
        assert metrics.gates == 4  # 1 H + 3 CX
        assert metrics.two_qubit_gates == 3

    def test_ghz_is_valid_qasm(self) -> None:
        """Generated GHZ circuit is valid QASM."""
        qasm = generate_ghz_circuit(8)
        is_valid, errors = validate_qasm(qasm)

        assert is_valid, f"Validation errors: {errors}"

    def test_ghz_depth_is_linear(self) -> None:
        """GHZ depth equals number of qubits (linear chain)."""
        for n in [4, 8, 12]:
            qasm = generate_ghz_circuit(n)
            metrics = extract_metrics(qasm)
            assert metrics.depth == n, f"GHZ-{n} depth should be {n}"

    def test_ghz_raises_for_single_qubit(self) -> None:
        """GHZ requires at least 2 qubits."""
        with pytest.raises(ValueError, match="at least 2 qubits"):
            generate_ghz_circuit(1)

    def test_ghz_raises_for_zero_qubits(self) -> None:
        """GHZ requires positive qubit count."""
        with pytest.raises(ValueError, match="at least 2 qubits"):
            generate_ghz_circuit(0)


# =============================================================================
# QFT Circuit Tests
# =============================================================================


class TestGenerateQFTCircuit:
    """Tests for QFT circuit generation."""

    def test_qft_1_qubit(self) -> None:
        """1-qubit QFT is just a Hadamard."""
        qasm = generate_qft_circuit(1)

        assert "OPENQASM 3.0" in qasm
        assert "qubit[1] q" in qasm
        assert "h q[0]" in qasm

    def test_qft_4_qubits_is_valid(self) -> None:
        """4-qubit QFT is valid QASM."""
        qasm = generate_qft_circuit(4)
        is_valid, errors = validate_qasm(qasm)

        assert is_valid, f"Validation errors: {errors}"

    def test_qft_has_hadamards(self) -> None:
        """QFT has Hadamard on each qubit."""
        qasm = generate_qft_circuit(4)

        for i in range(4):
            assert f"h q[{i}]" in qasm

    def test_qft_has_controlled_rotations(self) -> None:
        """QFT has controlled rotation gates (decomposed as rz + cx)."""
        qasm = generate_qft_circuit(4)

        # CRZ gates are decomposed into rz + cx for C++ optimizer compatibility
        assert "rz(" in qasm
        assert "cx " in qasm

    def test_qft_has_swaps(self) -> None:
        """QFT includes SWAP gates to reverse qubit order."""
        qasm = generate_qft_circuit(4)

        assert "swap" in qasm

    def test_qft_gate_count_grows_quadratically(self) -> None:
        """QFT gate count grows as O(n^2)."""
        metrics_4 = extract_metrics(generate_qft_circuit(4))
        metrics_8 = extract_metrics(generate_qft_circuit(8))

        # Rough check: 8-qubit should have more than 2x gates of 4-qubit
        assert metrics_8.gates > 2 * metrics_4.gates

    def test_qft_raises_for_zero_qubits(self) -> None:
        """QFT requires at least 1 qubit."""
        with pytest.raises(ValueError, match="at least 1 qubit"):
            generate_qft_circuit(0)


# =============================================================================
# QAOA Circuit Tests
# =============================================================================


class TestGenerateQAOACircuit:
    """Tests for QAOA circuit generation."""

    def test_qaoa_basic_structure(self) -> None:
        """QAOA has initial superposition and cost/mixer layers."""
        edges = [(0, 1), (1, 2)]
        qasm = generate_qaoa_circuit(3, edges)

        assert "OPENQASM 3.0" in qasm
        assert "qubit[3] q" in qasm
        # Initial H gates
        assert "h q[0]" in qasm
        assert "h q[1]" in qasm
        assert "h q[2]" in qasm
        # Cost layer (ZZ via CX-RZ-CX)
        assert "cx q[0], q[1]" in qasm
        assert "rz(" in qasm
        # Mixer layer
        assert "rx(" in qasm

    def test_qaoa_is_valid_qasm(self) -> None:
        """Generated QAOA circuit is valid QASM."""
        edges = [(0, 1), (1, 2), (0, 2)]
        qasm = generate_qaoa_circuit(3, edges)
        is_valid, errors = validate_qasm(qasm)

        assert is_valid, f"Validation errors: {errors}"

    def test_qaoa_multiple_layers(self) -> None:
        """QAOA with p=2 has twice the cost/mixer operations."""
        edges = [(0, 1)]
        qasm_p1 = generate_qaoa_circuit(2, edges, layers=1)
        qasm_p2 = generate_qaoa_circuit(2, edges, layers=2)

        metrics_p1 = extract_metrics(qasm_p1)
        metrics_p2 = extract_metrics(qasm_p2)

        # p=2 should have more gates than p=1
        assert metrics_p2.gates > metrics_p1.gates

    def test_qaoa_raises_for_single_qubit(self) -> None:
        """QAOA requires at least 2 qubits."""
        with pytest.raises(ValueError, match="at least 2 qubits"):
            generate_qaoa_circuit(1, [])

    def test_qaoa_raises_for_invalid_edge(self) -> None:
        """QAOA raises for edges referencing invalid qubits."""
        with pytest.raises(ValueError, match="invalid qubit"):
            generate_qaoa_circuit(3, [(0, 5)])

    def test_qaoa_raises_for_self_loop(self) -> None:
        """QAOA raises for self-loop edges."""
        with pytest.raises(ValueError, match="Self-loop"):
            generate_qaoa_circuit(3, [(1, 1)])


class TestGenerateRandomGraphEdges:
    """Tests for random graph edge generation."""

    def test_generates_edges(self) -> None:
        """Generates edges for given nodes."""
        edges = generate_random_graph_edges(4, edge_probability=0.5, seed=42)

        assert len(edges) > 0
        for i, j in edges:
            assert 0 <= i < 4
            assert 0 <= j < 4
            assert i < j  # Edges are ordered

    def test_reproducible_with_seed(self) -> None:
        """Same seed produces same edges."""
        edges1 = generate_random_graph_edges(6, seed=123)
        edges2 = generate_random_graph_edges(6, seed=123)

        assert edges1 == edges2

    def test_different_seeds_produce_different_edges(self) -> None:
        """Different seeds produce different edges."""
        edges1 = generate_random_graph_edges(6, seed=100)
        edges2 = generate_random_graph_edges(6, seed=200)

        # Very unlikely to be equal
        assert edges1 != edges2

    def test_ensures_at_least_one_edge(self) -> None:
        """At least one edge even with low probability."""
        edges = generate_random_graph_edges(4, edge_probability=0.0, seed=42)

        assert len(edges) >= 1


# =============================================================================
# Random Circuit Tests
# =============================================================================


class TestGenerateRandomCircuit:
    """Tests for random circuit generation."""

    def test_random_circuit_basic(self) -> None:
        """Random circuit has correct qubit count."""
        qasm = generate_random_circuit(4, depth=5, seed=42)
        metrics = extract_metrics(qasm)

        assert metrics.qubits == 4

    def test_random_circuit_is_valid_qasm(self) -> None:
        """Generated random circuit is valid QASM."""
        qasm = generate_random_circuit(4, depth=10, seed=42)
        is_valid, errors = validate_qasm(qasm)

        assert is_valid, f"Validation errors: {errors}"

    def test_random_circuit_reproducible(self) -> None:
        """Same seed produces same circuit."""
        qasm1 = generate_random_circuit(4, depth=5, seed=42)
        qasm2 = generate_random_circuit(4, depth=5, seed=42)

        assert qasm1 == qasm2

    def test_random_circuit_different_seeds(self) -> None:
        """Different seeds produce different circuits."""
        qasm1 = generate_random_circuit(4, depth=5, seed=100)
        qasm2 = generate_random_circuit(4, depth=5, seed=200)

        assert qasm1 != qasm2

    def test_random_circuit_has_gates(self) -> None:
        """Random circuit has gates in each layer."""
        qasm = generate_random_circuit(4, depth=10, seed=42)
        metrics = extract_metrics(qasm)

        # At least one gate per layer on average
        assert metrics.gates >= 10

    def test_random_circuit_two_qubit_density(self) -> None:
        """Higher 2Q density produces more 2Q gates."""
        qasm_low = generate_random_circuit(4, depth=20, two_qubit_gate_density=0.1, seed=42)
        qasm_high = generate_random_circuit(4, depth=20, two_qubit_gate_density=0.9, seed=42)

        metrics_low = extract_metrics(qasm_low)
        metrics_high = extract_metrics(qasm_high)

        assert metrics_high.two_qubit_gates > metrics_low.two_qubit_gates

    def test_random_circuit_single_qubit(self) -> None:
        """Single-qubit random circuit works."""
        qasm = generate_random_circuit(1, depth=5, seed=42)
        is_valid, _ = validate_qasm(qasm)

        assert is_valid

    def test_random_circuit_raises_for_zero_qubits(self) -> None:
        """Random circuit requires at least 1 qubit."""
        with pytest.raises(ValueError, match="at least 1 qubit"):
            generate_random_circuit(0, depth=5)

    def test_random_circuit_raises_for_zero_depth(self) -> None:
        """Random circuit requires at least depth 1."""
        with pytest.raises(ValueError, match="at least depth 1"):
            generate_random_circuit(4, depth=0)


# =============================================================================
# CircuitSpec Tests
# =============================================================================


class TestCircuitSpec:
    """Tests for CircuitSpec dataclass."""

    def test_spec_name_basic(self) -> None:
        """Spec name includes type and qubit count."""
        spec = CircuitSpec(circuit_type=CircuitType.GHZ, num_qubits=4)

        assert spec.name == "ghz_4q"

    def test_spec_name_with_depth(self) -> None:
        """Spec name includes depth when present."""
        spec = CircuitSpec(circuit_type=CircuitType.RANDOM, num_qubits=4, depth=10)

        assert spec.name == "random_4q_d10"

    def test_spec_name_with_params(self) -> None:
        """Spec name includes params when present."""
        spec = CircuitSpec(
            circuit_type=CircuitType.QAOA,
            num_qubits=4,
            params=(("p", 2), ("g", "0.5")),
        )

        assert "p2" in spec.name
        assert "g0.5" in spec.name


# =============================================================================
# CircuitCorpus Tests
# =============================================================================


class TestCircuitCorpus:
    """Tests for CircuitCorpus class."""

    def test_empty_corpus(self) -> None:
        """Empty corpus has length 0."""
        corpus = CircuitCorpus()

        assert len(corpus) == 0

    def test_add_ghz_circuits(self) -> None:
        """Add GHZ circuits to corpus."""
        corpus = CircuitCorpus()
        corpus.add_ghz_circuits([4, 8])

        assert len(corpus) == 2

    def test_add_qft_circuits(self) -> None:
        """Add QFT circuits to corpus."""
        corpus = CircuitCorpus()
        corpus.add_qft_circuits([4, 8, 12])

        assert len(corpus) == 3

    def test_add_qaoa_circuits(self) -> None:
        """Add QAOA circuits to corpus."""
        corpus = CircuitCorpus()
        corpus.add_qaoa_circuits([4, 8])

        assert len(corpus) == 2

    def test_add_random_circuits(self) -> None:
        """Add random circuits to corpus."""
        corpus = CircuitCorpus()
        corpus.add_random_circuits([4], [5, 10])

        assert len(corpus) == 2  # 1 qubit count * 2 depths

    def test_iterate_over_corpus(self) -> None:
        """Can iterate over corpus."""
        corpus = CircuitCorpus()
        corpus.add_ghz_circuits([4, 8])

        circuits = list(corpus)

        assert len(circuits) == 2
        assert all(isinstance(c, BenchmarkCircuit) for c in circuits)

    def test_filter_by_type(self) -> None:
        """Filter circuits by type."""
        corpus = CircuitCorpus()
        corpus.add_ghz_circuits([4, 8])
        corpus.add_qft_circuits([4])

        ghz_circuits = corpus.filter_by_type(CircuitType.GHZ)
        qft_circuits = corpus.filter_by_type(CircuitType.QFT)

        assert len(ghz_circuits) == 2
        assert len(qft_circuits) == 1

    def test_filter_by_qubits(self) -> None:
        """Filter circuits by qubit count."""
        corpus = CircuitCorpus()
        corpus.add_ghz_circuits([4, 8, 12, 16])

        small = corpus.filter_by_qubits(min_qubits=0, max_qubits=8)
        large = corpus.filter_by_qubits(min_qubits=12, max_qubits=20)

        assert len(small) == 2  # 4, 8
        assert len(large) == 2  # 12, 16

    def test_get_by_name(self) -> None:
        """Get circuit by name."""
        corpus = CircuitCorpus()
        corpus.add_ghz_circuits([4])

        circuit = corpus.get_by_name("ghz_4q")

        assert circuit is not None
        assert circuit.spec.num_qubits == 4

    def test_get_by_name_not_found(self) -> None:
        """Get by name returns None if not found."""
        corpus = CircuitCorpus()
        corpus.add_ghz_circuits([4])

        circuit = corpus.get_by_name("nonexistent")

        assert circuit is None

    def test_summary(self) -> None:
        """Summary counts circuits by type."""
        corpus = CircuitCorpus()
        corpus.add_ghz_circuits([4, 8])
        corpus.add_qft_circuits([4, 8, 12])

        summary = corpus.summary()

        assert summary["ghz"] == 2
        assert summary["qft"] == 3

    def test_add_circuit(self) -> None:
        """Add individual circuit to corpus."""
        corpus = CircuitCorpus()
        spec = CircuitSpec(circuit_type=CircuitType.GHZ, num_qubits=4)
        circuit = BenchmarkCircuit(spec=spec, qasm="OPENQASM 3.0;\nqubit[4] q;\nh q[0];")

        corpus.add_circuit(circuit)

        assert len(corpus) == 1


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCorpusFactories:
    """Tests for corpus factory functions."""

    def test_create_standard_corpus(self) -> None:
        """Standard corpus has expected circuit types."""
        corpus = create_standard_corpus()

        summary = corpus.summary()

        assert "ghz" in summary
        assert "qft" in summary
        assert "qaoa" in summary
        assert "random" in summary

    def test_create_standard_corpus_size(self) -> None:
        """Standard corpus has expected size."""
        corpus = create_standard_corpus()

        # 5 GHZ + 5 QFT + 3 QAOA + 6 Random (2 qubits * 3 depths)
        assert len(corpus) == 5 + 5 + 3 + 6

    def test_create_small_corpus(self) -> None:
        """Small corpus has fewer circuits."""
        small = create_small_corpus()
        standard = create_standard_corpus()

        assert len(small) < len(standard)

    def test_corpus_circuits_are_valid(self) -> None:
        """All circuits in small corpus are valid QASM."""
        corpus = create_small_corpus()

        for circuit in corpus:
            is_valid, errors = validate_qasm(circuit.qasm)
            assert is_valid, f"{circuit.spec.name}: {errors}"
