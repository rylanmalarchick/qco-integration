"""Statistical analysis for fidelity and optimization metrics.

This module provides analysis utilities for experimental results,
including aggregation, statistical summaries, pass effectiveness
analysis, and scaling behavior characterization. Functions are pure where
possible and raise ValueError on empty or mismatched inputs.
"""

from __future__ import annotations

import contextlib
import math
import statistics
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from src.metrics import EndToEndResult, PassMetrics

# =============================================================================
# Metric Extraction Registry
# =============================================================================

# Dictionary mapping metric names to extractor functions.
# Defined at module level to keep extract_metric() concise.
_METRIC_EXTRACTORS: dict[str, Callable[[EndToEndResult], float]] = {
    # Fidelity metrics
    "process_fidelity": lambda r: r.process_fidelity,
    "state_fidelity": lambda r: r.state_fidelity,
    # Input metrics
    "input_gates": lambda r: float(r.input_metrics.gates),
    "input_depth": lambda r: float(r.input_metrics.depth),
    "input_qubits": lambda r: float(r.input_metrics.qubits),
    "input_2q_gates": lambda r: float(r.input_metrics.two_qubit_gates),
    # Post-optimization metrics
    "post_opt_gates": lambda r: float(r.post_optimization.gates),
    "post_opt_depth": lambda r: float(r.post_optimization.depth),
    "post_opt_2q_gates": lambda r: float(r.post_optimization.two_qubit_gates),
    # Derived metrics
    "gate_reduction": lambda r: float(
        r.input_metrics.gates - r.post_optimization.gates
    ),
    "gate_reduction_pct": lambda r: (
        100.0 * (r.input_metrics.gates - r.post_optimization.gates)
        / r.input_metrics.gates
        if r.input_metrics.gates > 0
        else 0.0
    ),
    "depth_reduction": lambda r: float(
        r.input_metrics.depth - r.post_optimization.depth
    ),
    "depth_reduction_pct": lambda r: (
        100.0 * (r.input_metrics.depth - r.post_optimization.depth)
        / r.input_metrics.depth
        if r.input_metrics.depth > 0
        else 0.0
    ),
    # Pulse metrics
    "pulse_duration_ns": lambda r: r.pulse_metrics.total_duration_ns,
    "pulse_count": lambda r: float(r.pulse_metrics.pulse_count),
    # Routing metrics (0 if no routing)
    "swaps_inserted": lambda r: (
        float(r.routing_metrics.swaps_inserted) if r.routing_metrics else 0.0
    ),
    "routing_depth_increase": lambda r: (
        float(r.routing_metrics.depth_increase) if r.routing_metrics else 0.0
    ),
}


def get_available_metrics() -> list[str]:
    """Return list of available metric names for extraction."""
    return sorted(_METRIC_EXTRACTORS.keys())


# =============================================================================
# Statistical Summary Types
# =============================================================================


@dataclass(frozen=True)
class DescriptiveStats:
    """Descriptive statistics for a numeric variable.

    Attributes:
        count: Number of observations.
        mean: Arithmetic mean.
        std: Standard deviation (sample).
        min: Minimum value.
        max: Maximum value.
        median: Median value.
        q1: First quartile (25th percentile).
        q3: Third quartile (75th percentile).
    """

    count: int
    mean: float
    std: float
    min: float
    max: float
    median: float
    q1: float
    q3: float

    @property
    def iqr(self) -> float:
        """Interquartile range (Q3 - Q1)."""
        return self.q3 - self.q1

    @property
    def cv(self) -> float:
        """Coefficient of variation (std/mean)."""
        if self.mean == 0:
            return float("inf") if self.std > 0 else 0.0
        return self.std / abs(self.mean)


@dataclass(frozen=True)
class PassEffectiveness:
    """Effectiveness metrics for a single optimization pass.

    Attributes:
        pass_name: Name of the optimization pass.
        total_gates_removed: Total gates removed across all circuits.
        total_gates_added: Total gates added across all circuits.
        net_gate_reduction: Net reduction (removed - added).
        avg_gates_removed: Average gates removed per circuit.
        avg_depth_reduction: Average depth reduction per circuit.
        avg_2q_gate_reduction: Average 2-qubit gate reduction per circuit.
        circuits_improved: Number of circuits where this pass helped.
        circuits_total: Total circuits this pass was applied to.
        improvement_rate: Fraction of circuits improved.
    """

    pass_name: str
    total_gates_removed: int
    total_gates_added: int
    net_gate_reduction: int
    avg_gates_removed: float
    avg_depth_reduction: float
    avg_2q_gate_reduction: float
    circuits_improved: int
    circuits_total: int

    @property
    def improvement_rate(self) -> float:
        """Fraction of circuits where this pass improved the circuit."""
        if self.circuits_total == 0:
            return 0.0
        return self.circuits_improved / self.circuits_total


