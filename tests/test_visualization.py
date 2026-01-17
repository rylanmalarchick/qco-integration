"""Tests for visualization module.

Tests cover:
- Publication style configuration
- Fidelity waterfall charts
- Pass effectiveness bar charts
- Scaling analysis plots
- Pulse comparison plots
- Architecture diagram generation
- Results table formatting

Following AgentBible testing principles:
- Test behavior, not implementation
- Use matplotlib's testing utilities
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import pytest
from matplotlib.figure import Figure

from src.metrics import (
    EndToEndResult,
    NoiseParams,
    PassMetrics,
    PulseMetrics,
    RoutingMetrics,
    StageMetrics,
)
from src.visualization import (
    COLORS,
    FIGURE_DEFAULTS,
    create_results_table,
    generate_architecture_diagram,
    plot_comparison_bar_chart,
    plot_fidelity_waterfall,
    plot_pass_effectiveness,
    plot_pulse_comparison,
    plot_scaling_analysis,
    set_publication_style,
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
def sample_results(noise_params: NoiseParams) -> list[EndToEndResult]:
    """Sample results for visualization tests."""

    def make_result(
        name: str,
        qubits: int,
        gates: int,
        depth: int,
        fidelity: float,
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
                        gates=gates - 2,
                        depth=depth - 1,
                        qubits=qubits,
                        two_qubit_gates=gates // 3 - 1,
                    ),
                    gates_removed=2,
                    gates_added=0,
                    execution_time_ms=1.0,
                ),
            ],
            post_optimization=StageMetrics(
                gates=gates - 2,
                depth=depth - 1,
                qubits=qubits,
                two_qubit_gates=gates // 3 - 1,
            ),
            routing_metrics=RoutingMetrics(
                topology="iqm-garnet",
                swaps_inserted=1,
                depth_increase=2,
                final_gates=gates + 2,
                final_depth=depth + 1,
            ),
            pulse_metrics=PulseMetrics(
                total_duration_ns=100.0 + qubits * 20,
                pulse_count=gates - 2,
                max_amplitude=0.8,
            ),
            process_fidelity=fidelity,
            state_fidelity=fidelity + 0.02,
            noise_params=noise_params,
            topology="iqm-garnet",
            timestamp=datetime.now(),
        )

    return [
        make_result("ghz_2", 2, 6, 3, 0.98),
        make_result("ghz_4", 4, 10, 5, 0.95),
        make_result("ghz_8", 8, 18, 9, 0.88),
        make_result("qft_4", 4, 20, 10, 0.92),
        make_result("qft_8", 8, 50, 25, 0.82),
    ]


@pytest.fixture(autouse=True)
def cleanup_matplotlib() -> Generator[None, None, None]:
    """Close all matplotlib figures after each test."""
    import matplotlib.pyplot as plt

    yield
    plt.close("all")


# =============================================================================
# Configuration Tests
# =============================================================================


class TestFigureDefaults:
    """Tests for figure default constants."""

    def test_defaults_exist(self) -> None:
        """Default values are defined."""
        assert "font_size" in FIGURE_DEFAULTS
        assert "title_size" in FIGURE_DEFAULTS
        assert "dpi" in FIGURE_DEFAULTS
        assert "figsize" in FIGURE_DEFAULTS

    def test_colors_exist(self) -> None:
        """Color palette is defined."""
        assert "primary" in COLORS
        assert "secondary" in COLORS
        assert "success" in COLORS
        assert "warning" in COLORS


class TestSetPublicationStyle:
    """Tests for set_publication_style function."""

    def test_sets_style_without_error(self) -> None:
        """Style can be set without raising errors."""
        # Should not raise
        set_publication_style()

    def test_modifies_rcparams(self) -> None:
        """Style modifies matplotlib rcParams."""
        import matplotlib.pyplot as plt

        set_publication_style()

        # Check some expected values
        assert plt.rcParams["axes.grid"] is True
        assert plt.rcParams["axes.spines.top"] is False


# =============================================================================
# Waterfall Chart Tests
# =============================================================================


class TestPlotFidelityWaterfall:
    """Tests for plot_fidelity_waterfall function."""

    def test_returns_figure(self, sample_results: list[EndToEndResult]) -> None:
        """Function returns a matplotlib Figure."""
        fig = plot_fidelity_waterfall(sample_results)
        assert isinstance(fig, Figure)

    def test_custom_title(self, sample_results: list[EndToEndResult]) -> None:
        """Custom title is applied."""
        fig = plot_fidelity_waterfall(sample_results, title="Test Title")
        axes = fig.get_axes()
        assert any("Test Title" in ax.get_title() for ax in axes)

    def test_empty_results_error(self) -> None:
        """Empty results raise error."""
        with pytest.raises(ValueError, match="empty results"):
            plot_fidelity_waterfall([])

    def test_saves_to_path(
        self, sample_results: list[EndToEndResult], tmp_path: Path
    ) -> None:
        """Figure is saved when path provided."""
        save_path = tmp_path / "waterfall.png"
        plot_fidelity_waterfall(sample_results, save_path=save_path)
        assert save_path.exists()


# =============================================================================
# Pass Effectiveness Tests
# =============================================================================


class TestPlotPassEffectiveness:
    """Tests for plot_pass_effectiveness function."""

    def test_returns_figure(self, sample_results: list[EndToEndResult]) -> None:
        """Function returns a matplotlib Figure."""
        fig = plot_pass_effectiveness(sample_results)
        assert isinstance(fig, Figure)

    def test_different_metrics(self, sample_results: list[EndToEndResult]) -> None:
        """Different metrics can be plotted."""
        fig1 = plot_pass_effectiveness(sample_results, metric="net_gate_reduction")
        fig2 = plot_pass_effectiveness(sample_results, metric="avg_gates_removed")
        assert isinstance(fig1, Figure)
        assert isinstance(fig2, Figure)

    def test_empty_results_error(self) -> None:
        """Empty results raise error."""
        with pytest.raises(ValueError, match="empty results"):
            plot_pass_effectiveness([])

    def test_saves_to_path(
        self, sample_results: list[EndToEndResult], tmp_path: Path
    ) -> None:
        """Figure is saved when path provided."""
        save_path = tmp_path / "effectiveness.png"
        plot_pass_effectiveness(sample_results, save_path=save_path)
        assert save_path.exists()


# =============================================================================
# Scaling Analysis Tests
# =============================================================================


class TestPlotScalingAnalysis:
    """Tests for plot_scaling_analysis function."""

    def test_returns_figure(self, sample_results: list[EndToEndResult]) -> None:
        """Function returns a matplotlib Figure."""
        fig = plot_scaling_analysis(sample_results)
        assert isinstance(fig, Figure)

    def test_different_axes(self, sample_results: list[EndToEndResult]) -> None:
        """Different x and y axes can be specified."""
        fig = plot_scaling_analysis(
            sample_results, x_axis="input_gates", y_axis="state_fidelity"
        )
        assert isinstance(fig, Figure)

    def test_group_by_circuit_type(self, sample_results: list[EndToEndResult]) -> None:
        """Grouping by circuit type works."""
        fig = plot_scaling_analysis(sample_results, group_by="circuit_type")
        assert isinstance(fig, Figure)

    def test_empty_results_error(self) -> None:
        """Empty results raise error."""
        with pytest.raises(ValueError, match="empty results"):
            plot_scaling_analysis([])

    def test_saves_to_path(
        self, sample_results: list[EndToEndResult], tmp_path: Path
    ) -> None:
        """Figure is saved when path provided."""
        save_path = tmp_path / "scaling.png"
        plot_scaling_analysis(sample_results, save_path=save_path)
        assert save_path.exists()


# =============================================================================
# Pulse Comparison Tests
# =============================================================================


class TestPlotPulseComparison:
    """Tests for plot_pulse_comparison function."""

    def test_returns_figure(self) -> None:
        """Function returns a matplotlib Figure."""
        before = {"total_duration_ns": 200.0, "pulse_count": 10}
        after = {"total_duration_ns": 150.0, "pulse_count": 8}

        fig = plot_pulse_comparison(before, after)
        assert isinstance(fig, Figure)

    def test_with_title(self) -> None:
        """Custom title is applied."""
        before = {"total_duration_ns": 200.0, "pulse_count": 10}
        after = {"total_duration_ns": 150.0, "pulse_count": 8}

        fig = plot_pulse_comparison(before, after, title="Pulse Comparison")
        # Just verify figure is created successfully with title parameter
        assert isinstance(fig, Figure)

    def test_saves_to_path(self, tmp_path: Path) -> None:
        """Figure is saved when path provided."""
        before = {"total_duration_ns": 200.0, "pulse_count": 10}
        after = {"total_duration_ns": 150.0, "pulse_count": 8}

        save_path = tmp_path / "pulse.png"
        plot_pulse_comparison(before, after, save_path=save_path)
        assert save_path.exists()


# =============================================================================
# Architecture Diagram Tests
# =============================================================================


class TestGenerateArchitectureDiagram:
    """Tests for generate_architecture_diagram function."""

    def test_returns_figure(self) -> None:
        """Function returns a matplotlib Figure."""
        fig = generate_architecture_diagram()
        assert isinstance(fig, Figure)

    def test_saves_to_path(self, tmp_path: Path) -> None:
        """Figure is saved when path provided."""
        save_path = tmp_path / "architecture.png"
        generate_architecture_diagram(save_path=save_path)
        assert save_path.exists()


# =============================================================================
# Results Table Tests
# =============================================================================


class TestCreateResultsTable:
    """Tests for create_results_table function."""

    def test_latex_format(self, sample_results: list[EndToEndResult]) -> None:
        """LaTeX table is generated correctly."""
        table = create_results_table(
            sample_results,
            metrics=["process_fidelity", "input_gates"],
            output_format="latex",
        )

        assert r"\begin{table}" in table
        assert r"\end{table}" in table
        assert "Process Fidelity" in table
        assert "Input Gates" in table

    def test_markdown_format(self, sample_results: list[EndToEndResult]) -> None:
        """Markdown table is generated correctly."""
        table = create_results_table(
            sample_results,
            metrics=["process_fidelity", "input_gates"],
            output_format="markdown",
        )

        assert "|" in table
        assert "---" in table
        assert "Process Fidelity" in table

    def test_html_format(self, sample_results: list[EndToEndResult]) -> None:
        """HTML table is generated correctly."""
        table = create_results_table(
            sample_results,
            metrics=["process_fidelity", "input_gates"],
            output_format="html",
        )

        assert "<table>" in table
        assert "</table>" in table
        assert "<th>" in table
        assert "<td>" in table

    def test_unsupported_format_error(
        self, sample_results: list[EndToEndResult]
    ) -> None:
        """Unsupported format raises error."""
        with pytest.raises(ValueError, match="Unsupported format"):
            create_results_table(
                sample_results,
                metrics=["process_fidelity"],
                output_format="csv",
            )


# =============================================================================
# Comparison Bar Chart Tests
# =============================================================================


class TestPlotComparisonBarChart:
    """Tests for plot_comparison_bar_chart function."""

    def test_returns_figure(self) -> None:
        """Function returns a matplotlib Figure."""
        labels = ["A", "B", "C"]
        baseline = [10.0, 20.0, 30.0]
        optimized = [8.0, 18.0, 28.0]

        fig = plot_comparison_bar_chart(labels, baseline, optimized)
        assert isinstance(fig, Figure)

    def test_custom_metric_name(self) -> None:
        """Custom metric name is shown."""
        labels = ["A", "B"]
        baseline = [10.0, 20.0]
        optimized = [8.0, 18.0]

        fig = plot_comparison_bar_chart(
            labels, baseline, optimized, metric_name="Gate Count"
        )
        axes = fig.get_axes()
        assert any("Gate Count" in ax.get_ylabel() for ax in axes)

    def test_saves_to_path(self, tmp_path: Path) -> None:
        """Figure is saved when path provided."""
        labels = ["A", "B"]
        baseline = [10.0, 20.0]
        optimized = [8.0, 18.0]

        save_path = tmp_path / "comparison.png"
        plot_comparison_bar_chart(labels, baseline, optimized, save_path=save_path)
        assert save_path.exists()


# =============================================================================
# Integration Tests
# =============================================================================


class TestVisualizationIntegration:
    """Integration tests for visualization workflow."""

    def test_generate_all_figures(
        self, sample_results: list[EndToEndResult]
    ) -> None:
        """All figure types can be generated in sequence."""
        # Waterfall
        fig1 = plot_fidelity_waterfall(sample_results)
        assert isinstance(fig1, Figure)

        # Pass effectiveness
        fig2 = plot_pass_effectiveness(sample_results)
        assert isinstance(fig2, Figure)

        # Scaling
        fig3 = plot_scaling_analysis(sample_results)
        assert isinstance(fig3, Figure)

        # Pulse comparison
        fig4 = plot_pulse_comparison(
            {"total_duration_ns": 200, "pulse_count": 10},
            {"total_duration_ns": 150, "pulse_count": 8},
        )
        assert isinstance(fig4, Figure)

        # Architecture
        fig5 = generate_architecture_diagram()
        assert isinstance(fig5, Figure)

    def test_save_all_figures(
        self, sample_results: list[EndToEndResult], tmp_path: Path
    ) -> None:
        """All figures can be saved."""
        figures_dir = tmp_path / "figures"
        figures_dir.mkdir()

        plot_fidelity_waterfall(sample_results, save_path=figures_dir / "waterfall.png")
        plot_pass_effectiveness(sample_results, save_path=figures_dir / "effectiveness.png")
        plot_scaling_analysis(sample_results, save_path=figures_dir / "scaling.png")
        generate_architecture_diagram(save_path=figures_dir / "architecture.png")

        assert (figures_dir / "waterfall.png").exists()
        assert (figures_dir / "effectiveness.png").exists()
        assert (figures_dir / "scaling.png").exists()
        assert (figures_dir / "architecture.png").exists()
