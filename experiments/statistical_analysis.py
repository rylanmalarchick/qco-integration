#!/usr/bin/env python3
"""Comprehensive statistical analysis and LaTeX table generation for ACM TQC paper.

Reads experiment results from JSON files and produces:
  - Statistical tests (Wilcoxon, Kruskal-Wallis, bootstrap CIs, Cohen's d)
  - 7 publication-ready LaTeX tables
  - Summary text file

Usage:
    .venv/bin/python3 experiments/statistical_analysis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"

COMPILER_PATH = RESULTS_DIR / "compiler_comparison" / "comparison_detail_20260207_204727.json"
ABLATION_PATH = RESULTS_DIR / "ablation" / "ablation_20260207_195322.json"
BASELINE_PATH = RESULTS_DIR / "acm_tqc_real" / "baseline_20260207_204438.json"
PER_PASS_PATH = RESULTS_DIR / "acm_tqc_real" / "per_pass_20260207_204449.json"
PASS_COMB_PATH = RESULTS_DIR / "acm_tqc_real" / "pass_combinations_20260207_204507.json"

LATEX_OUT = RESULTS_DIR / "latex_tables.tex"
SUMMARY_OUT = RESULTS_DIR / "statistical_summary.txt"


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def filter_valid(results: list[dict]) -> list[dict]:
    """Remove results with non-null error."""
    return [r for r in results if r.get("error") is None]


def safe_2q(metrics: dict, prefix: str) -> int:
    """Get 2Q gate count from metrics, falling back to 0."""
    return metrics.get(f"{prefix}_2q_gates", 0)


def gate_reduction_pct(inp: int, out: int) -> float:
    if inp == 0:
        return 0.0
    return (inp - out) / inp * 100.0


# ---------------------------------------------------------------------------
# Statistical utilities
# ---------------------------------------------------------------------------

def bootstrap_ci(
    data: np.ndarray,
    n_resamples: int = 10_000,
    ci: float = 0.95,
    rng_seed: int = 42,
) -> tuple[float, float, float]:
    """Return (mean, lower, upper) from bootstrap resampling."""
    rng = np.random.default_rng(rng_seed)
    means = np.empty(n_resamples)
    n = len(data)
    for i in range(n_resamples):
        sample = data[rng.integers(0, n, size=n)]
        means[i] = np.mean(sample)
    alpha = (1 - ci) / 2
    lo = np.percentile(means, alpha * 100)
    hi = np.percentile(means, (1 - alpha) * 100)
    return float(np.mean(data)), float(lo), float(hi)


def cohens_d(group1: np.ndarray, group2: np.ndarray) -> float:
    """Cohen's d effect size (pooled SD)."""
    n1, n2 = len(group1), len(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled_std == 0:
        return 0.0
    return float((np.mean(group1) - np.mean(group2)) / pooled_std)


def fmt_pval(p: float) -> str:
    """Format p-value for LaTeX."""
    if p < 0.001:
        return "$p < 0.001$"
    return f"$p = {p:.3f}$"


def fmt_pval_txt(p: float) -> str:
    if p < 0.001:
        return "p < 0.001"
    return f"p = {p:.3f}"


# ---------------------------------------------------------------------------
# Compiler comparison analysis
# ---------------------------------------------------------------------------

def analyse_compiler_comparison(comp_data: dict) -> dict[str, Any]:
    results = filter_valid(comp_data["results"])

    # Build per-compiler per-circuit data
    compilers = sorted({r["compiler"] for r in results})
    circuit_names = sorted({r["circuit_name"] for r in results})
    circuit_types = sorted({r["circuit_type"] for r in results})

    # Index: (compiler, circuit_name) -> result
    idx: dict[tuple[str, str], dict] = {}
    for r in results:
        idx[(r["compiler"], r["circuit_name"])] = r

    # Per-compiler aggregate stats
    compiler_stats: dict[str, dict] = {}
    for comp in compilers:
        rows = [r for r in results if r["compiler"] == comp]
        gate_red = np.array([r["gate_reduction_pct"] for r in rows])
        twoq_red = np.array([r["two_q_reduction_pct"] for r in rows])
        depth_red = np.array([r["depth_reduction_pct"] for r in rows])
        times = np.array([r["compile_time_s"] for r in rows])

        gate_mean, gate_lo, gate_hi = bootstrap_ci(gate_red)
        twoq_mean, twoq_lo, twoq_hi = bootstrap_ci(twoq_red)
        depth_mean, depth_lo, depth_hi = bootstrap_ci(depth_red)

        compiler_stats[comp] = {
            "gate_red_mean": gate_mean,
            "gate_red_ci": (gate_lo, gate_hi),
            "twoq_red_mean": twoq_mean,
            "twoq_red_ci": (twoq_lo, twoq_hi),
            "depth_red_mean": depth_mean,
            "depth_red_ci": (depth_lo, depth_hi),
            "time_mean": float(np.mean(times)),
            "time_median": float(np.median(times)),
            "n": len(rows),
        }

    # Wilcoxon signed-rank: QCO vs each other compiler (paired by circuit, on 2Q reduction)
    wilcoxon_results: dict[str, dict] = {}
    qco_twoq = {r["circuit_name"]: r["two_q_reduction_pct"]
                 for r in results if r["compiler"] == "QCO"}

    for comp in compilers:
        if comp == "QCO":
            continue
        other_twoq = {r["circuit_name"]: r["two_q_reduction_pct"]
                      for r in results if r["compiler"] == comp}
        # Align by circuit
        common = sorted(set(qco_twoq.keys()) & set(other_twoq.keys()))
        if len(common) < 2:
            continue
        x = np.array([qco_twoq[c] for c in common])
        y = np.array([other_twoq[c] for c in common])
        diff = x - y
        # Wilcoxon needs non-zero differences
        nonzero = diff[diff != 0]
        if len(nonzero) < 1:
            wilcoxon_results[comp] = {"stat": 0, "p": 1.0, "n_pairs": len(common)}
            continue
        stat_val, p_val = stats.wilcoxon(nonzero)
        wilcoxon_results[comp] = {
            "stat": float(stat_val),
            "p": float(p_val),
            "n_pairs": len(common),
            "n_nonzero": len(nonzero),
        }

    # Cohen's d: QCO vs Qiskit-L3 and QCO vs Qiskit-L3-IQM
    cohens_d_results: dict[str, float] = {}
    qco_arr = np.array([qco_twoq[c] for c in circuit_names if c in qco_twoq])
    for target in ["Qiskit-L3", "Qiskit-L3-IQM"]:
        other = {r["circuit_name"]: r["two_q_reduction_pct"]
                 for r in results if r["compiler"] == target}
        common = sorted(set(qco_twoq.keys()) & set(other.keys()))
        x = np.array([qco_twoq[c] for c in common])
        y = np.array([other[c] for c in common])
        cohens_d_results[target] = cohens_d(x, y)

    # Head-to-head win/loss/tie (by output 2Q gate count, lower is better)
    head_to_head: dict[str, dict[str, int]] = {}
    for comp in compilers:
        if comp == "QCO":
            continue
        wins = losses = ties = 0
        for cname in circuit_names:
            qco_r = idx.get(("QCO", cname))
            other_r = idx.get((comp, cname))
            if qco_r is None or other_r is None:
                continue
            q2q = qco_r["output_2q_gates"]
            o2q = other_r["output_2q_gates"]
            if q2q < o2q:
                wins += 1
            elif q2q > o2q:
                losses += 1
            else:
                ties += 1
        head_to_head[comp] = {"wins": wins, "losses": losses, "ties": ties}

    # Per circuit type breakdown
    per_type: dict[str, dict[str, dict]] = {}
    for ctype in circuit_types:
        per_type[ctype] = {}
        for comp in compilers:
            rows = [r for r in results
                    if r["compiler"] == comp and r["circuit_type"] == ctype]
            if not rows:
                continue
            twoq = np.array([r["two_q_reduction_pct"] for r in rows])
            gate = np.array([r["gate_reduction_pct"] for r in rows])
            per_type[ctype][comp] = {
                "twoq_red_mean": float(np.mean(twoq)),
                "gate_red_mean": float(np.mean(gate)),
                "n": len(rows),
            }

    return {
        "compilers": compilers,
        "circuit_names": circuit_names,
        "circuit_types": circuit_types,
        "compiler_stats": compiler_stats,
        "wilcoxon": wilcoxon_results,
        "cohens_d": cohens_d_results,
        "head_to_head": head_to_head,
        "per_type": per_type,
    }


# ---------------------------------------------------------------------------
# Ablation analysis
# ---------------------------------------------------------------------------

def analyse_ablation(abl_data: dict, baseline_data: dict) -> dict[str, Any]:
    groups = abl_data["groups"]

    # Baseline: identity pass only (from baseline campaign)
    baseline_results = filter_valid(baseline_data["results"])
    baseline_by_circuit: dict[str, dict] = {}
    for r in baseline_results:
        m = r["metrics"]
        baseline_by_circuit[r["circuit_name"]] = m

    baseline_gate_red = []
    for m in baseline_by_circuit.values():
        inp = m["input_gates"]
        out = m["post_opt_gates"]
        baseline_gate_red.append(gate_reduction_pct(inp, out))
    baseline_gate_red_arr = np.array(baseline_gate_red)

    # --- Individual passes ---
    individual = filter_valid(groups["individual"]["results"])
    pass_names = sorted({tuple(r["passes"]) for r in individual})

    individual_stats: dict[str, dict] = {}
    for pname in pass_names:
        label = "+".join(pname)
        rows = [r for r in individual if tuple(r["passes"]) == pname]
        gate_reds = []
        twoq_reds = []
        fidelities = []
        for r in rows:
            m = r["metrics"]
            inp_g = m["input_gates"]
            out_g = m["post_opt_gates"]
            gate_reds.append(gate_reduction_pct(inp_g, out_g))
            inp_2q = safe_2q(m, "input")
            out_2q = safe_2q(m, "post_opt")
            twoq_reds.append(gate_reduction_pct(inp_2q, out_2q))
            fidelities.append(m.get("process_fidelity", 0.0))
        gate_arr = np.array(gate_reds)
        twoq_arr = np.array(twoq_reds)
        fid_arr = np.array(fidelities)
        d = cohens_d(gate_arr, baseline_gate_red_arr)
        individual_stats[label] = {
            "gate_red_mean": float(np.mean(gate_arr)),
            "twoq_red_mean": float(np.mean(twoq_arr)),
            "fidelity_mean": float(np.mean(fid_arr)),
            "cohens_d": d,
            "n": len(rows),
        }

    # --- Leave-one-out ---
    leave_one_out = filter_valid(groups["leave_one_out"]["results"])
    loo_configs = sorted({tuple(r["passes"]) for r in leave_one_out})

    # Full pipeline result: from ordering group, the default order
    ordering = filter_valid(groups["ordering"]["results"])
    default_order = ("cancel", "commute", "rotate", "identity")
    full_rows = [r for r in ordering if tuple(r["passes"]) == default_order]
    full_gate_reds = []
    for r in full_rows:
        m = r["metrics"]
        full_gate_reds.append(gate_reduction_pct(m["input_gates"], m["post_opt_gates"]))
    full_gate_red_arr = np.array(full_gate_reds)

    loo_stats: dict[str, dict] = {}
    all_passes = {"cancel", "commute", "rotate", "identity"}
    for config in loo_configs:
        missing = all_passes - set(config)
        label = "w/o " + "+".join(sorted(missing))
        rows = [r for r in leave_one_out if tuple(r["passes"]) == config]
        gate_reds = []
        twoq_reds = []
        fidelities = []
        for r in rows:
            m = r["metrics"]
            gate_reds.append(gate_reduction_pct(m["input_gates"], m["post_opt_gates"]))
            twoq_reds.append(gate_reduction_pct(safe_2q(m, "input"), safe_2q(m, "post_opt")))
            fidelities.append(m.get("process_fidelity", 0.0))
        gate_arr = np.array(gate_reds)
        fid_arr = np.array(fidelities)
        # Marginal contribution = full pipeline - leave-one-out
        marginal = float(np.mean(full_gate_red_arr)) - float(np.mean(gate_arr))
        d = cohens_d(full_gate_red_arr, gate_arr)
        loo_stats[label] = {
            "passes": list(config),
            "gate_red_mean": float(np.mean(gate_arr)),
            "twoq_red_mean": float(np.mean(np.array(twoq_reds))),
            "fidelity_mean": float(np.mean(fid_arr)),
            "marginal_contribution": marginal,
            "cohens_d": d,
            "n": len(rows),
        }

    # --- Ordering effects ---
    ordering_configs = sorted({tuple(r["passes"]) for r in ordering})
    ordering_stats: dict[str, dict] = {}
    ordering_gate_reds_by_config: dict[str, np.ndarray] = {}

    for config in ordering_configs:
        label = " -> ".join(config)
        rows = [r for r in ordering if tuple(r["passes"]) == config]
        gate_reds = []
        twoq_reds = []
        fidelities = []
        for r in rows:
            m = r["metrics"]
            gate_reds.append(gate_reduction_pct(m["input_gates"], m["post_opt_gates"]))
            twoq_reds.append(gate_reduction_pct(safe_2q(m, "input"), safe_2q(m, "post_opt")))
            fidelities.append(m.get("process_fidelity", 0.0))
        gate_arr = np.array(gate_reds)
        twoq_arr = np.array(twoq_reds)
        fid_arr = np.array(fidelities)
        mean_val, lo, hi = bootstrap_ci(gate_arr)
        ordering_stats[label] = {
            "gate_red_mean": mean_val,
            "gate_red_ci": (lo, hi),
            "twoq_red_mean": float(np.mean(twoq_arr)),
            "fidelity_mean": float(np.mean(fid_arr)),
            "n": len(rows),
        }
        ordering_gate_reds_by_config[label] = gate_arr

    # Kruskal-Wallis across orderings
    kw_groups = list(ordering_gate_reds_by_config.values())
    if len(kw_groups) >= 2:
        kw_stat, kw_p = stats.kruskal(*kw_groups)
    else:
        kw_stat, kw_p = 0.0, 1.0

    return {
        "individual": individual_stats,
        "leave_one_out": loo_stats,
        "ordering": ordering_stats,
        "kruskal_wallis": {"stat": float(kw_stat), "p": float(kw_p)},
    }


# ---------------------------------------------------------------------------
# Campaign summary analysis (for Table 1 and Table 2)
# ---------------------------------------------------------------------------

def analyse_campaign(
    baseline_data: dict,
    per_pass_data: dict,
    pass_comb_data: dict,
) -> dict[str, Any]:
    baseline = filter_valid(baseline_data["results"])
    per_pass = filter_valid(per_pass_data["results"])
    pass_comb = filter_valid(pass_comb_data["results"])

    # Table 1: Summary statistics from the full pipeline (pass_combinations,
    # take the full 4-pass config)
    full_config = ("cancel", "commute", "rotate", "identity")
    full_results = [r for r in pass_comb if tuple(r["passes"]) == full_config]
    if not full_results:
        # Fall back: use the longest pass combo
        max_len = max(len(r["passes"]) for r in pass_comb)
        full_results = [r for r in pass_comb if len(r["passes"]) == max_len]

    fidelities = []
    gate_reds = []
    for r in full_results:
        m = r["metrics"]
        fidelities.append(m.get("process_fidelity", 0.0))
        inp = m["input_gates"]
        out = m["post_opt_gates"]
        gate_reds.append(gate_reduction_pct(inp, out))
    fid_arr = np.array(fidelities)
    gate_arr = np.array(gate_reds)

    total_circuits = len(baseline)  # corpus size

    summary = {
        "total_circuits": total_circuits,
        "total_runs": len(baseline) + len(per_pass) + len(pass_comb),
        "mean_fidelity": float(np.mean(fid_arr)),
        "median_fidelity": float(np.median(fid_arr)),
        "std_fidelity": float(np.std(fid_arr)),
        "mean_gate_red": float(np.mean(gate_arr)),
        "median_gate_red": float(np.median(gate_arr)),
        "max_gate_red": float(np.max(gate_arr)),
        "min_gate_red": float(np.min(gate_arr)),
    }

    # Table 2: Per-pass effectiveness
    # Group per_pass by pass name
    pass_names_set = sorted({tuple(r["passes"]) for r in per_pass})
    pass_effectiveness: dict[str, dict] = {}

    for pname in pass_names_set:
        label = "+".join(pname)
        rows = [r for r in per_pass if tuple(r["passes"]) == pname]
        gates_removed = 0
        circuits_improved = 0
        total_input = 0
        for r in rows:
            m = r["metrics"]
            inp = m["input_gates"]
            out = m["post_opt_gates"]
            removed = inp - out
            gates_removed += removed
            total_input += inp
            if removed > 0:
                circuits_improved += 1
        pass_effectiveness[label] = {
            "gates_removed": gates_removed,
            "pct_improved": circuits_improved / len(rows) * 100 if rows else 0,
            "n_circuits": len(rows),
            "circuits_improved": circuits_improved,
        }

    # Rank by gates_removed
    ranked = sorted(pass_effectiveness.items(), key=lambda x: x[1]["gates_removed"], reverse=True)
    for rank_i, (label, info) in enumerate(ranked, 1):
        info["rank"] = rank_i

    return {
        "summary": summary,
        "pass_effectiveness": pass_effectiveness,
    }


# ---------------------------------------------------------------------------
# LaTeX table generators
# ---------------------------------------------------------------------------

def _bold_best(values: list[float], fmt: str = ".1f", higher_better: bool = True) -> list[str]:
    """Return formatted strings, bolding the best value."""
    if not values:
        return []
    if higher_better:
        best_val = max(values)
    else:
        best_val = min(values)
    out = []
    for v in values:
        s = f"{v:{fmt}}"
        if v == best_val:
            s = "\\textbf{" + s + "}"
        out.append(s)
    return out


def generate_table1(campaign: dict) -> str:
    """Table 1: Updated Summary Statistics."""
    s = campaign["summary"]
    lines = [
        "\\begin{table}[t]",
        "  \\centering",
        "  \\caption{Summary statistics for the full optimization pipeline across the benchmark corpus.}",
        "  \\label{tab:summary-stats}",
        "  \\begin{tabular}{lr}",
        "    \\toprule",
        "    \\textbf{Metric} & \\textbf{Value} \\\\",
        "    \\midrule",
        f"    Total circuits & {s['total_circuits']} \\\\",
        f"    Total experiment runs & {s['total_runs']} \\\\",
        "    \\midrule",
        f"    Mean process fidelity & {s['mean_fidelity']:.3f} \\\\",
        f"    Median process fidelity & {s['median_fidelity']:.3f} \\\\",
        f"    Std.\\ dev.\\ fidelity & {s['std_fidelity']:.3f} \\\\",
        "    \\midrule",
        f"    Mean gate reduction & {s['mean_gate_red']:.1f}\\% \\\\",
        f"    Median gate reduction & {s['median_gate_red']:.1f}\\% \\\\",
        f"    Max gate reduction & {s['max_gate_red']:.1f}\\% \\\\",
        "    \\bottomrule",
        "  \\end{tabular}",
        "\\end{table}",
    ]
    return "\n".join(lines)


def generate_table2(campaign: dict) -> str:
    """Table 2: Updated Pass Effectiveness."""
    pe = campaign["pass_effectiveness"]
    # Sort by rank
    ranked = sorted(pe.items(), key=lambda x: x[1]["rank"])
    lines = [
        "\\begin{table}[t]",
        "  \\centering",
        "  \\caption{Individual pass effectiveness on the benchmark corpus.}",
        "  \\label{tab:pass-effectiveness}",
        "  \\begin{tabular}{llrrr}",
        "    \\toprule",
        "    \\textbf{Rank} & \\textbf{Pass} & \\textbf{Gates Removed} & \\textbf{\\% Circuits Improved} & \\textbf{$N$} \\\\",
        "    \\midrule",
    ]
    for label, info in ranked:
        lines.append(
            f"    {info['rank']} & {label} & {info['gates_removed']} "
            f"& {info['pct_improved']:.1f}\\% & {info['n_circuits']} \\\\"
        )
    lines += [
        "    \\bottomrule",
        "  \\end{tabular}",
        "\\end{table}",
    ]
    return "\n".join(lines)


def generate_table3(comp_analysis: dict) -> str:
    """Table 3: Compiler Comparison."""
    cs = comp_analysis["compiler_stats"]
    wil = comp_analysis["wilcoxon"]
    compilers = comp_analysis["compilers"]

    # Collect column values for bolding
    gate_vals = [cs[c]["gate_red_mean"] for c in compilers]
    twoq_vals = [cs[c]["twoq_red_mean"] for c in compilers]
    depth_vals = [cs[c]["depth_red_mean"] for c in compilers]
    time_vals = [cs[c]["time_mean"] for c in compilers]

    gate_bold = _bold_best(gate_vals, ".1f", higher_better=True)
    twoq_bold = _bold_best(twoq_vals, ".1f", higher_better=True)
    depth_bold = _bold_best(depth_vals, ".1f", higher_better=True)
    time_bold = _bold_best(time_vals, ".4f", higher_better=False)

    lines = [
        "\\begin{table}[t]",
        "  \\centering",
        "  \\caption{Compiler comparison across 371 benchmark circuits. $p$-values from paired Wilcoxon signed-rank test on 2-qubit gate reduction vs.\\ QCO.}",
        "  \\label{tab:compiler-comparison}",
        "  \\begin{tabular}{lrrrrr}",
        "    \\toprule",
        "    \\textbf{Compiler} & \\textbf{Gate Red.\\%} & \\textbf{2Q Red.\\%} & \\textbf{Depth Red.\\%} & \\textbf{Time (s)} & \\textbf{$p$-value} \\\\",
        "    \\midrule",
    ]
    for i, comp in enumerate(compilers):
        if comp == "QCO":
            pval_str = "---"
        else:
            w = wil.get(comp)
            pval_str = fmt_pval(w["p"]) if w else "---"
        lines.append(
            f"    {comp} & {gate_bold[i]}\\% & {twoq_bold[i]}\\% "
            f"& {depth_bold[i]}\\% & {time_bold[i]} & {pval_str} \\\\"
        )
    lines += [
        "    \\bottomrule",
        "  \\end{tabular}",
        "\\end{table}",
    ]
    return "\n".join(lines)


def generate_table4(comp_analysis: dict) -> str:
    """Table 4: Compiler Comparison by Circuit Type."""
    pt = comp_analysis["per_type"]
    circuit_types = comp_analysis["circuit_types"]
    focus_compilers = ["QCO", "Qiskit-L3", "Qiskit-L3-IQM"]

    lines = [
        "\\begin{table}[t]",
        "  \\centering",
        "  \\caption{Mean 2-qubit gate reduction (\\%) by circuit type and compiler.}",
        "  \\label{tab:compiler-by-type}",
        "  \\begin{tabular}{lrrr}",
        "    \\toprule",
        "    \\textbf{Circuit Type} & \\textbf{QCO} & \\textbf{Qiskit-L3} & \\textbf{Qiskit-L3-IQM} \\\\",
        "    \\midrule",
    ]
    for ctype in circuit_types:
        vals = []
        for comp in focus_compilers:
            info = pt.get(ctype, {}).get(comp)
            vals.append(info["twoq_red_mean"] if info else 0.0)
        bold = _bold_best(vals, ".1f", higher_better=True)
        lines.append(f"    {ctype} & {bold[0]}\\% & {bold[1]}\\% & {bold[2]}\\% \\\\")
    lines += [
        "    \\bottomrule",
        "  \\end{tabular}",
        "\\end{table}",
    ]
    return "\n".join(lines)


def generate_table5(abl_analysis: dict) -> str:
    """Table 5: Ablation - Individual Passes."""
    ind = abl_analysis["individual"]
    # Sort by gate_red descending
    ranked = sorted(ind.items(), key=lambda x: x[1]["gate_red_mean"], reverse=True)

    lines = [
        "\\begin{table}[t]",
        "  \\centering",
        "  \\caption{Ablation study: individual pass effectiveness. Cohen's $d$ measures effect size relative to the identity-only baseline.}",
        "  \\label{tab:ablation-individual}",
        "  \\begin{tabular}{lrrrr}",
        "    \\toprule",
        "    \\textbf{Pass} & \\textbf{Gate Red.\\%} & \\textbf{2Q Red.\\%} & \\textbf{Fidelity} & \\textbf{Cohen's $d$} \\\\",
        "    \\midrule",
    ]
    gate_vals = [v["gate_red_mean"] for _, v in ranked]
    gate_bold = _bold_best(gate_vals, ".1f", higher_better=True)
    twoq_vals = [v["twoq_red_mean"] for _, v in ranked]
    twoq_bold = _bold_best(twoq_vals, ".1f", higher_better=True)
    fid_vals = [v["fidelity_mean"] for _, v in ranked]
    fid_bold = _bold_best(fid_vals, ".3f", higher_better=True)

    for i, (label, info) in enumerate(ranked):
        d_str = f"{info['cohens_d']:.2f}"
        lines.append(
            f"    {label} & {gate_bold[i]}\\% & {twoq_bold[i]}\\% "
            f"& {fid_bold[i]} & {d_str} \\\\"
        )
    lines += [
        "    \\bottomrule",
        "  \\end{tabular}",
        "\\end{table}",
    ]
    return "\n".join(lines)


def generate_table6(abl_analysis: dict) -> str:
    """Table 6: Ablation - Leave-One-Out."""
    loo = abl_analysis["leave_one_out"]
    ranked = sorted(loo.items(), key=lambda x: x[1]["gate_red_mean"], reverse=True)

    lines = [
        "\\begin{table}[t]",
        "  \\centering",
        "  \\caption{Leave-one-out ablation: each row omits one pass from the full pipeline. Marginal contribution shows the performance drop when that pass is removed.}",
        "  \\label{tab:ablation-loo}",
        "  \\begin{tabular}{lrrrrr}",
        "    \\toprule",
        "    \\textbf{Configuration} & \\textbf{Gate Red.\\%} & \\textbf{2Q Red.\\%} & \\textbf{Fidelity} & \\textbf{Marginal} & \\textbf{Cohen's $d$} \\\\",
        "    \\midrule",
    ]
    for label, info in ranked:
        lines.append(
            f"    {label} & {info['gate_red_mean']:.1f}\\% & {info['twoq_red_mean']:.1f}\\% "
            f"& {info['fidelity_mean']:.3f} & {info['marginal_contribution']:.1f}\\% "
            f"& {info['cohens_d']:.2f} \\\\"
        )
    lines += [
        "    \\bottomrule",
        "  \\end{tabular}",
        "\\end{table}",
    ]
    return "\n".join(lines)


def generate_table7(abl_analysis: dict) -> str:
    """Table 7: Ablation - Ordering Effects."""
    ordering = abl_analysis["ordering"]
    kw = abl_analysis["kruskal_wallis"]
    ranked = sorted(ordering.items(), key=lambda x: x[1]["gate_red_mean"], reverse=True)

    lines = [
        "\\begin{table}[t]",
        "  \\centering",
        "  \\caption{Pass ordering effects on optimization. Kruskal--Wallis test: $H = " + f"{kw['stat']:.2f}" + "$, " + fmt_pval(kw['p']) + ".}",
        "  \\label{tab:ablation-ordering}",
        "  \\begin{tabular}{lrrrr}",
        "    \\toprule",
        "    \\textbf{Ordering} & \\textbf{Gate Red.\\%} & \\textbf{95\\% CI} & \\textbf{2Q Red.\\%} & \\textbf{Fidelity} \\\\",
        "    \\midrule",
    ]
    gate_vals = [v["gate_red_mean"] for _, v in ranked]
    gate_bold = _bold_best(gate_vals, ".1f", higher_better=True)

    for i, (label, info) in enumerate(ranked):
        lo, hi = info["gate_red_ci"]
        ci_str = f"[{lo:.1f}, {hi:.1f}]"
        # Use right arrow in LaTeX
        latex_label = label.replace(" -> ", " $\\to$ ")
        lines.append(
            f"    {latex_label} & {gate_bold[i]}\\% & {ci_str} "
            f"& {info['twoq_red_mean']:.1f}\\% & {info['fidelity_mean']:.3f} \\\\"
        )
    lines += [
        "    \\bottomrule",
        "  \\end{tabular}",
        "\\end{table}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Text summary
# ---------------------------------------------------------------------------

def generate_text_summary(
    comp_analysis: dict,
    abl_analysis: dict,
    campaign: dict,
) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("STATISTICAL ANALYSIS SUMMARY - QCO ACM TQC Submission")
    lines.append("=" * 72)

    # Campaign summary
    s = campaign["summary"]
    lines.append("")
    lines.append("1. CAMPAIGN SUMMARY (Full Pipeline)")
    lines.append("-" * 40)
    lines.append(f"   Total circuits: {s['total_circuits']}")
    lines.append(f"   Total experiment runs: {s['total_runs']}")
    lines.append(f"   Mean process fidelity: {s['mean_fidelity']:.3f}")
    lines.append(f"   Median process fidelity: {s['median_fidelity']:.3f}")
    lines.append(f"   Std. dev. fidelity: {s['std_fidelity']:.3f}")
    lines.append(f"   Mean gate reduction: {s['mean_gate_red']:.1f}%")
    lines.append(f"   Median gate reduction: {s['median_gate_red']:.1f}%")
    lines.append(f"   Max gate reduction: {s['max_gate_red']:.1f}%")

    # Pass effectiveness
    pe = campaign["pass_effectiveness"]
    lines.append("")
    lines.append("2. PASS EFFECTIVENESS")
    lines.append("-" * 40)
    ranked = sorted(pe.items(), key=lambda x: x[1]["rank"])
    for label, info in ranked:
        lines.append(
            f"   #{info['rank']} {label}: "
            f"{info['gates_removed']} gates removed, "
            f"{info['pct_improved']:.1f}% circuits improved "
            f"(N={info['n_circuits']})"
        )

    # Compiler comparison
    cs = comp_analysis["compiler_stats"]
    lines.append("")
    lines.append("3. COMPILER COMPARISON")
    lines.append("-" * 40)
    for comp in comp_analysis["compilers"]:
        info = cs[comp]
        lo, hi = info["twoq_red_ci"]
        lines.append(
            f"   {comp:15s}: gate={info['gate_red_mean']:5.1f}%  "
            f"2Q={info['twoq_red_mean']:5.1f}% [{lo:.1f}, {hi:.1f}]  "
            f"depth={info['depth_red_mean']:5.1f}%  "
            f"time={info['time_mean']:.4f}s"
        )

    # Wilcoxon
    lines.append("")
    lines.append("   Wilcoxon signed-rank test (QCO vs each, on 2Q gate reduction):")
    for comp, w in comp_analysis["wilcoxon"].items():
        lines.append(
            f"   vs {comp:15s}: W={w['stat']:.1f}, "
            f"{fmt_pval_txt(w['p'])}, "
            f"N_pairs={w['n_pairs']}, N_nonzero={w.get('n_nonzero', 0)}"
        )

    # Cohen's d
    lines.append("")
    lines.append("   Cohen's d (QCO vs Qiskit, on 2Q gate reduction):")
    for comp, d in comp_analysis["cohens_d"].items():
        magnitude = "negligible"
        if abs(d) >= 0.8:
            magnitude = "large"
        elif abs(d) >= 0.5:
            magnitude = "medium"
        elif abs(d) >= 0.2:
            magnitude = "small"
        lines.append(f"   vs {comp}: d = {d:.3f} ({magnitude})")

    # Head-to-head
    lines.append("")
    lines.append("   Head-to-head (QCO wins/losses/ties by output 2Q gate count):")
    for comp, hth in comp_analysis["head_to_head"].items():
        lines.append(
            f"   vs {comp:15s}: W={hth['wins']} L={hth['losses']} T={hth['ties']}"
        )

    # Per circuit type
    lines.append("")
    lines.append("   Per circuit type (mean 2Q gate reduction %):")
    for ctype in comp_analysis["circuit_types"]:
        vals = []
        for comp in ["QCO", "Qiskit-L3", "Qiskit-L3-IQM"]:
            info = comp_analysis["per_type"].get(ctype, {}).get(comp)
            vals.append(f"{info['twoq_red_mean']:.1f}%" if info else "N/A")
        lines.append(f"   {ctype:8s}: QCO={vals[0]}  L3={vals[1]}  L3-IQM={vals[2]}")

    # Ablation
    lines.append("")
    lines.append("4. ABLATION STUDY")
    lines.append("-" * 40)

    lines.append("")
    lines.append("   Individual passes:")
    for label, info in sorted(abl_analysis["individual"].items(),
                              key=lambda x: x[1]["gate_red_mean"], reverse=True):
        lines.append(
            f"   {label:12s}: gate={info['gate_red_mean']:5.1f}%  "
            f"2Q={info['twoq_red_mean']:5.1f}%  "
            f"fidelity={info['fidelity_mean']:.3f}  "
            f"d={info['cohens_d']:.3f}"
        )

    lines.append("")
    lines.append("   Leave-one-out:")
    for label, info in sorted(abl_analysis["leave_one_out"].items(),
                              key=lambda x: x[1]["gate_red_mean"], reverse=True):
        lines.append(
            f"   {label:20s}: gate={info['gate_red_mean']:5.1f}%  "
            f"fidelity={info['fidelity_mean']:.3f}  "
            f"marginal={info['marginal_contribution']:+.1f}%  "
            f"d={info['cohens_d']:.3f}"
        )

    lines.append("")
    kw = abl_analysis["kruskal_wallis"]
    lines.append(
        f"   Ordering - Kruskal-Wallis: H={kw['stat']:.2f}, {fmt_pval_txt(kw['p'])}"
    )
    for label, info in sorted(abl_analysis["ordering"].items(),
                              key=lambda x: x[1]["gate_red_mean"], reverse=True):
        lo, hi = info["gate_red_ci"]
        lines.append(
            f"   {label:45s}: gate={info['gate_red_mean']:5.1f}% "
            f"[{lo:.1f}, {hi:.1f}]  "
            f"2Q={info['twoq_red_mean']:5.1f}%  "
            f"fidelity={info['fidelity_mean']:.3f}"
        )

    lines.append("")
    lines.append("=" * 72)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading experiment data...")
    comp_data = load_json(COMPILER_PATH)
    abl_data = load_json(ABLATION_PATH)
    baseline_data = load_json(BASELINE_PATH)
    per_pass_data = load_json(PER_PASS_PATH)
    pass_comb_data = load_json(PASS_COMB_PATH)

    print("Analysing compiler comparison...")
    comp_analysis = analyse_compiler_comparison(comp_data)

    print("Analysing ablation study...")
    abl_analysis = analyse_ablation(abl_data, baseline_data)

    print("Analysing campaign data...")
    campaign = analyse_campaign(baseline_data, per_pass_data, pass_comb_data)

    # Generate text summary
    summary_text = generate_text_summary(comp_analysis, abl_analysis, campaign)
    print()
    print(summary_text)

    # Generate LaTeX tables
    print("\nGenerating LaTeX tables...")
    tables = [
        ("% Table 1: Summary Statistics", generate_table1(campaign)),
        ("% Table 2: Pass Effectiveness", generate_table2(campaign)),
        ("% Table 3: Compiler Comparison", generate_table3(comp_analysis)),
        ("% Table 4: Compiler Comparison by Circuit Type", generate_table4(comp_analysis)),
        ("% Table 5: Ablation - Individual Passes", generate_table5(abl_analysis)),
        ("% Table 6: Ablation - Leave-One-Out", generate_table6(abl_analysis)),
        ("% Table 7: Ablation - Ordering Effects", generate_table7(abl_analysis)),
    ]

    latex_content = (
        "% Auto-generated LaTeX tables for ACM TQC submission\n"
        "% Generated by experiments/statistical_analysis.py\n"
        "% Requires: \\usepackage{booktabs}, \\usepackage{siunitx}\n\n"
    )
    for comment, table_tex in tables:
        latex_content += comment + "\n" + table_tex + "\n\n"

    # Write outputs
    LATEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    LATEX_OUT.write_text(latex_content)
    print(f"  LaTeX tables written to: {LATEX_OUT}")

    SUMMARY_OUT.write_text(summary_text)
    print(f"  Summary written to: {SUMMARY_OUT}")


if __name__ == "__main__":
    main()
