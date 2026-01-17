#!/usr/bin/env python3
"""Experimental Campaign Runner for QCO-Integration.

This script executes the full experimental campaign as defined in
SCOPE_OF_WORK.md Phase 3 (Experimental Campaign):

1. Baseline - No optimization, direct pulse compilation
2. Per-pass analysis - Each optimization pass individually
3. Pass combinations - Ordered combinations of passes
4. Routing impact - Pre/post routing fidelity comparison
5. Noise sensitivity - Vary T1/T2 parameters
6. Scaling analysis - Circuit size vs fidelity degradation

Results are saved to experiments/results/ and figures to experiments/figures/.

Usage:
    python experiments/run_campaign.py [--experiments EXP1,EXP2,...] [--quick]

    --experiments: Comma-separated list of experiments to run (default: all)
    --quick: Run with smaller circuit corpus for testing
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis import (  # noqa: E402
    format_summary_report,
    generate_experiment_summary,
)
from src.bridge import MockCircuitOptimizerBridge  # noqa: E402
from src.corpus import CircuitCorpus, create_small_corpus, create_standard_corpus  # noqa: E402
from src.metrics import EndToEndResult, NoiseParams  # noqa: E402
from src.pipeline import EndToEndPipeline, MockGateCompiler, create_real_pipeline  # noqa: E402
from src.runner import BenchmarkRunner, ExperimentConfig, ExperimentResults  # noqa: E402
from src.visualization import (  # noqa: E402
    generate_architecture_diagram,
    plot_comparison_bar_chart,
    plot_fidelity_waterfall,
    plot_pass_effectiveness,
    plot_scaling_analysis,
    set_publication_style,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Output directories
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
FIGURES_DIR = PROJECT_ROOT / "experiments" / "figures"
REPORTS_DIR = PROJECT_ROOT / "experiments" / "reports"

# IQM Garnet default noise parameters (from arXiv:2408.12433)
DEFAULT_NOISE = NoiseParams(
    t1_ns=37000.0,
    t2_ns=9600.0,
    single_qubit_error=0.001,
    two_qubit_error=0.006,
)

# Available optimization passes
ALL_PASSES = ["cancel", "commute", "rotate", "identity"]


def setup_directories() -> None:
    """Create output directories if they don't exist."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def create_pipeline(use_real: bool = False) -> EndToEndPipeline:
    """Create the end-to-end pipeline.

    Args:
        use_real: If True, use real C++ optimizer and pulse simulation.
                  If False, use mock components for testing.

    Returns:
        Configured EndToEndPipeline instance.
    """
    if use_real:
        logger.info("Using REAL pipeline (C++ optimizer + Lindblad pulse simulation)")
        return create_real_pipeline(noise_params=DEFAULT_NOISE, default_topology="iqm-garnet")
    else:
        logger.info("Using MOCK pipeline (for testing)")
        return EndToEndPipeline(
            optimizer_bridge=MockCircuitOptimizerBridge(),
            noise_params=DEFAULT_NOISE,
            gate_compiler=MockGateCompiler(),
            default_topology="iqm-garnet",
        )