@dataclass
class ScalingAnalysisResult:
    """Results from scaling analysis.

    Attributes:
        x_variable: Name of the independent variable.
        y_variable: Name of the dependent variable.
        data_points: List of (x, y) tuples.
        correlation: Pearson correlation coefficient.
        slope: Linear regression slope.
        intercept: Linear regression intercept.
        r_squared: Coefficient of determination.
    """

    x_variable: str
    y_variable: str
    data_points: list[tuple[float, float]] = field(default_factory=list)
    correlation: float = 0.0
    slope: float = 0.0
    intercept: float = 0.0
    r_squared: float = 0.0


@dataclass
class ComparisonResult:
    """Result from comparing two configurations.

    Attributes:
        config_a: Name/description of first configuration.
        config_b: Name/description of second configuration.
        metric: Metric being compared.
        stats_a: Descriptive statistics for config A.
        stats_b: Descriptive statistics for config B.
        mean_difference: Difference in means (B - A).
        percent_change: Percentage change ((B - A) / A * 100).
        effect_size: Cohen's d effect size.
    """

    config_a: str
    config_b: str
    metric: str
    stats_a: DescriptiveStats
    stats_b: DescriptiveStats
    mean_difference: float
    percent_change: float
    effect_size: float


# =============================================================================
# Core Statistical Functions
# =============================================================================


def compute_descriptive_stats(values: Sequence[float]) -> DescriptiveStats:
    """Compute descriptive statistics for a sequence of values.

    Args:
        values: Sequence of numeric values.

    Returns:
        DescriptiveStats with all computed statistics.

    Raises:
        ValueError: If values is empty.
    """
    if not values:
        raise ValueError("Cannot compute statistics for empty sequence")

    sorted_values = sorted(values)
    n = len(sorted_values)

    mean_val = statistics.mean(sorted_values)
    std_val = statistics.stdev(sorted_values) if n > 1 else 0.0
    median_val = statistics.median(sorted_values)

    # Compute quartiles
    if n == 1:
        q1 = q3 = sorted_values[0]
    elif n == 2:
        q1 = sorted_values[0]
        q3 = sorted_values[1]
    else:
        # Use linear interpolation for quartiles
        q1_idx = (n - 1) * 0.25
        q3_idx = (n - 1) * 0.75

        q1_low = int(math.floor(q1_idx))
        q1_high = int(math.ceil(q1_idx))
        q1_frac = q1_idx - q1_low

        q3_low = int(math.floor(q3_idx))
        q3_high = int(math.ceil(q3_idx))
        q3_frac = q3_idx - q3_low

        q1 = sorted_values[q1_low] * (1 - q1_frac) + sorted_values[q1_high] * q1_frac
        q3 = sorted_values[q3_low] * (1 - q3_frac) + sorted_values[q3_high] * q3_frac

    return DescriptiveStats(
        count=n,
        mean=mean_val,
        std=std_val,
        min=sorted_values[0],
        max=sorted_values[-1],
        median=median_val,
        q1=q1,
        q3=q3,
    )


