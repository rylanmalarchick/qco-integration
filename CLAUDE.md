# QCO-Integration — Agent Context for ACM TQC Submission Experiments

## Mission

You are working on **qco-integration**, a Python integration layer and paper repository for an end-to-end quantum circuit optimization pipeline. The C++ circuit optimizer source is at `~/dev/research/quantum-circuit-optimizer/`.

The goal is to run experiments needed to submit to **ACM Transactions on Quantum Computing** (free, CS-focused journal — ideal for compiler work).

**Target submission: ~Mar 10, 2026**

The arXiv preprint is at arXiv:2601.20871. The IEEE TQE draft is at `paper/ieee_tqe/main_full_extended.tex` (596 lines, appears complete). The paper needs to be adapted for ACM TQC format and strengthened with compiler comparison + ablation study.

## Current State

### What Works
- Full 5-stage pipeline: Parse → Optimize (C++ binary) → Route (SABRE) → Pulse Compile → Noise Simulate (Lindblad)
- 6 experiment types implemented in `experiments/run_campaign.py`: baseline, per_pass, pass_combinations, routing_impact, noise_sensitivity, scaling_analysis
- 8 publication-quality PDF figures generated
- C++ optimizer is fully complete (v1.0.0): 4 optimization passes (CancellationPass, CommutationPass, RotationMergePass, IdentityEliminationPass), SABRE routing, OpenQASM 3.0 parser

### Key Published Results (from paper)
- 371 circuits benchmarked (11 GHZ + 7 QFT + 50 QAOA + 303 Random)
- 23.1% mean gate reduction (max 96.2% on QFT circuits)
- CancellationPass most effective: 14,024 gates removed, 68% of circuits improved
- Pulse duration strongest fidelity predictor: r=-0.743, R²=0.553
- 8 hardware jobs executed on IQM Resonance

## Critical Issues to Address

### Issue 1: Paper Numbers Don't Match JSON Results (INVESTIGATE)

The paper claims 371 circuits and 14,024 gates eliminated, but the most recent experiment JSON files show only 4 circuits (small corpus) or 19 circuits (standard corpus). Possible explanations:
- An earlier full run produced these numbers but results weren't preserved
- The numbers were projected/estimated
- There's a different results directory

**Action:** Run `create_standard_corpus()` from `src/corpus.py` and verify it produces 371 circuits. Then run the full campaign with `--real` flag. If the C++ binary isn't available, build it first from `~/dev/research/quantum-circuit-optimizer/`.

### Issue 2: Compiler Comparison is Completely Empty

**File:** `experiments/benchmark_compilers.py` (153 lines)

The existing script has multiple problems:
1. Imports `OptimizationPipeline` which doesn't exist (line 23) — should use `EndToEndPipeline` or `CircuitOptimizerBridge`
2. Only 2 hardcoded test circuits (ghz_4q, qft_4q) — needs the full corpus
3. Uses QASM 3.0 syntax (`qubit[4] q`) but `QuantumCircuit.from_qasm_str()` only supports QASM 2.0
4. Only Qiskit has a runner function — Cirq and tket have import detection but NO optimization functions
5. The QCO path doesn't actually call the optimizer
6. Only compares gate counts, not fidelity or compilation time
7. The result file `experiments/results/compiler_comparison/comparison_20260202_210602.json` shows all compilers as `false`

**Action:** Rewrite `benchmark_compilers.py` from scratch. See Experiment 2 below.

### Issue 3: All Recent Experiments Used Mock Pipeline

Run times of 0.003-0.005s per circuit confirm the MockCircuitOptimizerBridge and MockGateCompiler were used. The `--real` flag in `run_campaign.py` enables real C++ optimizer + Lindblad simulation.

**Action:** Ensure the C++ binary is built, then re-run with `--real`.

### Issue 4: Hardware Validation Data Not in Repository

Table 7 in the paper cites specific IQM Resonance results (ghz_4/8/12q, qft_4q with 160 shots), but no hardware result files exist in `experiments/results/`. The data may have been collected interactively.

**Action:** Check if IQM Resonance free tier is still accessible. If so, re-run and save results. If not, clearly state in paper that hardware data was collected on specific date and is not reproducible on-demand.

