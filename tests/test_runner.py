"""Tests for BenchmarkRunner.

Tests cover:
- ExperimentConfig creation and serialization
- BenchmarkRunner.run() with mock pipeline
- BenchmarkRunner.run_single()
- save_results() / load_results() for JSON
- load_config() / save_config() for YAML
- Parallel execution

Following AgentBible testing principles:
- Specification Before Code
- Mock external dependencies
- Clear test names describing expected behavior
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.corpus import CircuitCorpus
from src.metrics import (
    EndToEndResult,
    NoiseParams,
    PassMetrics,
    PulseMetrics,
    RoutingMetrics,
    StageMetrics,
)
from src.runner import (
    BenchmarkRunner,
    ExperimentConfig,
    ExperimentResults,
    SingleRunResult,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def noise_params() -> NoiseParams:
    """IQM Garnet median noise parameters."""
    return NoiseParams(
        t1_ns=37000.0,
        t2_ns=9600.0,
        single_qubit_error=0.001,
        two_qubit_error=0.006,
    )


@pytest.fixture
def sample_end_to_end_result(noise_params: NoiseParams) -> EndToEndResult:
    """Sample EndToEndResult for testing."""
    return EndToEndResult(
        circuit_name="test_circuit",
        input_metrics=StageMetrics(gates=10, depth=5, qubits=2, two_qubit_gates=3),
        optimization_passes=[
            PassMetrics(
                name="CancellationPass",
                input_metrics=StageMetrics(gates=10, depth=5, qubits=2, two_qubit_gates=3),
                output_metrics=StageMetrics(gates=8, depth=4, qubits=2, two_qubit_gates=2),
                gates_removed=2,
                gates_added=0,
                execution_time_ms=1.5,
            )
        ],
        post_optimization=StageMetrics(gates=8, depth=4, qubits=2, two_qubit_gates=2),
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
def mock_pipeline(sample_end_to_end_result: EndToEndResult) -> MagicMock:
    """Create a mock EndToEndPipeline."""
    pipeline = MagicMock()
    pipeline.run.return_value = sample_end_to_end_result
    return pipeline


@pytest.fixture
def sample_corpus() -> CircuitCorpus:
    """Create a small test corpus."""
    corpus = CircuitCorpus()
    corpus.add_ghz_circuits([2, 3])
    return corpus


@pytest.fixture
def experiment_config() -> ExperimentConfig:
    """Sample experiment configuration."""
    return ExperimentConfig(
        name="test_experiment",
        description="Test experiment for unit testing",
        passes_configs=[["cancel"], ["cancel", "commute"]],
        topology="iqm-garnet",
        noise_params=NoiseParams(
            t1_ns=30000.0,
            t2_ns=10000.0,
            single_qubit_error=0.001,
            two_qubit_error=0.006,
        ),
        route=True,
        parallel=False,
        max_workers=2,
        output_dir=Path("test_results"),
        seed=42,
    )


@pytest.fixture
def runner(mock_pipeline: MagicMock, sample_corpus: CircuitCorpus) -> BenchmarkRunner:
    """Create a BenchmarkRunner with mock pipeline."""
    return BenchmarkRunner(pipeline=mock_pipeline, corpus=sample_corpus)


# =============================================================================
# ExperimentConfig Tests
# =============================================================================


class TestExperimentConfig:
    """Tests for ExperimentConfig dataclass."""

    def test_create_with_defaults(self) -> None:
        """Config can be created with only required fields."""
        config = ExperimentConfig(name="minimal_config")

        assert config.name == "minimal_config"
        assert config.description == ""
        assert config.passes_configs == [["cancel"]]
        assert config.topology == "iqm-garnet"
        assert config.noise_params is None
        assert config.route is True
        assert config.parallel is False
        assert config.max_workers == 4
        assert config.seed == 42

    def test_create_with_all_fields(self, experiment_config: ExperimentConfig) -> None:
        """Config can be created with all fields specified."""
        assert experiment_config.name == "test_experiment"
        assert experiment_config.description == "Test experiment for unit testing"
        assert len(experiment_config.passes_configs) == 2
        assert experiment_config.noise_params is not None
        assert experiment_config.noise_params.t1_ns == 30000.0

    def test_to_dict(self, experiment_config: ExperimentConfig) -> None:
        """Config can be serialized to dictionary."""
        data = experiment_config.to_dict()

        assert data["name"] == "test_experiment"
        assert data["description"] == "Test experiment for unit testing"
        assert data["passes_configs"] == [["cancel"], ["cancel", "commute"]]
        assert data["topology"] == "iqm-garnet"
        assert data["route"] is True
        assert data["parallel"] is False
        assert data["max_workers"] == 2
        assert data["output_dir"] == "test_results"
        assert data["seed"] == 42
        assert "noise_params" in data
        assert data["noise_params"]["t1_ns"] == 30000.0

    def test_to_dict_without_noise(self) -> None:
        """Config without noise_params serializes correctly."""
        config = ExperimentConfig(name="no_noise")
        data = config.to_dict()

        assert "noise_params" not in data

    def test_from_dict(self) -> None:
        """Config can be deserialized from dictionary."""
        data: dict[str, Any] = {
            "name": "from_dict_test",
            "description": "Created from dict",
            "passes_configs": [["opt1"], ["opt2"]],
            "topology": "custom-topo",
            "route": False,
            "parallel": True,
            "max_workers": 8,
            "output_dir": "custom/path",
            "seed": 123,
            "noise_params": {
                "t1_ns": 25000.0,
                "t2_ns": 8000.0,
                "single_qubit_error": 0.002,
                "two_qubit_error": 0.008,
            },
        }

        config = ExperimentConfig.from_dict(data)

        assert config.name == "from_dict_test"
        assert config.description == "Created from dict"
        assert config.passes_configs == [["opt1"], ["opt2"]]
        assert config.topology == "custom-topo"
        assert config.route is False
        assert config.parallel is True
        assert config.max_workers == 8
        assert config.output_dir == Path("custom/path")
        assert config.seed == 123
        assert config.noise_params is not None
        assert config.noise_params.t1_ns == 25000.0

    def test_from_dict_with_defaults(self) -> None:
        """Config from minimal dict uses defaults."""
        data = {"name": "minimal"}

        config = ExperimentConfig.from_dict(data)

        assert config.name == "minimal"
        assert config.passes_configs == [["cancel"]]
        assert config.topology == "iqm-garnet"
        assert config.noise_params is None

    def test_roundtrip_serialization(self, experiment_config: ExperimentConfig) -> None:
        """Config survives to_dict() -> from_dict() roundtrip."""
        data = experiment_config.to_dict()
        restored = ExperimentConfig.from_dict(data)

        assert restored.name == experiment_config.name
        assert restored.description == experiment_config.description
        assert restored.passes_configs == experiment_config.passes_configs
        assert restored.topology == experiment_config.topology
        assert restored.route == experiment_config.route
        assert restored.parallel == experiment_config.parallel
        assert restored.seed == experiment_config.seed


# =============================================================================
# SingleRunResult Tests
# =============================================================================


class TestSingleRunResult:
    """Tests for SingleRunResult dataclass."""

    def test_successful_result(
        self, sample_end_to_end_result: EndToEndResult
    ) -> None:
        """Successful run has result and no error."""
        result = SingleRunResult(
            circuit_name="test_circuit",
            passes=["cancel"],
            result=sample_end_to_end_result,
            error=None,
            duration_seconds=0.5,
        )

        assert result.circuit_name == "test_circuit"
        assert result.passes == ["cancel"]
        assert result.result is not None
        assert result.error is None
        assert result.duration_seconds == 0.5

    def test_failed_result(self) -> None:
        """Failed run has error and no result."""
        result = SingleRunResult(
            circuit_name="failed_circuit",
            passes=["bad_pass"],
            result=None,
            error="Unknown pass: bad_pass",
            duration_seconds=0.1,
        )

        assert result.result is None
        assert result.error == "Unknown pass: bad_pass"


# =============================================================================
# ExperimentResults Tests
# =============================================================================


class TestExperimentResults:
    """Tests for ExperimentResults dataclass."""

    def test_empty_results(self, experiment_config: ExperimentConfig) -> None:
        """Empty results have zero counts."""
        results = ExperimentResults(config=experiment_config)

        assert results.success_count == 0
        assert results.error_count == 0
        assert len(results.results) == 0

    def test_success_count(
        self,
        experiment_config: ExperimentConfig,
        sample_end_to_end_result: EndToEndResult,
    ) -> None:
        """Success count tracks successful runs."""
        results = ExperimentResults(
            config=experiment_config,
            results=[
                SingleRunResult("c1", ["p"], sample_end_to_end_result, None, 0.1),
                SingleRunResult("c2", ["p"], sample_end_to_end_result, None, 0.1),
                SingleRunResult("c3", ["p"], None, "error", 0.1),
            ],
        )

        assert results.success_count == 2
        assert results.error_count == 1

    def test_successful_results_filter(
        self,
        experiment_config: ExperimentConfig,
        sample_end_to_end_result: EndToEndResult,
    ) -> None:
        """successful_results() returns only successful EndToEndResults."""
        results = ExperimentResults(
            config=experiment_config,
            results=[
                SingleRunResult("c1", ["p"], sample_end_to_end_result, None, 0.1),
                SingleRunResult("c2", ["p"], None, "error", 0.1),
                SingleRunResult("c3", ["p"], sample_end_to_end_result, None, 0.1),
            ],
        )

        successful = results.successful_results()
        assert len(successful) == 2
        assert all(r.circuit_name == "test_circuit" for r in successful)

    def test_errors_filter(self, experiment_config: ExperimentConfig) -> None:
        """errors() returns tuples of error info."""
        results = ExperimentResults(
            config=experiment_config,
            results=[
                SingleRunResult("c1", ["p1"], None, "error1", 0.1),
                SingleRunResult("c2", ["p2", "p3"], None, "error2", 0.1),
            ],
        )

        errors = results.errors()
        assert len(errors) == 2
        assert errors[0] == ("c1", ["p1"], "error1")
        assert errors[1] == ("c2", ["p2", "p3"], "error2")

    def test_total_duration(self, experiment_config: ExperimentConfig) -> None:
        """Total duration is computed from start/end times."""
        start = datetime(2024, 1, 1, 12, 0, 0)
        end = datetime(2024, 1, 1, 12, 0, 30)

        results = ExperimentResults(
            config=experiment_config,
            start_time=start,
            end_time=end,
        )

        assert results.total_duration_seconds == 30.0

    def test_total_duration_no_end(self, experiment_config: ExperimentConfig) -> None:
        """Total duration is 0 if no end time."""
        results = ExperimentResults(
            config=experiment_config,
            end_time=None,
        )

        assert results.total_duration_seconds == 0.0


# =============================================================================
# BenchmarkRunner Tests
# =============================================================================


class TestBenchmarkRunner:
    """Tests for BenchmarkRunner class."""

    def test_init(
        self, mock_pipeline: MagicMock, sample_corpus: CircuitCorpus
    ) -> None:
        """Runner initializes with pipeline and corpus."""
        runner = BenchmarkRunner(pipeline=mock_pipeline, corpus=sample_corpus)

        assert runner.pipeline is mock_pipeline
        assert runner.corpus is sample_corpus

    def test_run_single_success(
        self,
        runner: BenchmarkRunner,
        experiment_config: ExperimentConfig,
    ) -> None:
        """run_single() returns successful result."""
        qasm = "OPENQASM 3.0;\nqubit[2] q;\nh q[0];\ncx q[0], q[1];"

        result = runner.run_single(
            circuit_qasm=qasm,
            circuit_name="test_circuit",
            passes=["cancel"],
            config=experiment_config,
        )

        assert result.circuit_name == "test_circuit"
        assert result.passes == ["cancel"]
        assert result.result is not None
        assert result.error is None
        assert result.duration_seconds > 0

    def test_run_single_failure(
        self,
        mock_pipeline: MagicMock,
        sample_corpus: CircuitCorpus,
        experiment_config: ExperimentConfig,
    ) -> None:
        """run_single() captures errors gracefully."""
        mock_pipeline.run.side_effect = RuntimeError("Pipeline failed")
        runner = BenchmarkRunner(pipeline=mock_pipeline, corpus=sample_corpus)

        result = runner.run_single(
            circuit_qasm="invalid",
            circuit_name="failing_circuit",
            passes=["cancel"],
            config=experiment_config,
        )

        assert result.circuit_name == "failing_circuit"
        assert result.result is None
        assert result.error == "Pipeline failed"
        assert result.duration_seconds > 0

    def test_run_sequential(
        self,
        runner: BenchmarkRunner,
        experiment_config: ExperimentConfig,
    ) -> None:
        """run() executes all circuit/pass combinations."""
        # 2 circuits x 2 pass configs = 4 runs
        experiment_config.parallel = False

        results = runner.run(experiment_config)

        assert len(results.results) == 4  # 2 circuits * 2 pass configs
        assert results.success_count == 4
        assert results.error_count == 0
        assert results.end_time is not None

    def test_run_parallel(
        self,
        runner: BenchmarkRunner,
        experiment_config: ExperimentConfig,
    ) -> None:
        """run() with parallel=True uses thread pool."""
        experiment_config.parallel = True
        experiment_config.max_workers = 2

        results = runner.run(experiment_config)

        assert len(results.results) == 4  # 2 circuits * 2 pass configs
        assert results.success_count == 4

    def test_run_with_errors(
        self,
        mock_pipeline: MagicMock,
        sample_corpus: CircuitCorpus,
        experiment_config: ExperimentConfig,
        sample_end_to_end_result: EndToEndResult,
    ) -> None:
        """run() handles mixed success/failure."""
        # First call succeeds, second fails, etc.
        mock_pipeline.run.side_effect = [
            sample_end_to_end_result,
            RuntimeError("Failed"),
            sample_end_to_end_result,
            RuntimeError("Failed"),
        ]

        runner = BenchmarkRunner(pipeline=mock_pipeline, corpus=sample_corpus)
        results = runner.run(experiment_config)

        assert results.success_count == 2
        assert results.error_count == 2


# =============================================================================
# Save/Load Results Tests
# =============================================================================


class TestResultsPersistence:
    """Tests for saving and loading results."""

    def test_save_results_json(
        self,
        runner: BenchmarkRunner,
        experiment_config: ExperimentConfig,
        tmp_path: Path,
    ) -> None:
        """save_results() creates JSON file."""
        results = runner.run(experiment_config)
        output_path = tmp_path / "results.json"

        saved_path = runner.save_results(
            results, output_format="json", output_path=output_path
        )

        assert saved_path == output_path
        assert output_path.exists()

        # Verify JSON content
        import json

        with output_path.open() as f:
            data = json.load(f)

        assert data["config"]["name"] == "test_experiment"
        assert len(data["results"]) == 4
        assert data["success_count"] == 4

    def test_save_results_auto_path(
        self,
        runner: BenchmarkRunner,
        experiment_config: ExperimentConfig,
        tmp_path: Path,
    ) -> None:
        """save_results() auto-generates path from config."""
        experiment_config.output_dir = tmp_path
        results = runner.run(experiment_config)

        saved_path = runner.save_results(results, output_format="json")

        assert saved_path.parent == tmp_path
        assert saved_path.name.startswith("test_experiment_")
        assert saved_path.suffix == ".json"
        assert saved_path.exists()

    def test_save_results_invalid_format(
        self,
        runner: BenchmarkRunner,
        experiment_config: ExperimentConfig,
    ) -> None:
        """save_results() rejects invalid format."""
        results = runner.run(experiment_config)

        with pytest.raises(ValueError, match="Unsupported output format"):
            runner.save_results(results, output_format="xml")

    def test_load_results_json(
        self,
        runner: BenchmarkRunner,
        experiment_config: ExperimentConfig,
        tmp_path: Path,
    ) -> None:
        """load_results() reads JSON file."""
        results = runner.run(experiment_config)
        output_path = tmp_path / "results.json"
        runner.save_results(results, output_format="json", output_path=output_path)

        loaded = runner.load_results(output_path)

        assert loaded.config.name == "test_experiment"
        assert len(loaded.results) == 4
        # Note: loaded.results don't have full EndToEndResult reconstruction

    def test_load_results_invalid_suffix(
        self,
        runner: BenchmarkRunner,
        tmp_path: Path,
    ) -> None:
        """load_results() rejects unsupported file formats."""
        invalid_path = tmp_path / "results.xml"
        invalid_path.touch()

        with pytest.raises(ValueError, match="Unsupported file format"):
            runner.load_results(invalid_path)


# =============================================================================
# Config YAML Tests
# =============================================================================


class TestConfigYAML:
    """Tests for YAML configuration persistence."""

    def test_save_config(
        self,
        experiment_config: ExperimentConfig,
        tmp_path: Path,
    ) -> None:
        """save_config() creates YAML file."""
        config_path = tmp_path / "config.yaml"

        BenchmarkRunner.save_config(experiment_config, config_path)

        assert config_path.exists()

        # Verify YAML content
        import yaml

        with config_path.open() as f:
            data = yaml.safe_load(f)

        assert data["name"] == "test_experiment"
        assert data["passes_configs"] == [["cancel"], ["cancel", "commute"]]
        assert data["topology"] == "iqm-garnet"

    def test_load_config(
        self,
        experiment_config: ExperimentConfig,
        tmp_path: Path,
    ) -> None:
        """load_config() reads YAML file."""
        config_path = tmp_path / "config.yaml"
        BenchmarkRunner.save_config(experiment_config, config_path)

        loaded = BenchmarkRunner.load_config(config_path)

        assert loaded.name == "test_experiment"
        assert loaded.description == "Test experiment for unit testing"
        assert loaded.passes_configs == [["cancel"], ["cancel", "commute"]]

    def test_config_yaml_roundtrip(
        self,
        experiment_config: ExperimentConfig,
        tmp_path: Path,
    ) -> None:
        """Config survives save -> load roundtrip."""
        config_path = tmp_path / "config.yaml"

        BenchmarkRunner.save_config(experiment_config, config_path)
        loaded = BenchmarkRunner.load_config(config_path)

        assert loaded.name == experiment_config.name
        assert loaded.passes_configs == experiment_config.passes_configs
        assert loaded.topology == experiment_config.topology
        assert loaded.route == experiment_config.route
        assert loaded.parallel == experiment_config.parallel
        assert loaded.seed == experiment_config.seed

    def test_save_config_creates_directories(
        self,
        experiment_config: ExperimentConfig,
        tmp_path: Path,
    ) -> None:
        """save_config() creates parent directories."""
        config_path = tmp_path / "nested" / "deep" / "config.yaml"

        BenchmarkRunner.save_config(experiment_config, config_path)

        assert config_path.exists()
        assert config_path.parent.exists()


# =============================================================================
# Parquet Tests (Optional)
# =============================================================================


class TestParquetPersistence:
    """Tests for Parquet output (requires pyarrow)."""

    def test_save_results_parquet_import_error(
        self,
        runner: BenchmarkRunner,
        experiment_config: ExperimentConfig,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """save_results() raises clear error when pyarrow missing."""
        # Simulate missing pyarrow
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "pyarrow" or name.startswith("pyarrow."):
                raise ImportError("No module named 'pyarrow'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        results = runner.run(experiment_config)
        output_path = tmp_path / "results.parquet"

        with pytest.raises(ImportError, match="pyarrow"):
            runner.save_results(results, output_format="parquet", output_path=output_path)
