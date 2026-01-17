# QCO-Integration Scope of Work

## Project Goal

Create an integration layer and experimental framework to analyze end-to-end quantum compilation fidelity, from high-level circuit optimization through pulse-level control, resulting in an arXiv preprint.

## Phases

### Phase 1: Integration Layer Infrastructure

**Objective:** Build the Python orchestration layer connecting the C++ optimizer to QubitPulseOpt.

#### Tasks
1. **CircuitOptimizerBridge** - Subprocess wrapper for C++ binary
   - Input: OpenQASM circuit string
   - Output: Optimized OpenQASM + JSON statistics (per-pass metrics)
   - Handle binary path configuration
   - Parse JSON output for metrics extraction

2. **OpenQASM utilities** - Round-trip parsing/emission
   - Convert between internal representation and OpenQASM 3.0
   - Validate circuit integrity after transformations

3. **EndToEndPipeline** - Main orchestration class
   - Stage 1: Parse input circuit
   - Stage 2: Run C++ optimizer (configurable passes)
   - Stage 3: Route for target topology
   - Stage 4: Compile to pulses via QubitPulseOpt GateCompiler
   - Stage 5: Simulate with noise model
   - Collect metrics at each stage

4. **Integration tests** - Verify round-trip correctness

### Phase 2: Circuit Corpus & Benchmark Infrastructure

**Objective:** Create a diverse set of benchmark circuits for experimental analysis.

#### Tasks
1. **VQE circuit extraction** - Convert QuantumVQE circuits to OpenQASM
2. **Synthetic benchmarks** - Generate:
   - QFT (various sizes: 4, 8, 12, 16, 20 qubits)
   - QAOA (MaxCut, various graph sizes)
   - GHZ states
   - Random circuits (controlled depth/gate density)
3. **BenchmarkRunner** - Automated experiment execution
   - Configuration-driven experiments
   - Parallel execution where possible
   - Results persistence (JSON/Parquet)
4. **Metrics schema** - Comprehensive data model for results

### Phase 3: Experimental Campaign

**Objective:** Run systematic experiments to characterize fidelity across the compilation pipeline.

#### Experiments
1. **Baseline** - No optimization, direct pulse compilation
2. **Per-pass analysis** - Each optimization pass individually
3. **Pass combinations** - Ordered combinations of passes
4. **Routing impact** - Pre/post routing fidelity comparison
5. **Sequential vs joint** - Compare gate-by-gate vs joint pulse optimization
6. **Noise sensitivity** - Vary T1/T2 parameters
7. **Scaling analysis** - Circuit size vs fidelity degradation

### Phase 4: Analysis & Visualization

**Objective:** Generate publication-quality figures and insights.

#### Deliverables
1. **Fidelity waterfall charts** - Stage-by-stage breakdown
2. **Per-pass effectiveness** - Tables and bar charts
3. **Scaling plots** - Qubits/depth vs fidelity
4. **Pulse comparisons** - Before/after optimization waveforms
5. **Architecture diagram** - System overview for paper

### Phase 5: Preprint Writing

**Objective:** Write and submit arXiv preprint (15-20 pages, LaTeX).

#### Structure
1. Introduction & Background
2. System Architecture
3. Methodology
4. Results
5. Discussion
6. Conclusion & Future Work
7. Supplementary Materials

## Out of Scope

- Hardware validation (too expensive)
- pybind11 integration (using subprocess instead)
- Real-time parameter updates from hardware
- Multi-QPU comparison (focusing on IQM Garnet only)

## Dependencies

### quantum-circuit-optimizer CLI (IMPLEMENTED)
The C++ CLI has been enhanced with the following interface:
```bash
./quantum_circuit_optimizer \
    --input circuit.qasm \
    --output result.json \
    --passes cancel,commute,rotate,identity \
    --topology iqm-garnet \
    --route \
    --output-format json
```

CLI Options:
- `--input <file>`: Input OpenQASM 3.0 file (required)
- `--output <file>`: Output file (default: stdout)
- `--passes <list>`: Comma-separated passes (cancel, commute, rotate, identity)
- `--topology <spec>`: Target topology (linear-N, ring-N, grid-RxC, heavy-hex-D, iqm-garnet)
- `--route`: Enable SABRE routing after optimization
- `--output-format <f>`: Output format (json or qasm)
- `--help`: Show usage

JSON Output format:
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

## Success Criteria

1. End-to-end pipeline runs without manual intervention
2. Per-pass fidelity data collected for all benchmark circuits
3. Reproducible experimental results
4. Publication-ready figures generated
5. Complete arXiv preprint draft
