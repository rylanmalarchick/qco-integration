"""Hardware-to-simulation comparison analysis.

This module provides comprehensive analysis tools for comparing quantum circuit
execution results from real hardware versus simulations, including:
- Fidelity metrics and statistical analysis
- Error characterization
- Performance benchmarking
- Device property correlation analysis
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ComparisonMetrics:
    """Metrics comparing hardware vs simulation results."""

    circuit_name: str
    hardware_fidelity: float
    simulated_fidelity: float
    fidelity_difference: float
    hellinger_distance: float  # Between distributions
    total_variation_distance: float
    ks_statistic: float  # Kolmogorov-Smirnov test
    shots: int
    execution_time_ms: float
    device: str


class HardwareSimulationComparison:
    """Comprehensive comparison between hardware and simulation results."""

    def __init__(self):
        """Initialize comparison analyzer."""
        self.comparisons: list[ComparisonMetrics] = []
        self.circuit_groups: dict[str, list[ComparisonMetrics]] = {}

    def add_comparison(
        self,
        circuit_name: str,
        hardware_counts: dict[str, int],
        simulated_counts: dict[str, int],
        shots: int,
        execution_time_ms: float,
        device: str = "IQM_RESONANCE_5Q",
    ) -> ComparisonMetrics:
        """Add a hardware-simulation comparison.

        Args:
            circuit_name: Name of the circuit.
            hardware_counts: Measurement counts from hardware (bitstring -> count).
            simulated_counts: Measurement counts from simulation.
            shots: Number of shots executed.
            execution_time_ms: Execution time in milliseconds.
            device: Device name.

        Returns:
            ComparisonMetrics object.
        """
        hw_fid = self._compute_fidelity(hardware_counts, shots)
        sim_fid = self._compute_fidelity(simulated_counts, shots)

        # Compute distance metrics
        hd = self._hellinger_distance(hardware_counts, simulated_counts)
        tvd = self._total_variation_distance(hardware_counts, simulated_counts)
        ks_stat = self._ks_statistic(hardware_counts, simulated_counts)

        metrics = ComparisonMetrics(
            circuit_name=circuit_name,
            hardware_fidelity=hw_fid,
            simulated_fidelity=sim_fid,
            fidelity_difference=hw_fid - sim_fid,
            hellinger_distance=hd,
            total_variation_distance=tvd,
            ks_statistic=ks_stat,
            shots=shots,
            execution_time_ms=execution_time_ms,
            device=device,
        )

        self.comparisons.append(metrics)

        # Group by circuit type
        circuit_type = circuit_name.split("_")[0]
        if circuit_type not in self.circuit_groups:
            self.circuit_groups[circuit_type] = []
        self.circuit_groups[circuit_type].append(metrics)

        return metrics

    def compute_aggregate_statistics(self) -> dict[str, Any]:
        """Compute aggregate statistics across all comparisons.

        Returns:
            Dictionary with comprehensive statistics.
        """
        if not self.comparisons:
            return {}

        hw_fidelities = [c.hardware_fidelity for c in self.comparisons]
        sim_fidelities = [c.simulated_fidelity for c in self.comparisons]
        differences = [c.fidelity_difference for c in self.comparisons]
        hd_distances = [c.hellinger_distance for c in self.comparisons]
        tvd_distances = [c.total_variation_distance for c in self.comparisons]

        stats = {
            "num_comparisons": len(self.comparisons),
            "hardware_fidelity": {
                "mean": statistics.mean(hw_fidelities),
                "median": statistics.median(hw_fidelities),
                "stdev": statistics.stdev(hw_fidelities) if len(hw_fidelities) > 1 else 0.0,
                "min": min(hw_fidelities),
                "max": max(hw_fidelities),
            },
            "simulated_fidelity": {
                "mean": statistics.mean(sim_fidelities),
                "median": statistics.median(sim_fidelities),
                "stdev": statistics.stdev(sim_fidelities) if len(sim_fidelities) > 1 else 0.0,
                "min": min(sim_fidelities),
                "max": max(sim_fidelities),
            },
            "fidelity_difference": {
                "mean": statistics.mean(differences),
                "median": statistics.median(differences),
                "stdev": statistics.stdev(differences) if len(differences) > 1 else 0.0,
                "min": min(differences),
                "max": max(differences),
            },
            "distance_metrics": {
                "hellinger_distance_mean": statistics.mean(hd_distances),
                "hellinger_distance_max": max(hd_distances),
                "total_variation_distance_mean": statistics.mean(tvd_distances),
                "total_variation_distance_max": max(tvd_distances),
            },
        }

        # Per-circuit-type statistics
        stats["per_circuit_type"] = {}
        for circuit_type, metrics_list in self.circuit_groups.items():
            type_hw_fids = [m.hardware_fidelity for m in metrics_list]
            type_sim_fids = [m.simulated_fidelity for m in metrics_list]

            stats["per_circuit_type"][circuit_type] = {
                "count": len(metrics_list),
                "hardware_fidelity_mean": statistics.mean(type_hw_fids),
                "simulated_fidelity_mean": statistics.mean(type_sim_fids),
                "fidelity_difference_mean": statistics.mean(
                    [h - s for h, s in zip(type_hw_fids, type_sim_fids)]
                ),
            }

        return stats

    def compute_correlation_analysis(self) -> dict[str, float]:
        """Compute correlations between hardware and simulated fidelities.

        Returns:
            Dictionary with correlation metrics.
        """
        if len(self.comparisons) < 2:
            return {}

        hw_fids_list = [c.hardware_fidelity for c in self.comparisons]
        sim_fids_list = [c.simulated_fidelity for c in self.comparisons]

        # Convert to numpy arrays for correlation
        hw_fids = np.asarray(hw_fids_list, dtype=float)
        sim_fids = np.asarray(sim_fids_list, dtype=float)

        # Pearson correlation
        correlation = np.corrcoef(hw_fids, sim_fids)[0, 1]

        # Spearman rank correlation
        from scipy import stats as scipy_stats

        spearman_corr, spearman_pval = scipy_stats.spearmanr(hw_fids_list, sim_fids_list)

        return {
            "pearson_correlation": float(correlation) if not np.isnan(correlation) else 0.0,
            "spearman_correlation": float(spearman_corr),
            "spearman_pvalue": float(spearman_pval),
        }

    @staticmethod
    def _compute_fidelity(counts: dict[str, int], shots: int) -> float:
        """Compute approximate fidelity from measurement counts.

        Uses the most probable outcome (simplified fidelity metric).

        Args:
            counts: Bitstring -> count mapping.
            shots: Total shots.

        Returns:
            Fidelity estimate (0 to 1).
        """
        if not counts:
            return 0.0

        max_count = max(counts.values())
        return max_count / shots

    @staticmethod
    def _hellinger_distance(counts1: dict[str, int], counts2: dict[str, int]) -> float:
        """Compute Hellinger distance between two probability distributions.

        Args:
            counts1: First measurement counts.
            counts2: Second measurement counts.

        Returns:
            Hellinger distance (0 to 1).
        """
        all_bitstrings = set(counts1.keys()) | set(counts2.keys())

        total1 = sum(counts1.values())
        total2 = sum(counts2.values())

        sum_sqrt = 0.0
        for bitstring in all_bitstrings:
            p1 = counts1.get(bitstring, 0) / total1 if total1 > 0 else 0.0
            p2 = counts2.get(bitstring, 0) / total2 if total2 > 0 else 0.0
            sum_sqrt += (np.sqrt(p1) - np.sqrt(p2)) ** 2

        return float(np.sqrt(sum_sqrt / 2.0))

    @staticmethod
    def _total_variation_distance(counts1: dict[str, int], counts2: dict[str, int]) -> float:
        """Compute total variation distance between two probability distributions.

        Args:
            counts1: First measurement counts.
            counts2: Second measurement counts.

        Returns:
            Total variation distance (0 to 1).
        """
        all_bitstrings = set(counts1.keys()) | set(counts2.keys())

        total1 = sum(counts1.values())
        total2 = sum(counts2.values())

        distance = 0.0
        for bitstring in all_bitstrings:
            p1 = counts1.get(bitstring, 0) / total1 if total1 > 0 else 0.0
            p2 = counts2.get(bitstring, 0) / total2 if total2 > 0 else 0.0
            distance += abs(p1 - p2)

        return distance / 2.0

    @staticmethod
    def _ks_statistic(counts1: dict[str, int], counts2: dict[str, int]) -> float:
        """Compute Kolmogorov-Smirnov statistic.

        Args:
            counts1: First measurement counts.
            counts2: Second measurement counts.

        Returns:
            KS statistic.
        """
        all_bitstrings = sorted(set(counts1.keys()) | set(counts2.keys()))

        total1 = sum(counts1.values())
        total2 = sum(counts2.values())

        cdf1 = 0.0
        cdf2 = 0.0
        max_diff = 0.0

        for bitstring in all_bitstrings:
            cdf1 += (counts1.get(bitstring, 0) / total1) if total1 > 0 else 0.0
            cdf2 += (counts2.get(bitstring, 0) / total2) if total2 > 0 else 0.0
            max_diff = max(max_diff, abs(cdf1 - cdf2))

        return max_diff

    def export_report(self, output_path: Path | str) -> None:
        """Export comparison report to JSON.

        Args:
            output_path: Path to save report.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "num_comparisons": len(self.comparisons),
            "aggregate_statistics": self.compute_aggregate_statistics(),
            "correlation_analysis": self.compute_correlation_analysis(),
            "detailed_results": [
                {
                    "circuit_name": c.circuit_name,
                    "hardware_fidelity": round(c.hardware_fidelity, 4),
                    "simulated_fidelity": round(c.simulated_fidelity, 4),
                    "fidelity_difference": round(c.fidelity_difference, 4),
                    "hellinger_distance": round(c.hellinger_distance, 4),
                    "total_variation_distance": round(c.total_variation_distance, 4),
                    "ks_statistic": round(c.ks_statistic, 4),
                    "shots": c.shots,
                    "execution_time_ms": c.execution_time_ms,
                    "device": c.device,
                }
                for c in self.comparisons
            ],
        }

        with output_path.open("w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Comparison report exported to {output_path}")
