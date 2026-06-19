#!/usr/bin/env python3
"""Dry-run script to estimate IQM hardware credits needed for validation.

This script:
1. Loads experimental results
2. Selects representative circuits
3. Estimates credit costs for hardware execution
4. Reports whether it fits in the free tier (30 credits/month)

Usage:
    python experiments/hardware_dryrun.py [--num-circuits 10] [--shots 10000]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
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
from src.hardware import HardwareCircuit, IQMHardwareExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run dry-run credit estimation."""
    parser = argparse.ArgumentParser(
        description="Estimate IQM credits needed for hardware validation"
    )
    parser.add_argument(
        "--num-circuits",
        type=int,
        default=10,
        help="Number of circuits to validate (default: 10)",
    )
    parser.add_argument(
        "--shots",
        type=int,
        default=10000,
        help="Shots per circuit (default: 10000)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("IQM RESONANCE HARDWARE DRY-RUN: CREDIT ESTIMATION")
    logger.info("=" * 70)
    logger.info("")

    # Create executor in dry-run mode
    executor = IQMHardwareExecutor(dry_run=True)

    # Load standard corpus
    logger.info("Loading circuit corpus...")
    corpus = create_standard_corpus()
    logger.info(f"Corpus: {corpus.summary()}")
    logger.info("")

    # Select diverse circuits for validation
    logger.info(f"Selecting {args.num_circuits} representative circuits...")
    circuits_to_validate = []

    # Get all circuits
    all_circuits = list(corpus._circuits)

    # Select diverse subset
    circuit_types = {}
    for circuit in all_circuits:
        ctype = circuit.spec.circuit_type.value
        if ctype not in circuit_types:
            circuit_types[ctype] = []
        circuit_types[ctype].append(circuit)

    # Pick from each type
    for ctype in circuit_types:
        circuits = circuit_types[ctype]
        num_per_type = max(1, args.num_circuits // len(circuit_types))
        for circuit in circuits[:num_per_type]:
            hw_circuit = HardwareCircuit(
                name=circuit.spec.name,
                qasm=circuit.qasm,
                gates=10,  # Estimate (would extract from metrics in real use)
                depth=5,
                two_qubit_gates=2,
            )
            circuits_to_validate.append(hw_circuit)
            if len(circuits_to_validate) >= args.num_circuits:
                break
        if len(circuits_to_validate) >= args.num_circuits:
            break

    logger.info(f"Selected {len(circuits_to_validate)} circuits:")
    for i, c in enumerate(circuits_to_validate, 1):
        logger.info(f"  {i}. {c.name}: {c.gates} gates, {c.depth} depth, {c.two_qubit_gates} 2Q")
    logger.info("")

    # Estimate credits
    logger.info(f"Estimating credits for {args.shots} shots per circuit...")
    estimate = executor.estimate_credits(circuits_to_validate, shots=args.shots)

    logger.info("")
    logger.info("=" * 70)
    logger.info("CREDIT ESTIMATION RESULTS")
    logger.info("=" * 70)
    logger.info(f"Total circuits:        {estimate['num_circuits']}")
    logger.info(f"Shots per circuit:     {estimate['shots']:,}")
    logger.info(f"Free tier limit:       {estimate['free_tier_limit']} credits/month")
    logger.info(f"Estimated total cost:  {estimate['total_credits']} credits")
    logger.info(f"Within free tier:      {'✓ YES' if estimate['within_free_tier'] else '✗ NO'}")
    logger.info("")

    logger.info("Per-circuit breakdown:")
    logger.info(f"  Average per circuit:  {estimate['per_circuit_avg']} credits")
    logger.info(f"  Min:                  {min(estimate['per_circuit_credits'])} credits")
    logger.info(f"  Max:                  {max(estimate['per_circuit_credits'])} credits")
    logger.info("")

    if args.verbose:
        logger.info("Detailed per-circuit costs:")
        for name, cost in zip(
            [c.name for c in circuits_to_validate],
            estimate["per_circuit_credits"], strict=False,
        ):
            logger.info(f"  {name}: {cost} credits")
        logger.info("")

    # Recommendations
    logger.info("=" * 70)
    logger.info("RECOMMENDATIONS")
    logger.info("=" * 70)

    if estimate["within_free_tier"]:
        logger.info(
            f"✓ This experiment fits in the free tier "
            f"({estimate['total_credits']}/{estimate['free_tier_limit']} credits)"
        )
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Sign up for free tier: https://resonance.meetiqm.com/signup")
        logger.info("  2. Get credentials (Client ID & Secret)")
        logger.info("  3. Set environment variables:")
        logger.info("     export IQM_CLIENT_ID='your-client-id'")
        logger.info("     export IQM_CLIENT_SECRET='your-client-secret'")
        logger.info("  4. Run actual experiment: python experiments/hardware_validate.py")
    else:
        logger.info(
            f"✗ This experiment exceeds free tier "
            f"({estimate['total_credits']}/{estimate['free_tier_limit']} credits)"
        )
        logger.info("")
        logger.info("Options:")
        logger.info(f"  1. Reduce circuit count to ~{int(estimate['free_tier_limit'] / estimate['per_circuit_avg'])}")
        logger.info(f"  2. Reduce shots per circuit to ~{int(args.shots * estimate['free_tier_limit'] / estimate['total_credits'])}")
        logger.info("  3. Apply for paid credits: https://ionq.com/programs/research-credits/application")

    logger.info("")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
