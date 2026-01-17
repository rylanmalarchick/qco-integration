"""BenchmarkRunner: Automated experiment execution.

This module provides utilities for running systematic experiments
with configuration-driven settings, parallel execution, and
results persistence.

Following AgentBible principles:
- Configuration-driven (no hardcoded experiments)
- Results persistence (JSON/Parquet)
- Reproducible execution with seed tracking
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from src.corpus import BenchmarkCircuit, CircuitCorpus
from src.metrics import EndToEndResult, NoiseParams
from src.pipeline import EndToEndPipeline

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Classes
# =============================================================================


@dataclass
class ExperimentConfig:
    """Configuration for a benchmark experiment.

    Attributes:
        name: Experiment name/identifier.
        description: Human-readable description.
        passes_configs: List of pass configurations to test.
        topology: Target topology.
        noise_params: Noise model parameters.
        route: Whether to apply routing.
        parallel: Whether to run circuits in parallel.
        max_workers: Maximum parallel workers (if parallel=True).
        output_dir: Directory for results output.
        seed: Random seed for reproducibility.
    """

    name: str
    description: str = ""
    passes_configs: list[list[str]] = field(default_factory=lambda: [["cancel"]])
    topology: str = "iqm-garnet"
    noise_params: NoiseParams | None = None
    route: bool = True
    parallel: bool = False
    max_workers: int = 4
    output_dir: Path = field(default_factory=lambda: Path("results/raw"))
    seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "passes_configs": self.passes_configs,
            "topology": self.topology,
            "route": self.route,
            "parallel": self.parallel,
            "max_workers": self.max_workers,
            "output_dir": str(self.output_dir),
            "seed": self.seed,
        }
        if self.noise_params is not None:
            result["noise_params"] = asdict(self.noise_params)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentConfig:
        """Create from dictionary."""
        noise_params = None
        if "noise_params" in data and data["noise_params"] is not None:
            noise_params = NoiseParams(**data["noise_params"])

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            passes_configs=data.get("passes_configs", [["cancel"]]),
            topology=data.get("topology", "iqm-garnet"),
            noise_params=noise_params,
            route=data.get("route", True),
            parallel=data.get("parallel", False),
            max_workers=data.get("max_workers", 4),
            output_dir=Path(data.get("output_dir", "results/raw")),
            seed=data.get("seed", 42),
        )


@dataclass
class SingleRunResult:
    """Result from a single circuit + passes combination.

    Attributes:
        circuit_name: Name of the circuit.
        passes: Passes applied.
        result: EndToEndResult if successful, None if failed.
        error: Error message if failed, None if successful.
        duration_seconds: Time taken for this run.
    """

    circuit_name: str
    passes: list[str]
    result: EndToEndResult | None
    error: str | None
    duration_seconds: float


@dataclass
class ExperimentResults:
    """Results from a complete experiment run.

    Attributes:
        config: Experiment configuration.
        results: List of single run results.
        start_time: When experiment started.
        end_time: When experiment completed.
    """

    config: ExperimentConfig
    results: list[SingleRunResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    @property
    def success_count(self) -> int:
        """Number of successful circuit runs."""
        return sum(1 for r in self.results if r.result is not None)

    @property
    def error_count(self) -> int:
        """Number of errors encountered."""
        return sum(1 for r in self.results if r.error is not None)

    @property
    def total_duration_seconds(self) -> float:
        """Total experiment duration in seconds."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()

    def successful_results(self) -> list[EndToEndResult]:
        """Get list of successful EndToEndResults."""
        return [r.result for r in self.results if r.result is not None]

    def errors(self) -> list[tuple[str, list[str], str]]:
        """Get list of errors as (circuit_name, passes, error_message)."""
        return [
            (r.circuit_name, r.passes, r.error)
            for r in self.results
            if r.error is not None
        ]


# =============================================================================
# BenchmarkRunner Class
# =============================================================================


