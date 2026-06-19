#!/usr/bin/env python3
"""End-to-end test: Optimize circuits with C++ optimizer, execute on Qiskit simulator.

This script validates that the circuit optimizer produces better fidelity when
circuits are executed on a simulator with realistic noise models.

Pipeline:
1. Load benchmark circuits
2. Optimize each circuit with C++ optimizer
3. Execute BOTH original and optimized circuits on Qiskit Aer simulator (with noise)
4. Compare fidelity metrics
5. Generate report with improvement data

Usage:
    python experiments/optimizer_simulator_test.py --num-circuits 5

Results saved to: experiments/reports/optimizer_simulator_*.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bridge import CircuitOptimizerBridge
from src.corpus import create_standard_corpus
from src.metrics import NoiseParams

try:
    from qiskit import QuantumCircuit, transpile
    from qiskit_aer import AerSimulator
    from qiskit_aer.noise import NoiseModel, depolarizing_error, thermal_relaxation_error
except ImportError:
    print("ERROR: qiskit and qiskit-aer required. Install with:")
    print("  pip install qiskit qiskit-aer")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Default optimizer binary location
DEFAULT_OPTIMIZER_BINARY = (
    Path.home()
    / "dev/research/quantum-circuit-optimizer/build/quantum_circuit_optimizer"
)

# Output directory
REPORTS_DIR = PROJECT_ROOT / "experiments" / "reports"


@dataclass
class SimulationTest:
    """Result of running optimizer on a circuit and executing both versions on simulator."""

    circuit_name: str
    num_qubits: int
    circuit_type: str

    # Original circuit metrics
    original_gates: int
    original_depth: int
    original_2q_gates: int

    # Optimized circuit metrics
    optimized_gates: int
    optimized_depth: int
    optimized_2q_gates: int

    # Simulation results
    original_fidelity: float
    optimized_fidelity: float
    fidelity_improvement: float

    # Metrics improvement (lower is better)
    gate_reduction: float  # percentage
    depth_reduction: float  # percentage
    two_q_gate_reduction: float  # percentage

    # Timing
    optimization_time_ms: float
    simulation_time_original_ms: float
    simulation_time_optimized_ms: float

    timestamp: str


@dataclass
class OptimizerSimulatorReport:
    """Full report for optimizer simulator test."""

    timestamp: str
    num_circuits: int
    shots: int
    optimizer_passes: list[str]
    noise_model: str

    tests: list[dict]  # List of SimulationTest as dicts

    # Summary statistics
    mean_fidelity_improvement: float
    mean_gate_reduction: float
    mean_depth_reduction: float
    successful_improvements: int  # Count of circuits that improved
    total_circuits: int


def qasm_to_qiskit_circuit(qasm: str) -> QuantumCircuit:
    """Convert OpenQASM string to Qiskit QuantumCircuit by parsing gates.

    Args:
        qasm: OpenQASM circuit string (2.0 or 3.0)

    Returns:
        Qiskit QuantumCircuit
    """
    import re

    lines = qasm.split("\n")

    # Extract qubit register size
    num_qubits = 1
    for line in lines:
        line = line.strip()
        if "qubit[" in line or "qreg" in line:
            # Extract size
            match = re.search(r"\[(\d+)\]", line)
            if match:
                num_qubits = int(match.group(1))
                break

    # Create circuit
    circuit = QuantumCircuit(num_qubits)

    # Parse and apply gates
    for line in lines:
        line = line.strip()

        # Skip headers, comments, and declarations
        if not line or line.startswith("//") or line.startswith("OPENQASM") or line.startswith("include") or line.startswith("qubit[") or line.startswith("qreg"):
            continue

        if not line.endswith(";"):
            continue

        line = line.rstrip(";")  # Remove trailing semicolon

        # Parse gate operations
        parts = line.split()
        if not parts:
            continue

        gate_name = parts[0].lower()

        # Extract qubit indices
        qubits = []
        for part in parts[1:]:
            # Handle q[0] or q[0],q[1] format
            matches = re.findall(r"\[(\d+)\]", part)
            qubits.extend([int(m) for m in matches])

        # Apply gate
        if gate_name == "h":
            circuit.h(qubits[0])
        elif gate_name == "x":
            circuit.x(qubits[0])
        elif gate_name == "y":
            circuit.y(qubits[0])
        elif gate_name == "z":
            circuit.z(qubits[0])
        elif gate_name == "s":
            circuit.s(qubits[0])
        elif gate_name == "t":
            circuit.t(qubits[0])
        elif gate_name == "rx" and len(parts) > 1:
            # Extract angle
            angle_match = re.search(r"\((.*?)\)", line)
            if angle_match:
                angle = float(angle_match.group(1))
                circuit.rx(angle, qubits[0])
        elif gate_name == "ry" and len(parts) > 1:
            angle_match = re.search(r"\((.*?)\)", line)
            if angle_match:
                angle = float(angle_match.group(1))
                circuit.ry(angle, qubits[0])
        elif gate_name == "rz" and len(parts) > 1:
            angle_match = re.search(r"\((.*?)\)", line)
            if angle_match:
                angle = float(angle_match.group(1))
                circuit.rz(angle, qubits[0])
        elif gate_name == "cx":
            circuit.cx(qubits[0], qubits[1])
        elif gate_name == "cz":
            circuit.cz(qubits[0], qubits[1])
        elif gate_name == "swap":
            circuit.swap(qubits[0], qubits[1])

    # Add measurement
    if circuit.num_clbits == 0:
        circuit.measure_all()

    return circuit


def convert_qasm3_to_qasm2(qasm3: str) -> str:
    """Convert OpenQASM 3.0 to OpenQASM 2.0 format.

    Args:
        qasm3: OpenQASM 3.0 circuit string

    Returns:
        OpenQASM 2.0 circuit string (WITHOUT include, since it causes encoding issues)
    """
    lines = qasm3.split("\n")
    qasm2_lines = []

    # Add OpenQASM 2.0 header
    qasm2_lines.append("OPENQASM 2.0;")
    # Don't include qelib1.inc - it causes encoding issues

    for line in lines:
        line = line.strip()

        # Skip comments and empty lines
        if not line or line.startswith("//"):
            continue

        # Skip OpenQASM 3.0 header
        if "OPENQASM 3.0" in line:
            continue

        # Skip any includes (they cause encoding problems)
        if line.startswith("include"):
            continue

        # Convert qubit declarations: qubit[N] q; -> qreg q[N];
        if line.startswith("qubit[") and line.endswith(";"):
            # Extract size and register name
            # Format: qubit[4] q;
            line_no_semi = line.rstrip(";")  # Remove trailing ;
            # Split by ] to get size and name
            bracket_pos = line_no_semi.find("]")
            size_str = line_no_semi[6:bracket_pos]  # Extract "4" from "qubit[4"
            reg_name = line_no_semi[bracket_pos + 1:].strip()  # Extract "q"
            qasm2_lines.append(f"qreg {reg_name}[{size_str}];")
            continue

        # Add other lines as-is (gate operations)
        if line and line.endswith(";"):
            qasm2_lines.append(line)

    return "\n".join(qasm2_lines)


def extract_metrics_from_circuit(circuit: QuantumCircuit) -> tuple[int, int, int]:
    """Extract gate count, depth, and 2-qubit gate count from circuit.

    Args:
        circuit: Qiskit QuantumCircuit

    Returns:
        (total_gates, depth, two_qubit_gates)
    """
    from qiskit.converters import circuit_to_dag

    dag = circuit_to_dag(circuit)
    op_nodes = list(dag.op_nodes())
    total_gates = len(op_nodes)
    two_q_gates = sum(1 for node in op_nodes if len(node.qargs) == 2)
    depth = dag.depth()
    return total_gates, depth, two_q_gates


def build_noise_model(noise_params: NoiseParams) -> NoiseModel:
    """Build Qiskit NoiseModel from noise parameters.

    Args:
        noise_params: NoiseParams dataclass with T1, T2, error rates

    Returns:
        NoiseModel for Aer simulator
    """
    noise_model = NoiseModel()

    # Single-qubit depolarizing error
    single_q_error = noise_params.single_qubit_error
    error_1q = depolarizing_error(single_q_error, 1)

    # Two-qubit depolarizing error
    two_q_error = noise_params.two_qubit_error
    error_2q = depolarizing_error(two_q_error, 2)

    # Add errors to all single and two-qubit gates
    noise_model.add_all_qubit_quantum_error(error_1q, ["h", "x", "y", "z", "s", "t", "rx", "ry", "rz"])
    noise_model.add_all_qubit_quantum_error(error_2q, ["cx", "cz", "swap"])

    # Readout error (~2.5% per qubit)
    readout_error_prob = 0.025
    for qubit in range(20):  # Garnet has 20 qubits
        noise_model.add_readout_error(
            [[1 - readout_error_prob, readout_error_prob], [readout_error_prob, 1 - readout_error_prob]],
            [qubit],
        )

    return noise_model


def run_optimizer(
    circuit_qasm: str, circuit_name: str, optimizer: CircuitOptimizerBridge, passes: list[str]
) -> tuple[str, int, int, int, float]:
    """Run the C++ optimizer on a circuit.

    Args:
        circuit_qasm: OpenQASM 3.0 circuit string
        circuit_name: Name for logging
        optimizer: CircuitOptimizerBridge instance
        passes: List of optimization passes

    Returns:
        (optimized_qasm, gates, depth, two_q_gates, time_ms)
    """
    logger.info(f"Optimizing {circuit_name}...")
    start = time.time()

    result = optimizer.optimize(
        qasm=circuit_qasm,
        passes=passes,
        topology="iqm-garnet",
        route=False,
    )

    elapsed_ms = (time.time() - start) * 1000

    gate_reduction = 100 * (1 - result.post_optimization.gates / result.input_metrics.gates)
    logger.info(
        f"  ✓ {result.input_metrics.gates}→{result.post_optimization.gates} gates "
        f"({gate_reduction:.0f}% reduction) in {elapsed_ms:.0f}ms"
    )

    return (
        result.output_qasm,
        result.post_optimization.gates,
        result.post_optimization.depth,
        result.post_optimization.two_qubit_gates,
        elapsed_ms,
    )


def simulate_circuit(
    qasm: str, circuit_name: str, simulator: AerSimulator, shots: int, is_optimized: bool = False
) -> tuple[float, float]:
    """Execute a circuit on simulator and compute fidelity.

    Args:
        qasm: OpenQASM 3.0 circuit string
        circuit_name: Name for logging
        simulator: AerSimulator instance
        shots: Number of shots
        is_optimized: Whether this is optimized version

    Returns:
        (fidelity, time_ms)
    """
    label = "OPTIMIZED" if is_optimized else "ORIGINAL"
    logger.info(f"  Simulating {label} {circuit_name}...")

    # Convert to Qiskit circuit
    circuit = qasm_to_qiskit_circuit(qasm)

    # Add measurement if not present
    if circuit.num_clbits == 0:
        circuit.measure_all()

    start = time.time()

    # Run simulation
    job = simulator.run(circuit, shots=shots)
    result = job.result()
    counts = result.get_counts(0)

    elapsed_ms = (time.time() - start) * 1000

    # Compute fidelity as fraction in most probable state
    total = sum(counts.values())
    max_count = max(counts.values())
    fidelity = max_count / total

    logger.info(f"    ✓ {elapsed_ms:.0f}ms, fidelity: {fidelity:.4f}")

    return fidelity, elapsed_ms


def test_circuit_pair(
    circuit_qasm: str,
    circuit_name: str,
    circuit_type: str,
    num_qubits: int,
    optimizer: CircuitOptimizerBridge,
    simulator: AerSimulator,
    passes: list[str],
    shots: int,
) -> SimulationTest:
    """Test a single circuit: optimize and compare fidelity on simulator.

    Args:
        circuit_qasm: OpenQASM circuit
        circuit_name: Circuit name
        circuit_type: Type of circuit
        num_qubits: Number of qubits
        optimizer: CircuitOptimizerBridge
        simulator: AerSimulator
        passes: Optimization passes
        shots: Number of shots for simulation

    Returns:
        SimulationTest result
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"Testing {circuit_name} ({num_qubits} qubits, {circuit_type})")
    logger.info(f"{'='*70}")

    # Get original circuit metrics
    original_circuit = qasm_to_qiskit_circuit(circuit_qasm)
    orig_gates, orig_depth, orig_2q = extract_metrics_from_circuit(original_circuit)

    # Step 1: Simulate original circuit
    logger.info("Step 1: Simulate ORIGINAL circuit")
    original_fidelity, sim_time_orig = simulate_circuit(circuit_qasm, circuit_name, simulator, shots)

    # Step 2: Optimize the circuit
    logger.info("Step 2: Optimize circuit")
    opt_qasm, opt_gates, opt_depth, opt_2q, opt_time = run_optimizer(
        circuit_qasm, circuit_name, optimizer, passes
    )

    # Step 3: Simulate optimized circuit
    logger.info("Step 3: Simulate OPTIMIZED circuit")
    optimized_fidelity, sim_time_opt = simulate_circuit(opt_qasm, circuit_name, simulator, shots, is_optimized=True)

    # Step 4: Compute improvements
    fidelity_improvement = optimized_fidelity - original_fidelity
    gate_reduction = 100 * (1 - opt_gates / orig_gates)
    depth_reduction = 100 * (1 - opt_depth / orig_depth)
    two_q_gate_reduction = 100 * (1 - opt_2q / max(1, orig_2q))

    logger.info(f"\nSummary for {circuit_name}:")
    logger.info(f"  Original fidelity:  {original_fidelity:.4f}")
    logger.info(f"  Optimized fidelity: {optimized_fidelity:.4f}")
    logger.info(f"  Fidelity improvement: {fidelity_improvement:+.4f}")
    logger.info(f"  Gate reduction: {gate_reduction:.1f}%")
    logger.info(f"  Depth reduction: {depth_reduction:.1f}%")
    logger.info(f"  2-qubit gate reduction: {two_q_gate_reduction:.1f}%")

    return SimulationTest(
        circuit_name=circuit_name,
        num_qubits=num_qubits,
        circuit_type=circuit_type,
        original_gates=orig_gates,
        original_depth=orig_depth,
        original_2q_gates=orig_2q,
        optimized_gates=opt_gates,
        optimized_depth=opt_depth,
        optimized_2q_gates=opt_2q,
        original_fidelity=original_fidelity,
        optimized_fidelity=optimized_fidelity,
        fidelity_improvement=fidelity_improvement,
        gate_reduction=gate_reduction,
        depth_reduction=depth_reduction,
        two_q_gate_reduction=two_q_gate_reduction,
        optimization_time_ms=opt_time,
        simulation_time_original_ms=sim_time_orig,
        simulation_time_optimized_ms=sim_time_opt,
        timestamp=datetime.now().isoformat(),
    )


