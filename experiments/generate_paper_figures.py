#!/usr/bin/env python3
"""Generate publication-quality figures for the ACM TQC paper.

Reads from experiment result JSON files and produces PDF figures.

Usage:
    python experiments/generate_paper_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
FIGURES_DIR = PROJECT_ROOT / "experiments" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# Publication style
plt.rcParams.update({
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "font.family": "serif",
})


def load_compiler_comparison() -> dict:
    """Load latest compiler comparison results."""
    files = sorted(RESULTS_DIR.glob("compiler_comparison/comparison_detail_*.json"))
    if not files:
        raise FileNotFoundError("No compiler comparison results found")
    with files[-1].open() as f:
        return json.load(f)


def load_ablation() -> dict:
    """Load latest ablation study results."""
    files = sorted(RESULTS_DIR.glob("ablation/ablation_*.json"))
    if not files:
        raise FileNotFoundError("No ablation results found")
    with files[-1].open() as f:
        return json.load(f)


def fig_compiler_comparison_2q(data: dict) -> None:
    """Figure: 2Q gate reduction by compiler and circuit type.

    Grouped bar chart with circuit types on x-axis, compilers as bars.
    Focus on 2Q gates since they dominate hardware error budgets.
    """
    # Subset of compilers to show (skip L0 which is always 0)
    show_compilers = ["QCO", "Qiskit-L1", "Qiskit-L3", "Qiskit-L3-IQM"]
    circuit_types = ["GHZ", "QFT", "QAOA", "Random"]
    colors = ["#2196F3", "#FFC107", "#FF5722", "#9C27B0"]

    by_type = data["summary"]["by_circuit_type"]

    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(circuit_types))
    width = 0.18
    offsets = np.arange(len(show_compilers)) - (len(show_compilers) - 1) / 2

    for i, compiler in enumerate(show_compilers):
        vals = []
        for ctype in circuit_types:
            if ctype in by_type and compiler in by_type[ctype]:
                vals.append(by_type[ctype][compiler]["mean_2q_reduction"])
            else:
                vals.append(0.0)
        bars = ax.bar(x + offsets[i] * width, vals, width * 0.9,
                      label=compiler, color=colors[i], edgecolor="white", linewidth=0.5)

    ax.set_xlabel("Circuit Type")
    ax.set_ylabel("Two-Qubit Gate Reduction (%)")
    ax.set_title("Two-Qubit Gate Reduction by Compiler")
    ax.set_xticks(x)
    ax.set_xticklabels(circuit_types)
    ax.legend(loc="upper left", framealpha=0.9)
    ax.set_ylim(-30, 110)
    ax.axhline(y=0, color="gray", linewidth=0.5, linestyle="-")
    ax.grid(axis="y", alpha=0.3)

    path = FIGURES_DIR / "compiler_comparison_2q.pdf"
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_compiler_comparison_overall(data: dict) -> None:
    """Figure: Overall gate reduction across all compilers.

    Shows both total gate reduction and 2Q gate reduction side by side.
    """
    show_compilers = ["QCO", "Qiskit-L1", "Qiskit-L2", "Qiskit-L3",
                      "Qiskit-L1-IQM", "Qiskit-L3-IQM"]
    summary = data["summary"]["compilers"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    # Left panel: Total gate reduction
    compilers = [c for c in show_compilers if c in summary]
    gate_reds = [summary[c]["gate_reduction_pct"]["mean"] for c in compilers]
    gate_stds = [summary[c]["gate_reduction_pct"]["std"] for c in compilers]

    colors = []
    for c in compilers:
        if c == "QCO":
            colors.append("#2196F3")
        elif "IQM" in c:
            colors.append("#9C27B0")
        else:
            colors.append("#FF9800")

    bars1 = ax1.bar(range(len(compilers)), gate_reds, yerr=gate_stds,
                    color=colors, edgecolor="white", linewidth=0.5,
                    capsize=3, error_kw={"linewidth": 0.8})
    ax1.set_xticks(range(len(compilers)))
    ax1.set_xticklabels(compilers, rotation=30, ha="right")
    ax1.set_ylabel("Total Gate Reduction (%)")
    ax1.set_title("(a) Total Gate Reduction")
    ax1.axhline(y=0, color="gray", linewidth=0.5)
    ax1.grid(axis="y", alpha=0.3)

    # Right panel: 2Q gate reduction
    twoq_reds = [summary[c]["two_q_reduction_pct"]["mean"] for c in compilers]
    twoq_stds = [summary[c]["two_q_reduction_pct"]["std"] for c in compilers]

    bars2 = ax2.bar(range(len(compilers)), twoq_reds, yerr=twoq_stds,
                    color=colors, edgecolor="white", linewidth=0.5,
                    capsize=3, error_kw={"linewidth": 0.8})
    ax2.set_xticks(range(len(compilers)))
    ax2.set_xticklabels(compilers, rotation=30, ha="right")
    ax2.set_ylabel("Two-Qubit Gate Reduction (%)")
    ax2.set_title("(b) Two-Qubit Gate Reduction")
    ax2.axhline(y=0, color="gray", linewidth=0.5)
    ax2.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    path = FIGURES_DIR / "compiler_comparison_overall.pdf"
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_ablation_cumulative(ablation: dict) -> None:
    """Figure: Cumulative pass addition showing gate reduction and fidelity."""
    cumulative = ablation["summary"]["cumulative"]

    configs = [
        ("identity", "Baseline"),
        ("cancel", "+Cancel"),
        ("cancel, commute", "+Commute"),
        ("cancel, commute, rotate", "+Rotate"),
        ("cancel, commute, rotate, identity", "+Identity"),
    ]

    gate_reds = []
    fidelities = []
    labels = []

    for key, label in configs:
        # Match by normalized key string
        # Find the matching key in the summary
        for k, v in cumulative.items():
            # Normalize both for comparison
            k_clean = k.replace("'", "").replace("[", "").replace("]", "").strip()
            key_clean = key.strip()
            if k_clean == key_clean:
                gate_reds.append(v["gate_reduction_pct"]["mean"])
                fidelities.append(v["fidelity"]["mean"])
                labels.append(label)
                break

    fig, ax1 = plt.subplots(figsize=(7, 4))

    x = np.arange(len(labels))
    color_gate = "#2196F3"
    color_fid = "#FF5722"

    bars = ax1.bar(x - 0.15, gate_reds, 0.3, label="Gate Reduction",
                   color=color_gate, edgecolor="white", linewidth=0.5)
    ax1.set_xlabel("Pass Configuration")
    ax1.set_ylabel("Gate Reduction (%)", color=color_gate)
    ax1.tick_params(axis="y", labelcolor=color_gate)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=15, ha="right")

    ax2 = ax1.twinx()
    ax2.plot(x, fidelities, "o-", color=color_fid, linewidth=2,
             markersize=8, label="Process Fidelity")
    ax2.set_ylabel("Process Fidelity", color=color_fid)
    ax2.tick_params(axis="y", labelcolor=color_fid)
    ax2.set_ylim(0.45, 0.65)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    ax1.set_title("Ablation Study: Cumulative Pass Addition")
    ax1.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    path = FIGURES_DIR / "ablation_cumulative.pdf"
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_ablation_leave_one_out(ablation: dict) -> None:
    """Figure: Leave-one-out ablation showing marginal contribution of each pass."""
    loo = ablation["summary"]["leave_one_out"]

    # Map config to which pass was removed
    pass_removed = {
        "commute, rotate, identity": "Cancel",
        "cancel, rotate, identity": "Commute",
        "cancel, commute, identity": "Rotate",
        "cancel, commute, rotate": "Identity",
    }

    # Get full pipeline as reference
    cumulative = ablation["summary"]["cumulative"]
    full_gate_red = None
    full_fidelity = None
    for k, v in cumulative.items():
        k_clean = k.replace("'", "").replace("[", "").replace("]", "").strip()
        if k_clean == "cancel, commute, rotate, identity":
            full_gate_red = v["gate_reduction_pct"]["mean"]
            full_fidelity = v["fidelity"]["mean"]
            break

    labels = []
    gate_reds = []
    fidelities = []
    for k, v in loo.items():
        k_clean = k.replace("'", "").replace("[", "").replace("]", "").strip()
        if k_clean in pass_removed:
            labels.append(f"w/o {pass_removed[k_clean]}")
            gate_reds.append(v["gate_reduction_pct"]["mean"])
            fidelities.append(v["fidelity"]["mean"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    x = np.arange(len(labels))
    colors = ["#f44336" if g < full_gate_red * 0.5 else "#FF9800"
              if g < full_gate_red * 0.95 else "#4CAF50" for g in gate_reds]

    # Left: Gate reduction
    ax1.barh(x, gate_reds, color=colors, edgecolor="white", linewidth=0.5)
    ax1.axvline(x=full_gate_red, color="blue", linestyle="--", linewidth=1.5,
                label=f"Full pipeline ({full_gate_red:.1f}%)")
    ax1.set_yticks(x)
    ax1.set_yticklabels(labels)
    ax1.set_xlabel("Gate Reduction (%)")
    ax1.set_title("(a) Gate Reduction Impact")
    ax1.legend(fontsize=8)
    ax1.grid(axis="x", alpha=0.3)

    # Right: Fidelity
    colors_f = ["#f44336" if f < full_fidelity * 0.9 else "#FF9800"
                if f < full_fidelity * 0.99 else "#4CAF50" for f in fidelities]
    ax2.barh(x, fidelities, color=colors_f, edgecolor="white", linewidth=0.5)
    ax2.axvline(x=full_fidelity, color="blue", linestyle="--", linewidth=1.5,
                label=f"Full pipeline ({full_fidelity:.4f})")
    ax2.set_yticks(x)
    ax2.set_yticklabels(labels)
    ax2.set_xlabel("Process Fidelity")
    ax2.set_title("(b) Fidelity Impact")
    ax2.legend(fontsize=8)
    ax2.grid(axis="x", alpha=0.3)

    fig.tight_layout()
    path = FIGURES_DIR / "ablation_leave_one_out.pdf"
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_compiler_by_circuit_type_heatmap(data: dict) -> None:
    """Heatmap showing 2Q reduction % for each compiler x circuit type."""
    show_compilers = ["QCO", "Qiskit-L1", "Qiskit-L3", "Qiskit-L1-IQM", "Qiskit-L3-IQM"]
    circuit_types = ["GHZ", "QFT", "QAOA", "Random"]
    by_type = data["summary"]["by_circuit_type"]

    matrix = np.zeros((len(show_compilers), len(circuit_types)))
    for j, ctype in enumerate(circuit_types):
        for i, compiler in enumerate(show_compilers):
            if ctype in by_type and compiler in by_type[ctype]:
                matrix[i, j] = by_type[ctype][compiler]["mean_2q_reduction"]

    fig, ax = plt.subplots(figsize=(6, 4))
    im = ax.imshow(matrix, cmap="RdYlGn", aspect="auto", vmin=-30, vmax=100)

    ax.set_xticks(range(len(circuit_types)))
    ax.set_xticklabels(circuit_types)
    ax.set_yticks(range(len(show_compilers)))
    ax.set_yticklabels(show_compilers)

    # Annotate cells
    for i in range(len(show_compilers)):
        for j in range(len(circuit_types)):
            val = matrix[i, j]
            color = "white" if abs(val) > 50 else "black"
            ax.text(j, i, f"{val:.1f}%", ha="center", va="center",
                    color=color, fontsize=9, fontweight="bold")

    ax.set_title("Two-Qubit Gate Reduction (%) by Compiler and Circuit Type")
    fig.colorbar(im, ax=ax, label="2Q Gate Reduction (%)")

    fig.tight_layout()
    path = FIGURES_DIR / "compiler_heatmap_2q.pdf"
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved: {path}")


def main() -> None:
    """Generate all paper figures."""
    print("Loading experiment results...")
    comp_data = load_compiler_comparison()
    ablation_data = load_ablation()

    print("\nGenerating figures:")

    fig_compiler_comparison_2q(comp_data)
    fig_compiler_comparison_overall(comp_data)
    fig_compiler_by_circuit_type_heatmap(comp_data)
    fig_ablation_cumulative(ablation_data)
    fig_ablation_leave_one_out(ablation_data)

    print(f"\nAll figures saved to {FIGURES_DIR}/")


if __name__ == "__main__":
    main()