class BenchmarkRunner:
    """Automated experiment execution with results persistence.

    This class runs experiments over circuit corpora, collecting
    metrics and persisting results.

    Example:
        >>> corpus = CircuitCorpus()
        >>> corpus.add_qft_circuits([4, 8, 12])
        >>> runner = BenchmarkRunner(pipeline, corpus)
        >>> config = ExperimentConfig(
        ...     name="qft_optimization",
        ...     passes_configs=[["cancel"], ["cancel", "commute"]],
        ... )
        >>> results = runner.run(config)
        >>> runner.save_results(results, output_format="json")
    """

    def __init__(
        self,
        pipeline: EndToEndPipeline,
        corpus: CircuitCorpus,
    ) -> None:
        """Initialize the benchmark runner.

        Args:
            pipeline: Configured end-to-end pipeline.
            corpus: Circuit corpus to run experiments on.
        """
        self.pipeline = pipeline
        self.corpus = corpus

    def run(self, config: ExperimentConfig) -> ExperimentResults:
        """Execute an experiment with the given configuration.

        Args:
            config: Experiment configuration.

        Returns:
            ExperimentResults with all collected data.
        """
        results = ExperimentResults(config=config, start_time=datetime.now())

        # Build list of all (circuit, passes) combinations to run
        run_items: list[tuple[BenchmarkCircuit, list[str]]] = []
        for circuit in self.corpus:
            for passes in config.passes_configs:
                run_items.append((circuit, passes))

        logger.info(
            f"Starting experiment '{config.name}' with {len(run_items)} runs "
            f"({len(self.corpus)} circuits x {len(config.passes_configs)} pass configs)"
        )

        if config.parallel and len(run_items) > 1:
            results.results = self._run_parallel(run_items, config)
        else:
            results.results = self._run_sequential(run_items, config)

        results.end_time = datetime.now()

        logger.info(
            f"Experiment '{config.name}' completed: "
            f"{results.success_count} succeeded, {results.error_count} failed, "
            f"duration: {results.total_duration_seconds:.1f}s"
        )

        return results

    def _run_sequential(
        self,
        run_items: list[tuple[BenchmarkCircuit, list[str]]],
        config: ExperimentConfig,
    ) -> list[SingleRunResult]:
        """Run experiments sequentially."""
        results = []
        for circuit, passes in run_items:
            result = self.run_single(
                circuit_qasm=circuit.qasm,
                circuit_name=circuit.spec.name,
                passes=passes,
                config=config,
            )
            results.append(result)
        return results

    def _run_parallel(
        self,
        run_items: list[tuple[BenchmarkCircuit, list[str]]],
        config: ExperimentConfig,
    ) -> list[SingleRunResult]:
        """Run experiments in parallel."""
        results: list[SingleRunResult] = []

        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            # Submit all tasks
            future_to_item = {
                executor.submit(
                    self.run_single,
                    circuit.qasm,
                    circuit.spec.name,
                    passes,
                    config,
                ): (circuit, passes)
                for circuit, passes in run_items
            }

            # Collect results as they complete
            for future in as_completed(future_to_item):
                result = future.result()
                results.append(result)

        return results

    def run_single(
        self,
        circuit_qasm: str,
        circuit_name: str,
        passes: list[str],
        config: ExperimentConfig,
    ) -> SingleRunResult:
        """Run a single circuit through the pipeline.

        Args:
            circuit_qasm: OpenQASM circuit string.
            circuit_name: Circuit identifier.
            passes: Optimization passes to apply.
            config: Experiment configuration for noise/topology.

        Returns:
            SingleRunResult for this circuit.
        """
        start_time = datetime.now()

        try:
            result = self.pipeline.run(
                circuit=circuit_qasm,
                passes=passes,
                topology=config.topology,
                noise_params=config.noise_params,
                circuit_name=circuit_name,
                route=config.route,
            )
            duration = (datetime.now() - start_time).total_seconds()

            return SingleRunResult(
                circuit_name=circuit_name,
                passes=passes,
                result=result,
                error=None,
                duration_seconds=duration,
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.warning(f"Error running {circuit_name} with {passes}: {e}")

            return SingleRunResult(
                circuit_name=circuit_name,
                passes=passes,
                result=None,
                error=str(e),
                duration_seconds=duration,
            )

    def save_results(
        self,
        results: ExperimentResults,
        output_format: str = "json",
        output_path: Path | None = None,
    ) -> Path:
        """Save experiment results to disk.

        Args:
            results: Results to save.
            output_format: Format ("json" or "parquet").
            output_path: Override output path.

        Returns:
            Path to saved results file.

        Raises:
            ValueError: If output_format is not supported.
        """
        if output_format not in ("json", "parquet"):
            raise ValueError(f"Unsupported output format: {output_format}")

        # Determine output path
        if output_path is None:
            results.config.output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = results.start_time.strftime("%Y%m%d_%H%M%S")
            filename = f"{results.config.name}_{timestamp}.{output_format}"
            output_path = results.config.output_dir / filename

        if output_format == "json":
            self._save_json(results, output_path)
        else:
            self._save_parquet(results, output_path)

        logger.info(f"Results saved to {output_path}")
        return output_path

    def _save_json(self, results: ExperimentResults, path: Path) -> None:
        """Save results as JSON."""
        data = self._results_to_dict(results)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(data, f, indent=2, default=str)

    def _save_parquet(self, results: ExperimentResults, path: Path) -> None:
        """Save results as Parquet (requires pyarrow)."""
        try:
            import pyarrow as pa  # type: ignore[import-not-found]
            import pyarrow.parquet as pq  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImportError(
                "Parquet support requires pyarrow. Install with: pip install pyarrow"
            ) from e

        # Convert to flat table format
        rows = []
        for single in results.results:
            row = {
                "circuit_name": single.circuit_name,
                "passes": ",".join(single.passes),
                "duration_seconds": single.duration_seconds,
                "error": single.error,
            }
            if single.result is not None:
                row.update({
                    "input_gates": single.result.input_metrics.gates,
                    "input_depth": single.result.input_metrics.depth,
                    "input_qubits": single.result.input_metrics.qubits,
                    "input_2q_gates": single.result.input_metrics.two_qubit_gates,
                    "post_opt_gates": single.result.post_optimization.gates,
                    "post_opt_depth": single.result.post_optimization.depth,
                    "pulse_duration_ns": single.result.pulse_metrics.total_duration_ns,
                    "pulse_count": single.result.pulse_metrics.pulse_count,
                    "process_fidelity": single.result.process_fidelity,
                    "state_fidelity": single.result.state_fidelity,
                    "topology": single.result.topology,
                })
                if single.result.routing_metrics is not None:
                    row.update({
                        "swaps_inserted": single.result.routing_metrics.swaps_inserted,
                        "routed_gates": single.result.routing_metrics.final_gates,
                        "routed_depth": single.result.routing_metrics.final_depth,
                    })
            rows.append(row)

        table = pa.Table.from_pylist(rows)
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, path)

    def _results_to_dict(self, results: ExperimentResults) -> dict[str, Any]:
        """Convert ExperimentResults to dictionary for JSON serialization."""
        return {
            "config": results.config.to_dict(),
            "start_time": results.start_time.isoformat(),
            "end_time": results.end_time.isoformat() if results.end_time else None,
            "success_count": results.success_count,
            "error_count": results.error_count,
            "total_duration_seconds": results.total_duration_seconds,
            "results": [self._single_result_to_dict(r) for r in results.results],
        }

    def _single_result_to_dict(self, result: SingleRunResult) -> dict[str, Any]:
        """Convert SingleRunResult to dictionary."""
        data: dict[str, Any] = {
            "circuit_name": result.circuit_name,
            "passes": result.passes,
            "duration_seconds": result.duration_seconds,
            "error": result.error,
        }
        if result.result is not None:
            data["result"] = self._end_to_end_result_to_dict(result.result)
        return data

    def _end_to_end_result_to_dict(self, result: EndToEndResult) -> dict[str, Any]:
        """Convert EndToEndResult to dictionary."""
        data: dict[str, Any] = {
            "circuit_name": result.circuit_name,
            "input_metrics": asdict(result.input_metrics),
            "post_optimization": asdict(result.post_optimization),
            "pulse_metrics": asdict(result.pulse_metrics),
            "process_fidelity": result.process_fidelity,
            "state_fidelity": result.state_fidelity,
            "noise_params": asdict(result.noise_params),
            "topology": result.topology,
            "timestamp": result.timestamp.isoformat(),
            "optimization_passes": [
                {
                    "name": p.name,
                    "input_metrics": asdict(p.input_metrics),
                    "output_metrics": asdict(p.output_metrics),
                    "gates_removed": p.gates_removed,
                    "gates_added": p.gates_added,
                    "execution_time_ms": p.execution_time_ms,
                }
                for p in result.optimization_passes
            ],
        }
        if result.routing_metrics is not None:
            data["routing_metrics"] = asdict(result.routing_metrics)
        return data

    def load_results(self, path: Path) -> ExperimentResults:
        """Load experiment results from disk.

        Args:
            path: Path to results file.

        Returns:
            Loaded ExperimentResults.

        Raises:
            ValueError: If file format is not supported.
        """
        if path.suffix == ".json":
            return self._load_json(path)
        elif path.suffix == ".parquet":
            raise NotImplementedError(
                "Parquet loading not yet implemented. Use JSON format."
            )
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

    def _load_json(self, path: Path) -> ExperimentResults:
        """Load results from JSON file."""
        with path.open() as f:
            data = json.load(f)

        config = ExperimentConfig.from_dict(data["config"])

        # Parse results (simplified - doesn't fully reconstruct EndToEndResult)
        results_list: list[SingleRunResult] = []
        for r in data.get("results", []):
            results_list.append(
                SingleRunResult(
                    circuit_name=r["circuit_name"],
                    passes=r["passes"],
                    result=None,  # Full reconstruction would require more code
                    error=r.get("error"),
                    duration_seconds=r.get("duration_seconds", 0.0),
                )
            )

        return ExperimentResults(
            config=config,
            results=results_list,
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=(
                datetime.fromisoformat(data["end_time"])
                if data.get("end_time")
                else None
            ),
        )

    @staticmethod
    def load_config(path: Path) -> ExperimentConfig:
        """Load experiment configuration from YAML file.

        Args:
            path: Path to YAML configuration file.

        Returns:
            Loaded ExperimentConfig.
        """
        with path.open() as f:
            data = yaml.safe_load(f)

        return ExperimentConfig.from_dict(data)

    @staticmethod
    def save_config(config: ExperimentConfig, path: Path) -> None:
        """Save experiment configuration to YAML file.

        Args:
            config: Configuration to save.
            path: Output path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)