## Codebase Structure

```
src/
├── bridge.py          — CircuitOptimizerBridge (subprocess to C++ binary) + MockBridge
├── pipeline.py        — EndToEndPipeline (5 stages), RealPulseGateCompiler, MockGateCompiler
├── pulse.py           — PulseSimulator (Lindblad), RealGateCompiler, IQM params
├── corpus.py          — CircuitCorpus: GHZ, QFT, QAOA, Random circuit generators
├── runner.py          — BenchmarkRunner, ExperimentConfig, JSON persistence
├── analysis.py        — Descriptive stats, pass effectiveness, scaling, regression, Cohen's d
├── metrics.py         — StageMetrics, PassMetrics, RoutingMetrics, PulseMetrics, EndToEndResult
├── visualization.py   — Publication plots: waterfall, pass effectiveness, scaling, architecture
├── qasm.py            — QASM utilities
├── hardware.py        — Hardware integration
└── hardware_analysis.py — Hellinger distance, TVD, KS-statistic

experiments/
├── run_campaign.py        — Main experiment runner (6 experiment types)
├── benchmark_compilers.py — BROKEN compiler comparison script
├── results/               — JSON results from multiple runs
│   └── compiler_comparison/ — Empty/failed comparison result
├── reports/               — Experiment summaries
├── figures/               — 8 PDF publication figures
└── configs/               — Experiment configs

paper/
├── main.tex, main.pdf     — arXiv v1
├── arxiv_v2/              — arXiv v2 with upload zip
└── ieee_tqe/              — IEEE TQE version (main.tex, main_full.tex, main_full_extended.tex, cover_letter.tex)

tests/                     — 251 passing tests
```

### C++ Optimizer (separate repo)
```
~/dev/research/quantum-circuit-optimizer/
├── include/
│   ├── ir/        — Gate, Circuit, DAGCircuit
│   ├── parser/    — OpenQASM 3.0 Lexer, Parser
│   ├── passes/    — CancellationPass, CommutationPass, RotationMergePass, IdentityEliminationPass, PassManager
│   └── routing/   — SabreRouter, Topology
├── src/           — Implementation files
├── tests/         — 340 unit tests
└── build/         — quantum_circuit_optimizer binary (if built)
```

## Experiments to Run (Priority Order)

### Experiment 0: Build C++ Optimizer + Verify Pipeline [PREREQUISITE]
**Effort:** 30 min

1. Check if binary exists: `ls ~/dev/research/quantum-circuit-optimizer/build/quantum_circuit_optimizer`
2. If not, build it:
   ```bash
   cd ~/dev/research/quantum-circuit-optimizer
   mkdir -p build && cd build
   cmake .. && make -j$(nproc)
   ```
3. Verify bridge works: In Python, instantiate `CircuitOptimizerBridge` with the binary path and run a small test circuit
4. Run the test suite: `pytest tests/ -v` from the qco-integration directory

### Experiment 1: Full Campaign with Real Pipeline [REGENERATE ALL DATA]
**Effort:** 2-4 hours (compute-bound)

1. Verify `create_standard_corpus()` produces 371 circuits
2. Run full campaign with real C++ optimizer + Lindblad simulation:
   ```bash
   cd ~/dev/research/qco-integration
   python experiments/run_campaign.py --real --output experiments/results/pra_submission/
   ```
3. Verify paper numbers match (or update paper with new numbers)
4. Regenerate all 8 figures

### Experiment 2: Compiler Comparison [CRITICAL FOR ACM TQC]
**Effort:** 1-2 days

Rewrite `experiments/benchmark_compilers.py` to properly compare against other compilers.

**What to compare:**
| Compiler | How to Run | Gate Set |
|----------|-----------|----------|
| QCO | CircuitOptimizerBridge | OpenQASM 3.0 native |
| Qiskit Level 0 | `transpile(qc, optimization_level=0)` | Qiskit basis gates |
| Qiskit Level 1 | `transpile(qc, optimization_level=1)` | Qiskit basis gates |
| Qiskit Level 2 | `transpile(qc, optimization_level=2)` | Qiskit basis gates |
| Qiskit Level 3 | `transpile(qc, optimization_level=3)` | Qiskit basis gates |

