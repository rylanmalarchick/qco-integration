#!/usr/bin/env python3
"""End-to-end test: Optimize circuits with C++ optimizer, execute on real IQM hardware.

This script validates that the circuit optimizer actually improves fidelity when
circuits are executed on real quantum hardware.

Pipeline:
1. Load benchmark circuits
2. Optimize each circuit with C++ optimizer (cancel, commute, rotate passes)
3. Execute BOTH original and optimized circuits on IQM Resonance (real QPU)
4. Compare fidelity metrics
5. Generate report with improvement data

Usage:
    # First, set your IQM credentials
    export RESONANCE_API_TOKEN='your-token'

    # Run on mock device (instant, free)
    python experiments/optimizer_hardware_test.py --quantum-computer garnet:mock --num-circuits 3

    # Run on real hardware (uses credits)
    python experiments/optimizer_hardware_test.py --quantum-computer garnet --num-circuits 5 --shots 1000

Results saved to: experiments/reports/optimizer_hardware_*.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

# Load .env file
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key] = value

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bridge import CircuitOptimizerBridge, OptimizationResult
from src.corpus import create_standard_corpus, CircuitType
from src.hardware import IQMHardwareExecutor, HardwareCircuit, HardwareResult

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
class OptimizationTest:
    """Result of running optimizer on a circuit and executing both versions on hardware."""

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

    # Hardware execution results
    original_hardware_result: dict  # HardwareResult as dict
    optimized_hardware_result: dict  # HardwareResult as dict

    # Fidelity comparison
    original_fidelity: float
    optimized_fidelity: float
    fidelity_improvement: float

    # Metrics improvement (lower is better)
    gate_reduction: float  # percentage
    depth_reduction: float  # percentage
    two_q_gate_reduction: float  # percentage

    # Timing
    optimization_time_ms: float
    execution_time_original_ms: float
    execution_time_optimized_ms: float

    timestamp: str


@dataclass
class OptimizerHardwareReport:
    """Full report for optimizer hardware test."""

    timestamp: str
    quantum_computer: str
    num_circuits: int
    shots: int
    optimizer_passes: list[str]

    tests: list[OptimizationTest]

    # Summary statistics
    mean_fidelity_improvement: float
    mean_gate_reduction: float
    mean_depth_reduction: float
    successful_improvements: int  # Count of circuits that improved
    total_circuits: int


def run_optimizer(
    circuit_qasm: str, circuit_name: str, optimizer: CircuitOptimizerBridge, passes: list[str]
) -> OptimizationResult:
    """Run the C++ optimizer on a circuit.

    Args:
        circuit_qasm: OpenQASM 3.0 circuit string
        circuit_name: Name for logging
        optimizer: CircuitOptimizerBridge instance
        passes: List of optimization passes

    Returns:
        OptimizationResult with metrics and optimized QASM
    """
    logger.info(f"Optimizing {circuit_name} with passes: {passes}")
    start = time.time()

    result = optimizer.optimize(
        qasm=circuit_qasm,
        passes=passes,
        topology="iqm-garnet",
        route=False,  # Don't route yet, just optimize
    )

    elapsed_ms = (time.time() - start) * 1000
    logger.info(
        f"  Optimization complete: {result.input_metrics.gates} → {result.post_optimization.gates} gates "
        f"({100 * (1 - result.post_optimization.gates/result.input_metrics.gates):.1f}% reduction) in {elapsed_ms:.0f}ms"
    )

    return result


def execute_on_hardware(
    circuit_qasm: str,
    circuit_name: str,
    executor: IQMHardwareExecutor,
    shots: int,
    is_optimized: bool = False,
) -> HardwareResult:
    """Execute a circuit on IQM hardware.

    Args:
        circuit_qasm: OpenQASM 3.0 circuit string
        circuit_name: Name for logging
        executor: IQMHardwareExecutor instance
        shots: Number of shots
        is_optimized: Whether this is the optimized version

    Returns:
        HardwareResult with measurement counts and fidelity
    """
    label = "OPTIMIZED" if is_optimized else "ORIGINAL"
    logger.info(f"Executing {label} {circuit_name} on hardware ({shots} shots)...")

    start = time.time()

    # Create HardwareCircuit wrapper
    hw_circuit = HardwareCircuit(
        name=circuit_name,
        qasm=circuit_qasm,
        gates=circuit_qasm.count("cx") + circuit_qasm.count("ry") + circuit_qasm.count("rx"),
        depth=10,  # Rough estimate
        two_qubit_gates=circuit_qasm.count("cx"),
    )

    # Execute
    result = executor.execute([hw_circuit], shots=shots)[0]

    elapsed_ms = (time.time() - start) * 1000
    logger.info(f"  Execution complete in {elapsed_ms:.0f}ms, fidelity: {result.compute_fidelity():.3f}")

    return result


def test_circuit_pair(
    circuit_qasm: str,
    circuit_name: str,
    circuit_type: str,
    num_qubits: int,
    optimizer: CircuitOptimizerBridge,
    executor: IQMHardwareExecutor,
    passes: list[str],
    shots: int,
) -> OptimizationTest:
    """Test a single circuit: optimize it and execute both versions on hardware.

    Args:
        circuit_qasm: OpenQASM circuit
        circuit_name: Circuit name
        circuit_type: Type of circuit (QFT, GHZ, etc.)
        num_qubits: Number of qubits
        optimizer: CircuitOptimizerBridge
        executor: IQMHardwareExecutor
        passes: Optimization passes to apply
        shots: Number of shots for hardware execution

    Returns:
        OptimizationTest result
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"Testing {circuit_name} ({num_qubits} qubits, {circuit_type})")
    logger.info(f"{'='*70}")

    # Step 1: Execute original circuit on hardware
    logger.info("Step 1: Execute ORIGINAL circuit on hardware")
    original_result = execute_on_hardware(circuit_qasm, circuit_name, executor, shots)
    original_fidelity = original_result.compute_fidelity()

    # Step 2: Optimize the circuit
    logger.info("Step 2: Optimize circuit with C++ optimizer")
    opt_result = run_optimizer(circuit_qasm, circuit_name, optimizer, passes)

    # Step 3: Execute optimized circuit on hardware
    logger.info("Step 3: Execute OPTIMIZED circuit on hardware")
    optimized_result = execute_on_hardware(
        opt_result.output_qasm, circuit_name, executor, shots, is_optimized=True
    )
    optimized_fidelity = optimized_result.compute_fidelity()

    # Step 4: Compute improvements
    fidelity_improvement = optimized_fidelity - original_fidelity
    gate_reduction = 100 * (1 - opt_result.post_optimization.gates / opt_result.input_metrics.gates)
    depth_reduction = 100 * (1 - opt_result.post_optimization.depth / opt_result.input_metrics.depth)
    two_q_gate_reduction = 100 * (
        1 - opt_result.post_optimization.two_qubit_gates / max(1, opt_result.input_metrics.two_qubit_gates)
    )

    logger.info(f"\nSummary for {circuit_name}:")
    logger.info(f"  Original fidelity:  {original_fidelity:.4f}")
    logger.info(f"  Optimized fidelity: {optimized_fidelity:.4f}")
    logger.info(f"  Fidelity improvement: {fidelity_improvement:+.4f}")
    logger.info(f"  Gate reduction: {gate_reduction:.1f}%")
    logger.info(f"  Depth reduction: {depth_reduction:.1f}%")

    return OptimizationTest(
        circuit_name=circuit_name,
        num_qubits=num_qubits,
        circuit_type=circuit_type,
        original_gates=opt_result.input_metrics.gates,
        original_depth=opt_result.input_metrics.depth,
        original_2q_gates=opt_result.input_metrics.two_qubit_gates,
        optimized_gates=opt_result.post_optimization.gates,
        optimized_depth=opt_result.post_optimization.depth,
        optimized_2q_gates=opt_result.post_optimization.two_qubit_gates,
        original_hardware_result=asdict(original_result),
        optimized_hardware_result=asdict(optimized_result),
        original_fidelity=original_fidelity,
        optimized_fidelity=optimized_fidelity,
        fidelity_improvement=fidelity_improvement,
        gate_reduction=gate_reduction,
        depth_reduction=depth_reduction,
        two_q_gate_reduction=two_q_gate_reduction,
        optimization_time_ms=0.0,  # Not tracked currently
        execution_time_original_ms=0.0,  # Not tracked currently
        execution_time_optimized_ms=0.0,  # Not tracked currently
        timestamp=datetime.now().isoformat(),
    )


