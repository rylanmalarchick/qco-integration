"""Visualization utilities for publication-ready figures.

This module provides plotting functions for experimental analysis,
generating figures suitable for arXiv preprint.

Figure types:
- Fidelity waterfall charts (stage-by-stage breakdown)
- Per-pass effectiveness (bar charts/tables)
- Scaling plots (qubits/depth vs fidelity)
- Pulse comparison waveforms

Uses consistent publication-ready styling (serif fonts, 300 DPI).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from src.analysis import (
    analyze_pass_effectiveness,
    analyze_scaling,
)
from src.metrics import EndToEndResult

# Publication-ready plot defaults
FONT_SIZE = 12
TITLE_SIZE = 14
DPI = 300
FIGSIZE = (8, 6)
FORMAT = "pdf"

FIGURE_DEFAULTS = {
    "font_size": FONT_SIZE,
    "title_size": TITLE_SIZE,
    "dpi": DPI,
    "figsize": FIGSIZE,
    "format": FORMAT,
}

# Color palette for consistent styling
COLORS = {
    "primary": "#1f77b4",
    "secondary": "#ff7f0e",
    "success": "#2ca02c",
    "warning": "#d62728",
    "neutral": "#7f7f7f",
    "accent1": "#9467bd",
    "accent2": "#8c564b",
}


def set_publication_style() -> None:
    """Configure matplotlib for publication-quality figures.

    Sets consistent fonts, sizes, and styling suitable for
    arXiv/journal submissions.
    """
    plt.rcParams.update({
        # Font settings
        "font.size": FONT_SIZE,
        "axes.titlesize": TITLE_SIZE,
        "axes.labelsize": FONT_SIZE,
        "xtick.labelsize": FONT_SIZE - 2,
        "ytick.labelsize": FONT_SIZE - 2,
        "legend.fontsize": FONT_SIZE - 2,
        # Figure settings
        "figure.figsize": FIGSIZE,
        "figure.dpi": 100,  # Screen DPI
        "savefig.dpi": DPI,
        "savefig.format": FORMAT,
        # Style settings
        "axes.grid": True,
        "grid.alpha": 0.3,
        "axes.spines.top": False,
        "axes.spines.right": False,
        # Use serif fonts for publications
        "font.family": "serif",
    })


def _save_figure(fig: Figure, save_path: Path | None) -> None:
    """Save figure to path if provided."""
    if save_path is not None:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, bbox_inches="tight")


def _compute_waterfall_metrics(results: Sequence[EndToEndResult]) -> tuple[float, float, float, float]:
    """Compute average metrics for waterfall chart."""
    n = len(results)
    avg_input = sum(r.input_metrics.gates for r in results) / n
    avg_post_opt = sum(r.post_optimization.gates for r in results) / n
    avg_routed = sum(
        r.routing_metrics.final_gates if r.routing_metrics else r.post_optimization.gates
        for r in results
    ) / n
    avg_fidelity = sum(r.process_fidelity for r in results) / n
    return avg_input, avg_post_opt, avg_routed, avg_fidelity


def _add_bar_labels(ax: Any, bars: Any, values: Sequence[float]) -> None:
    """Add value labels on top of bars."""
    for bar, val in zip(bars, values, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.5,
            f"{val:.0f}",
            ha="center",
            va="bottom",
            fontsize=10,
        )


def plot_fidelity_waterfall(
    results: Sequence[EndToEndResult],
    title: str | None = None,
    save_path: Path | None = None,
) -> Figure:
    """Generate fidelity waterfall chart showing stage-by-stage breakdown.

    Args:
        results: List of end-to-end results to visualize.
        title: Optional figure title.
        save_path: If provided, save figure to this path.

    Returns:
        Matplotlib figure object.
    """
    if not results:
        raise ValueError("Cannot plot empty results")

    avg_input, avg_post_opt, avg_routed, avg_fidelity = _compute_waterfall_metrics(results)
    stages = ["Input", "Optimized", "Routed", "Fidelity"]
    values = [avg_input, avg_post_opt, avg_routed, avg_fidelity * 100]

    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Plot gate counts on left y-axis
    bars = ax1.bar(range(3), values[:-1], color=[COLORS["primary"], COLORS["success"], COLORS["secondary"]])
    ax1.set_ylabel("Gate Count", color=COLORS["primary"])
    ax1.tick_params(axis="y", labelcolor=COLORS["primary"])

    # Add fidelity on right y-axis
    ax2 = ax1.twinx()
    ax2.bar([3], [values[-1]], color=COLORS["accent1"])
    ax2.set_ylabel("Fidelity (%)", color=COLORS["accent1"])
    ax2.tick_params(axis="y", labelcolor=COLORS["accent1"])
    ax2.set_ylim(0, 100)

    ax1.set_xticks(range(len(stages)))
    ax1.set_xticklabels(stages)
    ax1.set_xlabel("Pipeline Stage")
    ax1.set_title(title or f"Pipeline Waterfall (n={len(results)} circuits)")

    _add_bar_labels(ax1, bars, values[:-1])
    fig.tight_layout()
    _save_figure(fig, save_path)
    return fig


def plot_pass_effectiveness(
    results: Sequence[EndToEndResult],
    metric: str = "net_gate_reduction",
    save_path: Path | None = None,
) -> Figure:
    """Generate bar chart showing per-pass effectiveness.

    Args:
        results: List of end-to-end results to visualize.
        metric: Metric to plot ("net_gate_reduction", "avg_gates_removed",
                "avg_depth_reduction", "improvement_rate").
        save_path: If provided, save figure to this path.

    Returns:
        Matplotlib figure object.
    """
    if not results:
        raise ValueError("Cannot plot empty results")

    effectiveness = analyze_pass_effectiveness(results)

    # Sort by the metric
    sorted_passes = sorted(
        effectiveness.items(),
        key=lambda x: getattr(x[1], metric, 0),
        reverse=True,
    )

    pass_names = [name for name, _ in sorted_passes]
    values = [getattr(eff, metric, 0) for _, eff in sorted_passes]

    fig, ax = plt.subplots(figsize=(10, 6))

    colors = [COLORS["primary"] if v >= 0 else COLORS["warning"] for v in values]
    bars = ax.barh(pass_names, values, color=colors)

    ax.set_xlabel(_format_metric_label(metric))
    ax.set_ylabel("Optimization Pass")
    ax.set_title(f"Pass Effectiveness: {_format_metric_label(metric)}")

    # Add value labels
    for bar, val in zip(bars, values, strict=True):
        x_pos = bar.get_width() + (max(values) * 0.02 if val >= 0 else min(values) * 0.02)
        ax.text(
            x_pos,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}" if isinstance(val, float) else str(val),
            ha="left" if val >= 0 else "right",
            va="center",
            fontsize=10,
        )

    ax.axvline(x=0, color=COLORS["neutral"], linestyle="-", linewidth=0.5)

    fig.tight_layout()
    _save_figure(fig, save_path)
    return fig


def _plot_grouped_scaling(
    ax: Any,
    results: Sequence[EndToEndResult],
    x_axis: str,
    y_axis: str,
) -> None:
    """Plot scaling data grouped by circuit type."""
    groups: dict[str, list[EndToEndResult]] = {}
    for r in results:
        circuit_type = r.circuit_name.split("_")[0]
        groups.setdefault(circuit_type, []).append(r)

    colors_list = list(COLORS.values())
    for i, (group_name, group_results) in enumerate(sorted(groups.items())):
        scaling = analyze_scaling(group_results, x_axis, y_axis)
        x_vals = [p[0] for p in scaling.data_points]
        y_vals = [p[1] for p in scaling.data_points]
        color = colors_list[i % len(colors_list)]
        ax.scatter(x_vals, y_vals, label=group_name, color=color, s=60, alpha=0.7)


def _plot_single_scaling(ax: Any, results: Sequence[EndToEndResult], x_axis: str, y_axis: str) -> None:
    """Plot scaling data as single group with regression line."""
    scaling = analyze_scaling(results, x_axis, y_axis)
    x_vals = [p[0] for p in scaling.data_points]
    y_vals = [p[1] for p in scaling.data_points]

    ax.scatter(x_vals, y_vals, color=COLORS["primary"], s=60, alpha=0.7)

    if len(x_vals) >= 2:
        x_min, x_max = min(x_vals), max(x_vals)
        y_min = scaling.slope * x_min + scaling.intercept
        y_max = scaling.slope * x_max + scaling.intercept
        ax.plot([x_min, x_max], [y_min, y_max], color=COLORS["warning"],
                linestyle="--", linewidth=2, label=f"R²={scaling.r_squared:.3f}")


def plot_scaling_analysis(
    results: Sequence[EndToEndResult],
    x_axis: str = "input_qubits",
    y_axis: str = "process_fidelity",
    group_by: str | None = None,
    save_path: Path | None = None,
) -> Figure:
    """Generate scaling plot (qubits/depth vs fidelity).

    Args:
        results: List of end-to-end results to visualize.
        x_axis: What to plot on x-axis ("input_qubits", "input_depth", "input_gates").
        y_axis: What to plot on y-axis ("process_fidelity", "state_fidelity").
        group_by: Optional grouping variable for multiple lines (e.g., "circuit_type").
        save_path: If provided, save figure to this path.

    Returns:
        Matplotlib figure object.
    """
    if not results:
        raise ValueError("Cannot plot empty results")

    fig, ax = plt.subplots(figsize=(10, 6))

    if group_by == "circuit_type":
        _plot_grouped_scaling(ax, results, x_axis, y_axis)
    else:
        _plot_single_scaling(ax, results, x_axis, y_axis)

    ax.set_xlabel(_format_metric_label(x_axis))
    ax.set_ylabel(_format_metric_label(y_axis))
    ax.set_title(f"{_format_metric_label(y_axis)} vs {_format_metric_label(x_axis)}")

    if y_axis in ("process_fidelity", "state_fidelity"):
        ax.set_ylim(0, 1.05)

    ax.legend()
    fig.tight_layout()
    _save_figure(fig, save_path)
    return fig


def plot_pulse_comparison(
    before_pulses: dict[str, Any],
    after_pulses: dict[str, Any],
    title: str | None = None,
    save_path: Path | None = None,
) -> Figure:
    """Generate pulse waveform comparison (before/after optimization).

    Args:
        before_pulses: Pulse data before optimization (dict with 'total_duration_ns', 'pulse_count').
        after_pulses: Pulse data after optimization.
        title: Optional figure title.
        save_path: If provided, save figure to this path.

    Returns:
        Matplotlib figure object.
    """
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Before optimization
    ax1 = axes[0]
    duration_before = before_pulses.get("total_duration_ns", 0)
    count_before = before_pulses.get("pulse_count", 0)

    ax1.bar(["Duration (ns)", "Pulse Count"], [duration_before, count_before], color=COLORS["primary"])
    ax1.set_title("Before Optimization")
    ax1.set_ylabel("Value")

    # After optimization
    ax2 = axes[1]
    duration_after = after_pulses.get("total_duration_ns", 0)
    count_after = after_pulses.get("pulse_count", 0)

    ax2.bar(["Duration (ns)", "Pulse Count"], [duration_after, count_after], color=COLORS["success"])
    ax2.set_title("After Optimization")
    ax2.set_ylabel("Value")

    # Ensure same y-scale for comparison
    max_val = max(duration_before, duration_after, count_before, count_after)
    ax1.set_ylim(0, max_val * 1.1)
    ax2.set_ylim(0, max_val * 1.1)

    if title:
        fig.suptitle(title, fontsize=14)

    fig.tight_layout()
    _save_figure(fig, save_path)
    return fig


# Architecture diagram layout configuration
_ARCH_BOXES: list[tuple[float, float, float, float, str, str]] = [
    (1, 8, 2, 1, "Input\nOpenQASM", "neutral"),
    (1, 6, 2, 1, "Stage 1:\nParse", "primary"),
    (1, 4, 2, 1, "Stage 2:\nOptimize", "primary"),
    (1, 2, 2, 1, "Stage 3:\nRoute", "primary"),
    (5, 4, 2, 1, "Stage 4:\nPulse Compile", "secondary"),
    (5, 2, 2, 1, "Stage 5:\nSimulate", "secondary"),
    (5, 0, 2, 1, "Fidelity\nMetrics", "success"),
]

_ARCH_ARROWS: list[tuple[float, float, float, float]] = [
    (2.0, 8.0, 0.0, -1.0),  # Input -> Parse
    (2.0, 6.0, 0.0, -1.0),  # Parse -> Optimize
    (2.0, 4.0, 0.0, -1.0),  # Optimize -> Route
    (3.0, 2.5, 2.0, 1.5),   # Route -> Pulse Compile
    (6.0, 4.0, 0.0, -1.0),  # Pulse Compile -> Simulate
    (6.0, 2.0, 0.0, -1.0),  # Simulate -> Metrics
]


def _draw_arch_boxes(ax: Any) -> None:
    """Draw architecture diagram boxes."""
    for x, y, w, h, text, color_key in _ARCH_BOXES:
        rect = Rectangle((x, y), w, h, facecolor=COLORS[color_key], edgecolor="black", linewidth=2, alpha=0.7)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=10, fontweight="bold")


def _draw_arch_arrows(ax: Any) -> None:
    """Draw architecture diagram arrows."""
    for ax_x, ax_y, ax_dx, ax_dy in _ARCH_ARROWS:
        ax.annotate("", xy=(ax_x + ax_dx, ax_y + ax_dy), xytext=(ax_x, ax_y),
                    arrowprops={"arrowstyle": "->", "color": "black", "lw": 2})


def generate_architecture_diagram(save_path: Path | None = None) -> Figure:
    """Generate system architecture diagram for paper.

    Args:
        save_path: If provided, save figure to this path.

    Returns:
        Matplotlib figure object.
    """
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    _draw_arch_boxes(ax)
    _draw_arch_arrows(ax)

    # External component labels
    ax.text(8, 7, "quantum-circuit-\noptimizer\n(C++)", ha="center", va="center", fontsize=9, style="italic")
    ax.text(8, 3, "QubitPulseOpt\n(Python)", ha="center", va="center", fontsize=9, style="italic")
    ax.plot([3, 7], [5, 7], "k--", alpha=0.5)
    ax.plot([7, 8], [3, 3], "k--", alpha=0.5)

    ax.set_title("QCO-Integration Pipeline Architecture", fontsize=14, fontweight="bold")
    fig.tight_layout()
    _save_figure(fig, save_path)
    return fig


def create_results_table(
    results: Sequence[EndToEndResult],
    metrics: Sequence[str],
    output_format: str = "latex",
) -> str:
    """Create formatted table of results.

    Args:
        results: List of end-to-end results.
        metrics: List of metrics to include in table.
        output_format: Output format ("latex", "markdown", "html").

    Returns:
        Formatted table string.

    Raises:
        ValueError: If output_format is not supported.
    """
    if output_format not in ("latex", "markdown", "html"):
        raise ValueError(f"Unsupported format: {output_format}. Use 'latex', 'markdown', or 'html'.")

    from src.analysis import extract_metric

    # Build table data
    headers = ["Circuit"] + [_format_metric_label(m) for m in metrics]
    rows = []
    for result in results:
        row = [result.circuit_name]
        for metric in metrics:
            value = extract_metric(result, metric)
            if isinstance(value, float):
                row.append(f"{value:.4f}" if abs(value) < 10 else f"{value:.1f}")
            else:
                row.append(str(value))
        rows.append(row)

    if output_format == "latex":
        return _format_latex_table(headers, rows)
    elif output_format == "markdown":
        return _format_markdown_table(headers, rows)
    else:
        return _format_html_table(headers, rows)


def _format_metric_label(metric: str) -> str:
    """Convert metric name to human-readable label."""
    labels = {
        "input_qubits": "Qubits",
        "input_gates": "Input Gates",
        "input_depth": "Input Depth",
        "input_2q_gates": "2Q Gates",
        "post_opt_gates": "Optimized Gates",
        "post_opt_depth": "Optimized Depth",
        "process_fidelity": "Process Fidelity",
        "state_fidelity": "State Fidelity",
        "gate_reduction": "Gate Reduction",
        "gate_reduction_pct": "Gate Reduction (%)",
        "depth_reduction": "Depth Reduction",
        "pulse_duration_ns": "Pulse Duration (ns)",
        "net_gate_reduction": "Net Gates Removed",
        "avg_gates_removed": "Avg Gates Removed",
        "avg_depth_reduction": "Avg Depth Reduction",
        "improvement_rate": "Improvement Rate",
    }
    return labels.get(metric, metric.replace("_", " ").title())


def _format_latex_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format table as LaTeX."""
    col_spec = "l" + "r" * (len(headers) - 1)
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        f"\\begin{{tabular}}{{{col_spec}}}",
        r"\toprule",
        " & ".join(headers) + r" \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(row) + r" \\")
    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Experimental Results}",
        r"\label{tab:results}",
        r"\end{table}",
    ])
    return "\n".join(lines)