**Important implementation notes:**
- Circuits must be in QASM 2.0 format for Qiskit (`QuantumCircuit.from_qasm_str()` doesn't support QASM 3.0)
- The `CircuitCorpus` generates QASM 3.0 — you'll need a conversion function (check `src/qasm.py`)
- If QASM 3.0→2.0 conversion is too complex, generate circuits directly as Qiskit QuantumCircuit objects AND as QASM 3.0 strings for QCO
- Cirq and tket are nice-to-have but Qiskit comparison alone is sufficient for ACM TQC
- Compare: gate count, circuit depth, compilation time, and (if possible) estimated fidelity

**Metrics per circuit per compiler:**
- Input gates, output gates, reduction %
- Input depth, output depth, depth reduction %
- Compilation wall-clock time
- (Optional) Fidelity estimate using PulseSimulator

**Use the full 371-circuit corpus** (or at minimum, a representative subset of 50+ circuits covering all types).

### Experiment 3: Formal Ablation Study [REQUIRED]
**Effort:** 1 day

The per_pass and pass_combinations experiments already exist but need to be structured as a formal ablation:

1. **Individual passes:** Run each pass alone on the full corpus
   - CancellationPass only
   - CommutationPass only
   - RotationMergePass only
   - IdentityEliminationPass only
2. **Leave-one-out:** Run all passes EXCEPT one
   - All except Cancel
   - All except Commute
   - All except Rotate
   - All except Identity
3. **Ordered combinations:** Test ordering effects
   - Cancel → Commute → Rotate → Identity (default)
   - Rotate → Cancel → Commute → Identity
   - Commute → Cancel → Rotate → Identity
4. **Metrics:** Gate reduction, depth reduction, fidelity impact

The infrastructure for this is already in `run_campaign.py` (per_pass and pass_combinations experiments). May just need to add the leave-one-out and ordering variants.

### Experiment 4: Physical Interpretation of r=-0.74 [WRITING TASK]
**Effort:** 0.5 day

Why is pulse duration the strongest fidelity predictor (r=-0.743)?

Physical explanation: longer pulse duration → more time exposed to T1/T2 decoherence → lower fidelity. This is essentially F ≈ exp(-t_gate/T2) for dephasing-dominated noise.

Verify by:
1. Plotting fidelity vs pulse_duration and fitting exponential decay
2. Comparing the decay rate to 1/T2
3. Showing that after controlling for pulse duration, gate count has weak residual correlation

### Experiment 5: Larger Circuit Benchmarks [NICE-TO-HAVE]
**Effort:** 0.5 day

Add to corpus:
- VQE ansatz circuits (2-8 qubits, 1-3 layers)
- Grover's algorithm circuits
- Quantum phase estimation circuits
- Increase random circuit diversity (depths 1-50, qubits 2-16)

## Paper Adaptation for ACM TQC

After experiments, convert from IEEE TQE to ACM format:
1. Use `acmart` document class with `acmtog` or `acmlarge` style
2. Add ACM CCS concepts for quantum computing
3. Add new sections:
   - Compiler comparison (with table and figure)
   - Formal ablation study (with table)
   - Expanded r=-0.74 analysis
4. Expand bibliography from 13 to 30+ references
5. Add reproducibility section (ACM values artifact evaluation)
6. Rewrite cover letter for ACM TQC

## Installed Dependencies

The venv at `.venv/` has Python 3.12 with:
- qiskit, qiskit-aer (for compiler comparison)
- iqm-client, iqm-pulse (for hardware)
- numpy, scipy, pandas, matplotlib
- pytest, ruff, mypy

Activate: `source .venv/bin/activate`

## Key Metrics to Track

- Gate count reduction (%)
- Circuit depth reduction (%)
- Process fidelity (from Lindblad simulation)
- Compilation time (wall-clock seconds)
- Statistical significance (Cohen's d, p-values from `src/analysis.py`)

## Style

- Snake_case functions, PascalCase classes
- Type hints on all functions
- Run tests: `source .venv/bin/activate && pytest tests/ -v`
- Run experiments: `source .venv/bin/activate && python experiments/run_campaign.py`
- Lint: `ruff check src/`
