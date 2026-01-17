"""QCO-Integration: End-to-end quantum compilation fidelity analysis.

This package provides an integration layer connecting quantum-circuit-optimizer
(C++17) with QubitPulseOpt (Python) for analyzing fidelity from circuit
optimization through pulse-level control.

Main components:
- bridge: CircuitOptimizerBridge for calling C++ optimizer via subprocess
- pipeline: EndToEndPipeline for orchestrating full compilation flow
- corpus: CircuitCorpus for benchmark circuit generation
- metrics: Dataclasses for stage-by-stage metrics collection
- runner: BenchmarkRunner for automated experiment execution
- visualization: Plotting utilities for publication-ready figures

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
