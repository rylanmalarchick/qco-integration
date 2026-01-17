# qco-integration

Integration layer connecting quantum-circuit-optimizer (C++17) with QubitPulseOpt (Python) for end-to-end quantum compilation fidelity analysis.

## Overview

This project provides an orchestration layer for analyzing fidelity degradation across the quantum compilation pipeline, from high-level circuit optimization through pulse-level control. The goal is to produce an arXiv preprint with systematic experimental analysis.

## Project Status

**Phase 1: Integration Layer Infrastructure** - Scaffolding complete, implementation pending

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
│   ├── corpus.py         # CircuitCorpus (benchmarks)
│   ├── metrics.py        # Dataclasses for metrics
│   ├── runner.py         # BenchmarkRunner
│   └── visualization.py  # Plotting utilities
├── experiments/          # Experiment configurations
├── results/              # Output data (gitignored)
├── paper/                # LaTeX preprint
└── tests/                # Test suite
```

## Dependencies

### External Projects (not pip-installed)

- **quantum-circuit-optimizer**: C++ circuit optimizer binary
  - Location: See `QCO_OPTIMIZER_BINARY` in `.env`
  - Required for: Circuit optimization, routing

- **QubitPulseOpt**: Python pulse optimization library
  - Location: See `QUBIT_PULSE_OPT_PATH` in `.env`
  - Required for: Pulse compilation, noise simulation

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