def save_results(
    results: ExperimentResults,
    experiment_name: str,
) -> Path:
    """Save experiment results to JSON."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{experiment_name}_{timestamp}.json"
    filepath = RESULTS_DIR / filename

    # Convert to serializable format
    data = {
        "experiment_name": experiment_name,
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

    with filepath.open("w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Results saved to {filepath}")
    return filepath


def _result_to_dict(result: EndToEndResult) -> dict[str, Any]:
    """Convert EndToEndResult to serializable dict."""
    return {
        "circuit_name": result.circuit_name,
        "process_fidelity": result.process_fidelity,
        "state_fidelity": result.state_fidelity,
        "input_gates": result.input_metrics.gates,
        "input_depth": result.input_metrics.depth,
        "input_qubits": result.input_metrics.qubits,
        "post_opt_gates": result.post_optimization.gates,
        "post_opt_depth": result.post_optimization.depth,
        "pulse_duration_ns": result.pulse_metrics.total_duration_ns,
        "pulse_count": result.pulse_metrics.pulse_count,
    }


# =============================================================================
# Experiment Definitions
# =============================================================================


def run_baseline(
    pipeline: EndToEndPipeline,
    corpus: CircuitCorpus,
) -> ExperimentResults:
    """Experiment 1: Baseline - no optimization.

    Run circuits with minimal optimization (identity pass only) to establish baseline.
    Note: We use 'identity' pass since the C++ optimizer requires at least one pass.
    """
    logger.info("=" * 60)
    logger.info("EXPERIMENT 1: Baseline (identity pass only)")
    logger.info("=" * 60)

    config = ExperimentConfig(
        name="baseline",
        description="Identity pass only - baseline fidelity measurement",
        passes_configs=[["identity"]],  # Use identity pass as baseline
        topology="iqm-garnet",
        noise_params=DEFAULT_NOISE,
        route=True,
    )

    runner = BenchmarkRunner(pipeline, corpus)
    return runner.run(config)


def run_per_pass_analysis(
    pipeline: EndToEndPipeline,
    corpus: CircuitCorpus,
) -> ExperimentResults:
    """Experiment 2: Per-pass analysis.

    Run each optimization pass individually to measure its effectiveness.
    """
    logger.info("=" * 60)
    logger.info("EXPERIMENT 2: Per-pass analysis")
    logger.info("=" * 60)

    config = ExperimentConfig(
        name="per_pass",
        description="Each optimization pass run individually",
        passes_configs=[[p] for p in ALL_PASSES],
        topology="iqm-garnet",
        noise_params=DEFAULT_NOISE,
        route=True,
    )

    runner = BenchmarkRunner(pipeline, corpus)
    return runner.run(config)


def run_pass_combinations(
    pipeline: EndToEndPipeline,
    corpus: CircuitCorpus,
) -> ExperimentResults:
    """Experiment 3: Pass combinations.

    Test various combinations of passes to find optimal orderings.
    """
    logger.info("=" * 60)
    logger.info("EXPERIMENT 3: Pass combinations")
    logger.info("=" * 60)

    # Key combinations to test
    combinations = [
        ["cancel"],
        ["cancel", "commute"],
        ["commute", "cancel"],
        ["cancel", "commute", "rotate"],
        ["cancel", "commute", "rotate", "identity"],
        ["rotate", "cancel", "commute"],
        ["commute", "rotate", "cancel"],
    ]

    config = ExperimentConfig(
        name="pass_combinations",
        description="Various pass orderings to find optimal combinations",
        passes_configs=combinations,
        topology="iqm-garnet",
        noise_params=DEFAULT_NOISE,
        route=True,
    )

    runner = BenchmarkRunner(pipeline, corpus)
    return runner.run(config)


def run_routing_impact(
    pipeline: EndToEndPipeline,
    corpus: CircuitCorpus,
) -> tuple[ExperimentResults, ExperimentResults]:
    """Experiment 4: Routing impact analysis.

    Compare fidelity with and without routing to measure SWAP overhead.
    """
    logger.info("=" * 60)
    logger.info("EXPERIMENT 4: Routing impact analysis")
    logger.info("=" * 60)

    best_passes = ["cancel", "commute", "rotate"]

    # Without routing
    config_no_route = ExperimentConfig(
        name="routing_impact_no_route",
        description="Optimization without routing",
        passes_configs=[best_passes],
        topology="iqm-garnet",
        noise_params=DEFAULT_NOISE,
        route=False,
    )

    # With routing
    config_with_route = ExperimentConfig(
        name="routing_impact_with_route",
        description="Optimization with routing",
        passes_configs=[best_passes],
        topology="iqm-garnet",
        noise_params=DEFAULT_NOISE,
        route=True,
    )

    runner = BenchmarkRunner(pipeline, corpus)
    results_no_route = runner.run(config_no_route)
    results_with_route = runner.run(config_with_route)

    return results_no_route, results_with_route


def run_noise_sensitivity(
    pipeline: EndToEndPipeline,
    corpus: CircuitCorpus,
) -> list[ExperimentResults]:
    """Experiment 5: Noise sensitivity analysis.

    Vary T1/T2 parameters to see how optimization benefits scale with noise.
    """
    logger.info("=" * 60)
    logger.info("EXPERIMENT 5: Noise sensitivity analysis")
    logger.info("=" * 60)

    best_passes = ["cancel", "commute", "rotate"]

    # Noise parameter variations
    noise_configs = [
        ("low_noise", NoiseParams(t1_ns=100000.0, t2_ns=50000.0, single_qubit_error=0.0005, two_qubit_error=0.003)),
        ("medium_noise", DEFAULT_NOISE),
        ("high_noise", NoiseParams(t1_ns=20000.0, t2_ns=5000.0, single_qubit_error=0.002, two_qubit_error=0.012)),
        ("very_high_noise", NoiseParams(t1_ns=10000.0, t2_ns=2500.0, single_qubit_error=0.005, two_qubit_error=0.025)),
    ]

    results_list = []
    runner = BenchmarkRunner(pipeline, corpus)

    for noise_name, noise_params in noise_configs:
        config = ExperimentConfig(
            name=f"noise_sensitivity_{noise_name}",
            description=f"Noise sensitivity test with {noise_name} parameters",
            passes_configs=[best_passes],
            topology="iqm-garnet",
            noise_params=noise_params,
            route=True,
        )
        results_list.append(runner.run(config))

    return results_list


def run_scaling_analysis(
    pipeline: EndToEndPipeline,
) -> ExperimentResults:
    """Experiment 6: Scaling analysis.

    Measure fidelity vs circuit size (qubits and depth).
    Uses a specialized corpus with varied sizes.
    """
    logger.info("=" * 60)
    logger.info("EXPERIMENT 6: Scaling analysis")
    logger.info("=" * 60)

    # Create corpus with varied sizes for scaling analysis
    corpus = CircuitCorpus()

    # GHZ at various sizes
    corpus.add_ghz_circuits([2, 3, 4, 5, 6, 8, 10, 12])

    # QFT at various sizes
    corpus.add_qft_circuits([2, 3, 4, 5, 6, 8])

    # Random circuits with varied depth
    for depth in [5, 10, 15, 20, 30]:
        corpus.add_random_circuits(
            qubit_counts=[4, 6, 8],
            depths=[depth],
            seed=42 + depth,
        )

    best_passes = ["cancel", "commute", "rotate"]

    config = ExperimentConfig(
        name="scaling_analysis",
        description="Fidelity vs circuit size analysis",
        passes_configs=[best_passes],
        topology="iqm-garnet",
        noise_params=DEFAULT_NOISE,
        route=True,
    )

    runner = BenchmarkRunner(pipeline, corpus)
    return runner.run(config)


# =============================================================================
# Visualization and Reporting
# =============================================================================


def generate_figures(all_results: dict[str, Any]) -> None:
    """Generate publication figures from experiment results."""
    logger.info("Generating publication figures...")
    set_publication_style()

    # Collect all successful results for aggregate analysis
    all_end_to_end: list[EndToEndResult] = []
    for _exp_name, exp_results in all_results.items():
        if isinstance(exp_results, ExperimentResults):
            all_end_to_end.extend(exp_results.successful_results())
        elif isinstance(exp_results, (tuple, list)):
            for r in exp_results:
                all_end_to_end.extend(r.successful_results())

    if not all_end_to_end:
        logger.warning("No successful results to generate figures from")
        return

    # 1. Architecture diagram
    generate_architecture_diagram(save_path=FIGURES_DIR / "architecture.pdf")
    logger.info("  - architecture.pdf")

    # 2. Fidelity waterfall
    plot_fidelity_waterfall(
        all_end_to_end,
        title="End-to-End Pipeline Fidelity Breakdown",
        save_path=FIGURES_DIR / "fidelity_waterfall.pdf",
    )
    logger.info("  - fidelity_waterfall.pdf")

    # 3. Pass effectiveness
    plot_pass_effectiveness(
        all_end_to_end,
        metric="net_gate_reduction",
        save_path=FIGURES_DIR / "pass_effectiveness.pdf",
    )
    logger.info("  - pass_effectiveness.pdf")

    # 4. Scaling analysis (qubits) - skip if not enough data points
    try:
        plot_scaling_analysis(
            all_end_to_end,
            x_axis="input_qubits",
            y_axis="process_fidelity",
            group_by="circuit_type",
            save_path=FIGURES_DIR / "scaling_qubits.pdf",
        )
        logger.info("  - scaling_qubits.pdf")
    except ValueError as e:
        logger.warning(f"  - scaling_qubits.pdf skipped: {e}")

    # 5. Scaling analysis (depth) - skip if not enough data points
    try:
        plot_scaling_analysis(
            all_end_to_end,
            x_axis="input_depth",
            y_axis="process_fidelity",
            save_path=FIGURES_DIR / "scaling_depth.pdf",
        )
        logger.info("  - scaling_depth.pdf")
    except ValueError as e:
        logger.warning(f"  - scaling_depth.pdf skipped: {e}")

    # 6. Comparison bar chart if we have baseline vs optimized
    if "baseline" in all_results and "pass_combinations" in all_results:
        baseline_results = all_results["baseline"].successful_results()
        optimized_results = all_results["pass_combinations"].successful_results()

        if baseline_results and optimized_results:
            # Extract fidelity values for comparison
            labels = [r.circuit_name for r in baseline_results[:10]]  # Limit to 10
            baseline_fidelities = [r.process_fidelity for r in baseline_results[:10]]
            optimized_fidelities = [r.process_fidelity for r in optimized_results[:10]]

            plot_comparison_bar_chart(
                labels=labels,
                baseline_values=baseline_fidelities,
                optimized_values=optimized_fidelities,
                metric_name="Process Fidelity",
                save_path=FIGURES_DIR / "baseline_vs_optimized.pdf",
            )
            logger.info("  - baseline_vs_optimized.pdf")


def generate_report(all_results: dict[str, Any]) -> None:
    """Generate summary report from all experiment results."""
    logger.info("Generating experiment report...")

    # Collect all successful results
    all_end_to_end: list[EndToEndResult] = []
    for _exp_name, exp_results in all_results.items():
        if isinstance(exp_results, ExperimentResults):
            all_end_to_end.extend(exp_results.successful_results())
        elif isinstance(exp_results, (tuple, list)):
            for r in exp_results:
                all_end_to_end.extend(r.successful_results())

    if not all_end_to_end:
        logger.warning("No successful results to generate report from")
        return

    # Generate summary
    summary = generate_experiment_summary(all_end_to_end)
    report = format_summary_report(summary)

    # Save report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"experiment_summary_{timestamp}.txt"
    with report_path.open("w") as f:
        f.write(report)

    logger.info(f"Report saved to {report_path}")
    print("\n" + report)


# =============================================================================
# Main Entry Point
# =============================================================================


def main() -> None:
    """Run the experimental campaign."""
    parser = argparse.ArgumentParser(
        description="Run QCO-Integration experimental campaign"
    )
    parser.add_argument(
        "--experiments",
        type=str,
        default="all",
        help="Comma-separated list of experiments (baseline,per_pass,combinations,routing,noise,scaling)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use small corpus for quick testing",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Use real C++ optimizer and Lindblad pulse simulation (default: mock)",
    )
    args = parser.parse_args()

    # Setup
    setup_directories()
    pipeline = create_pipeline(use_real=args.real)

    # Create corpus
    if args.quick:
        logger.info("Using small corpus for quick testing")
        corpus = create_small_corpus()
    else:
        logger.info("Using standard corpus")
        corpus = create_standard_corpus()

    logger.info(f"Corpus: {corpus.summary()}")

    # Determine which experiments to run
    if args.experiments == "all":
        experiments_to_run = ["baseline", "per_pass", "combinations", "routing", "noise", "scaling"]
    else:
        experiments_to_run = [e.strip() for e in args.experiments.split(",")]

    # Run experiments
    all_results: dict[str, Any] = {}

    if "baseline" in experiments_to_run:
        results = run_baseline(pipeline, corpus)
        save_results(results, "baseline")
        all_results["baseline"] = results

    if "per_pass" in experiments_to_run:
        results = run_per_pass_analysis(pipeline, corpus)
        save_results(results, "per_pass")
        all_results["per_pass"] = results

    if "combinations" in experiments_to_run:
        results = run_pass_combinations(pipeline, corpus)
        save_results(results, "pass_combinations")
        all_results["pass_combinations"] = results

    if "routing" in experiments_to_run:
        no_route, with_route = run_routing_impact(pipeline, corpus)
        save_results(no_route, "routing_no_route")
        save_results(with_route, "routing_with_route")
        all_results["routing"] = (no_route, with_route)

    if "noise" in experiments_to_run:
        noise_results = run_noise_sensitivity(pipeline, corpus)
        for i, nr in enumerate(noise_results):
            save_results(nr, f"noise_{i}")
        all_results["noise"] = noise_results

    if "scaling" in experiments_to_run:
        results = run_scaling_analysis(pipeline)
        save_results(results, "scaling")
        all_results["scaling"] = results

    # Generate figures and report
    if all_results:
        generate_figures(all_results)
        generate_report(all_results)

    logger.info("=" * 60)
    logger.info("Experimental campaign complete!")
    logger.info(f"Results: {RESULTS_DIR}")
    logger.info(f"Figures: {FIGURES_DIR}")
    logger.info(f"Reports: {REPORTS_DIR}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
