"""Tests for statistical analysis module.

Tests cover:
- Descriptive statistics computation
- Correlation and regression analysis
- Pass effectiveness analysis
- Scaling analysis
- Comparison analysis
- Summary report generation

Following AgentBible testing principles:
- Specification Before Code
- Clear test names describing expected behavior
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.analysis import (
    DescriptiveStats,
    analyze_by_circuit_type,
    analyze_by_qubit_count,
    analyze_fidelity_scaling,
    analyze_pass_effectiveness,
    analyze_results,
    analyze_scaling,
    compare_configurations,
    compare_with_baseline,
    compute_cohens_d,
    compute_correlation,
    compute_descriptive_stats,
    compute_linear_regression,
    extract_metric,
    format_summary_report,
    generate_experiment_summary,
    rank_passes_by_effectiveness,
)
from src.metrics import (
    EndToEndResult,
    NoiseParams,
    PassMetrics,
    PulseMetrics,
    RoutingMetrics,
    StageMetrics,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def noise_params() -> NoiseParams:
    """Standard noise parameters for testing."""
    return NoiseParams(
        t1_ns=37000.0,
        t2_ns=9600.0,
        single_qubit_error=0.001,
        two_qubit_error=0.006,
    )


@pytest.fixture
def sample_result(noise_params: NoiseParams) -> EndToEndResult:
    """Single sample EndToEndResult."""
    return EndToEndResult(
        circuit_name="ghz_4",
        input_metrics=StageMetrics(gates=10, depth=5, qubits=4, two_qubit_gates=3),
        optimization_passes=[
            PassMetrics(
                name="CancellationPass",
                input_metrics=StageMetrics(gates=10, depth=5, qubits=4, two_qubit_gates=3),
                output_metrics=StageMetrics(gates=8, depth=4, qubits=4, two_qubit_gates=2),
                gates_removed=2,
                gates_added=0,
                execution_time_ms=1.5,
            )
        ],
        post_optimization=StageMetrics(gates=8, depth=4, qubits=4, two_qubit_gates=2),
        routing_metrics=RoutingMetrics(
            topology="iqm-garnet",
            swaps_inserted=1,
            depth_increase=2,
            final_gates=11,
            final_depth=6,
        ),
        pulse_metrics=PulseMetrics(
            total_duration_ns=200.0,
            pulse_count=8,
            max_amplitude=0.8,
        ),
        process_fidelity=0.95,
        state_fidelity=0.97,
        noise_params=noise_params,
        topology="iqm-garnet",
        timestamp=datetime.now(),
    )


@pytest.fixture
def sample_results(noise_params: NoiseParams) -> list[EndToEndResult]:
    """Multiple sample results for aggregation tests."""

    def make_result(
        name: str,
        qubits: int,
        gates: int,
        depth: int,
        fidelity: float,
        gates_removed: int = 2,
    ) -> EndToEndResult:
        return EndToEndResult(
            circuit_name=name,
            input_metrics=StageMetrics(
                gates=gates, depth=depth, qubits=qubits, two_qubit_gates=gates // 3
            ),
            optimization_passes=[
                PassMetrics(
                    name="CancellationPass",
                    input_metrics=StageMetrics(
                        gates=gates, depth=depth, qubits=qubits, two_qubit_gates=gates // 3
                    ),
                    output_metrics=StageMetrics(
                        gates=gates - gates_removed,
                        depth=depth - 1,
                        qubits=qubits,
                        two_qubit_gates=gates // 3 - 1,
                    ),
                    gates_removed=gates_removed,
                    gates_added=0,
                    execution_time_ms=1.0,
                ),
                PassMetrics(
                    name="CommutationPass",
                    input_metrics=StageMetrics(
                        gates=gates - gates_removed,
                        depth=depth - 1,
                        qubits=qubits,
                        two_qubit_gates=gates // 3 - 1,
                    ),
                    output_metrics=StageMetrics(
                        gates=gates - gates_removed - 1,
                        depth=depth - 2,
                        qubits=qubits,
                        two_qubit_gates=gates // 3 - 1,
                    ),
                    gates_removed=1,
                    gates_added=0,
                    execution_time_ms=0.5,
                ),
            ],
            post_optimization=StageMetrics(
                gates=gates - gates_removed - 1,
                depth=depth - 2,
                qubits=qubits,
                two_qubit_gates=gates // 3 - 1,
            ),
            routing_metrics=RoutingMetrics(
                topology="iqm-garnet",
                swaps_inserted=1,
                depth_increase=2,
                final_gates=gates - gates_removed + 2,
                final_depth=depth,
            ),
            pulse_metrics=PulseMetrics(
                total_duration_ns=100.0 + qubits * 20,
                pulse_count=gates - gates_removed,
                max_amplitude=0.8,
            ),
            process_fidelity=fidelity,
            state_fidelity=fidelity + 0.02,
            noise_params=noise_params,
            topology="iqm-garnet",
            timestamp=datetime.now(),
        )

    return [
        make_result("ghz_2", 2, 6, 3, 0.98, 1),
        make_result("ghz_4", 4, 10, 5, 0.95, 2),
        make_result("ghz_8", 8, 18, 9, 0.88, 4),
        make_result("qft_4", 4, 20, 10, 0.92, 3),
        make_result("qft_8", 8, 50, 25, 0.82, 8),
        make_result("random_4", 4, 15, 8, 0.90, 2),
    ]


# =============================================================================
# Descriptive Statistics Tests
# =============================================================================


class TestDescriptiveStats:
    """Tests for DescriptiveStats dataclass."""

    def test_iqr_property(self) -> None:
        """IQR is computed correctly."""
        stats = DescriptiveStats(
            count=10, mean=5.0, std=2.0, min=1.0, max=10.0, median=5.0, q1=3.0, q3=7.0
        )
        assert stats.iqr == 4.0

    def test_cv_property(self) -> None:
        """Coefficient of variation computed correctly."""
        stats = DescriptiveStats(
            count=10, mean=5.0, std=1.0, min=1.0, max=10.0, median=5.0, q1=3.0, q3=7.0
        )
        assert stats.cv == 0.2

    def test_cv_zero_mean(self) -> None:
        """CV handles zero mean gracefully."""
        stats = DescriptiveStats(
            count=10, mean=0.0, std=1.0, min=-1.0, max=1.0, median=0.0, q1=-0.5, q3=0.5
        )
        assert stats.cv == float("inf")


class TestComputeDescriptiveStats:
    """Tests for compute_descriptive_stats function."""

    def test_single_value(self) -> None:
        """Single value produces degenerate statistics."""
        stats = compute_descriptive_stats([5.0])

        assert stats.count == 1
        assert stats.mean == 5.0
        assert stats.std == 0.0
        assert stats.min == 5.0
        assert stats.max == 5.0
        assert stats.median == 5.0

    def test_two_values(self) -> None:
        """Two values produce correct statistics."""
        stats = compute_descriptive_stats([2.0, 8.0])

        assert stats.count == 2
        assert stats.mean == 5.0
        assert stats.min == 2.0
        assert stats.max == 8.0
        assert stats.median == 5.0

    def test_multiple_values(self) -> None:
        """Multiple values produce correct statistics."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
        stats = compute_descriptive_stats(values)

        assert stats.count == 9
        assert stats.mean == 5.0
        assert stats.min == 1.0
        assert stats.max == 9.0
        assert stats.median == 5.0

    def test_empty_raises_error(self) -> None:
        """Empty sequence raises ValueError."""
        with pytest.raises(ValueError, match="empty sequence"):
            compute_descriptive_stats([])


