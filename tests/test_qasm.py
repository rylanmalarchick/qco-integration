"""Tests for OpenQASM utilities.

Tests cover:
- Parsing QASM strings
- Extracting metrics
- Validation
- Round-trip operations
- Edge cases and error handling

Following AgentBible testing principles:
- Specification Before Code (tests written to verify behavior)
- Clear test names describing expected behavior
"""

from __future__ import annotations

import pytest

from src.metrics import StageMetrics
from src.qasm import (
    GateInfo,
    QASMParseError,
    circuits_equivalent,
    count_gates_by_type,
    extract_metrics,
    normalize_qasm,
    parse_qasm,
    validate_circuit_integrity,
    validate_qasm,
)


# =============================================================================
# Parsing Tests
# =============================================================================
class TestParseQasm:
    """Tests for parse_qasm function."""

    def test_parse_simple_circuit(self, simple_qasm: str) -> None:
        """Parse a simple single-qubit circuit."""
        result = parse_qasm(simple_qasm)

        assert result.version == "3.0"
        assert result.total_qubits == 1
        assert len(result.gates) == 1
        assert result.gates[0].name == "h"

    def test_parse_bell_circuit(self, bell_qasm: str) -> None:
        """Parse a Bell state circuit with 2 qubits and 2 gates."""
        result = parse_qasm(bell_qasm)

        assert result.version == "3.0"
        assert result.total_qubits == 2
        assert len(result.gates) == 2
        assert result.gates[0].name == "h"
        assert result.gates[1].name == "cx"

    def test_parse_ghz_circuit(self, ghz_4_qasm: str) -> None:
        """Parse a 4-qubit GHZ circuit."""
        result = parse_qasm(ghz_4_qasm)

        assert result.version == "3.0"
        assert result.total_qubits == 4
        assert len(result.gates) == 4  # 1 H + 3 CX

    def test_parse_extracts_qubit_declarations(self) -> None:
        """Qubit declarations are extracted correctly."""
        qasm = """OPENQASM 3.0;
qubit[3] a;
qubit[2] b;
h a[0];
"""
        result = parse_qasm(qasm)

        assert result.total_qubits == 5
        assert len(result.qubit_declarations) == 2

    def test_parse_parametric_gate(self) -> None:
        """Parametric gates have parameters extracted."""
        qasm = """OPENQASM 3.0;
qubit q;
rx(3.14159) q;
"""
        result = parse_qasm(qasm)

        assert len(result.gates) == 1
        assert result.gates[0].name == "rx"
        assert result.gates[0].parameters == ("3.14159",)

    def test_parse_multi_parameter_gate(self) -> None:
        """Gates with multiple parameters are parsed correctly."""
        qasm = """OPENQASM 3.0;
qubit q;
u3(1.57, 0, 3.14) q;
"""
        result = parse_qasm(qasm)

        assert len(result.gates) == 1
        assert result.gates[0].name == "u3"
        assert result.gates[0].parameters == ("1.57", "0", "3.14")

    def test_parse_empty_qasm_raises(self) -> None:
        """Empty QASM raises QASMParseError."""
        with pytest.raises(QASMParseError, match="Empty QASM"):
            parse_qasm("")

    def test_parse_whitespace_only_raises(self) -> None:
        """Whitespace-only QASM raises QASMParseError."""
        with pytest.raises(QASMParseError, match="Empty QASM"):
            parse_qasm("   \n\n   ")

    def test_parse_no_version_raises(self) -> None:
        """QASM without version declaration raises QASMParseError."""
        with pytest.raises(QASMParseError, match="No OPENQASM version"):
            parse_qasm("qubit q;\nh q;")

    def test_parse_preserves_raw_qasm(self, bell_qasm: str) -> None:
        """Original QASM string is preserved."""
        result = parse_qasm(bell_qasm)
        assert result.raw_qasm == bell_qasm

    def test_parse_skips_comments(self) -> None:
        """Comments are skipped during parsing."""
        qasm = """OPENQASM 3.0;
// This is a comment
qubit q;
// Another comment
h q;
"""
        result = parse_qasm(qasm)

        assert result.total_qubits == 1
        assert len(result.gates) == 1


# =============================================================================
# GateInfo Tests
# =============================================================================
class TestGateInfo:
    """Tests for GateInfo dataclass."""

    def test_gate_info_num_qubits(self) -> None:
        """num_qubits returns correct count."""
        gate = GateInfo(name="cx", qubits=("q[0]", "q[1]"), parameters=(), line_number=1)
        assert gate.num_qubits == 2

    def test_gate_info_is_two_qubit_cx(self) -> None:
        """CX is identified as a two-qubit gate."""
        gate = GateInfo(name="cx", qubits=("q[0]", "q[1]"), parameters=(), line_number=1)
        assert gate.is_two_qubit is True

    def test_gate_info_is_two_qubit_cz(self) -> None:
        """CZ is identified as a two-qubit gate."""
        gate = GateInfo(name="cz", qubits=("q[0]", "q[1]"), parameters=(), line_number=1)
        assert gate.is_two_qubit is True

    def test_gate_info_single_qubit_not_two_qubit(self) -> None:
        """H is not a two-qubit gate."""
        gate = GateInfo(name="h", qubits=("q[0]",), parameters=(), line_number=1)
        assert gate.is_two_qubit is False