def compute_correlation(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Pearson correlation coefficient.

    Args:
        x: First variable values.
        y: Second variable values.

    Returns:
        Pearson correlation coefficient in [-1, 1].

    Raises:
        ValueError: If sequences have different lengths or are too short.
    """
    if len(x) != len(y):
        raise ValueError(f"Sequences must have same length: {len(x)} != {len(y)}")
    if len(x) < 2:
        raise ValueError("Need at least 2 data points for correlation")

    n = len(x)
    mean_x = statistics.mean(x)
    mean_y = statistics.mean(y)

    # Compute covariance and standard deviations
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y, strict=True)) / (n - 1)
    std_x = statistics.stdev(x)
    std_y = statistics.stdev(y)

    if std_x == 0 or std_y == 0:
        return 0.0

    return cov / (std_x * std_y)


def compute_linear_regression(
    x: Sequence[float], y: Sequence[float]
) -> tuple[float, float, float]:
    """Compute simple linear regression.

    Args:
        x: Independent variable values.
        y: Dependent variable values.

    Returns:
        Tuple of (slope, intercept, r_squared).

    Raises:
        ValueError: If sequences have different lengths or are too short.
    """
    if len(x) != len(y):
        raise ValueError(f"Sequences must have same length: {len(x)} != {len(y)}")
    if len(x) < 2:
        raise ValueError("Need at least 2 data points for regression")

    mean_x = statistics.mean(x)
    mean_y = statistics.mean(y)

    # Compute slope
    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y, strict=True))
    denominator = sum((xi - mean_x) ** 2 for xi in x)

    if denominator == 0:
        return 0.0, mean_y, 0.0

    slope = numerator / denominator
    intercept = mean_y - slope * mean_x

    # Compute R-squared
    ss_tot = sum((yi - mean_y) ** 2 for yi in y)
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y, strict=True))

    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

    return slope, intercept, r_squared


def compute_cohens_d(
    group1: Sequence[float], group2: Sequence[float]
) -> float:
    """Compute Cohen's d effect size.

    Args:
        group1: First group values.
        group2: Second group values.

    Returns:
        Cohen's d effect size.

    Raises:
        ValueError: If either group is empty.
    """
    if not group1 or not group2:
        raise ValueError("Both groups must be non-empty")

    n1, n2 = len(group1), len(group2)
    mean1 = statistics.mean(group1)
    mean2 = statistics.mean(group2)

    # Pooled standard deviation
    var1 = statistics.variance(group1) if n1 > 1 else 0.0
    var2 = statistics.variance(group2) if n2 > 1 else 0.0

    pooled_std = math.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))

    if pooled_std == 0:
        return 0.0

    return (mean2 - mean1) / pooled_std


# =============================================================================
# Result Analysis Functions
# =============================================================================


def extract_metric(
    result: EndToEndResult,
    metric: str,
) -> float:
    """Extract a numeric metric value from an EndToEndResult.

    Uses the module-level _METRIC_EXTRACTORS registry to look up
    the appropriate extractor function for the given metric name.

    Args:
        result: The result to extract from.
        metric: Name of the metric to extract. Use get_available_metrics()
            to see all valid metric names.

    Returns:
        The numeric value of the metric.

    Raises:
        ValueError: If metric name is not recognized.
    """
    if metric not in _METRIC_EXTRACTORS:
        raise ValueError(
            f"Unknown metric: {metric}. "
            f"Available: {get_available_metrics()}"
        )

    return _METRIC_EXTRACTORS[metric](result)


def analyze_results(
    results: Sequence[EndToEndResult],
    metric: str = "process_fidelity",
) -> DescriptiveStats:
    """Compute descriptive statistics for a metric across results.

    Args:
        results: Sequence of EndToEndResults.
        metric: Name of metric to analyze.

    Returns:
        DescriptiveStats for the specified metric.

    Raises:
        ValueError: If results is empty or metric is unknown.
    """
    if not results:
        raise ValueError("Cannot analyze empty results")

    values = [extract_metric(r, metric) for r in results]
    return compute_descriptive_stats(values)


def analyze_by_group(
    results: Sequence[EndToEndResult],
    group_by: Callable[[EndToEndResult], str],
    metric: str = "process_fidelity",
) -> dict[str, DescriptiveStats]:
    """Analyze results grouped by a custom key.

    Args:
        results: Sequence of EndToEndResults.
        group_by: Function that extracts group key from result.
        metric: Metric to analyze within each group.

    Returns:
        Dictionary mapping group key to DescriptiveStats.

    Raises:
        ValueError: If results is empty.
    """
    if not results:
        raise ValueError("Cannot analyze empty results")

    groups: dict[str, list[float]] = defaultdict(list)
    for result in results:
        key = group_by(result)
        value = extract_metric(result, metric)
        groups[key].append(value)

    return {key: compute_descriptive_stats(values) for key, values in groups.items()}


def analyze_by_circuit_type(
    results: Sequence[EndToEndResult],
    metric: str = "process_fidelity",
) -> dict[str, DescriptiveStats]:
    """Analyze results grouped by circuit type (parsed from circuit_name).

    Assumes circuit names follow the pattern "type_params" (e.g., "ghz_4", "qft_8").

    Args:
        results: Sequence of EndToEndResults.
        metric: Metric to analyze.

    Returns:
        Dictionary mapping circuit type to DescriptiveStats.
    """

    def extract_type(result: EndToEndResult) -> str:
        """Extract circuit type from circuit name (e.g., 'ghz' from 'ghz_4')."""
        name = result.circuit_name
        # Extract type from patterns like "ghz_4", "qft_8_routed", etc.
        parts = name.split("_")
        return parts[0] if parts else "unknown"

    return analyze_by_group(results, extract_type, metric)


def analyze_by_qubit_count(
    results: Sequence[EndToEndResult],
    metric: str = "process_fidelity",
) -> dict[int, DescriptiveStats]:
    """Analyze results grouped by qubit count.

    Args:
        results: Sequence of EndToEndResults.
        metric: Metric to analyze.

    Returns:
        Dictionary mapping qubit count to DescriptiveStats.
    """
    if not results:
        raise ValueError("Cannot analyze empty results")

    groups: dict[int, list[float]] = defaultdict(list)
    for result in results:
        qubits = result.input_metrics.qubits
        value = extract_metric(result, metric)
        groups[qubits].append(value)

    return {qubits: compute_descriptive_stats(values) for qubits, values in groups.items()}


# =============================================================================
# Pass Effectiveness Analysis
# =============================================================================


def analyze_pass_effectiveness(
    results: Sequence[EndToEndResult],
) -> dict[str, PassEffectiveness]:
    """Analyze effectiveness of each optimization pass.

    Aggregates metrics across all results to determine how effective
    each optimization pass is at reducing gates and depth.

    Args:
        results: Sequence of EndToEndResults.

    Returns:
        Dictionary mapping pass name to PassEffectiveness.

    Raises:
        ValueError: If results is empty.
    """
    if not results:
        raise ValueError("Cannot analyze empty results")

    # Aggregate pass metrics
    pass_data: dict[str, list[PassMetrics]] = defaultdict(list)

    for result in results:
        for pass_metrics in result.optimization_passes:
            pass_data[pass_metrics.name].append(pass_metrics)

    effectiveness: dict[str, PassEffectiveness] = {}

    for pass_name, metrics_list in pass_data.items():
        total_removed = sum(m.gates_removed for m in metrics_list)
        total_added = sum(m.gates_added for m in metrics_list)

        gate_reductions = [m.gates_removed - m.gates_added for m in metrics_list]
        depth_reductions = [
            m.input_metrics.depth - m.output_metrics.depth for m in metrics_list
        ]
        twoq_reductions = [
            m.input_metrics.two_qubit_gates - m.output_metrics.two_qubit_gates
            for m in metrics_list
        ]

        circuits_improved = sum(1 for r in gate_reductions if r > 0)

        effectiveness[pass_name] = PassEffectiveness(
            pass_name=pass_name,
            total_gates_removed=total_removed,
            total_gates_added=total_added,
            net_gate_reduction=total_removed - total_added,
            avg_gates_removed=statistics.mean(gate_reductions) if gate_reductions else 0.0,
            avg_depth_reduction=statistics.mean(depth_reductions) if depth_reductions else 0.0,
            avg_2q_gate_reduction=statistics.mean(twoq_reductions) if twoq_reductions else 0.0,
            circuits_improved=circuits_improved,
            circuits_total=len(metrics_list),
        )

    return effectiveness


def rank_passes_by_effectiveness(
    results: Sequence[EndToEndResult],
    metric: str = "net_gate_reduction",
) -> list[tuple[str, float]]:
    """Rank optimization passes by effectiveness.

    Args:
        results: Sequence of EndToEndResults.
        metric: Metric to rank by (attribute of PassEffectiveness).

    Returns:
        List of (pass_name, metric_value) sorted by effectiveness descending.
    """
    effectiveness = analyze_pass_effectiveness(results)

    ranked = []
    for name, eff in effectiveness.items():
        value = getattr(eff, metric, 0.0)
        ranked.append((name, value))

    return sorted(ranked, key=lambda x: x[1], reverse=True)


# =============================================================================
# Scaling Analysis
# =============================================================================


def analyze_scaling(
    results: Sequence[EndToEndResult],
    x_variable: str = "input_qubits",
    y_variable: str = "process_fidelity",
) -> ScalingAnalysisResult:
    """Analyze how a metric scales with circuit size.

    Args:
        results: Sequence of EndToEndResults.
        x_variable: Independent variable (metric name).
        y_variable: Dependent variable (metric name).

    Returns:
        ScalingAnalysisResult with correlation and regression.

    Raises:
        ValueError: If results is empty or has fewer than 2 points.
    """
    if not results:
        raise ValueError("Cannot analyze empty results")
    if len(results) < 2:
        raise ValueError("Need at least 2 data points for scaling analysis")

    x_values = [extract_metric(r, x_variable) for r in results]
    y_values = [extract_metric(r, y_variable) for r in results]

    correlation = compute_correlation(x_values, y_values)
    slope, intercept, r_squared = compute_linear_regression(x_values, y_values)

    return ScalingAnalysisResult(
        x_variable=x_variable,
        y_variable=y_variable,
        data_points=list(zip(x_values, y_values, strict=True)),
        correlation=correlation,
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
    )


def analyze_fidelity_scaling(
    results: Sequence[EndToEndResult],
) -> dict[str, ScalingAnalysisResult]:
    """Analyze how fidelity scales with various circuit properties.

    Args:
        results: Sequence of EndToEndResults.

    Returns:
        Dictionary with scaling analysis for different x-variables.
    """
    x_variables = [
        "input_qubits",
        "input_gates",
        "input_depth",
        "input_2q_gates",
        "pulse_duration_ns",
    ]

    scaling_results = {}
    for x_var in x_variables:
        with contextlib.suppress(ValueError):
            scaling_results[x_var] = analyze_scaling(
                results, x_variable=x_var, y_variable="process_fidelity"
            )

    return scaling_results


# =============================================================================
# Comparison Analysis
# =============================================================================


def compare_configurations(
    results_a: Sequence[EndToEndResult],
    results_b: Sequence[EndToEndResult],
    config_a_name: str,
    config_b_name: str,
    metric: str = "process_fidelity",
) -> ComparisonResult:
    """Compare two configurations on a given metric.

    Args:
        results_a: Results from configuration A.
        results_b: Results from configuration B.
        config_a_name: Name for configuration A.
        config_b_name: Name for configuration B.
        metric: Metric to compare.

    Returns:
        ComparisonResult with statistical comparison.

    Raises:
        ValueError: If either results set is empty.
    """
    if not results_a or not results_b:
        raise ValueError("Both result sets must be non-empty")

    values_a = [extract_metric(r, metric) for r in results_a]
    values_b = [extract_metric(r, metric) for r in results_b]

    stats_a = compute_descriptive_stats(values_a)
    stats_b = compute_descriptive_stats(values_b)

    mean_diff = stats_b.mean - stats_a.mean
    pct_change = (mean_diff / stats_a.mean * 100) if stats_a.mean != 0 else 0.0
    effect_size = compute_cohens_d(values_a, values_b)

    return ComparisonResult(
        config_a=config_a_name,
        config_b=config_b_name,
        metric=metric,
        stats_a=stats_a,
        stats_b=stats_b,
        mean_difference=mean_diff,
        percent_change=pct_change,
        effect_size=effect_size,
    )


def compare_with_baseline(
    baseline_results: Sequence[EndToEndResult],
    optimized_results: Sequence[EndToEndResult],
    metrics: Sequence[str] | None = None,
) -> dict[str, ComparisonResult]:
    """Compare optimized results against a baseline.

    Args:
        baseline_results: Results from baseline (no optimization).
        optimized_results: Results from optimized configuration.
        metrics: List of metrics to compare. Defaults to common metrics.

    Returns:
        Dictionary mapping metric name to ComparisonResult.
    """
    if metrics is None:
        metrics = [
            "process_fidelity",
            "state_fidelity",
            "post_opt_gates",
            "post_opt_depth",
            "pulse_duration_ns",
        ]

    comparisons = {}
    for metric in metrics:
        with contextlib.suppress(ValueError):
            comparisons[metric] = compare_configurations(
                baseline_results,
                optimized_results,
                config_a_name="baseline",
                config_b_name="optimized",
                metric=metric,
            )

    return comparisons


# =============================================================================
# Summary Report Generation
# =============================================================================


@dataclass
class ExperimentSummary:
    """Summary of an experiment's results.

    Attributes:
        total_circuits: Number of circuits analyzed.
        fidelity_stats: Statistics for process fidelity.
        gate_reduction_stats: Statistics for gate reduction percentage.
        pass_effectiveness: Effectiveness of each pass.
        scaling_analysis: Scaling behavior analysis.
        best_pass: Most effective optimization pass.
        worst_pass: Least effective optimization pass.
    """

    total_circuits: int
    fidelity_stats: DescriptiveStats
    gate_reduction_stats: DescriptiveStats
    pass_effectiveness: dict[str, PassEffectiveness]
    scaling_analysis: dict[str, ScalingAnalysisResult]
    best_pass: str
    worst_pass: str


def generate_experiment_summary(
    results: Sequence[EndToEndResult],
) -> ExperimentSummary:
    """Generate a comprehensive summary of experiment results.

    Args:
        results: Sequence of EndToEndResults.

    Returns:
        ExperimentSummary with aggregated statistics.

    Raises:
        ValueError: If results is empty.
    """
    if not results:
        raise ValueError("Cannot summarize empty results")

    fidelity_stats = analyze_results(results, "process_fidelity")
    gate_reduction_stats = analyze_results(results, "gate_reduction_pct")
    pass_eff = analyze_pass_effectiveness(results)
    scaling = analyze_fidelity_scaling(results)

    # Find best/worst passes
    ranked = rank_passes_by_effectiveness(results, "net_gate_reduction")
    best_pass = ranked[0][0] if ranked else "none"
    worst_pass = ranked[-1][0] if ranked else "none"

    return ExperimentSummary(
        total_circuits=len(results),
        fidelity_stats=fidelity_stats,
        gate_reduction_stats=gate_reduction_stats,
        pass_effectiveness=pass_eff,
        scaling_analysis=scaling,
        best_pass=best_pass,
        worst_pass=worst_pass,
    )


def _format_stats_section(title: str, stats: DescriptiveStats, pct: bool = False) -> list[str]:
    """Format a statistics section for the summary report."""
    suffix = "%" if pct else ""
    fmt = ".1f" if pct else ".4f"
    return [
        title,
        "-" * 30,
        f"  Mean:   {stats.mean:{fmt}}{suffix}",
        f"  Std:    {stats.std:{fmt}}{suffix}",
        f"  Min:    {stats.min:{fmt}}{suffix}",
        f"  Max:    {stats.max:{fmt}}{suffix}",
        *([] if pct else [f"  Median: {stats.median:{fmt}}"]),
        "",
    ]


def _format_pass_section(summary: ExperimentSummary) -> list[str]:
    """Format pass effectiveness section for the summary report."""
    lines = ["PASS EFFECTIVENESS", "-" * 30]
    for name, eff in sorted(
        summary.pass_effectiveness.items(),
        key=lambda x: x[1].net_gate_reduction,
        reverse=True,
    ):
        lines.append(
            f"  {name}: {eff.net_gate_reduction} gates "
            f"({eff.improvement_rate:.0%} improved)"
        )
    lines.extend(["", f"Best pass:  {summary.best_pass}", f"Worst pass: {summary.worst_pass}", ""])
    return lines


def format_summary_report(summary: ExperimentSummary) -> str:
    """Format experiment summary as human-readable text.

    Args:
        summary: ExperimentSummary to format.

    Returns:
        Formatted string report.
    """
    lines = [
        "=" * 60,
        "EXPERIMENT SUMMARY",
        "=" * 60,
        "",
        f"Total circuits analyzed: {summary.total_circuits}",
        "",
    ]
    lines.extend(_format_stats_section("PROCESS FIDELITY", summary.fidelity_stats))
    lines.extend(_format_stats_section("GATE REDUCTION (%)", summary.gate_reduction_stats, pct=True))
    lines.extend(_format_pass_section(summary))
    lines.append("SCALING ANALYSIS")
    lines.append("-" * 30)
    for x_var, scaling in summary.scaling_analysis.items():
        lines.append(f"  {x_var} vs fidelity: r={scaling.correlation:.3f}, R²={scaling.r_squared:.3f}")
    lines.append("=" * 60)
    return "\n".join(lines)
