# qco-integration

Integration layer connecting quantum-circuit-optimizer (C++17) with QubitPulseOpt (Python) for end-to-end quantum compilation fidelity analysis.

## Overview

This project provides an orchestration layer for analyzing fidelity degradation across the quantum compilation pipeline, from high-level circuit optimization through pulse-level control. The goal is to produce an arXiv preprint with systematic experimental analysis.

## Project Status

**Phase 5: Complete** - End-to-end framework operational with real components and hardware validation support

### Completed Phases

1. **Integration Architecture** - C++ optimizer + Python pulse simulation connected
2. **Real Component Integration** - Working with actual quantum-circuit-optimizer binary
3. **Experimental Campaign** - 371 circuits analyzed with real optimization + Lindblad simulation
4. **Publication-Ready Paper** - 5-page arXiv preprint with real experimental results
5. **Hardware Validation** - IQM Resonance integration with dry-run credit estimation

### Key Results

- **23.1% mean gate reduction** (max 96.2%)
- **CancellationPass most effective** (14,024 gates, 68% improved)
- **Pulse duration strongest fidelity predictor** (r=-0.74, R²=0.55)
- **251 passing tests**, clean linting
- **Free-tier hardware validation** fits in 30 credits/month

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
├── agent_docs/           # Project documentation for AI agents
│   ├── PROJECT_CONTEXT.md
│   ├── SCOPE_OF_WORK.md
│   ├── ARCHITECTURE.md
│   └── IQM_GARNET_SPEC.md
├── src/                  # Source code
│   ├── bridge.py         # CircuitOptimizerBridge (C++ subprocess)
│   ├── pipeline.py       # EndToEndPipeline (orchestration)
│   ├── pulse.py          # PulseSimulator (Lindblad-based)
│   ├── hardware.py       # IQMHardwareExecutor (validation)
│   ├── corpus.py         # CircuitCorpus (benchmarks)
│   ├── metrics.py        # Dataclasses for metrics
│   ├── runner.py         # BenchmarkRunner
│   ├── analysis.py       # Statistical analysis
│   ├── qasm.py           # QASM utilities
│   └── visualization.py  # Plotting utilities
├── experiments/          # Experiment scripts
│   ├── run_campaign.py   # Full experimental campaign
│   ├── hardware_dryrun.py # Credit estimation (no credentials needed!)
│   └── hardware_validate.py # Hardware execution
├── results/              # Output data (gitignored)
├── paper/                # LaTeX preprint (ready to submit)
├── tests/                # 251 passing tests
├── HARDWARE_VALIDATION.md # Hardware validation guide
└── README.md
```

## Dependencies

### External Projects (not pip-installed)

- **quantum-circuit-optimizer**: C++ circuit optimizer binary
  - Location: See `QCO_OPTIMIZER_BINARY` in `.env`
  - Required for: Circuit optimization, routing

- **QubitPulseOpt**: Python pulse optimization library
  - Location: See `QUBIT_PULSE_OPT_PATH` in `.env`
  - Required for: Pulse compilation, noise simulation

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

# 4. Run hardware validation
python experiments/hardware_validate.py --num-circuits 10 --shots 1000
```

See [HARDWARE_VALIDATION.md](HARDWARE_VALIDATION.md) for detailed guide.

## Development

```bash
# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check .

# Audit code against AgentBible principles
python -m agentbible.cli.main audit ./src
```

## AgentBible Principles

This project follows the [AgentBible](https://pypi.org/project/agentbible/) principles:

1. **Correctness First** - Physical accuracy is non-negotiable
2. **Specification Before Code** - Tests define the contract
3. **Fail Fast with Clarity** - Detect errors at boundaries
4. **Simplicity by Design** - Simple code is correct code
5. **Infrastructure Enables Speed** - Invest in tooling

## License

MIT
