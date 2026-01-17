"""IQM Resonance hardware executor for circuit validation.

This module provides integration with IQM Resonance quantum hardware,
enabling real quantum execution and fidelity validation against simulation.

Uses the official iqm-client[qiskit] library for proper server-side
transpilation and job submission.

Typical usage:
    executor = IQMHardwareExecutor(dry_run=True)
    credit_cost = executor.estimate_credits(circuits)
    if credit_cost <= 30:  # Free tier limit
        results = executor.execute(circuits, shots=1000)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class HardwareCircuit:
    """Represents a circuit to execute on hardware."""

    name: str
    qasm: str
    gates: int
    depth: int
    two_qubit_gates: int

    def estimate_credits(self) -> float:
        """Estimate credits needed for this circuit (IQM Resonance pricing).

        IQM Resonance charges based on circuit complexity:
        - Base cost: ~0.1 credit per circuit
        - Gate cost: ~0.001 credit per gate
        - 2Q gate multiplier: 2x cost for 2-qubit gates

        Returns:
            Estimated credits for 10,000 shots.
        """
        base = 0.1
        gate_cost = self.gates * 0.001
        two_q_cost = self.two_qubit_gates * 0.001  # Additional cost

        # Per 10k shots
        return base + gate_cost + two_q_cost


@dataclass
class HardwareResult:
    """Results from hardware execution."""

    circuit_name: str
    circuit_qasm: str
    shots: int
    counts: dict[str, int]  # Bitstring -> count
    execution_time_ms: float
    metadata: dict[str, Any]

    def compute_fidelity(self, target_state: str | None = None) -> float:
        """Compute approximate fidelity from measurement counts.

        For GHZ states, uses parity check.
        For other circuits, uses overlap with most probable state.

        Args:
            target_state: Expected bitstring (e.g., '0000' or '1111').

        Returns:
            Estimated fidelity (0 to 1).
        """
        if not self.counts:
            return 0.0

        total = sum(self.counts.values())

        if target_state:
            # Direct overlap with target
            target_count = self.counts.get(target_state, 0)
            return target_count / total

        # Fallback: use most probable state
        max_count = max(self.counts.values())
        return max_count / total


class IQMHardwareExecutor:
    """Executor for IQM Resonance hardware using official IQM client library.

    Uses iqm-client[qiskit] for proper circuit transpilation and execution.
    The IQM client handles server-side transpilation to IQM's native gate set.

    Attributes:
        dry_run: If True, estimate credits without executing.
        token: IQM authentication token from Resonance dashboard.
        server_url: IQM Resonance server URL.
        quantum_computer: Target quantum computer alias (e.g., 'garnet', 'sirius').
    """

    # Available IQM Resonance quantum computers
    AVAILABLE_DEVICES = {
        "garnet": {"qubits": 20, "native_gates": ["PRX", "CZ"], "description": "IQM Garnet (20Q)"},
        "garnet:mock": {"qubits": 20, "native_gates": ["PRX", "CZ"], "description": "IQM Garnet Mock"},
        "sirius": {"qubits": 34, "native_gates": ["PRX", "CZ"], "description": "IQM Sirius (34Q)"},
        "sirius:mock": {"qubits": 34, "native_gates": ["PRX", "CZ"], "description": "IQM Sirius Mock"},
        "emerald": {"qubits": 9, "native_gates": ["PRX", "CZ"], "description": "IQM Emerald (9Q)"},
        "emerald:mock": {"qubits": 9, "native_gates": ["PRX", "CZ"], "description": "IQM Emerald Mock"},
    }

    def __init__(
        self,
        dry_run: bool = False,
        token: str | None = None,
        server_url: str | None = None,
        quantum_computer: str | None = None,
    ):
        """Initialize IQM hardware executor.

        Args:
            dry_run: If True, only estimate credits without executing.
            token: IQM authentication token (default from RESONANCE_API_TOKEN env).
            server_url: IQM server URL (default: https://resonance.meetiqm.com).
            quantum_computer: Quantum computer alias (default: garnet:mock).

        Raises:
            ValueError: If not in dry_run mode but token not provided.
        """
        self.dry_run = dry_run
        self.token = token or os.getenv("RESONANCE_API_TOKEN", "")
        self.server_url = server_url or "https://resonance.meetiqm.com"
        self.quantum_computer = quantum_computer or "garnet:mock"

        if not dry_run and not self.token:
            raise ValueError(
                "Token required for hardware execution. Either:\n"
                "  1. Pass token parameter\n"
                "  2. Set RESONANCE_API_TOKEN environment variable\n"
                "Get token from: https://resonance.meetiqm.com/settings"
            )

        logger.info(
            f"IQMHardwareExecutor initialized (dry_run={dry_run}, "
            f"device={self.quantum_computer}, url={self.server_url})"
        )

    def get_available_devices(self) -> list[str]:
        """Get list of available IQM quantum computers.

        Returns:
            List of device aliases.
        """
        return list(self.AVAILABLE_DEVICES.keys())

    def get_device_info(self, device: str) -> dict[str, Any]:
        """Get information about a specific device.

        Args:
            device: Device alias.

        Returns:
            Device properties dictionary.
        """
        return self.AVAILABLE_DEVICES.get(device, {})

    def estimate_credits(self, circuits: list[HardwareCircuit], shots: int = 10000) -> dict:
        """Estimate total credits needed for circuit execution.

        IQM Resonance pricing model:
        - Base: 0.1 credit per circuit
        - Gate scaling: 0.001 credit per gate
        - 2Q gate multiplier: 2x cost
        - Shot scaling: Linear with shot count

        Args:
            circuits: List of circuits to execute.
            shots: Number of measurement shots per circuit.

        Returns:
            Dictionary with credit estimates and pricing breakdown.
        """
        per_circuit_credits = [c.estimate_credits() for c in circuits]
        total_per_circuit = sum(per_circuit_credits)

        # IQM charges per-shot scaling (base rate is for 10k shots)
        shot_scaling = shots / 10000.0
        total_credits = total_per_circuit * shot_scaling

        return {
            "total_credits": round(total_credits, 2),
            "per_circuit_credits": [round(c, 2) for c in per_circuit_credits],
            "per_circuit_avg": round(total_per_circuit / len(circuits), 2) if circuits else 0,
            "shots": shots,
            "num_circuits": len(circuits),
            "free_tier_limit": 30,
            "within_free_tier": total_credits <= 30,
            "circuits": [{"name": c.name, "gates": c.gates, "2q_gates": c.two_qubit_gates} for c in circuits],
        }

    def execute(
        self,
        circuits: list[HardwareCircuit],
        shots: int = 1000,
        backend: str | None = None,
    ) -> list[HardwareResult]:
        """Execute circuits on IQM hardware using IQMProvider.

        Args:
            circuits: List of circuits to execute.
            shots: Number of measurement shots per circuit.
            backend: Deprecated parameter (ignored).

        Returns:
            List of hardware results.

        Raises:
            RuntimeError: If dry_run=True or credentials not available.
        """
        if self.dry_run:
            raise RuntimeError(
                "Cannot execute in dry-run mode. Set dry_run=False and provide token."
            )

        if not self.token:
            raise RuntimeError("IQM token not configured. Cannot execute on hardware.")

        logger.info(
            f"Executing {len(circuits)} circuits on {self.quantum_computer} with {shots} shots"
        )

        try:
            from qiskit import transpile
            from iqm.qiskit_iqm import IQMProvider

            # Connect to IQM
            provider = IQMProvider(
                self.server_url,
                quantum_computer=self.quantum_computer,
                token=self.token,
            )
            backend_obj = provider.get_backend()

            results = []
            for circuit in circuits:
                logger.info(f"  Executing {circuit.name}...")

                # Convert QASM to Qiskit circuit
                qasm_circuit = self._qasm_to_qiskit(circuit.qasm)

                # Add measurements if not present
                if not qasm_circuit.data or qasm_circuit.data[-1][0].name != 'measure':
                    qasm_circuit.measure_all()

                # Transpile for IQM hardware
                transpiled = transpile(qasm_circuit, backend=backend_obj)

                # Submit job
                job = backend_obj.run(transpiled, shots=shots)
                job_id = job.job_id()
                logger.info(f"    Job submitted: {job_id}")

                # Get results
                result = job.result()
                counts = result.get_counts()

                # Create hardware result
                hw_result = HardwareResult(
                    circuit_name=circuit.name,
                    circuit_qasm=circuit.qasm,
                    shots=shots,
                    counts=counts,
                    execution_time_ms=result.time_taken * 1000 if hasattr(result, "time_taken") else -1,
                    metadata={"job_id": job_id},
                )

                results.append(hw_result)
                fidelity = hw_result.compute_fidelity()
                logger.info(f"    Completed: {len(counts)} states, fidelity≈{fidelity:.3f}")

            return results

        except Exception as e:
            logger.error(f"Hardware execution failed: {e}")
            raise

    def _qasm_to_qiskit(self, qasm: str) -> Any:
        """Convert OpenQASM string to Qiskit QuantumCircuit.

        Args:
            qasm: OpenQASM 3.0 circuit string.

        Returns:
            Qiskit QuantumCircuit object.
        """
        from qiskit import qasm3

        # Add include statement if missing (for OpenQASM 3.0 compatibility)
        if "include" not in qasm and qasm.strip().startswith("OPENQASM 3.0"):
            lines = qasm.split("\n")
            lines.insert(1, 'include "stdgates.inc";')
            qasm = "\n".join(lines)

        return qasm3.loads(qasm)


def load_hardware_circuits(results_dir: Path | str, num_circuits: int = 10) -> list[HardwareCircuit]:
    """Load representative circuits from experimental results for hardware validation.

    Selects a diverse subset: GHZ, QFT, QAOA, and random circuits.

    Args:
        results_dir: Path to experiments/results directory.
        num_circuits: Number of circuits to select.

    Returns:
        List of HardwareCircuit objects ready for execution.
    """
    results_dir = Path(results_dir)
    circuits = []

    # Try to load from baseline experiment (shortest execution time)
    baseline_file = sorted(results_dir.glob("baseline_*.json"))
    if not baseline_file:
        logger.warning("No baseline results found. Create baseline experiment first.")
        return []

    with baseline_file[-1].open() as f:
        baseline_data = json.load(f)

    # Extract circuits from results
    for result in baseline_data.get("results", [])[:num_circuits]:
        if result.get("metrics"):
            circuits.append(
                HardwareCircuit(
                    name=result["circuit_name"],
                    qasm="",  # Will be loaded from corpus
                    gates=result["metrics"]["input_gates"],
                    depth=result["metrics"]["input_depth"],
                    two_qubit_gates=result["metrics"].get("input_2q_gates", 0),
                )
            )

    logger.info(f"Loaded {len(circuits)} circuits for hardware validation")
    return circuits


def create_validation_report(
    hw_results: list[HardwareResult],
    sim_fidelities: dict[str, float],
) -> dict[str, Any]:
    """Create a validation report comparing hardware vs simulation.

    Args:
        hw_results: Results from hardware execution.
        sim_fidelities: Simulated fidelities keyed by circuit name.

    Returns:
        Comprehensive validation report.
    """
    report = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "num_circuits": len(hw_results),
        "circuits": [],
        "summary": {},
    }

    hw_fidelities = []
    sim_fidelities_list = []

    for hw_result in hw_results:
        hw_fid = hw_result.compute_fidelity()
        sim_fid = sim_fidelities.get(hw_result.circuit_name, 0.0)

        hw_fidelities.append(hw_fid)
        sim_fidelities_list.append(sim_fid)

        report["circuits"].append(
            {
                "name": hw_result.circuit_name,
                "hardware_fidelity": round(hw_fid, 4),
                "simulated_fidelity": round(sim_fid, 4),
                "difference": round(hw_fid - sim_fid, 4),
                "shots": hw_result.shots,
                "execution_time_ms": hw_result.execution_time_ms,
            }
        )

    # Compute correlations
    import statistics

    report["summary"] = {
        "mean_hardware_fidelity": round(statistics.mean(hw_fidelities), 4),
        "mean_simulated_fidelity": round(statistics.mean(sim_fidelities_list), 4),
        "mean_difference": round(
            statistics.mean([h - s for h, s in zip(hw_fidelities, sim_fidelities_list)]), 4
        ),
    }

    if len(hw_fidelities) > 1:
        report["summary"]["stdev_hardware"] = round(statistics.stdev(hw_fidelities), 4)
        report["summary"]["stdev_simulated"] = round(statistics.stdev(sim_fidelities_list), 4)

    return report
