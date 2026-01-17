# QCO-Integration Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          qco-integration (Python)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌─────────────────────┐    ┌──────────────────────┐   │
│  │ CircuitCorpus│───▶│ CircuitOptimizerBridge│───▶│  EndToEndPipeline   │   │
│  │              │    │     (subprocess)     │    │                      │   │
│  │ - VQE        │    │                      │    │ Stage 1: Parse       │   │
│  │ - QFT        │    │ Input: OpenQASM      │    │ Stage 2: Optimize    │   │
│  │ - QAOA       │    │ Output: JSON+QASM    │    │ Stage 3: Route       │   │
│  │ - GHZ        │    │                      │    │ Stage 4: Pulse       │   │
│  │ - Random     │    └──────────┬───────────┘    │ Stage 5: Simulate    │   │
│  └──────────────┘               │                └───────────┬──────────┘   │
│                                 │                            │              │
│                                 ▼                            ▼              │
│                    ┌────────────────────────┐   ┌────────────────────────┐  │
│                    │ quantum-circuit-        │   │ QubitPulseOpt          │  │
│                    │ optimizer (C++ binary)  │   │ (Python library)       │  │
│                    │                         │   │                        │  │
│                    │ - OpenQASM 3.0 parser   │   │ - GateCompiler         │  │
│                    │ - DAG IR                │   │ - GRAPE/Krotov         │  │
│                    │ - Optimization passes   │   │ - Lindblad simulation  │  │
│                    │ - SABRE routing         │   │ - IQM noise model      │  │
│                    └────────────────────────┘   └────────────────────────┘  │
│                                                                              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐   │
│  │  BenchmarkRunner │    │   MetricsStore   │    │   Visualization      │   │
│  │                  │    │                  │    │                      │   │
│  │ - Experiment     │    │ - JSON/Parquet   │    │ - Waterfall charts   │   │
│  │   configuration  │    │ - Per-stage data │    │ - Scaling plots      │   │
│  │ - Parallel exec  │    │ - Aggregations   │    │ - Pass effectiveness │   │
│  └──────────────────┘    └──────────────────┘    └──────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Input Circuit (OpenQASM)
         │
         ▼
┌─────────────────────────────┐
│ Stage 1: Parse & Validate   │ ──▶ input_metrics: {gates, depth, qubits}
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Stage 2: Optimize           │ ──▶ per_pass_metrics: [{name, gates_in, gates_out, ...}]
│ (C++ subprocess)            │
│ - CancellationPass          │
│ - CommutationPass           │
│ - RotationMergePass         │
│ - IdentityEliminationPass   │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Stage 3: Route              │ ──▶ routing_metrics: {swaps_inserted, depth_increase}
│ (SABRE for IQM Garnet)      │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Stage 4: Pulse Compilation  │ ──▶ pulse_metrics: {total_duration, pulse_count}
│ (QubitPulseOpt GateCompiler)│
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Stage 5: Noise Simulation   │ ──▶ fidelity_metrics: {process_fidelity, state_fidelity}
│ (Lindblad master equation)  │
└─────────────────────────────┘
         │
         ▼
    EndToEndResult
```

## Key Classes

### CircuitOptimizerBridge

```python
class CircuitOptimizerBridge:
    """Subprocess wrapper for quantum-circuit-optimizer C++ binary."""
    
    def __init__(self, binary_path: str):
        self.binary_path = binary_path
    
    def optimize(
        self,
        qasm: str,
        passes: List[str],
        topology: Optional[str] = None,
        route: bool = False,
    ) -> OptimizationResult:
        """Run optimization and return results with per-pass metrics."""
        ...
```

### EndToEndPipeline

```python
class EndToEndPipeline:
    """Orchestrates the full compilation and simulation flow."""
    
    def __init__(
        self,
        optimizer_bridge: CircuitOptimizerBridge,
        gate_compiler: GateCompiler,
        noise_params: NoiseParams,
    ):
        ...
    
    def run(
        self,
        circuit: str,
        passes: List[str],
        topology: str = "iqm-garnet",
    ) -> EndToEndResult:
        """Execute full pipeline and collect metrics."""
        ...
```

### Metrics Dataclasses

```python
@dataclass
class StageMetrics:
    gates: int
    depth: int
    qubits: int
    two_qubit_gates: int

@dataclass
class PassMetrics:
    name: str
    input_metrics: StageMetrics
    output_metrics: StageMetrics
    gates_removed: int
    execution_time_ms: float

@dataclass
class PulseMetrics:
    total_duration_ns: float
    pulse_count: int
    max_amplitude: float

@dataclass
class EndToEndResult:
    circuit_name: str
    input_metrics: StageMetrics
    optimization_passes: List[PassMetrics]
    post_optimization: StageMetrics
    routing_metrics: RoutingMetrics
    pulse_metrics: PulseMetrics
    process_fidelity: float
    state_fidelity: float
    noise_params: NoiseParams
    topology: str
    timestamp: datetime
```

## Directory Structure

```
qco-integration/
├── agent_docs/
│   ├── PROJECT_CONTEXT.md
│   ├── SCOPE_OF_WORK.md
│   ├── IQM_GARNET_SPEC.md
│   └── ARCHITECTURE.md
├── src/
│   ├── __init__.py
│   ├── bridge.py              # CircuitOptimizerBridge
│   ├── pipeline.py            # EndToEndPipeline
│   ├── corpus.py              # CircuitCorpus
│   ├── metrics.py             # Dataclasses for metrics
│   ├── runner.py              # BenchmarkRunner
│   └── visualization.py       # Plotting utilities
├── experiments/
│   ├── configs/               # Experiment configurations (YAML)
│   └── notebooks/             # Jupyter notebooks for analysis
├── results/
│   ├── raw/                   # Raw experiment outputs (JSON)
│   └── processed/             # Aggregated results (Parquet)
├── paper/
│   ├── main.tex               # LaTeX preprint
│   ├── figures/               # Generated figures
│   └── references.bib         # Bibliography
├── tests/
│   ├── test_bridge.py
│   ├── test_pipeline.py
│   └── test_corpus.py
├── pyproject.toml
└── README.md
```

## Integration Points

### quantum-circuit-optimizer (IMPLEMENTED)

**Binary Interface:**
```bash
./quantum_circuit_optimizer \
  --input /path/to/circuit.qasm \
  --output /path/to/output.json \
  --passes cancel,commute,rotate,identity \
  --topology iqm-garnet \
  --route \
  --output-format json
```

**JSON Output Schema:**
```json
{
  "input": {
    "gates": 50,
    "depth": 20,
    "qubits": 8,
    "two_qubit_gates": 15
  },
  "passes": [
    {
      "name": "CancellationPass",
      "gates_removed": 5,
      "gates_added": 0,
      "output_gates": 45,
      "output_depth": 18
    }
  ],
  "post_optimization": {
    "gates": 40,
    "depth": 15,
    "qubits": 8,
    "two_qubit_gates": 12
  },
  "routing": {
    "topology": "iqm-garnet",
    "swaps_inserted": 6,
    "final_gates": 52,
    "final_depth": 22
  },
  "output_qasm": "OPENQASM 3.0; ..."
}
```

### QubitPulseOpt

**GateCompiler Interface:**
```python
from qubit_pulse_opt.optimization.compilation import GateCompiler

compiler = GateCompiler(
    qubit_params=iqm_garnet_params,
    optimizer="grape",
    fidelity_target=0.999,
)

pulses = compiler.compile_gate_sequence(gate_sequence)
fidelity = compiler.simulate_with_noise(pulses, noise_model)
```