# =============================================================================
# Correlation and Regression Tests
# =============================================================================


class TestComputeCorrelation:
    """Tests for compute_correlation function."""

    def test_perfect_positive_correlation(self) -> None:
        """Perfect positive correlation returns 1.0."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]

        corr = compute_correlation(x, y)
        assert corr == pytest.approx(1.0)

    def test_perfect_negative_correlation(self) -> None:
        """Perfect negative correlation returns -1.0."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]

        corr = compute_correlation(x, y)
        assert corr == pytest.approx(-1.0)

    def test_no_correlation(self) -> None:
        """Uncorrelated data returns near 0."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [3.0, 1.0, 4.0, 1.0, 5.0]  # Pi digits, roughly uncorrelated

        corr = compute_correlation(x, y)
        assert -0.5 < corr < 0.5  # Weak correlation

    def test_different_lengths_error(self) -> None:
        """Different length sequences raise error."""
        with pytest.raises(ValueError, match="same length"):
            compute_correlation([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_too_short_error(self) -> None:
        """Single element raises error."""
        with pytest.raises(ValueError, match="at least 2"):
            compute_correlation([1.0], [1.0])


class TestComputeLinearRegression:
    """Tests for compute_linear_regression function."""

    def test_perfect_linear_relationship(self) -> None:
        """Perfect linear relationship gives R²=1."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [3.0, 5.0, 7.0, 9.0, 11.0]  # y = 2x + 1

        slope, intercept, r_squared = compute_linear_regression(x, y)

        assert slope == pytest.approx(2.0)
        assert intercept == pytest.approx(1.0)
        assert r_squared == pytest.approx(1.0)

    def test_horizontal_line(self) -> None:
        """Constant y gives slope=0."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [5.0, 5.0, 5.0, 5.0, 5.0]

        slope, intercept, r_squared = compute_linear_regression(x, y)

        assert slope == pytest.approx(0.0)
        assert intercept == pytest.approx(5.0)

    def test_different_lengths_error(self) -> None:
        """Different length sequences raise error."""
        with pytest.raises(ValueError, match="same length"):
            compute_linear_regression([1.0, 2.0], [1.0, 2.0, 3.0])


class TestComputeCohensD:
    """Tests for compute_cohens_d function."""

    def test_identical_groups(self) -> None:
        """Identical groups have d=0."""
        group = [1.0, 2.0, 3.0, 4.0, 5.0]
        d = compute_cohens_d(group, group)
        assert d == pytest.approx(0.0)

    def test_large_effect_size(self) -> None:
        """Clearly different groups have large effect size."""
        group1 = [1.0, 2.0, 3.0, 4.0, 5.0]
        group2 = [10.0, 11.0, 12.0, 13.0, 14.0]

        d = compute_cohens_d(group1, group2)
        assert d > 0.8  # Large effect size

    def test_empty_group_error(self) -> None:
        """Empty group raises error."""
        with pytest.raises(ValueError, match="non-empty"):
            compute_cohens_d([], [1.0, 2.0])


# =============================================================================
# Metric Extraction Tests
# =============================================================================


class TestExtractMetric:
    """Tests for extract_metric function."""

    def test_extract_process_fidelity(self, sample_result: EndToEndResult) -> None:
        """Process fidelity is extracted correctly."""
        value = extract_metric(sample_result, "process_fidelity")
        assert value == 0.95

    def test_extract_state_fidelity(self, sample_result: EndToEndResult) -> None:
        """State fidelity is extracted correctly."""
        value = extract_metric(sample_result, "state_fidelity")
        assert value == 0.97

    def test_extract_input_gates(self, sample_result: EndToEndResult) -> None:
        """Input gates is extracted correctly."""
        value = extract_metric(sample_result, "input_gates")
        assert value == 10.0

    def test_extract_gate_reduction(self, sample_result: EndToEndResult) -> None:
        """Gate reduction is computed correctly."""
        value = extract_metric(sample_result, "gate_reduction")
        assert value == 2.0  # 10 - 8

    def test_extract_gate_reduction_pct(self, sample_result: EndToEndResult) -> None:
        """Gate reduction percentage is computed correctly."""
        value = extract_metric(sample_result, "gate_reduction_pct")
        assert value == pytest.approx(20.0)  # 2/10 * 100

    def test_extract_unknown_metric_error(self, sample_result: EndToEndResult) -> None:
        """Unknown metric raises error with helpful message."""
        with pytest.raises(ValueError, match="Unknown metric.*bad_metric"):
            extract_metric(sample_result, "bad_metric")


# =============================================================================
# Results Analysis Tests
# =============================================================================


class TestAnalyzeResults:
    """Tests for analyze_results function."""

    def test_analyze_fidelity(self, sample_results: list[EndToEndResult]) -> None:
        """Fidelity statistics are computed correctly."""
        stats = analyze_results(sample_results, "process_fidelity")

        assert stats.count == 6
        assert 0.8 < stats.mean < 1.0
        assert stats.min <= stats.mean <= stats.max

    def test_analyze_empty_error(self) -> None:
        """Empty results raise error."""
        with pytest.raises(ValueError, match="empty results"):
            analyze_results([], "process_fidelity")


class TestAnalyzeByCircuitType:
    """Tests for analyze_by_circuit_type function."""

    def test_groups_by_type(self, sample_results: list[EndToEndResult]) -> None:
        """Results are grouped by circuit type prefix."""
        by_type = analyze_by_circuit_type(sample_results, "process_fidelity")

        assert "ghz" in by_type
        assert "qft" in by_type
        assert "random" in by_type
        assert by_type["ghz"].count == 3  # ghz_2, ghz_4, ghz_8


class TestAnalyzeByQubitCount:
    """Tests for analyze_by_qubit_count function."""

    def test_groups_by_qubits(self, sample_results: list[EndToEndResult]) -> None:
        """Results are grouped by qubit count."""
        by_qubits = analyze_by_qubit_count(sample_results, "process_fidelity")

        assert 4 in by_qubits
        assert 8 in by_qubits
        assert by_qubits[4].count == 3  # ghz_4, qft_4, random_4


# =============================================================================
# Pass Effectiveness Tests
# =============================================================================


class TestAnalyzePassEffectiveness:
    """Tests for analyze_pass_effectiveness function."""

    def test_aggregates_pass_data(self, sample_results: list[EndToEndResult]) -> None:
        """Pass effectiveness is aggregated across results."""
        effectiveness = analyze_pass_effectiveness(sample_results)

        assert "CancellationPass" in effectiveness
        assert "CommutationPass" in effectiveness

        cancel_eff = effectiveness["CancellationPass"]
        assert cancel_eff.circuits_total == 6
        assert cancel_eff.total_gates_removed > 0
        assert 0 <= cancel_eff.improvement_rate <= 1

    def test_empty_results_error(self) -> None:
        """Empty results raise error."""
        with pytest.raises(ValueError, match="empty results"):
            analyze_pass_effectiveness([])


class TestRankPassesByEffectiveness:
    """Tests for rank_passes_by_effectiveness function."""

    def test_ranking_order(self, sample_results: list[EndToEndResult]) -> None:
        """Passes are ranked in descending order."""
        ranked = rank_passes_by_effectiveness(sample_results, "net_gate_reduction")

        # First pass should have highest value
        assert len(ranked) == 2
        assert ranked[0][1] >= ranked[1][1]


# =============================================================================
# Scaling Analysis Tests
# =============================================================================


class TestAnalyzeScaling:
    """Tests for analyze_scaling function."""

    def test_scaling_result_structure(
        self, sample_results: list[EndToEndResult]
    ) -> None:
        """Scaling analysis returns complete result."""
        result = analyze_scaling(sample_results, "input_qubits", "process_fidelity")

        assert result.x_variable == "input_qubits"
        assert result.y_variable == "process_fidelity"
        assert len(result.data_points) == 6
        assert -1 <= result.correlation <= 1
        assert 0 <= result.r_squared <= 1

    def test_empty_results_error(self) -> None:
        """Empty results raise error."""
        with pytest.raises(ValueError, match="empty results"):
            analyze_scaling([], "input_qubits", "process_fidelity")


class TestAnalyzeFidelityScaling:
    """Tests for analyze_fidelity_scaling function."""

    def test_analyzes_multiple_variables(
        self, sample_results: list[EndToEndResult]
    ) -> None:
        """Multiple x-variables are analyzed."""
        scaling = analyze_fidelity_scaling(sample_results)

        assert "input_qubits" in scaling
        assert "input_gates" in scaling
        assert "input_depth" in scaling


# =============================================================================
# Comparison Tests
# =============================================================================


class TestCompareConfigurations:
    """Tests for compare_configurations function."""

    def test_comparison_result_structure(
        self, sample_results: list[EndToEndResult]
    ) -> None:
        """Comparison returns complete result."""
        # Split results into two groups
        group_a = sample_results[:3]
        group_b = sample_results[3:]

        result = compare_configurations(
            group_a, group_b, "config_a", "config_b", "process_fidelity"
        )

        assert result.config_a == "config_a"
        assert result.config_b == "config_b"
        assert result.metric == "process_fidelity"
        assert result.stats_a.count == 3
        assert result.stats_b.count == 3
        assert isinstance(result.mean_difference, float)
        assert isinstance(result.effect_size, float)

    def test_empty_group_error(self, sample_results: list[EndToEndResult]) -> None:
        """Empty group raises error."""
        with pytest.raises(ValueError, match="non-empty"):
            compare_configurations([], sample_results, "a", "b", "process_fidelity")


class TestCompareWithBaseline:
    """Tests for compare_with_baseline function."""

    def test_compares_default_metrics(
        self, sample_results: list[EndToEndResult]
    ) -> None:
        """Default metrics are compared."""
        baseline = sample_results[:3]
        optimized = sample_results[3:]

        comparisons = compare_with_baseline(baseline, optimized)

        assert "process_fidelity" in comparisons
        assert "state_fidelity" in comparisons


# =============================================================================
# Summary Report Tests
# =============================================================================


class TestGenerateExperimentSummary:
    """Tests for generate_experiment_summary function."""

    def test_summary_structure(self, sample_results: list[EndToEndResult]) -> None:
        """Summary contains all expected fields."""
        summary = generate_experiment_summary(sample_results)

        assert summary.total_circuits == 6
        assert summary.fidelity_stats.count == 6
        assert summary.gate_reduction_stats.count == 6
        assert len(summary.pass_effectiveness) == 2
        assert summary.best_pass in ["CancellationPass", "CommutationPass"]
        assert summary.worst_pass in ["CancellationPass", "CommutationPass"]

    def test_empty_results_error(self) -> None:
        """Empty results raise error."""
        with pytest.raises(ValueError, match="empty results"):
            generate_experiment_summary([])


class TestFormatSummaryReport:
    """Tests for format_summary_report function."""

    def test_report_format(self, sample_results: list[EndToEndResult]) -> None:
        """Report is formatted as readable text."""
        summary = generate_experiment_summary(sample_results)
        report = format_summary_report(summary)

        assert "EXPERIMENT SUMMARY" in report
        assert "PROCESS FIDELITY" in report
        assert "GATE REDUCTION" in report
        assert "PASS EFFECTIVENESS" in report
        assert "CancellationPass" in report
        assert "SCALING ANALYSIS" in report

    def test_report_contains_metrics(
        self, sample_results: list[EndToEndResult]
    ) -> None:
        """Report includes numeric metrics."""
        summary = generate_experiment_summary(sample_results)
        report = format_summary_report(summary)

        # Check that numeric values are present
        assert "Mean:" in report
        assert "Std:" in report
        assert "Min:" in report
        assert "Max:" in report


# =============================================================================
# Integration Tests
# =============================================================================


class TestAnalysisIntegration:
    """Integration tests for analysis workflow."""

    def test_full_analysis_workflow(
        self, sample_results: list[EndToEndResult]
    ) -> None:
        """Complete analysis workflow runs without error."""
        # Step 1: Compute basic statistics
        fidelity_stats = analyze_results(sample_results, "process_fidelity")
        assert fidelity_stats.count == 6

        # Step 2: Analyze by grouping
        by_type = analyze_by_circuit_type(sample_results, "process_fidelity")
        assert len(by_type) == 3

        # Step 3: Pass effectiveness
        effectiveness = analyze_pass_effectiveness(sample_results)
        assert len(effectiveness) == 2

        # Step 4: Scaling analysis
        scaling = analyze_fidelity_scaling(sample_results)
        assert len(scaling) > 0

        # Step 5: Generate summary
        summary = generate_experiment_summary(sample_results)
        assert summary.total_circuits == 6

        # Step 6: Format report
        report = format_summary_report(summary)
        assert len(report) > 100
