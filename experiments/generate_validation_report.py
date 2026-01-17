#!/usr/bin/env python3
"""Hardware validation report and metrics dashboard.

This script generates comprehensive HTML and JSON reports of hardware
validation experiments, including:
- Fidelity comparisons (hardware vs simulation)
- Performance metrics and timings
- Error analysis and characterization
- Interactive visualizations (in HTML)
- Structured data export for further analysis

Usage:
    python experiments/generate_validation_report.py --results-dir experiments/reports
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import statistics

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ValidationReportGenerator:
    """Generate comprehensive validation reports."""

    def __init__(self, results_dir: Path | str):
        """Initialize report generator.

        Args:
            results_dir: Directory containing validation results.
        """
        self.results_dir = Path(results_dir)
        self.validation_files: list[Path] = []
        self.load_results()

    def load_results(self) -> None:
        """Load all validation result files."""
        if not self.results_dir.exists():
            logger.warning(f"Results directory not found: {self.results_dir}")
            return

        self.validation_files = list(self.results_dir.glob("hardware_validation_*.json"))
        logger.info(f"Found {len(self.validation_files)} validation result files")

    def generate_summary_report(self) -> dict[str, Any]:
        """Generate summary report across all validation experiments.

        Returns:
            Dictionary with aggregated metrics.
        """
        if not self.validation_files:
            logger.warning("No validation files found")
            return {}

        all_results = []
        for results_file in self.validation_files:
            with results_file.open() as f:
                all_results.append(json.load(f))

        # Aggregate metrics
        all_hw_fidelities = []
        all_sim_fidelities = []
        all_differences = []
        all_timings = []

        circuit_summaries = {}

        for result in all_results:
            for circuit in result.get("circuits", []):
                hw_fid = circuit.get("hardware_fidelity", 0.0)
                sim_fid = circuit.get("simulated_fidelity", 0.0)

                all_hw_fidelities.append(hw_fid)
                all_sim_fidelities.append(sim_fid)
                all_differences.append(hw_fid - sim_fid)

                if circuit.get("execution_time_ms"):
                    all_timings.append(circuit["execution_time_ms"])

                # Per-circuit tracking
                circuit_name = circuit.get("name", "unknown")
                if circuit_name not in circuit_summaries:
                    circuit_summaries[circuit_name] = {
                        "hw_fidelities": [],
                        "sim_fidelities": [],
                        "timings": [],
                        "count": 0,
                    }

                circuit_summaries[circuit_name]["hw_fidelities"].append(hw_fid)
                circuit_summaries[circuit_name]["sim_fidelities"].append(sim_fid)
                if circuit.get("execution_time_ms"):
                    circuit_summaries[circuit_name]["timings"].append(
                        circuit["execution_time_ms"]
                    )
                circuit_summaries[circuit_name]["count"] += 1

        # Compute aggregate statistics
        summary = {
            "generated_at": datetime.now().isoformat(),
            "num_experiments": len(all_results),
            "total_circuits": len(all_hw_fidelities),
            "hardware_fidelity": {
                "mean": statistics.mean(all_hw_fidelities),
                "median": statistics.median(all_hw_fidelities),
                "stdev": (
                    statistics.stdev(all_hw_fidelities)
                    if len(all_hw_fidelities) > 1
                    else 0.0
                ),
                "min": min(all_hw_fidelities),
                "max": max(all_hw_fidelities),
            },
            "simulated_fidelity": {
                "mean": statistics.mean(all_sim_fidelities),
                "median": statistics.median(all_sim_fidelities),
                "stdev": (
                    statistics.stdev(all_sim_fidelities)
                    if len(all_sim_fidelities) > 1
                    else 0.0
                ),
                "min": min(all_sim_fidelities),
                "max": max(all_sim_fidelities),
            },
            "fidelity_difference": {
                "mean": statistics.mean(all_differences),
                "median": statistics.median(all_differences),
                "stdev": (
                    statistics.stdev(all_differences)
                    if len(all_differences) > 1
                    else 0.0
                ),
                "min": min(all_differences),
                "max": max(all_differences),
            },
            "timing": {
                "mean_ms": statistics.mean(all_timings) if all_timings else 0.0,
                "max_ms": max(all_timings) if all_timings else 0.0,
                "min_ms": min(all_timings) if all_timings else 0.0,
            },
            "per_circuit": {},
        }

        # Per-circuit summaries
        for circuit_name, metrics in circuit_summaries.items():
            hw_fids = metrics["hw_fidelities"]
            sim_fids = metrics["sim_fidelities"]

            summary["per_circuit"][circuit_name] = {
                "count": metrics["count"],
                "hardware_fidelity_mean": statistics.mean(hw_fids),
                "simulated_fidelity_mean": statistics.mean(sim_fids),
                "fidelity_difference_mean": statistics.mean(
                    [h - s for h, s in zip(hw_fids, sim_fids)]
                ),
                "avg_execution_time_ms": (
                    statistics.mean(metrics["timings"]) if metrics["timings"] else 0.0
                ),
            }

        return summary

    def generate_html_report(self, summary: dict[str, Any], output_path: Path | str) -> None:
        """Generate interactive HTML report.

        Args:
            summary: Summary data from generate_summary_report.
            output_path: Path to save HTML file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hardware Validation Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 30px;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background-color: #f8f9fa;
            border-left: 4px solid #3498db;
            padding: 15px;
            border-radius: 4px;
        }}
        .metric-card h3 {{
            margin: 0 0 10px 0;
            font-size: 14px;
            color: #7f8c8d;
            text-transform: uppercase;
        }}
        .metric-value {{
            font-size: 28px;
            font-weight: bold;
            color: #2c3e50;
        }}
        .metric-unit {{
            font-size: 12px;
            color: #95a5a6;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th {{
            background-color: #ecf0f1;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #2c3e50;
            border-bottom: 2px solid #bdc3c7;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #ecf0f1;
        }}
        tr:hover {{
            background-color: #f8f9fa;
        }}
        .success {{
            color: #27ae60;
        }}
        .warning {{
            color: #e74c3c;
        }}
        .info {{
            color: #3498db;
        }}
        .generated {{
            color: #95a5a6;
            font-size: 12px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔬 Hardware Validation Report</h1>
        
        <h2>📊 Overall Statistics</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <h3>Total Circuits</h3>
                <div class="metric-value">{summary.get('total_circuits', 0)}</div>
            </div>
            <div class="metric-card">
                <h3>Hardware Fidelity</h3>
                <div class="metric-value success">{summary.get('hardware_fidelity', {}).get('mean', 0):.3f}</div>
                <div class="metric-unit">mean ± {summary.get('hardware_fidelity', {}).get('stdev', 0):.3f}</div>
            </div>
            <div class="metric-card">
                <h3>Simulated Fidelity</h3>
                <div class="metric-value info">{summary.get('simulated_fidelity', {}).get('mean', 0):.3f}</div>
                <div class="metric-unit">mean ± {summary.get('simulated_fidelity', {}).get('stdev', 0):.3f}</div>
            </div>
            <div class="metric-card">
                <h3>Fidelity Gap</h3>
                <div class="metric-value">{summary.get('fidelity_difference', {}).get('mean', 0):.3f}</div>
                <div class="metric-unit">mean difference</div>
            </div>
        </div>

        <h2>⏱️ Performance Metrics</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <h3>Avg Execution Time</h3>
                <div class="metric-value">{summary.get('timing', {}).get('mean_ms', 0):.1f}</div>
                <div class="metric-unit">milliseconds</div>
            </div>
            <div class="metric-card">
                <h3>Max Execution Time</h3>
                <div class="metric-value">{summary.get('timing', {}).get('max_ms', 0):.1f}</div>
                <div class="metric-unit">milliseconds</div>
            </div>
        </div>

        <h2>📈 Fidelity Distribution</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Mean</th>
                <th>Median</th>
                <th>Stdev</th>
                <th>Min</th>
                <th>Max</th>
            </tr>
            <tr>
                <td><strong>Hardware Fidelity</strong></td>
                <td>{summary.get('hardware_fidelity', {}).get('mean', 0):.4f}</td>
                <td>{summary.get('hardware_fidelity', {}).get('median', 0):.4f}</td>
                <td>{summary.get('hardware_fidelity', {}).get('stdev', 0):.4f}</td>
                <td>{summary.get('hardware_fidelity', {}).get('min', 0):.4f}</td>
                <td>{summary.get('hardware_fidelity', {}).get('max', 0):.4f}</td>
            </tr>
            <tr>
                <td><strong>Simulated Fidelity</strong></td>
                <td>{summary.get('simulated_fidelity', {}).get('mean', 0):.4f}</td>
                <td>{summary.get('simulated_fidelity', {}).get('median', 0):.4f}</td>
                <td>{summary.get('simulated_fidelity', {}).get('stdev', 0):.4f}</td>
                <td>{summary.get('simulated_fidelity', {}).get('min', 0):.4f}</td>
                <td>{summary.get('simulated_fidelity', {}).get('max', 0):.4f}</td>
            </tr>
        </table>

        <h2>🎯 Per-Circuit Results</h2>
        <table>
            <tr>
                <th>Circuit Name</th>
                <th>Runs</th>
                <th>Hw Fidelity</th>
                <th>Sim Fidelity</th>
                <th>Gap</th>
                <th>Avg Time (ms)</th>
            </tr>
"""

        for circuit_name, metrics in summary.get("per_circuit", {}).items():
            hw_fid = metrics.get("hardware_fidelity_mean", 0)
            sim_fid = metrics.get("simulated_fidelity_mean", 0)
            gap = metrics.get("fidelity_difference_mean", 0)
            exec_time = metrics.get("avg_execution_time_ms", 0)

            html_content += f"""            <tr>
                <td><code>{circuit_name}</code></td>
                <td>{metrics.get('count', 0)}</td>
                <td>{hw_fid:.4f}</td>
                <td>{sim_fid:.4f}</td>
                <td>{gap:.4f}</td>
                <td>{exec_time:.1f}</td>
            </tr>
"""

        html_content += """        </table>

        <div class="generated">
            <p>Report generated at: <strong>""" + summary.get(
            "generated_at", datetime.now().isoformat()
        ) + """</strong></p>
        </div>
    </div>
</body>
</html>
"""

        with output_path.open("w") as f:
            f.write(html_content)

        logger.info(f"HTML report saved to {output_path}")

    def export_json_report(self, summary: dict[str, Any], output_path: Path | str) -> None:
        """Export summary report to JSON.

        Args:
            summary: Summary data.
            output_path: Path to save JSON file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"JSON report saved to {output_path}")


def main() -> None:
    """Generate validation reports."""
    parser = argparse.ArgumentParser(description="Generate hardware validation reports")
    parser.add_argument(
        "--results-dir",
        type=str,
        default="experiments/reports",
        help="Directory with validation results (default: experiments/reports)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="experiments/reports",
        help="Output directory for reports (default: experiments/reports)",
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("HARDWARE VALIDATION REPORT GENERATOR")
    logger.info("=" * 70)
    logger.info("")

    generator = ValidationReportGenerator(args.results_dir)

    if not generator.validation_files:
        logger.error("No validation result files found")
        logger.info("Run hardware validation first: python experiments/hardware_validate.py")
        return

    # Generate summary report
    summary = generator.generate_summary_report()

    # Export reports
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"validation_summary_{timestamp}.json"
    html_path = output_dir / f"validation_report_{timestamp}.html"

    generator.export_json_report(summary, json_path)
    generator.generate_html_report(summary, html_path)

    logger.info("")
    logger.info("Reports generated successfully!")
    logger.info(f"  HTML: {html_path}")
    logger.info(f"  JSON: {json_path}")
    logger.info("")


if __name__ == "__main__":
    main()
