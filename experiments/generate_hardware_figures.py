#!/usr/bin/env python3
"""Hardware figures from the validated, provenanced IQM Garnet run.

Reads the newest experiments/reports/hardware_validation_*.json (which now
carries per-circuit job IDs, device, and validated-Lindblad simulated fidelity)
and produces two publication figures:

  fig_hardware_vs_sim.pdf   grouped bars: measured hardware fidelity vs validated
                            simulated fidelity per circuit (shows the sim-optimism
                            gap honestly, replacing the old "validated" overclaim)
  fig_hardware_gap.pdf      scatter of sim vs hw with y=x reference and the mean
                            gap annotated; quantifies unmodeled error budget

Usage:
    python experiments/generate_hardware_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
REPORTS_DIR = PROJECT_ROOT / "experiments" / "reports"
FIGURES_DIR = PROJECT_ROOT / "experiments" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

COLORS = {"hw": "#d62728", "sim": "#1f77b4", "ref": "#7f7f7f"}


def _style() -> None:
    plt.rcParams.update(
        {
            "font.size": 12,
            "font.family": "serif",
            "axes.grid": True,
            "grid.alpha": 0.3,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.dpi": 300,
            "savefig.format": "pdf",
        }
    )


def _latest_report() -> Path:
    matches = sorted(REPORTS_DIR.glob("hardware_validation_*.json"))
    if not matches:
        raise FileNotFoundError(f"No hardware_validation_*.json under {REPORTS_DIR}")
    return matches[-1]


def _short(name: str) -> str:
    """Compact circuit label for axis ticks."""
    return (
        name.replace("_p1_g0.50_b0.50", "")
        .replace("_density0.3", "")
        .replace("random", "rand")
    )


def load(report_path: Path) -> tuple[list[str], np.ndarray, np.ndarray, dict]:
    data = json.loads(report_path.read_text())
    circuits = [c for c in data["circuits"] if c.get("job_id")]  # real runs only
    if not circuits:
        raise ValueError(
            f"{report_path.name} has no circuits with job_id — refusing to plot "
            "unprovenanced data."
        )
    names = [_short(c["name"]) for c in circuits]
    hw = np.array([c["hardware_fidelity"] for c in circuits])
    sim = np.array([c["simulated_fidelity"] for c in circuits])
    return names, hw, sim, data


def fig_bars(names: list[str], hw: np.ndarray, sim: np.ndarray, device: str) -> Path:
    _style()
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(names))
    w = 0.4
    ax.bar(x - w / 2, sim, w, label="Simulated (validated Lindblad)", color=COLORS["sim"])
    ax.bar(x + w / 2, hw, w, label=f"Measured ({device})", color=COLORS["hw"])
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=30, ha="right")
    ax.set_ylabel("Process fidelity")
    ax.set_ylim(0, 1.0)
    ax.set_title("Validated simulation vs measured hardware fidelity")
    ax.legend()
    fig.tight_layout()
    path = FIGURES_DIR / "fig_hardware_vs_sim.pdf"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_gap(hw: np.ndarray, sim: np.ndarray) -> Path:
    _style()
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(sim, hw, s=70, color=COLORS["hw"], alpha=0.8, zorder=3)
    ax.plot([0, 1], [0, 1], "--", color=COLORS["ref"], label="hw = sim (perfect model)")
    mean_gap = float(np.mean(sim - hw))
    # Pearson correlation of the ranking the model gets right even when biased.
    if len(hw) > 1 and np.std(hw) > 0 and np.std(sim) > 0:
        r = float(np.corrcoef(sim, hw)[0, 1])
        ax.text(
            0.05,
            0.92,
            f"mean sim$-$hw gap = {mean_gap:.2f}\nPearson r = {r:.2f}",
            transform=ax.transAxes,
            va="top",
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8},
        )
    ax.set_xlabel("Simulated fidelity (validated Lindblad)")
    ax.set_ylabel("Measured hardware fidelity")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title("Sim-optimism gap on IQM Garnet")
    ax.legend(loc="lower right")
    fig.tight_layout()
    path = FIGURES_DIR / "fig_hardware_gap.pdf"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> None:
    report = _latest_report()
    names, hw, sim, data = load(report)
    device = data["circuits"][0].get("device") or "garnet"
    print(f"Source: {report.name}  ({len(names)} provenanced circuits, device={device})")
    print(f"  mean hw={hw.mean():.3f}  mean sim={sim.mean():.3f}  gap={float((sim-hw).mean()):.3f}")
    for p in (fig_bars(names, hw, sim, device), fig_gap(hw, sim)):
        print(f"  saved {p}")


if __name__ == "__main__":
    main()