def select_circuits(corpus, circuit_type: str | None = None, max_qubits: int = 12, limit: int | None = None):
    """Select circuits from corpus for testing.

    Args:
        corpus: CircuitCorpus instance
        circuit_type: Filter by circuit type (e.g., 'qft', 'ghz')
        max_qubits: Max qubits to include
        limit: Max number of circuits to return

    Yields:
        (BenchmarkCircuit, circuit_type_str)
    """
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
    """Run optimizer + hardware test."""
    parser = argparse.ArgumentParser(
        description="Test circuit optimizer on real IQM Resonance hardware"
    )
    parser.add_argument(
        "--num-circuits",
        type=int,
        default=3,
        help="Number of circuits to test (default: 3)",
    )
    parser.add_argument(
        "--shots",
        type=int,
        default=1000,
        help="Shots per circuit execution (default: 1000)",
    )
    parser.add_argument(
        "--circuit-type",
        type=str,
        default=None,
        help="Filter by circuit type (qft, ghz, qaoa, random, vqe)",
    )
    parser.add_argument(
        "--quantum-computer",
        type=str,
        default="garnet:mock",
        help="IQM quantum computer (e.g., 'garnet', 'garnet:mock'). Default: garnet:mock",
    )
    parser.add_argument(
        "--optimizer-binary",
        type=Path,
        default=DEFAULT_OPTIMIZER_BINARY,
        help=f"Path to optimizer binary (default: {DEFAULT_OPTIMIZER_BINARY})",
    )
    parser.add_argument(
        "--passes",
        type=str,
        default="cancel,commute,rotate",
        help="Optimization passes (comma-separated, default: cancel,commute,rotate)",
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

    # Initialize hardware executor
    logger.info(f"Initializing IQM hardware executor: {args.quantum_computer}")
    executor = IQMHardwareExecutor(quantum_computer=args.quantum_computer)
    logger.info("✓ Hardware executor initialized")

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
    logger.info(f"STARTING OPTIMIZER + HARDWARE TEST")
    logger.info(f"Circuits: {len(circuits)}")
    logger.info(f"Shots: {args.shots}")
    logger.info(f"Quantum computer: {args.quantum_computer}")
    logger.info(f"Passes: {passes}")
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
                executor=executor,
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

    report = OptimizerHardwareReport(
        timestamp=datetime.now().isoformat(),
        quantum_computer=args.quantum_computer,
        num_circuits=len(tests),
        shots=args.shots,
        optimizer_passes=passes,
        tests=[asdict(t) for t in tests],  # Convert to dicts for JSON serialization
        mean_fidelity_improvement=mean_fidelity_improvement,
        mean_gate_reduction=mean_gate_reduction,
        mean_depth_reduction=mean_depth_reduction,
        successful_improvements=successful_improvements,
        total_circuits=len(tests),
    )

    # Save report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"optimizer_hardware_{timestamp}.json"

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
    logger.info(f"\nDetailed results:")

    for test in tests:
        status = "✓ IMPROVED" if test.fidelity_improvement > 0 else "✗ DEGRADED"
        logger.info(
            f"  {test.circuit_name:20s} | "
            f"Fidelity: {test.original_fidelity:.3f} → {test.optimized_fidelity:.3f} ({test.fidelity_improvement:+.4f}) | "
            f"Gates: {test.original_gates} → {test.optimized_gates} ({test.gate_reduction:.0f}%) | "
            f"{status}"
        )

    logger.info("=" * 70)


if __name__ == "__main__":
    main()