# =============================================================================
# Metrics Tests
# =============================================================================
class TestMetricsExtraction:
    """Tests for metrics extraction."""

    def test_extract_metrics_simple(self, simple_qasm: str) -> None:
        """Extract metrics from simple circuit."""
        metrics = extract_metrics(simple_qasm)

        assert metrics.gates == 1
        assert metrics.qubits == 1
        assert metrics.two_qubit_gates == 0

    def test_extract_metrics_bell(self, bell_qasm: str) -> None:
        """Extract metrics from Bell circuit."""
        metrics = extract_metrics(bell_qasm)

        assert metrics.gates == 2
        assert metrics.qubits == 2
        assert metrics.two_qubit_gates == 1  # CX is two-qubit

    def test_extract_metrics_ghz(self, ghz_4_qasm: str) -> None:
        """Extract metrics from GHZ circuit."""
        metrics = extract_metrics(ghz_4_qasm)

        assert metrics.gates == 4
        assert metrics.qubits == 4
        assert metrics.two_qubit_gates == 3  # 3 CX gates

    def test_parsed_circuit_to_metrics(self, bell_qasm: str) -> None:
        """ParsedCircuit.to_metrics() returns StageMetrics."""
        parsed = parse_qasm(bell_qasm)
        metrics = parsed.to_metrics()

        assert isinstance(metrics, StageMetrics)
        assert metrics.gates == 2


# =============================================================================
# Depth Calculation Tests
# =============================================================================
class TestDepthCalculation:
    """Tests for circuit depth calculation."""

    def test_depth_single_gate(self, simple_qasm: str) -> None:
        """Single gate has depth 1."""
        metrics = extract_metrics(simple_qasm)
        assert metrics.depth == 1

    def test_depth_sequential_on_same_qubit(self) -> None:
        """Sequential gates on same qubit have additive depth."""
        qasm = """OPENQASM 3.0;
qubit q;
h q;
x q;
z q;
"""
        metrics = extract_metrics(qasm)
        assert metrics.depth == 3

    def test_depth_parallel_on_different_qubits(self) -> None:
        """Parallel gates on different qubits have depth 1."""
        qasm = """OPENQASM 3.0;
qubit[3] q;
h q[0];
x q[1];
z q[2];
"""
        metrics = extract_metrics(qasm)
        assert metrics.depth == 1

    def test_depth_bell_circuit(self, bell_qasm: str) -> None:
        """Bell circuit: H then CX has depth 2."""
        metrics = extract_metrics(bell_qasm)
        assert metrics.depth == 2

    def test_depth_ghz_linear_chain(self, ghz_4_qasm: str) -> None:
        """GHZ with linear chain: H, CX01, CX12, CX23 has depth 4."""
        metrics = extract_metrics(ghz_4_qasm)
        assert metrics.depth == 4

    def test_depth_empty_circuit(self) -> None:
        """Circuit with no gates has depth 0."""
        qasm = """OPENQASM 3.0;
qubit[2] q;
"""
        metrics = extract_metrics(qasm)
        assert metrics.depth == 0


# =============================================================================
# Validation Tests
# =============================================================================
class TestValidateQasm:
    """Tests for validate_qasm function."""

    def test_validate_valid_circuit(self, bell_qasm: str) -> None:
        """Valid circuit returns True with no errors."""
        is_valid, errors = validate_qasm(bell_qasm)

        assert is_valid is True
        assert errors == []

    def test_validate_empty_returns_error(self) -> None:
        """Empty QASM returns False with error."""
        is_valid, errors = validate_qasm("")

        assert is_valid is False
        assert len(errors) == 1
        assert "Empty QASM" in errors[0]

    def test_validate_no_qubits_returns_error(self) -> None:
        """QASM with no qubit declarations returns error."""
        qasm = """OPENQASM 3.0;
h q;
"""
        is_valid, errors = validate_qasm(qasm)

        assert is_valid is False
        assert any("No qubit declarations" in e for e in errors)


