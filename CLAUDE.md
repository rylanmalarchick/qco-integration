# QCO-Integration — Agent Context for ACM TQC Submission

## Mission

You are working on **qco-integration**, a Python integration layer and paper repository for an end-to-end quantum circuit optimization pipeline. The C++ circuit optimizer source is at `~/dev/research/quantum-circuit-optimizer/`.

The goal is to finalize experiments and submit to **ACM Transactions on Quantum Computing** (free, CS-focused journal — ideal for compiler work).

**Target submission: ~Mar 10, 2026**

Existing preprint: arXiv:2601.20871. ACM TQC paper draft: `paper/acm_tqc/main.tex` (67KB, compiled PDF at `paper/acm_tqc/main.pdf` with 13 figures).

## Current State (Updated Feb 7, 2026)

### What's Done

- **Full ACM TQC paper draft** at `paper/acm_tqc/` — updated with real pipeline numbers
- **Bug fix**: `RealPulseGateCompiler.simulate_with_noise()` in `src/pipeline.py` was ignoring the `noise_model` argument; now correctly propagates noise params so noise sensitivity experiment produces distinct fidelities per regime
- **Bug fix**: `experiments/run_campaign.py` figure generation crash — bar chart alignment when baseline and optimized have different circuit counts; now matches by circuit name
- **Real pipeline campaign**: 6 experiments, 371 circuits, 6,707 runs, results at `experiments/results/acm_tqc_real/` (10 JSON files, ~3.7MB)
- **Compiler comparison**: 371 circuits x 7 compilers (QCO, Qiskit L0/L1/L1-IQM/L2/L3/L3-IQM). Results at `experiments/results/compiler_comparison/comparison_detail_20260207_204727.json`
- **Ablation study**: Complete — individual passes, leave-one-out, 6 orderings, Kruskal-Wallis significance test
- **Statistical analysis**: `experiments/statistical_analysis.py` generates LaTeX tables and summary from real data
- **LaTeX tables**: `experiments/results/latex_tables.tex` (7 auto-generated tables)
- **Statistical summary**: `experiments/results/statistical_summary.txt`
- **Paper updated**: All numerical values in `paper/acm_tqc/main.tex` now reflect real pipeline data
- **252 tests passing** (all green)

### Key Results (Real Pipeline)

| Metric | Value | Notes |
|--------|-------|-------|
| QCO gate reduction | 18.9% mean | |
| QCO 2Q gate reduction | 17.7% | **QCO's main advantage** |
| CancellationPass gates removed | 7,064 | |
| Max gate reduction | 95.2% | |
| Pulse duration correlation | r=-0.868, R^2=0.754 | Strongest predictor |
| Input gates correlation | r=-0.857, R^2=0.734 | |
| Two-qubit gates correlation | r=-0.750, R^2=0.563 | |
| QCO on QAOA circuits | 100% 2Q reduction | Dominates |
| QCO on QFT circuits | 87.8% 2Q reduction | Strong |
| QCO on Random circuits | 3.2% 2Q reduction | Loses to L3's 10.9% |
| QCO vs L3 Cohen's d | 0.291 (small) | On 2Q gates |
| QCO vs L3 p-value | 0.200 | Not significant |
| QCO vs L3-IQM p-value | 0.012 | Significant |
| Noise (low, T1/T2=100/50us) | baseline 0.75, opt 0.81 | 8% improvement |
| Noise (very high, T1/T2=10/2.5us) | baseline 0.20, opt 0.30 | 50% improvement |

**Framing note:** QCO loses on random circuits but dominates on structured circuits (QAOA, QFT). The paper frames QCO as a specialized optimizer for structured quantum algorithms, not a general-purpose replacement for Qiskit L3.

## Remaining Tasks

### Task 1: Verify LaTeX compiles [5 min]

```bash
cd paper/acm_tqc && latexmk -pdf main.tex
```

### Task 2: Expand bibliography to 30+ references [writing task]

ACM TQC expects comprehensive references. Current count: 32 bibitems. May want to add more.

### Task 3: Write cover letter for submission

### Task 4: Hardware validation [nice-to-have]

IQM Resonance data was collected previously (8 QPU jobs) but results aren't saved in the repo. If IQM free tier is still accessible, re-run and save. Otherwise, state collection date in paper.

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
│   Flags: --real (use C++ binary + Lindblad), --paper (371 circuits), --quick (4 circuits)
│   Default: mock pipeline, 19-circuit standard corpus
├── statistical_analysis.py — Stats + LaTeX table generation (927 lines)
├── benchmark_compilers.py — Compiler comparison (7 compilers x 371 circuits)
├── results/
│   ├── acm_tqc/            — Original mock campaign results
│   ├── acm_tqc_real/       — Real pipeline campaign results (10 JSON files)
│   ├── compiler_comparison/ — 7 compilers x 371 circuits (1.2MB)
│   ├── ablation/           — Individual + leave-one-out + ordering
│   ├── smoke_test/         — 4-circuit test run
│   ├── latex_tables.tex    — 7 auto-generated tables
│   └── statistical_summary.txt — Human-readable summary
├── figures/                — PDF publication figures
└── configs/                — Experiment configs

paper/
├── main.tex, main.pdf     — arXiv v1
├── arxiv_v2/              — arXiv v2 with upload zip
├── ieee_tqe/              — IEEE TQE version
└── acm_tqc/               — ACM TQC version
    ├── main.tex           — 67KB full paper (updated with real numbers)
    ├── main.pdf           — Compiled PDF
    └── figures/           — 13 PDF figures

tests/                     — 252 passing tests
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
└── build/         — quantum_circuit_optimizer binary (198KB, built Dec 31 2025)
```

## Environment

- Python 3.12+ (use `.venv/bin/python`, NOT bare `python3` — system python is 3.14)
- qiskit, qiskit-aer, iqm-client, iqm-pulse, numpy, scipy, pandas, matplotlib
- Run tests: `.venv/bin/python -m pytest tests/ -q`
- Run campaign: `.venv/bin/python experiments/run_campaign.py --real --paper`
- Lint: `ruff check src/`
- Style: snake_case functions, PascalCase classes, type hints
- Git: conventional commits (feat, fix, test, docs)
