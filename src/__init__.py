"""QCO-Integration: End-to-end quantum compilation fidelity analysis.

This package connects the quantum-circuit-optimizer (C++17) binary to a per-gate
Lindblad fidelity model, analyzing fidelity from circuit optimization through
pulse-level decoherence.

Main components:
- bridge: CircuitOptimizerBridge for calling the C++ optimizer via subprocess
- pipeline: EndToEndPipeline for orchestrating the full compilation flow
- pulse: per-gate Lindblad fidelity model (relaxation, dephasing, depolarizing, idle)
- noise_spectrum: non-Markovian 1/f filter-function dephasing
- corpus: CircuitCorpus for benchmark circuit generation
- metrics: dataclasses for stage-by-stage metrics collection
- runner: BenchmarkRunner for automated experiment execution
- hardware: IQMHardwareExecutor for IQM Resonance execution
- visualization: plotting utilities for publication-ready figures

Example:
    >>> from src import CircuitOptimizerBridge, EndToEndPipeline
    >>> bridge = CircuitOptimizerBridge("/path/to/optimizer")
    >>> # ... setup pipeline and run experiments
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "Rylan Malarchick"
__email__ = "rylan1012@gmail.com"

# Public API will be populated as modules are implemented
__all__: list[str] = [
    "__version__",
    "__author__",
    "__email__",
]
