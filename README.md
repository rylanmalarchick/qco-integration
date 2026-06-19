# qco-integration

Integration layer connecting quantum-circuit-optimizer (C++17) with QubitPulseOpt (Python) for end-to-end quantum compilation fidelity analysis.

## Overview

This project provides an orchestration layer for analyzing fidelity degradation across the quantum compilation pipeline, from high-level circuit optimization through pulse-level control. The goal is to produce an arXiv preprint with systematic experimental analysis.

## Project Status

Active revision. An earlier version was submitted to ACM Transactions on Quantum
Computing (manuscript TQC-2026-0027) and rejected; preprint
[arXiv:2601.20871](https://arxiv.org/abs/2601.20871). The current work replaces
the original simulation model with a validated one and rewrites the manuscript
around what that model actually supports (see `docs/bakeoff_evidence.md` and the
revised `paper/acm_tqc/main.tex`).

### What changed in this revision

- **Real fidelity model.** The original "Lindblad" fidelities were a closed-form
  exponential-decay heuristic. They are replaced by a per-gate Lindblad
  master-equation solve (relaxation + dephasing + a calibrated depolarizing
  channel, plus idle decoherence on an ASAP schedule), cross-validated against
  `qiskit-dynamics` to `<1e-7`. An optional non-Markovian `1/f` filter-function
  model is included.
- **Provenanced hardware run.** Eight circuits executed on IQM Resonance Garnet
  (10,000 shots each, job IDs recorded). The validated model is a consistent
  upper bound on measured fidelity (mean sim$-$hw gap 0.49); it preserves
  relative circuit ordering but omits crosstalk, leakage, and readout error.
- **Honest framing.** No "hardware-validated" claim for absolute fidelity; the
  hardware run quantifies the model's error budget instead.

### Key results (validated model, 371-circuit campaign)

- Mean process fidelity **0.537** (median 0.603); mean gate reduction **9.1%** (max 40.0%)
- **Cancellation is the dominant pass** (Cohen's d = 1.66); other passes negligible in isolation
- Strongest fidelity predictors: **input gate count** (r = −0.78) and **pulse duration** (r = −0.73)
- **Two-qubit** gate count, not total gate count, is the hardware-relevant compiler metric (QCO 17.7% 2Q reduction vs Qiskit-L2/L3 9.3%)
- **281 passing tests** (3 are `qiskit-dynamics` cross-validation); `ruff` and `mypy --strict` clean
- Hardware validation fits the IQM free tier (~0.9 of 30 credits/month)

## Installation

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Copy environment configuration
cp .env.example .env
# Edit .env with paths to your binaries
```

## Project Structure

```
qco-integration/
├── src/                  # Source code
│   ├── bridge.py         # CircuitOptimizerBridge (C++ subprocess)
│   ├── pipeline.py       # EndToEndPipeline (orchestration)
│   ├── pulse.py          # Per-gate Lindblad fidelity model
│   ├── noise_spectrum.py # Non-Markovian 1/f filter-function dephasing
│   ├── hardware.py       # IQMHardwareExecutor (IQM Resonance)
│   ├── corpus.py         # CircuitCorpus (benchmarks)
│   ├── metrics.py        # Dataclasses for metrics
│   ├── runner.py         # BenchmarkRunner
│   ├── analysis.py       # Statistical analysis
│   ├── qasm.py           # QASM utilities
│   └── visualization.py  # Plotting utilities
├── experiments/          # Experiment + figure/table scripts
│   ├── run_campaign.py        # Full experimental campaign
│   ├── run_ablation.py        # Ablation study
│   ├── statistical_analysis.py # LaTeX tables + summary
│   ├── hardware_dryrun.py     # Credit estimation (no credentials needed)
│   └── hardware_validate.py   # Hardware execution
├── results/              # Output data (gitignored)
├── docs/                 # bakeoff_evidence.md (thesis decision record)
├── paper/acm_tqc/        # LaTeX manuscript (main.tex) + figures
├── tests/                # pytest suite (281 tests; run `pytest`)
└── README.md
```

## Dependencies

### External projects (not pip-installed)

- **quantum-circuit-optimizer**: C++ circuit optimizer binary
  - Location: set `QCO_OPTIMIZER_BINARY` (defaults to the sibling
    `quantum-circuit-optimizer/build/` checkout)
  - Required for: circuit optimization and routing

The pulse-level fidelity model is implemented natively in `src/pulse.py`
(per-gate Lindblad). `qiskit` / `qiskit-dynamics` are dev dependencies used by
the hardware executor and the cross-validation tests; install with
`pip install -e '.[dev]'`.

## Quick Start: Hardware Validation

Test the full pipeline on real quantum hardware (IQM Resonance - FREE):

```bash
# 1. Estimate credits needed (no credentials required!)
python experiments/hardware_dryrun.py --num-circuits 10

# Output:
# Estimated total cost:  0.9 credits
# Within free tier:      YES

# 2. Sign up for free tier: https://resonance.meetiqm.com/signup

# 3. Set credentials
export IQM_CLIENT_ID='your-client-id'
export IQM_CLIENT_SECRET='your-client-secret'

# 4. Run hardware validation on real Garnet (records job IDs)
python experiments/hardware_validate.py --quantum-computer garnet --num-circuits 8 --shots 10000
```

## Development

```bash
pytest                 # full suite (281 tests)
pytest -m crossval     # qiskit-dynamics cross-validation of the noise model
ruff check .           # lint
mypy src/              # strict type check
```

## License

MIT
