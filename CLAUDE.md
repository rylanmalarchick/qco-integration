# QCO-Integration — Agent Context for ACM TQC Submission

## Mission

You are working on **qco-integration**, a Python integration layer and paper repository for an end-to-end quantum circuit optimization pipeline. The C++ circuit optimizer source is at `~/dev/research/quantum-circuit-optimizer/`.

The goal is to finalize experiments and submit to **ACM Transactions on Quantum Computing** (free, CS-focused journal — ideal for compiler work).

**Target submission: ~Mar 10, 2026**

Existing preprint: arXiv:2601.20871. ACM TQC paper draft: `paper/acm_tqc/main.tex` (67KB, compiled PDF at `paper/acm_tqc/main.pdf` with 13 figures).

## Current State (Updated Feb 7, 2026)

### What's Done

- **Full ACM TQC paper draft** exists at `paper/acm_tqc/` (67KB main.tex, 685KB PDF, 13 figures) — UNTRACKED
- **Compiler comparison**: Working, 371 circuits x 7 compilers (QCO, Qiskit L0/L1/L1-IQM/L2/L3/L3-IQM). Results at `experiments/results/compiler_comparison/comparison_detail_20260207_195040.json` (1.2MB)
- **Ablation study**: Complete — individual passes, leave-one-out, 6 orderings, Kruskal-Wallis significance test
- **Full campaign**: 6 experiments run (baseline, per_pass, pass_combinations, routing, noise, scaling) with 371 circuits each. Results at `experiments/results/acm_tqc/`
- **Statistical analysis**: `experiments/statistical_analysis.py` (35KB) generates LaTeX tables and summary
- **LaTeX tables**: `experiments/results/latex_tables.tex` (7 auto-generated tables, ready to `\input{}`)
- **Statistical summary**: `experiments/results/statistical_summary.txt` (human-readable)
- **252 tests passing** (all green)

### The One Critical Issue: ALL DATA IS FROM MOCK PIPELINE

**Every result from Feb 7 used MockCircuitOptimizerBridge + MockGateCompiler.** Evidence:
- Per-circuit processing: ~0.0075s (real C++ optimizer + Lindblad would take ~0.1-1s per circuit)
- The `--real` flag was NOT used when running the campaign

**The C++ binary exists and is built:** `~/dev/research/quantum-circuit-optimizer/build/quantum_circuit_optimizer` (198KB, built Dec 31 2025). It should work — just needs to be invoked via `--real` flag.

**Action required:** Re-run with real pipeline:
```bash
.venv/bin/python experiments/run_campaign.py --real --paper
```
This will take **2-4 hours** (371 circuits x real C++ optimizer + Lindblad simulation). The compiler comparison script also needs a real-pipeline rerun.

### Key Results from Mock Data (will change with real pipeline)

| Metric | Mock Value | Notes |
|--------|-----------|-------|
| QCO gate reduction | 18.9% mean | (arXiv paper claimed 23.1%) |
| QCO 2Q gate reduction | 17.7% | **QCO's main advantage** |
| CancellationPass gates removed | 7,064 | (arXiv paper claimed 14,024) |
| Max gate reduction | 95.2% | (arXiv paper claimed 96.2%) |
| QCO vs Qiskit-L3 (head-to-head) | 57 wins, 110 losses, 204 ties | On total gate count |
| QCO on QAOA circuits | 100% 2Q reduction | Dominates |
| QCO on QFT circuits | 87.8% 2Q reduction | Strong |
| QCO on Random circuits | 3.2% 2Q reduction | Loses to L3's 10.9% |
| QCO vs L3 Cohen's d | 0.291 (small) | On 2Q gates |
| QCO vs L3 p-value | 0.200 | Not significant |
| QCO vs L3-IQM p-value | 0.012 | Significant |

**Framing note:** QCO loses on random circuits but dominates on structured circuits (QAOA, QFT). The paper should frame QCO as a specialized optimizer for structured quantum algorithms, not a general-purpose replacement for Qiskit L3.

