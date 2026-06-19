#!/usr/bin/env python3
"""Automated circuit generation for systematic hardware testing.

This script generates a diverse set of quantum circuits with known properties
for comprehensive hardware validation. It creates circuits with varying:
- Circuit depth
- Gate count
- Number of qubits
- Gate types
- Circuit structure (GHZ, QFT, QAOA, random)

Usage:
    python experiments/generate_test_circuits.py --num-circuits 20 --output test_circuits.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.corpus import create_standard_corpus
from src.hardware import HardwareCircuit
from src.qasm import extract_metrics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class TestCircuitGenerator:
    """Generate diverse circuits for hardware testing."""

    def __init__(self):
        """Initialize circuit generator."""
        self.corpus = create_standard_corpus()
        self.circuits: list[HardwareCircuit] = []

    def generate_diversity_set(self, num_circuits: int = 20) -> list[HardwareCircuit]:
        """Generate a diverse set of circuits for testing.

        Ensures good coverage across:
        - Circuit types (GHZ, QFT, QAOA, Random)
        - Circuit depths (small, medium, large)
        - Gate counts (light, moderate, heavy)
        - Qubit counts (within device limits)

        Args:
            num_circuits: Total number of circuits to generate.

        Returns:
            List of HardwareCircuit objects.
        """
        circuits = []

        # Get all circuits from corpus
        all_circuits = list(self.corpus._circuits)

        # Group by circuit type
        circuits_by_type = {}
        for circuit in all_circuits:
            ctype = circuit.spec.circuit_type.value
            if ctype not in circuits_by_type:
                circuits_by_type[ctype] = []
            circuits_by_type[ctype].append(circuit)

        # Select circuits ensuring diversity
        circuits_per_type = max(1, num_circuits // len(circuits_by_type))

        for _circuit_type, type_circuits in circuits_by_type.items():
            # Sort by depth to get diversity within each type
            sorted_circuits = sorted(
                type_circuits,
                key=lambda c: c.spec.depth if c.spec.depth is not None else 0,
            )

            # Select evenly spaced circuits
            step = max(1, len(sorted_circuits) // circuits_per_type)
            for i in range(0, len(sorted_circuits), step):
                if len(circuits) >= num_circuits:
                    break

                circuit = sorted_circuits[i]

                # Parse QASM to get metrics
                metrics = extract_metrics(circuit.qasm)

                hw_circuit = HardwareCircuit(
                    name=circuit.spec.name,
                    qasm=circuit.qasm,
                    gates=metrics.gates,
                    depth=metrics.depth,
                    two_qubit_gates=metrics.two_qubit_gates,
                )

                circuits.append(hw_circuit)

            if len(circuits) >= num_circuits:
                break

        # Trim to exact count if needed
        circuits = circuits[:num_circuits]

        logger.info(f"Generated {len(circuits)} diverse test circuits")
        self._log_circuit_statistics(circuits)

        return circuits

    def generate_scaling_set(
        self,
        min_depth: int = 1,
        max_depth: int = 10,
        num_per_depth: int = 2,
    ) -> list[HardwareCircuit]:
        """Generate circuits with increasing depth for scaling analysis.

        Args:
            min_depth: Minimum circuit depth.
            max_depth: Maximum circuit depth.
            num_per_depth: Number of circuits per depth level.

        Returns:
            List of HardwareCircuit objects.
        """
        circuits = []

        # Get all circuits
        all_circuits = list(self.corpus._circuits)

        for target_depth in range(min_depth, max_depth + 1):
            depth_circuits = [
                c
                for c in all_circuits
                if c.spec.depth is not None
                and abs(c.spec.depth - target_depth) < 2  # Within 1 of target
            ]

            if not depth_circuits:
                logger.warning(f"No circuits found with depth ~{target_depth}")
                continue

            # Select diverse circuits at this depth
            selected = depth_circuits[:num_per_depth]
            for circuit in selected:
                if len(circuits) >= max_depth * num_per_depth:
                    break

                metrics = extract_metrics(circuit.qasm)

                hw_circuit = HardwareCircuit(
                    name=f"{circuit.spec.name}_d{target_depth}",
                    qasm=circuit.qasm,
                    gates=metrics.gates,
                    depth=metrics.depth,
                    two_qubit_gates=metrics.two_qubit_gates,
                )

                circuits.append(hw_circuit)

        logger.info(f"Generated {len(circuits)} scaling test circuits")
        return circuits

    def generate_stress_test_set(self, max_circuits: int = 50) -> list[HardwareCircuit]:
        """Generate circuits for stress testing (varying complexity).

        Creates circuits across the full spectrum of circuit properties.

        Args:
            max_circuits: Maximum number of circuits to generate.

        Returns:
            List of HardwareCircuit objects.
        """
        circuits = []

        # Get all circuits and sort by gates (proxy for complexity)
        all_circuits = list(self.corpus._circuits)

        # Create complexity bins
        min_gates = min((extract_metrics(c.qasm).get("total_gates", 0)) for c in all_circuits)
        max_gates = max((extract_metrics(c.qasm).get("total_gates", 0)) for c in all_circuits)

        num_bins = min(10, max_circuits // 2)
        bin_size = (max_gates - min_gates) / num_bins

        for bin_idx in range(num_bins):
            bin_start = min_gates + bin_idx * bin_size
            bin_end = bin_start + bin_size

            bin_circuits = [
                c
                for c in all_circuits
                if bin_start <= extract_metrics(c.qasm).get("total_gates", 0) < bin_end
            ]

            if bin_circuits:
                # Pick one from each bin for even coverage
                circuit = bin_circuits[0]
                metrics = extract_metrics(circuit.qasm)

                hw_circuit = HardwareCircuit(
                    name=circuit.spec.name,
                    qasm=circuit.qasm,
                    gates=metrics.gates,
                    depth=metrics.depth,
                    two_qubit_gates=metrics.two_qubit_gates,
                )

                circuits.append(hw_circuit)

        logger.info(f"Generated {len(circuits)} stress test circuits")
        self._log_circuit_statistics(circuits)

        return circuits

    @staticmethod
    def _log_circuit_statistics(circuits: list[HardwareCircuit]) -> None:
        """Log statistics about generated circuits.

        Args:
            circuits: List of circuits to analyze.
        """
        gates = [c.gates for c in circuits]
        depths = [c.depth for c in circuits]
        two_q_gates = [c.two_qubit_gates for c in circuits]

        logger.info("  Circuit statistics:")
        logger.info(f"    Gate count: min={min(gates)}, max={max(gates)}, avg={sum(gates)//len(gates)}")
        logger.info(f"    Depth: min={min(depths)}, max={max(depths)}, avg={sum(depths)//len(depths)}")
        logger.info(f"    2Q gates: min={min(two_q_gates)}, max={max(two_q_gates)}, avg={sum(two_q_gates)//len(two_q_gates)}")


def main() -> None:
    """Generate and save test circuits."""
    parser = argparse.ArgumentParser(description="Generate test circuits for hardware validation")
    parser.add_argument(
        "--num-circuits",
        type=int,
        default=20,
        help="Number of circuits to generate (default: 20)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="experiments/test_circuits.json",
        help="Output file for circuits (default: experiments/test_circuits.json)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["diversity", "scaling", "stress"],
        default="diversity",
        help="Generation mode (default: diversity)",
    )
    parser.add_argument(
        "--min-depth",
        type=int,
        default=1,
        help="Minimum depth for scaling mode (default: 1)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Maximum depth for scaling mode (default: 10)",
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("TEST CIRCUIT GENERATOR")
    logger.info("=" * 70)
    logger.info("")

    generator = TestCircuitGenerator()

    # Generate circuits based on mode
    if args.mode == "diversity":
        circuits = generator.generate_diversity_set(args.num_circuits)
    elif args.mode == "scaling":
        circuits = generator.generate_scaling_set(args.min_depth, args.max_depth)
    elif args.mode == "stress":
        circuits = generator.generate_stress_test_set(args.num_circuits)
    else:
        logger.error(f"Unknown mode: {args.mode}")
        return

    # Save to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    circuit_data = [
        {
            "name": c.name,
            "qasm": c.qasm,
            "gates": c.gates,
            "depth": c.depth,
            "two_qubit_gates": c.two_qubit_gates,
        }
        for c in circuits
    ]

    with output_path.open("w") as f:
        json.dump(circuit_data, f, indent=2)

    logger.info("")
    logger.info(f"Saved {len(circuits)} circuits to {output_path}")
    logger.info("")


if __name__ == "__main__":
    main()
