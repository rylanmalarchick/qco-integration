#!/usr/bin/env python3
"""Formal Ablation Study for ACM TQC Submission.

Runs a systematic ablation study of QCO optimization passes:

1. Individual passes (already in per_pass, but re-run for consistency)
2. Leave-one-out: all passes except one
3. Ordering variants: different orderings of all 4 passes
4. Cumulative build-up: add passes one at a time

Uses the full 371-circuit paper corpus with real C++ optimizer + Lindblad sim.

Usage:
    python experiments/run_ablation.py [--quick] [--paper] [--real]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bridge import MockCircuitOptimizerBridge  # noqa: E402
from src.corpus import (  # noqa: E402
    CircuitCorpus,
    create_paper_corpus,
    create_small_corpus,
    create_standard_corpus,
)
from src.metrics import EndToEndResult, NoiseParams  # noqa: E402
from src.pipeline import EndToEndPipeline, MockGateCompiler, create_real_pipeline  # noqa: E402
from src.runner import BenchmarkRunner, ExperimentConfig, ExperimentResults  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results" / "ablation"

DEFAULT_NOISE = NoiseParams(
    t1_ns=37000.0,
    t2_ns=9600.0,
    single_qubit_error=0.001,
    two_qubit_error=0.006,
)

ALL_PASSES = ["cancel", "commute", "rotate", "identity"]

# Ablation configurations
ABLATION_CONFIGS = {
    # -- Individual passes --
    "individual": {
        "description": "Each pass alone",
        "configs": [
            ["cancel"],
            ["commute"],
            ["rotate"],
            ["identity"],
        ],
    },
    # -- Leave-one-out --
    "leave_one_out": {
        "description": "All passes except one (measures marginal contribution)",
        "configs": [
            ["commute", "rotate", "identity"],   # no cancel
            ["cancel", "rotate", "identity"],     # no commute
            ["cancel", "commute", "identity"],    # no rotate
            ["cancel", "commute", "rotate"],      # no identity
        ],
    },
    # -- Ordering variants (all 4 passes, different orders) --
    "ordering": {
        "description": "All 4 passes in different orderings",
        "configs": [
            ["cancel", "commute", "rotate", "identity"],   # default
            ["identity", "rotate", "commute", "cancel"],   # reverse
            ["rotate", "cancel", "commute", "identity"],   # rotate-first
            ["commute", "cancel", "rotate", "identity"],   # commute-first
            ["identity", "cancel", "commute", "rotate"],   # identity-first
            ["cancel", "rotate", "commute", "identity"],   # swap middle two
        ],
    },
    # -- Cumulative build-up (add passes incrementally in default order) --
    "cumulative": {
        "description": "Incrementally adding passes (default order)",
        "configs": [
            [],                                            # no optimization (baseline)
            ["cancel"],
            ["cancel", "commute"],
            ["cancel", "commute", "rotate"],
            ["cancel", "commute", "rotate", "identity"],
        ],
    },
}


def _result_to_dict(result: EndToEndResult) -> dict[str, Any]:
    """Convert EndToEndResult to serializable dict."""
    return {
        "circuit_name": result.circuit_name,
        "process_fidelity": result.process_fidelity,
        "state_fidelity": result.state_fidelity,
        "input_gates": result.input_metrics.gates,
        "input_depth": result.input_metrics.depth,
        "input_qubits": result.input_metrics.qubits,
        "input_2q_gates": result.input_metrics.two_qubit_gates,
        "post_opt_gates": result.post_optimization.gates,
        "post_opt_depth": result.post_optimization.depth,
        "post_opt_2q_gates": result.post_optimization.two_qubit_gates,
        "pulse_duration_ns": result.pulse_metrics.total_duration_ns,
        "pulse_count": result.pulse_metrics.pulse_count,
    }


def run_ablation_group(
    pipeline: EndToEndPipeline,
    corpus: CircuitCorpus,
    group_name: str,
    configs: list[list[str]],
    description: str,
) -> ExperimentResults:
    """Run one group of ablation experiments."""
    logger.info(f"\n{'='*60}")
    logger.info(f"ABLATION: {group_name} — {description}")
    logger.info(f"  Configs: {len(configs)}, Circuits: {len(corpus)}")
    logger.info(f"{'='*60}")

    # Handle empty pass list (baseline) — use identity as pass-through
    effective_configs = []
    for cfg in configs:
        if len(cfg) == 0:
            effective_configs.append(["identity"])  # C++ requires at least 1 pass
        else:
            effective_configs.append(cfg)

    experiment = ExperimentConfig(
        name=f"ablation_{group_name}",
        description=description,
        passes_configs=effective_configs,
        topology="iqm-garnet",
        noise_params=DEFAULT_NOISE,
        route=True,
    )

    runner = BenchmarkRunner(pipeline, corpus)
    return runner.run(experiment)


def save_ablation_results(
    all_results: dict[str, ExperimentResults],
) -> Path:
    """Save all ablation results to a single JSON file."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = RESULTS_DIR / f"ablation_{timestamp}.json"

    data: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "groups": {},
    }

    for group_name, results in all_results.items():
        group_data = {
            "config": results.config.to_dict(),
            "start_time": results.start_time.isoformat(),
            "end_time": results.end_time.isoformat() if results.end_time else None,
            "success_count": results.success_count,
            "error_count": results.error_count,
            "total_duration_seconds": results.total_duration_seconds,
            "results": [
                {
                    "circuit_name": r.circuit_name,
                    "passes": r.passes,
                    "duration_seconds": r.duration_seconds,
                    "error": r.error,
                    "metrics": _result_to_dict(r.result) if r.result else None,
                }
                for r in results.results
            ],
        }
        data["groups"][group_name] = group_data

    # Compute summary statistics
    data["summary"] = compute_ablation_summary(all_results)

    with filepath.open("w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"All ablation results saved to {filepath}")
    return filepath


def compute_ablation_summary(
    all_results: dict[str, ExperimentResults],
) -> dict[str, Any]:
    """Compute summary statistics for the ablation study."""
    import numpy as np

    summary: dict[str, Any] = {}

    for group_name, results in all_results.items():
        group_summary: dict[str, Any] = {}

        # Group results by pass configuration
        by_config: dict[str, list] = {}
        for r in results.results:
            key = str(r.passes)
            by_config.setdefault(key, [])
            if r.result:
                by_config[key].append(r)

        for config_str, runs in by_config.items():
            if not runs:
                continue

            gate_reductions = []
            twoq_reductions = []
            fidelities = []

            for r in runs:
                m = r.result
                inp = m.input_metrics.gates
                out = m.post_optimization.gates
                if inp > 0:
                    gate_reductions.append(100.0 * (inp - out) / inp)

                inp_2q = m.input_metrics.two_qubit_gates
                out_2q = m.post_optimization.two_qubit_gates
                if inp_2q > 0:
                    twoq_reductions.append(100.0 * (inp_2q - out_2q) / inp_2q)

                fidelities.append(m.process_fidelity)

            group_summary[config_str] = {
                "n_circuits": len(runs),
                "gate_reduction_pct": {
                    "mean": float(np.mean(gate_reductions)) if gate_reductions else 0.0,
                    "std": float(np.std(gate_reductions)) if gate_reductions else 0.0,
                },
                "two_q_reduction_pct": {
                    "mean": float(np.mean(twoq_reductions)) if twoq_reductions else 0.0,
                    "std": float(np.std(twoq_reductions)) if twoq_reductions else 0.0,
                },
                "fidelity": {
                    "mean": float(np.mean(fidelities)) if fidelities else 0.0,
                    "std": float(np.std(fidelities)) if fidelities else 0.0,
                },
            }

        summary[group_name] = group_summary

    return summary


def print_ablation_summary(summary: dict[str, Any]) -> None:
    """Print formatted ablation summary."""
    print("\n" + "=" * 90)
    print("ABLATION STUDY RESULTS")
    print("=" * 90)

    for group_name, group_data in summary.items():
        print(f"\n--- {group_name.upper()} ---")
        print(f"{'Passes':<45} {'Gate%':>8} {'2Q%':>8} {'Fidelity':>10}")
        print("-" * 75)

        for config_str, stats in group_data.items():
            gr = stats["gate_reduction_pct"]
            tq = stats["two_q_reduction_pct"]
            fi = stats["fidelity"]
            # Shorten the config string for display
            display = config_str.replace("'", "").replace("[", "").replace("]", "")
            if len(display) > 43:
                display = display[:40] + "..."
            print(
                f"{display:<45} "
                f"{gr['mean']:>5.1f}±{gr['std']:<3.0f}"
                f"{tq['mean']:>5.1f}±{tq['std']:<3.0f}"
                f"{fi['mean']:>8.4f}±{fi['std']:<5.4f}"
            )


def main() -> None:
    """Run the formal ablation study."""
    parser = argparse.ArgumentParser(description="Formal Ablation Study")
    parser.add_argument("--quick", action="store_true", help="Small corpus (4 circuits)")
    parser.add_argument("--paper", action="store_true", help="Full 371-circuit corpus")
    parser.add_argument("--real", action="store_true", help="Use real C++ optimizer + Lindblad")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Select corpus
    if args.quick:
        logger.info("Using small corpus (4 circuits)")
        corpus = create_small_corpus()
    elif args.paper:
        logger.info("Using full 371-circuit paper corpus")
        corpus = create_paper_corpus()
    else:
        logger.info("Using standard corpus (19 circuits)")
        corpus = create_standard_corpus()

    logger.info(f"Corpus: {len(corpus)} circuits — {corpus.summary()}")

    # Create pipeline
    if args.real:
        pipeline = create_real_pipeline(
            noise_params=DEFAULT_NOISE, default_topology="iqm-garnet"
        )
    else:
        logger.warning("Using MOCK pipeline — pass --real for actual results")
        pipeline = EndToEndPipeline(
            optimizer_bridge=MockCircuitOptimizerBridge(),
            noise_params=DEFAULT_NOISE,
            gate_compiler=MockGateCompiler(),
            default_topology="iqm-garnet",
        )

    # Run all ablation groups
    all_results: dict[str, ExperimentResults] = {}
    t0 = time.time()

    for group_name, group_info in ABLATION_CONFIGS.items():
        results = run_ablation_group(
            pipeline=pipeline,
            corpus=corpus,
            group_name=group_name,
            configs=group_info["configs"],
            description=group_info["description"],
        )
        all_results[group_name] = results

    total_time = time.time() - t0

    # Save and print
    filepath = save_ablation_results(all_results)
    summary = compute_ablation_summary(all_results)
    print_ablation_summary(summary)

    total_runs = sum(r.success_count + r.error_count for r in all_results.values())
    total_errors = sum(r.error_count for r in all_results.values())
    print(f"\nTotal: {total_runs} runs, {total_errors} errors, {total_time:.1f}s")
    print(f"Results: {filepath}")


if __name__ == "__main__":
    main()