def select_circuits(corpus, circuit_type: str | None = None, max_qubits: int = 12, limit: int | None = None):
    """Select circuits from corpus for testing."""
    count = 0
    for circuit in corpus:
        if limit and count >= limit:
            break

        if circuit.spec.num_qubits > max_qubits:
            continue

        if circuit_type and circuit.spec.circuit_type.value != circuit_type:
            continue

        yield circuit, circuit.spec.circuit_type.value
        count += 1


def main() -> None:
    """Run optimizer + simulator test."""
    parser = argparse.ArgumentParser(description="Test circuit optimizer on Qiskit simulator")
    parser.add_argument("--num-circuits", type=int, default=5, help="Number of circuits to test (default: 5)")
    parser.add_argument("--shots", type=int, default=1000, help="Shots per simulation (default: 1000)")
    parser.add_argument("--circuit-type", type=str, default=None, help="Filter by circuit type")
    parser.add_argument(
        "--optimizer-binary",
        type=Path,
        default=DEFAULT_OPTIMIZER_BINARY,
        help=f"Path to optimizer binary (default: {DEFAULT_OPTIMIZER_BINARY})",
    )
    parser.add_argument(
        "--passes", type=str, default="cancel,commute,rotate", help="Optimization passes (comma-separated)"
    )

    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Parse passes
    passes = [p.strip() for p in args.passes.split(",")]
    logger.info(f"Using optimization passes: {passes}")

    # Initialize optimizer
    logger.info(f"Initializing optimizer: {args.optimizer_binary}")
    if not args.optimizer_binary.exists():
        logger.error(f"Optimizer binary not found: {args.optimizer_binary}")
        sys.exit(1)

    optimizer = CircuitOptimizerBridge(args.optimizer_binary)
    logger.info("✓ Optimizer initialized")

    # Initialize simulator with realistic noise
    logger.info("Initializing Qiskit Aer simulator with IQM Garnet noise model...")
    noise_params = NoiseParams(
        t1_ns=37000.0,
        t2_ns=9600.0,
        single_qubit_error=0.001,
        two_qubit_error=0.006,
    )
    noise_model = build_noise_model(noise_params)
    simulator = AerSimulator(noise_model=noise_model)
    logger.info("✓ Simulator initialized")

    # Load circuit corpus
    logger.info("Loading circuit corpus...")
    corpus = create_standard_corpus()
    logger.info(f"✓ Corpus loaded ({len(corpus)} total circuits)")

    # Select circuits to test
    circuits = list(select_circuits(corpus, circuit_type=args.circuit_type, limit=args.num_circuits))
    logger.info(f"Selected {len(circuits)} circuits for testing")

    if not circuits:
        logger.error("No circuits selected!")
        sys.exit(1)

    # Run tests
    logger.info(f"\n{'='*70}")
    logger.info("OPTIMIZER VALIDATION TEST (Simulator)")
    logger.info(f"Circuits: {len(circuits)}")
    logger.info(f"Shots: {args.shots}")
    logger.info(f"Passes: {passes}")
    logger.info("Noise model: IQM Garnet")
    logger.info(f"{'='*70}\n")

    tests = []
    for circuit, circuit_type in circuits:
        try:
            test_result = test_circuit_pair(
                circuit_qasm=circuit.qasm,
                circuit_name=circuit.spec.name,
                circuit_type=circuit_type,
                num_qubits=circuit.spec.num_qubits,
                optimizer=optimizer,
                simulator=simulator,
                passes=passes,
                shots=args.shots,
            )
            tests.append(test_result)
        except Exception as e:
            logger.error(f"Failed to test {circuit.spec.name}: {e}", exc_info=True)
            continue

    # Generate report
    logger.info(f"\n{'='*70}")
    logger.info("GENERATING REPORT")
    logger.info(f"{'='*70}\n")

    if not tests:
        logger.error("No successful tests!")
        sys.exit(1)

    # Compute summary statistics
    fidelity_improvements = [t.fidelity_improvement for t in tests]
    gate_reductions = [t.gate_reduction for t in tests]
    depth_reductions = [t.depth_reduction for t in tests]

    mean_fidelity_improvement = sum(fidelity_improvements) / len(fidelity_improvements)
    mean_gate_reduction = sum(gate_reductions) / len(gate_reductions)
    mean_depth_reduction = sum(depth_reductions) / len(depth_reductions)
    successful_improvements = sum(1 for t in tests if t.fidelity_improvement > 0)

    report = OptimizerSimulatorReport(
        timestamp=datetime.now().isoformat(),
        num_circuits=len(tests),
        shots=args.shots,
        optimizer_passes=passes,
        noise_model="IQM Garnet (T1=37µs, T2=9.6µs, 1Q:0.1%, 2Q:0.6%)",
        tests=[asdict(t) for t in tests],
        mean_fidelity_improvement=mean_fidelity_improvement,
        mean_gate_reduction=mean_gate_reduction,
        mean_depth_reduction=mean_depth_reduction,
        successful_improvements=successful_improvements,
        total_circuits=len(tests),
    )

    # Save report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"optimizer_simulator_{timestamp}.json"

    with report_path.open("w") as f:
        json.dump(asdict(report), f, indent=2)

    logger.info(f"✓ Report saved: {report_path}")

    # Print summary
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Circuits tested: {len(tests)}")
    logger.info(f"Successful improvements: {successful_improvements}/{len(tests)}")
    logger.info(f"Mean fidelity improvement: {mean_fidelity_improvement:+.4f}")
    logger.info(f"Mean gate reduction: {mean_gate_reduction:.1f}%")
    logger.info(f"Mean depth reduction: {mean_depth_reduction:.1f}%")
    logger.info("\nDetailed results:")

    for test in tests:
        status = "✓ IMPROVED" if test.fidelity_improvement > 0 else "✗ DEGRADED"
        logger.info(
            f"  {test.circuit_name:20s} | "
            f"Fidelity: {test.original_fidelity:.3f}→{test.optimized_fidelity:.3f} ({test.fidelity_improvement:+.4f}) | "
            f"Gates: {test.original_gates}→{test.optimized_gates} ({test.gate_reduction:.0f}%) | "
            f"{status}"
        )

    logger.info("=" * 70)


if __name__ == "__main__":
    main()