def _format_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format table as Markdown."""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _format_html_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format table as HTML."""
    lines = [
        "<table>",
        "  <thead>",
        "    <tr>",
    ]
    for h in headers:
        lines.append(f"      <th>{h}</th>")
    lines.extend([
        "    </tr>",
        "  </thead>",
        "  <tbody>",
    ])
    for row in rows:
        lines.append("    <tr>")
        for cell in row:
            lines.append(f"      <td>{cell}</td>")
        lines.append("    </tr>")
    lines.extend([
        "  </tbody>",
        "</table>",
    ])
    return "\n".join(lines)


def plot_comparison_bar_chart(
    labels: Sequence[str],
    baseline_values: Sequence[float],
    optimized_values: Sequence[float],
    metric_name: str = "Value",
    title: str | None = None,
    save_path: Path | None = None,
) -> Figure:
    """Generate grouped bar chart comparing baseline vs optimized.

    Args:
        labels: Labels for each group (e.g., circuit names).
        baseline_values: Values for baseline configuration.
        optimized_values: Values for optimized configuration.
        metric_name: Name of the metric being compared.
        title: Optional figure title.
        save_path: If provided, save figure to this path.

    Returns:
        Matplotlib figure object.
    """
    import numpy as np

    fig, ax = plt.subplots(figsize=(10, 6))

    x = np.arange(len(labels))
    width = 0.35

    ax.bar(x - width / 2, baseline_values, width, label="Baseline", color=COLORS["neutral"])
    ax.bar(x + width / 2, optimized_values, width, label="Optimized", color=COLORS["success"])

    ax.set_xlabel("Configuration")
    ax.set_ylabel(metric_name)
    ax.set_title(title or f"{metric_name} Comparison")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()

    fig.tight_layout()
    _save_figure(fig, save_path)
    return fig
