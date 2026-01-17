# QCO-Integration Project Context

## Project Overview

**Name:** qco-integration  
**Purpose:** Integration layer connecting quantum-circuit-optimizer (C++17) with QubitPulseOpt (Python) for end-to-end quantum compilation fidelity analysis.  
**Output:** arXiv preprint analyzing fidelity from circuit optimization through pulse-level control.

## Related Projects

### quantum-circuit-optimizer (C++17)
- **Location:** `/home/rylan/Documents/career/code_bases/quantum/compilers/quantum-circuit-optimizer/`
- **Status:** v1.0.0 complete (all 5 sprints done)
- **Tests:** 340 tests passing
- **Features:**
  - OpenQASM 3.0 parser
  - DAG-based intermediate representation
  - 4 optimization passes: CancellationPass, CommutationPass, RotationMergePass, IdentityEliminationPass
  - SABRE routing algorithm
  - Topology support: linear, ring, grid, heavy-hex
- **CLI Status:** Current `main.cpp` is a demo, not a proper CLI tool. Needs enhancement for JSON output with per-pass statistics.

### QubitPulseOpt (Python)
- **Location:** `/home/rylan/Documents/career/code_bases/quantum/Controls/QubitPulseOpt/`
- **Status:** Complete with existing preprint
- **Tests:** 864 tests, 74% coverage
- **Features:**
  - GRAPE/Krotov pulse optimizers
  - Lindblad master equation simulation
  - `GateCompiler` class in `src/optimization/compilation.py` for gate-to-pulse compilation
  - IQM Garnet hardware parameters

### QuantumVQE
- **Location:** `/home/rylan/Documents/career/code_bases/quantum/HPC/QuantumVQE/`
- **Purpose:** Starting point for circuit corpus (H2 VQE circuits)
- **Note:** Simple 4-qubit circuits; need to generate more complex benchmarks

## Integration Approach

**Decision:** Pure Python integration layer (not pybind11)
- Cleaner separation of concerns
- Faster iteration during research
- Better reproducibility
- C++ optimizer called via subprocess with JSON I/O

## Research Methodology

**Approach:** Exploration-first
- Run experiments, let data reveal patterns
- Per-pass breakdown for compiler-focused analysis
- No hypothesis forcing

## Hardware Target

**Primary:** IQM Garnet (20-qubit superconducting QPU)
- Simulation only (no hardware validation - too expensive)
- May explore other noise regimes for sensitivity analysis
