#!/usr/bin/env python3
"""Compiler Comparison Benchmark for ACM TQC Submission.

Compares gate count reduction, depth reduction, two-qubit gate reduction,
and compilation time across QCO (our C++ optimizer) and Qiskit transpiler
levels 0-3, with both virtual and IQM-realistic basis gates.

Key design decisions:
  - QCO counts gates in QASM 3.0 representation (e.g., cp as 1 gate)
  - Qiskit with basis_gates=None uses virtual u3 gates (consolidates rotations)
  - Qiskit with IQM basis gates decomposes to {cz, rx, ry, rz}
  - Two-qubit gate count is the fairest hardware-agnostic metric since
    2Q gates dominate error budgets on superconducting hardware

Usage:
    python experiments/benchmark_compilers.py [--quick] [--paper]
    python experiments/benchmark_compilers.py --quick   # 4-circuit small corpus
    python experiments/benchmark_compilers.py --paper   # Full 371-circuit corpus
    python experiments/benchmark_compilers.py           # Standard corpus (default)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bridge import CircuitOptimizerBridge  # noqa: E402
from src.corpus import (  # noqa: E402
    BenchmarkCircuit,
    CircuitCorpus,
    create_paper_corpus,
    create_small_corpus,
    create_standard_corpus,
)
from src.qasm import extract_metrics  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress verbose Qiskit/stevedore logging (each transpile pass gets logged)
for _noisy in ("qiskit", "stevedore", "qiskit.transpiler", "qiskit.compiler"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results" / "compiler_comparison"
QCO_BINARY = Path.home() / "dev/research/quantum-circuit-optimizer/build/quantum_circuit_optimizer"
QCO_PASSES = ["cancel", "commute", "rotate", "identity"]

# IQM Garnet native gate set: CZ + single-qubit rotations
IQM_BASIS_GATES = ["cz", "rx", "ry", "rz"]


@dataclass
class CompilerResult:
    """Result from a single compiler run on a single circuit."""

    compiler: str
    circuit_name: str
    input_gates: int
    input_depth: int
    input_2q_gates: int
    output_gates: int
    output_depth: int
    output_2q_gates: int
    compile_time_s: float
    error: str | None = None

    @property
    def gate_reduction_pct(self) -> float:
        if self.input_gates == 0:
            return 0.0
        return 100.0 * (self.input_gates - self.output_gates) / self.input_gates

    @property
    def depth_reduction_pct(self) -> float:
        if self.input_depth == 0:
            return 0.0
        return 100.0 * (self.input_depth - self.output_depth) / self.input_depth

    @property
    def two_q_reduction_pct(self) -> float:
        if self.input_2q_gates == 0:
            return 0.0
        return 100.0 * (self.input_2q_gates - self.output_2q_gates) / self.input_2q_gates


def add_stdgates_include(qasm: str) -> str:
    """Add 'include stdgates.inc' to QASM 3.0 if not present."""
    if 'include "stdgates.inc"' not in qasm:
        return qasm.replace("OPENQASM 3.0;", 'OPENQASM 3.0;\ninclude "stdgates.inc";', 1)
    return qasm


def qasm3_to_qiskit(qasm: str) -> Any:
    """Convert QASM 3.0 string to Qiskit QuantumCircuit."""
    from qiskit import qasm3

    qasm_with_include = add_stdgates_include(qasm)
    return qasm3.loads(qasm_with_include)


def run_qco(
    bridge: CircuitOptimizerBridge,
    circuit: BenchmarkCircuit,
) -> CompilerResult:
    """Run QCO optimizer on a circuit."""
    name = circuit.spec.name
    input_metrics = extract_metrics(circuit.qasm)

    t0 = time.perf_counter()
    try:
        result = bridge.optimize(
            qasm=circuit.qasm,
            passes=QCO_PASSES,
            route=False,  # Compare optimization only, no routing
        )
        dt = time.perf_counter() - t0
        output_metrics = extract_metrics(result.output_qasm)
        return CompilerResult(
            compiler="QCO",
            circuit_name=name,
            input_gates=input_metrics.gates,
            input_depth=input_metrics.depth,
            input_2q_gates=input_metrics.two_qubit_gates,
            output_gates=output_metrics.gates,
            output_depth=output_metrics.depth,
            output_2q_gates=output_metrics.two_qubit_gates,
            compile_time_s=dt,
        )
    except Exception as e:
        dt = time.perf_counter() - t0
        return CompilerResult(
            compiler="QCO",
            circuit_name=name,
            input_gates=input_metrics.gates,
            input_depth=input_metrics.depth,
            input_2q_gates=input_metrics.two_qubit_gates,
            output_gates=input_metrics.gates,
            output_depth=input_metrics.depth,
            output_2q_gates=input_metrics.two_qubit_gates,
            compile_time_s=dt,
            error=str(e),
        )


def run_qiskit(
    circuit: BenchmarkCircuit,
    optimization_level: int,
    basis_gates: list[str] | None = None,
    label_suffix: str = "",
) -> CompilerResult:
    """Run Qiskit transpiler at a given optimization level.

    Args:
        circuit: Input circuit.
        optimization_level: Qiskit optimization level (0-3).
        basis_gates: Target basis gates, or None for virtual gate set.
        label_suffix: Appended to compiler name (e.g., "-IQM").
    """
    from qiskit import transpile

    compiler_name = f"Qiskit-L{optimization_level}{label_suffix}"
    name = circuit.spec.name

    try:
        qc = qasm3_to_qiskit(circuit.qasm)
    except Exception as e:
        input_metrics = extract_metrics(circuit.qasm)
        return CompilerResult(
            compiler=compiler_name,
            circuit_name=name,
            input_gates=input_metrics.gates,
            input_depth=input_metrics.depth,
            input_2q_gates=input_metrics.two_qubit_gates,
            output_gates=input_metrics.gates,
            output_depth=input_metrics.depth,
            output_2q_gates=input_metrics.two_qubit_gates,
            compile_time_s=0.0,
            error=f"QASM import failed: {e}",
        )

    input_gates = qc.size()
    input_depth = qc.depth()
    input_2q = qc.num_nonlocal_gates()

    t0 = time.perf_counter()
    try:
        optimized = transpile(
            qc,
            optimization_level=optimization_level,
            basis_gates=basis_gates,
        )
        dt = time.perf_counter() - t0
        return CompilerResult(
            compiler=compiler_name,
            circuit_name=name,
            input_gates=input_gates,
            input_depth=input_depth,
            input_2q_gates=input_2q,
            output_gates=optimized.size(),
            output_depth=optimized.depth(),
            output_2q_gates=optimized.num_nonlocal_gates(),
            compile_time_s=dt,
        )
    except Exception as e:
        dt = time.perf_counter() - t0
        return CompilerResult(
            compiler=compiler_name,
            circuit_name=name,
            input_gates=input_gates,
            input_depth=input_depth,
            input_2q_gates=input_2q,
            output_gates=input_gates,
            output_depth=input_depth,
            output_2q_gates=input_2q,
            compile_time_s=dt,
            error=str(e),
        )


def run_benchmark(corpus: CircuitCorpus) -> list[CompilerResult]:
    """Run all compilers on all circuits in the corpus.

    Compilers run per circuit:
      - QCO (all 4 passes, no routing)
      - Qiskit L0-L3 with virtual gate set (basis_gates=None)
      - Qiskit L1, L3 with IQM basis gates (realistic hardware target)

    Returns:
        List of CompilerResult for every (compiler, circuit) combination.
    """
    from qiskit import qasm3, transpile  # noqa: F401 — warmup import

    # Warmup Qiskit JIT (first transpile call is slow)
    logger.info("Warming up Qiskit transpiler...")
    from qiskit import QuantumCircuit

    warmup_qc = QuantumCircuit(2)
    warmup_qc.h(0)
    warmup_qc.cx(0, 1)
    transpile(warmup_qc, optimization_level=0)
    transpile(warmup_qc, optimization_level=0, basis_gates=IQM_BASIS_GATES)
    logger.info("Warmup complete")

    # Setup QCO bridge
    if not QCO_BINARY.exists():
        logger.error(f"QCO binary not found at {QCO_BINARY}")
        logger.error(
            "Build it: cd ~/dev/research/quantum-circuit-optimizer "
            "&& mkdir -p build && cd build && cmake .. && make -j$(nproc)"
        )
        sys.exit(1)

    bridge = CircuitOptimizerBridge(QCO_BINARY)
    circuits = list(corpus)
    n_circuits = len(circuits)
    # QCO + Qiskit L0-L3 (virtual) + Qiskit L1,L3 (IQM) = 7 compilers
    n_compilers = 7
    total_runs = n_circuits * n_compilers

    logger.info(
        f"Running benchmark: {n_circuits} circuits x {n_compilers} compilers = {total_runs} runs"
    )

    all_results: list[CompilerResult] = []
    errors = 0

    for i, circuit in enumerate(circuits):
        if (i + 1) % 50 == 0 or i == 0:
            logger.info(f"  Circuit {i + 1}/{n_circuits}: {circuit.spec.name}")

        # QCO
        result = run_qco(bridge, circuit)
        if result.error:
            errors += 1
        all_results.append(result)

        # Qiskit levels 0-3, virtual basis (no decomposition)
        for level in range(4):
            result = run_qiskit(circuit, level, basis_gates=None)
            if result.error:
                errors += 1
            all_results.append(result)

        # Qiskit L1 + L3 with IQM basis gates (realistic hardware target)
        for level in (1, 3):
            result = run_qiskit(
                circuit, level, basis_gates=IQM_BASIS_GATES, label_suffix="-IQM"
            )
            if result.error:
                errors += 1
            all_results.append(result)

    logger.info(f"Benchmark complete: {len(all_results)} runs, {errors} errors")
    return all_results


def _classify_circuit(name: str) -> str:
    """Classify circuit name into type."""
    if "ghz" in name:
        return "GHZ"
    elif "qft" in name:
        return "QFT"
    elif "qaoa" in name:
        return "QAOA"
    return "Random"


def summarize_results(results: list[CompilerResult]) -> dict[str, Any]:
    """Compute summary statistics grouped by compiler and circuit type."""
    import numpy as np

    compilers = sorted({r.compiler for r in results})
    circuit_types: dict[str, list[str]] = {}

    for r in results:
        ctype = _classify_circuit(r.circuit_name)
        circuit_types.setdefault(ctype, [])
        if r.circuit_name not in circuit_types[ctype]:
            circuit_types[ctype].append(r.circuit_name)

    summary: dict[str, Any] = {"compilers": {}, "by_circuit_type": {}}

    for compiler in compilers:
        cr = [r for r in results if r.compiler == compiler and r.error is None]
        if not cr:
            continue
        gate_reductions = [r.gate_reduction_pct for r in cr]
        depth_reductions = [r.depth_reduction_pct for r in cr]
        twoq_reductions = [r.two_q_reduction_pct for r in cr]
        times = [r.compile_time_s for r in cr]

        def _stats(vals: list[float]) -> dict[str, float]:
            return {
                "mean": float(np.mean(vals)),
                "std": float(np.std(vals)),
                "min": float(np.min(vals)),
                "max": float(np.max(vals)),
                "median": float(np.median(vals)),
            }

        summary["compilers"][compiler] = {
            "n_circuits": len(cr),
            "n_errors": len([r for r in results if r.compiler == compiler and r.error]),
            "gate_reduction_pct": _stats(gate_reductions),
            "depth_reduction_pct": _stats(depth_reductions),
            "two_q_reduction_pct": _stats(twoq_reductions),
            "compile_time_s": {
                "mean": float(np.mean(times)),
                "std": float(np.std(times)),
                "total": float(np.sum(times)),
            },
        }

    # Per circuit type per compiler
    for ctype, names in sorted(circuit_types.items()):
        summary["by_circuit_type"][ctype] = {}
        for compiler in compilers:
            cr = [
                r
                for r in results
                if r.compiler == compiler and r.error is None and r.circuit_name in names
            ]
            if not cr:
                continue
            gate_reds = [r.gate_reduction_pct for r in cr]
            twoq_reds = [r.two_q_reduction_pct for r in cr]
            summary["by_circuit_type"][ctype][compiler] = {
                "n_circuits": len(cr),
                "mean_gate_reduction": float(np.mean(gate_reds)),
                "max_gate_reduction": float(np.max(gate_reds)),
                "mean_2q_reduction": float(np.mean(twoq_reds)),
                "mean_compile_time": float(np.mean([r.compile_time_s for r in cr])),
            }

    # Head-to-head: QCO vs Qiskit-L3 (virtual) on 2Q gates
    qco_results = {r.circuit_name: r for r in results if r.compiler == "QCO" and not r.error}
    ql3_results = {r.circuit_name: r for r in results if r.compiler == "Qiskit-L3" and not r.error}
    common = set(qco_results) & set(ql3_results)

    qco_wins = sum(1 for n in common if qco_results[n].output_2q_gates < ql3_results[n].output_2q_gates)
    ql3_wins = sum(1 for n in common if ql3_results[n].output_2q_gates < qco_results[n].output_2q_gates)
    ties = len(common) - qco_wins - ql3_wins

    summary["head_to_head_2q"] = {
        "qco_wins": qco_wins,
        "qiskit_l3_wins": ql3_wins,
        "ties": ties,
        "total": len(common),
    }

    return summary


def print_summary(summary: dict[str, Any]) -> None:
    """Print formatted summary to console."""
    print("\n" + "=" * 100)
    print("COMPILER COMPARISON SUMMARY")
    print("=" * 100)

    # Overall table
    print(
        f"\n{'Compiler':<18} {'N':>5} {'Gate Red%':>11} {'2Q Red%':>11} "
        f"{'Depth Red%':>11} {'Time(s)':>10}"
    )
    print("-" * 70)
    for compiler, stats in summary["compilers"].items():
        gr = stats["gate_reduction_pct"]
        tq = stats["two_q_reduction_pct"]
        dr = stats["depth_reduction_pct"]
        print(
            f"{compiler:<18} {stats['n_circuits']:>5} "
            f"{gr['mean']:>7.1f}±{gr['std']:<4.1f}"
            f"{tq['mean']:>7.1f}±{tq['std']:<4.1f}"
            f"{dr['mean']:>7.1f}±{dr['std']:<4.1f}"
            f"{stats['compile_time_s']['mean']:>10.4f}"
        )

    # Per circuit type — Gate reduction
    print("\n\nPer Circuit Type — Mean Gate Reduction %:")
    compilers = list(summary["compilers"].keys())
    col_w = max(len(c) for c in compilers) + 2
    print("-" * (10 + col_w * len(compilers)))
    header = f"{'Type':<10}" + "".join(f"{c:>{col_w}}" for c in compilers)
    print(header)
    print("-" * (10 + col_w * len(compilers)))
    for ctype, type_data in sorted(summary["by_circuit_type"].items()):
        row = f"{ctype:<10}"
        for compiler in compilers:
            if compiler in type_data:
                row += f"{type_data[compiler]['mean_gate_reduction']:>{col_w}.1f}"
            else:
                row += f"{'N/A':>{col_w}}"
        print(row)

    # Per circuit type — 2Q gate reduction
    print("\n\nPer Circuit Type — Mean 2Q Gate Reduction %:")
    print("-" * (10 + col_w * len(compilers)))
    print(header)
    print("-" * (10 + col_w * len(compilers)))
    for ctype, type_data in sorted(summary["by_circuit_type"].items()):
        row = f"{ctype:<10}"
        for compiler in compilers:
            if compiler in type_data:
                row += f"{type_data[compiler]['mean_2q_reduction']:>{col_w}.1f}"
            else:
                row += f"{'N/A':>{col_w}}"
        print(row)

    # Head-to-head
    h2h = summary.get("head_to_head_2q", {})
    if h2h:
        print("\n\nHead-to-Head (2Q gates): QCO vs Qiskit-L3 (virtual)")
        print(f"  QCO wins:       {h2h['qco_wins']}")
        print(f"  Qiskit-L3 wins: {h2h['qiskit_l3_wins']}")
        print(f"  Ties:           {h2h['ties']}")


def save_results(
    results: list[CompilerResult],
    summary: dict[str, Any],
    total_time: float,
    corpus_size: int,
) -> Path:
    """Save detailed results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail_path = RESULTS_DIR / f"comparison_detail_{timestamp}.json"

    with detail_path.open("w") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "corpus_size": corpus_size,
                "total_time_s": total_time,
                "compilers": [
                    "QCO",
                    "Qiskit-L0", "Qiskit-L1", "Qiskit-L2", "Qiskit-L3",
                    "Qiskit-L1-IQM", "Qiskit-L3-IQM",
                ],
                "basis_gates_iqm": IQM_BASIS_GATES,
                "results": [
                    {
                        "compiler": r.compiler,
                        "circuit_name": r.circuit_name,
                        "circuit_type": _classify_circuit(r.circuit_name),
                        "input_gates": r.input_gates,
                        "input_depth": r.input_depth,
                        "input_2q_gates": r.input_2q_gates,
                        "output_gates": r.output_gates,
                        "output_depth": r.output_depth,
                        "output_2q_gates": r.output_2q_gates,
                        "gate_reduction_pct": r.gate_reduction_pct,
                        "depth_reduction_pct": r.depth_reduction_pct,
                        "two_q_reduction_pct": r.two_q_reduction_pct,
                        "compile_time_s": r.compile_time_s,
                        "error": r.error,
                    }
                    for r in results
                ],
                "summary": summary,
            },
            f,
            indent=2,
        )
    return detail_path


def main() -> None:
    """Run the compiler comparison benchmark."""
    parser = argparse.ArgumentParser(description="Compiler Comparison Benchmark")
    parser.add_argument("--quick", action="store_true", help="Use small corpus (4 circuits)")
    parser.add_argument("--paper", action="store_true", help="Use full 371-circuit paper corpus")
    args = parser.parse_args()

    # Select corpus
    if args.quick:
        logger.info("Using small corpus")
        corpus = create_small_corpus()
    elif args.paper:
        logger.info("Using full 371-circuit paper corpus")
        corpus = create_paper_corpus()
    else:
        logger.info("Using standard corpus (19 circuits)")
        corpus = create_standard_corpus()

    logger.info(f"Corpus: {len(corpus)} circuits — {corpus.summary()}")

    # Run benchmark
    t0 = time.time()
    results = run_benchmark(corpus)
    total_time = time.time() - t0

    # Summarize and save
    summary = summarize_results(results)
    detail_path = save_results(results, summary, total_time, len(corpus))
    logger.info(f"Detailed results saved to {detail_path}")

    # Print summary
    print_summary(summary)
    print(f"\nTotal benchmark time: {total_time:.1f}s")
    print(f"Results saved to: {detail_path}")


if __name__ == "__main__":
    main()
