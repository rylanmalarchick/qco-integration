# qco-integration

Python integration layer connecting quantum-circuit-optimizer (C++17) with QubitPulseOpt (Python). End-to-end quantum compilation fidelity analysis. Preprint: arXiv:2601.20871 (an earlier version was submitted to ACM TQC and rejected).

## Structure

```
qco-integration/
├── src/qco_integration/  # Pipeline orchestration, analysis, visualization
├── experiments/          # Experiment configs and scripts
├── tests/                # 252 pytest tests
├── paper/acm_tqc/        # LaTeX manuscript (13 figures)
└── results/              # Cached experiment outputs
```

## Build & Test

```bash
pip install -e '.[dev]'
pytest
pytest -m "not slow"      # skip long-running integration tests
```

## Gotchas

- Requires `quantum-circuit-optimizer` binary on PATH (C++ build); see `setup_iqm.sh`
- Custom pytest markers: `slow`, `deterministic`, `integration`
- No CI/CD pipeline; tests run locally only
- IQM Garnet noise parameters hardcoded in `src/qco_integration/noise.py`