## Git Status

**Last commit:** `b329c71` (Feb 7) — "ACM TQC experiments: full campaign, compiler comparison, ablation study, figures"

**Tracked files:** All clean (no modifications).

**Untracked (4 items):**
1. `experiments/results/latex_tables.tex` — 7 auto-generated LaTeX tables
2. `experiments/results/statistical_summary.txt` — human-readable stats summary
3. `experiments/statistical_analysis.py` — 35KB analysis script
4. `paper/acm_tqc/` — Complete paper draft (main.tex, main.pdf, 13 figures, build artifacts)

**All of these should be committed.**

## Task List (Priority Order)

### Task 1: Commit untracked files [5 min]

```bash
git add experiments/statistical_analysis.py experiments/results/latex_tables.tex experiments/results/statistical_summary.txt
git add paper/acm_tqc/main.tex paper/acm_tqc/figures/
git commit -m "feat: add statistical analysis, LaTeX tables, and ACM TQC paper draft

- Statistical analysis script with Wilcoxon, Cohen's d, bootstrap CIs
- 7 auto-generated LaTeX tables for paper
- Full ACM TQC paper draft with 13 figures"
```

Do NOT commit LaTeX build artifacts (`.aux`, `.log`, `.out`, `comment.cut`, `.pdf`). Add to `.gitignore` if not already there.

### Task 2: Re-run full campaign with real pipeline [2-4 hours]

```bash
.venv/bin/python experiments/run_campaign.py --real --paper --output experiments/results/acm_tqc_real/
```

This is the blocker. All paper numbers currently come from mock data.

**Pre-check:** Verify the C++ binary works:
```python
from src.bridge import CircuitOptimizerBridge
bridge = CircuitOptimizerBridge("~/dev/research/quantum-circuit-optimizer/build/quantum_circuit_optimizer")
# Test with a small circuit
```

### Task 3: Re-run compiler comparison with real QCO [1-2 hours]

After real campaign, re-run the compiler comparison to get real QCO compile times and fidelity estimates.

### Task 4: Re-run statistical analysis on real data [10 min]

```bash
.venv/bin/python experiments/statistical_analysis.py
```

Update `latex_tables.tex` and `statistical_summary.txt` with real numbers.

### Task 5: Update paper with real numbers [writing task]

- Replace all mock-derived numbers in `paper/acm_tqc/main.tex`
- Regenerate figures from real data
- Carefully frame QCO vs Qiskit-L3 results (structured vs random circuit performance)
- Expand bibliography to 30+ references
- Add reproducibility section (ACM values artifact evaluation)
- Finalize cover letter

### Task 6: Hardware validation [nice-to-have]

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
├── statistical_analysis.py — Stats + LaTeX table generation (35KB, UNTRACKED)
├── benchmark_compilers.py — Compiler comparison (working, replaced old broken version)
├── results/
│   ├── acm_tqc/            — Full campaign results (10 JSON files, 371 circuits each, MOCK)
│   ├── compiler_comparison/ — 7 compilers x 371 circuits (1.2MB final, MOCK for QCO path)
│   ├── ablation/           — Individual + leave-one-out + ordering (MOCK)
│   ├── smoke_test/         — 4-circuit test run
│   ├── latex_tables.tex    — 7 auto-generated tables (UNTRACKED)
│   └── statistical_summary.txt — Human-readable summary (UNTRACKED)
├── figures/                — PDF publication figures (13 in paper/acm_tqc/figures/)
└── configs/                — Experiment configs

paper/
├── main.tex, main.pdf     — arXiv v1
├── arxiv_v2/              — arXiv v2 with upload zip
├── ieee_tqe/              — IEEE TQE version
└── acm_tqc/               — ACM TQC version (UNTRACKED)
    ├── main.tex           — 67KB full paper
    ├── main.pdf           — 685KB compiled
    └── figures/           — 13 PDF figures (compiler heatmaps, ablation plots, etc.)

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
