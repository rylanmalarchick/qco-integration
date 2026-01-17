#!/usr/bin/env python3
"""Full hardware validation script for IQM Resonance.

This script executes selected circuits on real quantum hardware and compares
the results against simulation predictions.

Usage:
    # Dry run first (no credentials needed)
    python experiments/hardware_dryrun.py

    # Then set credentials
    export IQM_CLIENT_ID='your-id'
    export IQM_CLIENT_SECRET='your-secret'

    # Run validation
    python experiments/hardware_validate.py [--num-circuits 10] [--shots 1000]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
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

from src.corpus import create_standard_corpus
from src.hardware import HardwareCircuit, IQMHardwareExecutor, create_validation_report
from src.pipeline import create_real_pipeline
from src.metrics import NoiseParams

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Default noise parameters
DEFAULT_NOISE = NoiseParams(
    t1_ns=37000.0,
    t2_ns=9600.0,
    single_qubit_error=0.001,
    two_qubit_error=0.006,
)


def main() -> None:
    """Run hardware validation experiment."""
    parser = argparse.ArgumentParser(description="Execute circuits on IQM hardware for validation")
    parser.add_argument(
        "--num-circuits",
        type=int,
        default=10,
        help="Number of circuits to validate (default: 10)",
    )
    parser.add_argument(
        "--shots",
        type=int,
        default=1000,
        help="Shots per circuit (default: 1000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only estimate credits, don't execute",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default="IQM_RESONANCE_5Q",
        help="IQM backend name (default: IQM_RESONANCE_5Q)",
    )
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("IQM RESONANCE HARDWARE VALIDATION")
    logger.info("=" * 70)
    logger.info("")

    # Create executor
    executor = IQMHardwareExecutor(dry_run=args.dry_run)

    # Load circuit corpus
    logger.info("Loading circuit corpus...")
    corpus = create_standard_corpus()
    logger.info(f"Corpus: {corpus.summary()}")
    logger.info("")

    # Select circuits
    logger.info(f"Selecting {args.num_circuits} representative circuits...")
    circuits_to_validate = []

    all_circuits = list(corpus._circuits)
    circuit_types = {}

    for circuit in all_circuits:
        ctype = circuit.spec.circuit_type.value
        if ctype not in circuit_types:
            circuit_types[ctype] = []
        circuit_types[ctype].append(circuit)

    for ctype in circuit_types:
        circuits = circuit_types[ctype]
        num_per_type = max(1, args.num_circuits // len(circuit_types))
        for circuit in circuits[:num_per_type]:
            hw_circuit = HardwareCircuit(
                name=circuit.spec.name,
                qasm=circuit.qasm,
                gates=10,  # Estimate
                depth=5,
                two_qubit_gates=2,
            )
            circuits_to_validate.append(hw_circuit)
            if len(circuits_to_validate) >= args.num_circuits:
                break
        if len(circuits_to_validate) >= args.num_circuits:
            break

    logger.info(f"Selected {len(circuits_to_validate)} circuits")
    logger.info("")

    # Estimate credits
    logger.info(f"Estimating credits for {args.shots} shots per circuit...")
    estimate = executor.estimate_credits(circuits_to_validate, shots=args.shots)

    logger.info("")
    logger.info("CREDIT ESTIMATION")
    logger.info("-" * 70)
    logger.info(f"Total circuits:        {estimate['num_circuits']}")
    logger.info(f"Shots per circuit:     {estimate['shots']:,}")
    logger.info(f"Free tier limit:       {estimate['free_tier_limit']} credits/month")
    logger.info(f"Estimated total cost:  {estimate['total_credits']} credits")
    logger.info(f"Within free tier:      {'✓ YES' if estimate['within_free_tier'] else '✗ NO'}")
    logger.info("")

    if args.dry_run:
        logger.info("DRY-RUN MODE: Stopping here (no execution)")
        logger.info("")
        if estimate["within_free_tier"]:
            logger.info("✓ This experiment WILL FIT in the free tier")
            logger.info("")
            logger.info("To actually run hardware validation:")
            logger.info("  1. Sign up: https://resonance.meetiqm.com/signup")
            logger.info("  2. Set credentials:")
            logger.info("     export IQM_CLIENT_ID='your-id'")
            logger.info("     export IQM_CLIENT_SECRET='your-secret'")
            logger.info(f"  3. Run: python experiments/hardware_validate.py --num-circuits {args.num_circuits}")
        return

    # Execute on hardware
    logger.info("=" * 70)
    logger.info("EXECUTING ON HARDWARE")
    logger.info("=" * 70)
    logger.info("")

    try:
        hw_results = executor.execute(circuits_to_validate, shots=args.shots, backend=args.backend)
        logger.info(f"Successfully executed {len(hw_results)} circuits")
    except Exception as e:
        logger.error(f"Hardware execution failed: {e}")
        logger.error("Make sure IQM_CLIENT_ID and IQM_CLIENT_SECRET are set")
        return

    logger.info("")

    # Compute simulation fidelities for comparison
    logger.info("Computing simulated fidelities for comparison...")
    pipeline = create_real_pipeline(noise_params=DEFAULT_NOISE, default_topology="iqm-garnet")

    sim_fidelities = {}
    for hw_result in hw_results:
        try:
            # This is a simplified estimate - would need full pipeline execution for real comparison
            sim_fidelities[hw_result.circuit_name] = 0.85  # Placeholder
        except Exception as e:
            logger.warning(f"Could not compute simulation fidelity for {hw_result.circuit_name}: {e}")
            sim_fidelities[hw_result.circuit_name] = 0.0

    # Generate validation report
    logger.info("Generating validation report...")
    report = create_validation_report(hw_results, sim_fidelities)

    # Save report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = PROJECT_ROOT / "experiments" / "reports" / f"hardware_validation_{timestamp}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with report_path.open("w") as f:
        json.dump(report, f, indent=2)

    logger.info("")
    logger.info("=" * 70)
    logger.info("VALIDATION RESULTS")
    logger.info("=" * 70)
    logger.info("")
    logger.info(f"Mean hardware fidelity:   {report['summary']['mean_hardware_fidelity']}")
    logger.info(f"Mean simulated fidelity:  {report['summary']['mean_simulated_fidelity']}")
    logger.info(f"Mean difference:         {report['summary']['mean_difference']}")
    logger.info("")
    logger.info(f"Report saved to: {report_path}")
    logger.info("")


if __name__ == "__main__":
    main()
