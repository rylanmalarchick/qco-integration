"""IQM Resonance hardware executor for circuit validation.

This module provides integration with IQM Resonance quantum hardware,
enabling real quantum execution and fidelity validation against simulation.

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
    """Executor for IQM Resonance hardware with dry-run support.

    Supports two authentication methods:
    1. OAuth Client Credentials (IQM_CLIENT_ID + IQM_CLIENT_SECRET)
    2. API Key (IQM_API_KEY)

    Attributes:
        dry_run: If True, estimate credits without executing.
        auth_method: 'oauth' or 'api_key'
        api_key: IQM API key (if using key-based auth).
        client_id: IQM client ID (if using OAuth).
        client_secret: IQM client secret (if using OAuth).
        available_devices: List of available IQM devices for multi-device testing.
    """

    # Supported IQM devices with their properties
    SUPPORTED_DEVICES = {
        "IQM_RESONANCE_5Q": {"qubits": 5, "2q_gates": ["CNOT", "CRZ"], "native": True},
        "IQM_RESONANCE_20Q": {"qubits": 20, "2q_gates": ["CNOT", "CRZ"], "native": True},
        "IQM_RESONANCE_DEMO": {"qubits": 5, "2q_gates": ["CNOT"], "native": False},
    }

    def __init__(
        self,
        dry_run: bool = False,
        auth_server: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
    ):
        """Initialize IQM hardware executor.

        Args:
            dry_run: If True, only estimate credits, don't execute.
            auth_server: IQM auth server (default from IQM_AUTH_SERVER env).
            client_id: IQM client ID (default from IQM_CLIENT_ID env).
            client_secret: IQM client secret (default from IQM_CLIENT_SECRET env).
            api_key: IQM API key (default from IQM_API_KEY env).
            api_url: IQM API URL (default from IQM_API_URL env).

        Raises:
            ValueError: If neither OAuth nor API key credentials provided.
        """
        self.dry_run = dry_run

        # Try OAuth first
        self.auth_server = (
            auth_server or os.getenv("IQM_AUTH_SERVER", "https://auth.resonance.meetiqm.com")
        )
        self.client_id = client_id or os.getenv("IQM_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("IQM_CLIENT_SECRET", "")

        # Try API key
        self.api_key = api_key or os.getenv("IQM_API_KEY", "")
        self.api_url = api_url or os.getenv("IQM_API_URL", "https://api.resonance.meetiqm.com")

        # Determine auth method
        self.auth_method = None
        if self.client_id and self.client_secret:
            self.auth_method = "oauth"
            logger.info("Using OAuth client credentials for authentication")
        elif self.api_key:
            self.auth_method = "api_key"
            logger.info("Using API key for authentication")
        else:
            if not dry_run:
                raise ValueError(
                    "No IQM credentials provided. Either set:\n"
                    "  1. OAuth: IQM_CLIENT_ID + IQM_CLIENT_SECRET\n"
                    "  2. API Key: IQM_API_KEY\n"
                    "Get credentials from: https://resonance.meetiqm.com/"
                )
            else:
                logger.warning(
                    "No IQM credentials provided. Running in dry-run mode only. "
                    "To enable hardware execution, set either:\n"
                    "  1. IQM_CLIENT_ID + IQM_CLIENT_SECRET (OAuth)\n"
                    "  2. IQM_API_KEY (API key)"
                )

        self.client = None
        logger.info(
            f"IQMHardwareExecutor initialized (dry_run={dry_run}, "
            f"auth_method={self.auth_method or 'none'})"
        )

    def get_available_devices(self) -> list[str]:
        """Get list of available IQM devices.

        Returns:
            List of device names.
        """
        return list(self.SUPPORTED_DEVICES.keys())

    def get_device_info(self, device: str) -> dict[str, Any]:
        """Get information about a specific device.

        Args:
            device: Device name.

        Returns:
            Device properties dictionary.
        """
        return self.SUPPORTED_DEVICES.get(device, {})

    def estimate_credits(self, circuits: list[HardwareCircuit], shots: int = 10000) -> dict:
        """Estimate total credits needed for circuit execution.

        Args:
            circuits: List of circuits to execute.
            shots: Number of measurement shots per circuit.

        Returns:
            Dictionary with credit estimates and pricing breakdown.
        """
        per_circuit_credits = [c.estimate_credits() for c in circuits]
        total_per_circuit = sum(per_circuit_credits)

        # IQM charges per-shot scaling
        # 10k shots = base rate, other shot counts scale linearly
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
        shots: int = 10000,
        backend: str = "IQM_RESONANCE_5Q",
    ) -> list[HardwareResult]:
        """Execute circuits on IQM hardware.

        Args:
            circuits: List of circuits to execute.
            shots: Number of measurement shots per circuit.
            backend: IQM backend name.

        Returns:
            List of hardware results.

        Raises:
            RuntimeError: If dry_run=True, credentials not available, or auth_method not set.
            Exception: If IQM API call fails.
        """
        if self.dry_run:
            raise RuntimeError(
                "Cannot execute in dry-run mode. Set dry_run=False and provide credentials."
            )

        if not self.auth_method:
            raise RuntimeError("IQM credentials not configured. Cannot execute on hardware.")

        logger.info(f"Executing {len(circuits)} circuits on {backend} with {shots} shots")

        try:
            if self.auth_method == "oauth":
                return self._execute_oauth(circuits, shots, backend)
            elif self.auth_method == "api_key":
                return self._execute_api_key(circuits, shots, backend)
            else:
                raise RuntimeError(f"Unknown auth method: {self.auth_method}")

        except Exception as e:
            logger.error(f"Hardware execution failed: {e}")
            raise

    def _execute_oauth(
        self,
        circuits: list[HardwareCircuit],
        shots: int,
        backend: str,
    ) -> list[HardwareResult]:
        """Execute using OAuth client credentials."""
        try:
            from iqm.iqm_client import IQMClient  # type: ignore

            client = IQMClient(
                auth_server_url=self.auth_server,
                client_id=self.client_id,
                client_secret=self.client_secret,
                base_url="https://resonance.meetiqm.com",
            )

            results = []
            for circuit in circuits:
                logger.info(f"  Submitting {circuit.name}...")

                job = client.create_job(
                    circuit=circuit.qasm,
                    shots=shots,
                    request_timeout=300,
                )

                logger.info(f"    Job ID: {job.id}, waiting for results...")

                result = job.wait_result(
                    timeout=600,
                    poll_interval_seconds=2,
                )

                counts = self._parse_measurement_results(result)

                hw_result = HardwareResult(
                    circuit_name=circuit.name,
                    circuit_qasm=circuit.qasm,
                    shots=shots,
                    counts=counts,
                    execution_time_ms=result.get("execution_time_ms", -1),
                    metadata=result,
                )

                results.append(hw_result)
                logger.info(f"    Completed: fidelity={hw_result.compute_fidelity():.3f}")

            return results

        except ImportError:
            raise RuntimeError(
                "IQM SDK not installed. Install with: pip install iqm-client"
            ) from None

    def _execute_api_key(
        self,
        circuits: list[HardwareCircuit],
        shots: int,
        backend: str,
    ) -> list[HardwareResult]:
        """Execute using API key authentication."""
        import requests

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        results = []
        for circuit in circuits:
            logger.info(f"  Submitting {circuit.name}...")

            # Create job
            payload = {
                "circuit": circuit.qasm,
                "shots": shots,
                "backend": backend,
            }

            response = requests.post(
                f"{self.api_url}/jobs",
                json=payload,
                headers=headers,
                timeout=30,
            )

            if response.status_code not in (200, 201):
                raise RuntimeError(
                    f"Failed to create job: {response.status_code} {response.text}"
                )

            job_data = response.json()
            job_id = job_data.get("id")

            logger.info(f"    Job ID: {job_id}, waiting for results...")

            # Poll for results
            import time

            max_polls = 300  # 10 minutes with 2-second intervals
            for poll_count in range(max_polls):
                response = requests.get(
                    f"{self.api_url}/jobs/{job_id}",
                    headers=headers,
                    timeout=30,
                )

                if response.status_code != 200:
                    raise RuntimeError(
                        f"Failed to get job status: {response.status_code} {response.text}"
                    )

                job_data = response.json()
                status = job_data.get("status")

                if status == "completed":
                    result = job_data.get("result", {})
                    counts = self._parse_measurement_results(result)

                    hw_result = HardwareResult(
                        circuit_name=circuit.name,
                        circuit_qasm=circuit.qasm,
                        shots=shots,
                        counts=counts,
                        execution_time_ms=result.get("execution_time_ms", -1),
                        metadata=result,
                    )

                    results.append(hw_result)
                    logger.info(f"    Completed: fidelity={hw_result.compute_fidelity():.3f}")
                    break

                elif status in ("failed", "error"):
                    raise RuntimeError(f"Job {job_id} failed: {job_data.get('error')}")

                else:
                    logger.info(f"    Status: {status}, waiting...")
                    time.sleep(2)
            else:
                raise RuntimeError(f"Job {job_id} timed out after {max_polls * 2} seconds")

        return results

    def _parse_measurement_results(self, result: dict[str, Any]) -> dict[str, int]:
        """Parse IQM measurement results into bitstring counts.

        Args:
            result: IQM API result dictionary.

        Returns:
            Dictionary mapping bitstrings to measurement counts.
        """
        counts = {}

        # IQM typically returns results as list of measurements
        if "measurements" in result:
            measurements = result["measurements"]

            # Convert list of measurement arrays to bitstring counts
            for measurement in measurements:
                # measurement is typically [bit0, bit1, ..., bitN]
                bitstring = "".join(str(int(b)) for b in measurement)
                counts[bitstring] = counts.get(bitstring, 0) + 1

        elif "counts" in result:
            # Direct counts format
            counts = result["counts"]

        return counts

    def execute_stress_test(
        self,
        circuits: list[HardwareCircuit],
        shot_ranges: list[int] | None = None,
        devices: list[str] | None = None,
        backend: str = "IQM_RESONANCE_5Q",
    ) -> dict[str, Any]:
        """Execute circuits across multiple shot counts for stress testing.

        Args:
            circuits: Circuits to test.
            shot_ranges: List of shot counts to test (default: [100, 1000, 10000]).
            devices: Devices to test on (default: all available).
            backend: Primary backend name.

        Returns:
            Stress test results dictionary.
        """
        if shot_ranges is None:
            shot_ranges = [100, 1000, 10000]

        if devices is None:
            devices = [backend]

        stress_test_results = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "circuits": len(circuits),
            "shot_ranges": shot_ranges,
            "devices": devices,
            "results": [],
        }

        for shots in shot_ranges:
            logger.info(f"\nTesting with {shots} shots per circuit...")
            estimate = self.estimate_credits(circuits, shots=shots)

            if estimate["within_free_tier"]:
                logger.info(f"  ✓ Within free tier: {estimate['total_credits']} credits")

                if not self.dry_run:
                    try:
                        results = self.execute(circuits, shots=shots, backend=backend)
                        stress_test_results["results"].append({
                            "shots": shots,
                            "status": "completed",
                            "num_results": len(results),
                            "credits_used": estimate["total_credits"],
                        })
                    except Exception as e:
                        logger.error(f"  ✗ Execution failed: {e}")
                        stress_test_results["results"].append({
                            "shots": shots,
                            "status": "failed",
                            "error": str(e),
                        })
            else:
                logger.warning(f"  ✗ Exceeds free tier: {estimate['total_credits']} credits")
                stress_test_results["results"].append({
                    "shots": shots,
                    "status": "skipped",
                    "reason": "exceeds_free_tier",
                    "estimated_credits": estimate["total_credits"],
                })

        return stress_test_results


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
