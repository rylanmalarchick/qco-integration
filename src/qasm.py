"""OpenQASM 3.0 utilities for parsing, validation, and round-trip operations.

This module provides utilities for working with OpenQASM 3.0 circuits:
- Parsing QASM strings into structured representations
- Validating circuit integrity
- Extracting gate statistics
- Round-trip conversion verification

Following AgentBible principles:
- Type hints on all interfaces
- Fail fast with context
- Clear documentation

Reference: SCOPE_OF_WORK.md Phase 1 Task 2
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from src.metrics import StageMetrics

# =============================================================================
# Constants
# =============================================================================

# Gate patterns for parsing OpenQASM 3.0
# Single-qubit gates: h, x, y, z, s, t, sdg, tdg, rx, ry, rz, u1, u2, u3
SINGLE_QUBIT_GATES: frozenset[str] = frozenset({
    "h", "x", "y", "z", "s", "t", "sdg", "tdg",
    "rx", "ry", "rz", "u1", "u2", "u3", "id",
    "prx",  # IQM native gate
})

# Two-qubit gates: cx, cz, cy, swap, iswap, ecr
TWO_QUBIT_GATES: frozenset[str] = frozenset({
    "cx", "cnot", "cz", "cy", "swap", "iswap", "ecr",
    "rzz", "rxx", "ryy",
})

# Three-qubit gates: ccx (Toffoli), cswap (Fredkin)
THREE_QUBIT_GATES: frozenset[str] = frozenset({
    "ccx", "toffoli", "cswap", "fredkin",
})


# =============================================================================
# Exceptions
# =============================================================================

class QASMParseError(ValueError):
    """Raised when QASM parsing fails."""

    pass


class QASMValidationError(ValueError):
    """Raised when QASM validation fails."""

    pass


# =============================================================================
# Data Classes
# =============================================================================

@dataclass(frozen=True)
class GateInfo:
    """Information about a single gate in a circuit.

    Attributes:
        name: Gate name (lowercase).
        qubits: List of qubit operands.
        parameters: List of gate parameters (for parametric gates).
        line_number: Line number in the QASM source.
    """

    name: str
    qubits: tuple[str, ...]
    parameters: tuple[str, ...]
    line_number: int

    @property
    def num_qubits(self) -> int:
        """Return the number of qubits this gate acts on."""
        return len(self.qubits)

    @property
    def is_two_qubit(self) -> bool:
        """Return True if this is a two-qubit gate."""
        return self.name in TWO_QUBIT_GATES or self.num_qubits == 2


@dataclass
class ParsedCircuit:
    """Parsed representation of an OpenQASM circuit.

    Attributes:
        version: OpenQASM version string (e.g., "3.0").
        qubit_declarations: List of qubit declaration strings.
        gates: List of GateInfo objects.
        total_qubits: Total number of qubits in the circuit.
        raw_qasm: Original QASM string.
    """

    version: str
    qubit_declarations: list[str]
    gates: list[GateInfo]
    total_qubits: int
    raw_qasm: str

    # Regex patterns as class variables
    _VERSION_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"OPENQASM\s+(\d+(?:\.\d+)?)\s*;"
    )
    _QUBIT_DECL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"qubit(?:\s*\[(\d+)\])?\s+(\w+)\s*;"
    )
    _GATE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(\w+)(?:\s*\(([^)]*)\))?\s+([^;]+)\s*;"
    )

    def to_metrics(self) -> StageMetrics:
        """Convert to StageMetrics.

        Returns:
            StageMetrics with gate count, depth, qubit count, and 2Q gate count.
        """
        two_qubit_count = sum(1 for g in self.gates if g.is_two_qubit)
        return StageMetrics(
            gates=len(self.gates),
            depth=self._calculate_depth(),
            qubits=self.total_qubits,
            two_qubit_gates=two_qubit_count,
        )

    def _calculate_depth(self) -> int:
        """Calculate circuit depth based on gate dependencies.

        Depth is the longest path through the circuit when gates are
        scheduled as early as possible (ASAP scheduling).

        Returns:
            Circuit depth.
        """
        if not self.gates:
            return 0

        # Track the depth at which each qubit is next available
        qubit_depths: dict[str, int] = {}

        for gate in self.gates:
            # Find the maximum depth among all qubits this gate acts on
            max_qubit_depth = 0
            for qubit in gate.qubits:
                if qubit in qubit_depths:
                    max_qubit_depth = max(max_qubit_depth, qubit_depths[qubit])

            # This gate executes at max_qubit_depth, finishes at max_qubit_depth + 1
            new_depth = max_qubit_depth + 1
            for qubit in gate.qubits:
                qubit_depths[qubit] = new_depth

        return max(qubit_depths.values()) if qubit_depths else 0


# =============================================================================
# Parsing Functions
# =============================================================================

def parse_qasm(qasm: str) -> ParsedCircuit:
    """Parse an OpenQASM 3.0 circuit string.

    Args:
        qasm: OpenQASM 3.0 circuit string.

    Returns:
        ParsedCircuit with version, declarations, gates, and metadata.

    Raises:
        QASMParseError: If the QASM is malformed.
    """
    if not qasm or not qasm.strip():
        raise QASMParseError("Empty QASM string")

    lines = qasm.strip().split("\n")

    # Parse version
    version = _parse_version(lines)

    # Parse qubit declarations and count
    qubit_declarations, total_qubits, qubit_names = _parse_qubit_declarations(lines)

    # Parse gates
    gates = _parse_gates(lines, qubit_names)

    return ParsedCircuit(
        version=version,
        qubit_declarations=qubit_declarations,
        gates=gates,
        total_qubits=total_qubits,
        raw_qasm=qasm,
    )


def _parse_version(lines: list[str]) -> str:
    """Extract OpenQASM version from lines.

    Args:
        lines: List of QASM lines.

    Returns:
        Version string (e.g., "3.0").

    Raises:
        QASMParseError: If no valid OPENQASM declaration found.
    """
    for line in lines:
        line = line.strip()
        if line.startswith("//"):
            continue
        match = ParsedCircuit._VERSION_PATTERN.match(line)
        if match:
            return match.group(1)

    raise QASMParseError("No OPENQASM version declaration found")


def _parse_qubit_declarations(
    lines: list[str],
) -> tuple[list[str], int, set[str]]:
    """Parse qubit declarations from QASM lines.

    Args:
        lines: List of QASM lines.

    Returns:
        Tuple of (declarations, total_qubits, qubit_names).
    """
    declarations: list[str] = []
    total_qubits = 0
    qubit_names: set[str] = set()

    for line in lines:
        line = line.strip()
        if line.startswith("//"):
            continue

        match = ParsedCircuit._QUBIT_DECL_PATTERN.match(line)
        if match:
            size_str, name = match.groups()
            size = int(size_str) if size_str else 1
            total_qubits += size
            declarations.append(line)

            # Track individual qubit names for depth calculation
            if size == 1:
                qubit_names.add(name)
            else:
                for i in range(size):
                    qubit_names.add(f"{name}[{i}]")

    return declarations, total_qubits, qubit_names


# Keywords that are not gates
_NON_GATE_KEYWORDS = frozenset({
    "openqasm", "include", "qubit", "bit", "creg", "qreg",
    "gate", "measure", "reset", "barrier", "if", "for", "while",
})


def _parse_gates(lines: list[str], qubit_names: set[str]) -> list[GateInfo]:  # noqa: ARG001
    """Parse gate operations from QASM lines.

    Args:
        lines: List of QASM lines.
        qubit_names: Set of declared qubit names (reserved for future validation).

    Returns:
        List of GateInfo objects.
    """
    gates: list[GateInfo] = []

    for line_num, line in enumerate(lines, 1):
        gate = _try_parse_gate_line(line, line_num)
        if gate is not None:
            gates.append(gate)

    return gates


def _try_parse_gate_line(line: str, line_num: int) -> GateInfo | None:
    """Try to parse a single line as a gate operation.

    Args:
        line: A single QASM line.
        line_num: Line number for error reporting.

    Returns:
        GateInfo if the line is a gate, None otherwise.
    """
    line = line.strip()

    # Skip empty lines, comments, version, and qubit declarations
    if not line or line.startswith("//"):
        return None
    if line.upper().startswith("OPENQASM"):
        return None
    if ParsedCircuit._QUBIT_DECL_PATTERN.match(line):
        return None

    # Try to parse as gate
    match = ParsedCircuit._GATE_PATTERN.match(line)
    if not match:
        return None

    gate_name = match.group(1).lower()
    if gate_name in _NON_GATE_KEYWORDS:
        return None

    params_str = match.group(2) or ""
    qubits_str = match.group(3)

    params = tuple(p.strip() for p in params_str.split(",") if p.strip())
    qubits = tuple(q.strip() for q in qubits_str.split(",") if q.strip())

    return GateInfo(
        name=gate_name,
        qubits=qubits,
        parameters=params,
        line_number=line_num,
    )


# =============================================================================
# Validation Functions
# =============================================================================

def validate_qasm(qasm: str) -> tuple[bool, list[str]]:
    """Validate an OpenQASM 3.0 circuit.

    Performs the following checks:
    1. Parseable structure
    2. Valid version declaration
    3. Qubit declarations present
    4. Gates reference declared qubits

    Args:
        qasm: OpenQASM 3.0 circuit string.

    Returns:
        Tuple of (is_valid, list of error messages).
    """
    errors: list[str] = []

    # Check not empty
    if not qasm or not qasm.strip():
        return False, ["Empty QASM string"]

    # Try to parse
    try:
        parsed = parse_qasm(qasm)
    except QASMParseError as e:
        return False, [str(e)]

    # Check version
    if not parsed.version.startswith("3"):
        errors.append(f"Expected OpenQASM 3.x, got {parsed.version}")

    # Check qubit declarations
    if parsed.total_qubits == 0:
        errors.append("No qubit declarations found")

    return len(errors) == 0, errors


def validate_circuit_integrity(
    original: str,
    transformed: str,
    *,
    allow_gate_count_change: bool = True,
    allow_qubit_count_change: bool = False,
) -> tuple[bool, list[str]]:
    """Validate that a transformed circuit maintains integrity.

    Args:
        original: Original OpenQASM circuit.
        transformed: Transformed OpenQASM circuit.
        allow_gate_count_change: Whether gate count can change (default True).
        allow_qubit_count_change: Whether qubit count can change (default False).

    Returns:
        Tuple of (is_valid, list of error messages).
    """
    errors: list[str] = []

    # Parse both circuits
    try:
        orig_parsed = parse_qasm(original)
    except QASMParseError as e:
        return False, [f"Failed to parse original: {e}"]

    try:
        trans_parsed = parse_qasm(transformed)
    except QASMParseError as e:
        return False, [f"Failed to parse transformed: {e}"]

    # Check qubit count
    if (
        not allow_qubit_count_change
        and orig_parsed.total_qubits != trans_parsed.total_qubits
    ):
        errors.append(
            f"Qubit count changed: {orig_parsed.total_qubits} -> "
            f"{trans_parsed.total_qubits}"
        )

    # Check gate count if not allowed to change
    if (
        not allow_gate_count_change
        and len(orig_parsed.gates) != len(trans_parsed.gates)
    ):
        errors.append(
            f"Gate count changed: {len(orig_parsed.gates)} -> "
            f"{len(trans_parsed.gates)}"
        )

    return len(errors) == 0, errors


# =============================================================================
# Metrics Extraction
# =============================================================================

def extract_metrics(qasm: str) -> StageMetrics:
    """Extract StageMetrics from an OpenQASM circuit.

    Args:
        qasm: OpenQASM 3.0 circuit string.

    Returns:
        StageMetrics with gate count, depth, qubit count, and 2Q gate count.

    Raises:
        QASMParseError: If the QASM is malformed.
    """
    parsed = parse_qasm(qasm)
    return parsed.to_metrics()


# =============================================================================
# Utility Functions
# =============================================================================

def normalize_qasm(qasm: str) -> str:
    """Normalize QASM formatting for comparison.

    Normalizations applied:
    - Strip whitespace from lines
    - Remove empty lines
    - Lowercase gate names
    - Consistent spacing

    Args:
        qasm: OpenQASM circuit string.

    Returns:
        Normalized QASM string.
    """
    lines = []
    for line in qasm.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("//"):
            continue

        # Normalize OPENQASM declaration
        if line.upper().startswith("OPENQASM"):
            lines.append(line)
            continue

        # Normalize qubit declarations
        if ParsedCircuit._QUBIT_DECL_PATTERN.match(line):
            lines.append(line)
            continue

        # Normalize gate lines
        match = ParsedCircuit._GATE_PATTERN.match(line)
        if match:
            gate_name = match.group(1).lower()
            params = match.group(2)
            qubits = match.group(3).strip()

            if params:
                lines.append(f"{gate_name}({params}) {qubits};")
            else:
                lines.append(f"{gate_name} {qubits};")
        else:
            lines.append(line)

    return "\n".join(lines)


def circuits_equivalent(qasm1: str, qasm2: str) -> bool:
    """Check if two QASM circuits are equivalent (same normalized form).

    This is a structural equivalence check, not a unitary equivalence check.

    Args:
        qasm1: First OpenQASM circuit.
        qasm2: Second OpenQASM circuit.

    Returns:
        True if circuits have the same normalized form.
    """
    return normalize_qasm(qasm1) == normalize_qasm(qasm2)


def count_gates_by_type(qasm: str) -> dict[str, int]:
    """Count gates by type in a circuit.

    Args:
        qasm: OpenQASM circuit string.

    Returns:
        Dictionary mapping gate names to counts.
    """
    parsed = parse_qasm(qasm)
    counts: dict[str, int] = {}
    for gate in parsed.gates:
        counts[gate.name] = counts.get(gate.name, 0) + 1
    return counts