class TestValidateCircuitIntegrity:
    """Tests for validate_circuit_integrity function."""

    def test_identical_circuits_valid(self, bell_qasm: str) -> None:
        """Identical circuits pass integrity check."""
        is_valid, errors = validate_circuit_integrity(bell_qasm, bell_qasm)

        assert is_valid is True
        assert errors == []

    def test_qubit_count_change_detected(self) -> None:
        """Qubit count change is detected when not allowed."""
        original = """OPENQASM 3.0;
qubit[2] q;
h q[0];
"""
        transformed = """OPENQASM 3.0;
qubit[3] q;
h q[0];
"""
        is_valid, errors = validate_circuit_integrity(
            original, transformed, allow_qubit_count_change=False
        )

        assert is_valid is False
        assert any("Qubit count changed" in e for e in errors)

    def test_qubit_count_change_allowed(self) -> None:
        """Qubit count change allowed when explicitly permitted."""
        original = """OPENQASM 3.0;
qubit[2] q;
h q[0];
"""
        transformed = """OPENQASM 3.0;
qubit[3] q;
h q[0];
"""
        is_valid, errors = validate_circuit_integrity(
            original, transformed, allow_qubit_count_change=True
        )

        assert is_valid is True

    def test_gate_count_change_allowed_by_default(self) -> None:
        """Gate count changes are allowed by default (optimization)."""
        original = """OPENQASM 3.0;
qubit q;
h q;
h q;
"""
        transformed = """OPENQASM 3.0;
qubit q;
"""
        is_valid, errors = validate_circuit_integrity(original, transformed)

        assert is_valid is True

    def test_gate_count_change_detected_when_not_allowed(self) -> None:
        """Gate count change detected when not allowed."""
        original = """OPENQASM 3.0;
qubit q;
h q;
h q;
"""
        transformed = """OPENQASM 3.0;
qubit q;
"""
        is_valid, errors = validate_circuit_integrity(
            original, transformed, allow_gate_count_change=False
        )

        assert is_valid is False
        assert any("Gate count changed" in e for e in errors)


# =============================================================================
# Normalization Tests
# =============================================================================
class TestNormalizeQasm:
    """Tests for normalize_qasm function."""

    def test_normalize_strips_whitespace(self) -> None:
        """Extra whitespace is stripped."""
        qasm = """OPENQASM 3.0;
    qubit q;
        h q;
"""
        normalized = normalize_qasm(qasm)

        assert "    " not in normalized

    def test_normalize_removes_empty_lines(self) -> None:
        """Empty lines are removed."""
        qasm = """OPENQASM 3.0;

qubit q;

h q;

"""
        normalized = normalize_qasm(qasm)
        lines = normalized.split("\n")

        assert all(line.strip() for line in lines)

    def test_normalize_removes_comments(self) -> None:
        """Comments are removed."""
        qasm = """OPENQASM 3.0;
// comment
qubit q;
h q;
"""
        normalized = normalize_qasm(qasm)

        assert "//" not in normalized

    def test_normalize_lowercases_gate_names(self) -> None:
        """Gate names are lowercased."""
        qasm = """OPENQASM 3.0;
qubit q;
H q;
"""
        normalized = normalize_qasm(qasm)

        assert "h q;" in normalized
        assert "H q;" not in normalized


class TestCircuitsEquivalent:
    """Tests for circuits_equivalent function."""

    def test_equivalent_identical(self, bell_qasm: str) -> None:
        """Identical circuits are equivalent."""
        assert circuits_equivalent(bell_qasm, bell_qasm) is True

    def test_equivalent_different_whitespace(self) -> None:
        """Circuits with different whitespace are equivalent."""
        qasm1 = """OPENQASM 3.0;
qubit q;
h q;"""
        qasm2 = """OPENQASM 3.0;
  qubit q;
    h q;
"""
        assert circuits_equivalent(qasm1, qasm2) is True

    def test_not_equivalent_different_gates(self) -> None:
        """Circuits with different gates are not equivalent."""
        qasm1 = """OPENQASM 3.0;
qubit q;
h q;"""
        qasm2 = """OPENQASM 3.0;
qubit q;
x q;"""
        assert circuits_equivalent(qasm1, qasm2) is False


# =============================================================================
# Gate Counting Tests
# =============================================================================
class TestCountGatesByType:
    """Tests for count_gates_by_type function."""

    def test_count_single_gate_type(self, simple_qasm: str) -> None:
        """Single gate type is counted correctly."""
        counts = count_gates_by_type(simple_qasm)

        assert counts == {"h": 1}

    def test_count_multiple_gate_types(self, bell_qasm: str) -> None:
        """Multiple gate types are counted correctly."""
        counts = count_gates_by_type(bell_qasm)

        assert counts == {"h": 1, "cx": 1}

    def test_count_repeated_gates(self) -> None:
        """Repeated gates of same type are summed."""
        qasm = """OPENQASM 3.0;
qubit[3] q;
h q[0];
h q[1];
h q[2];
cx q[0], q[1];
cx q[1], q[2];
"""
        counts = count_gates_by_type(qasm)

        assert counts["h"] == 3
        assert counts["cx"] == 2
