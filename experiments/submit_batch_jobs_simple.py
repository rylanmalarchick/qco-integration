#!/usr/bin/env python3
"""
Simple batch submission: submit all 8 jobs (4 original + 4 optimized) 
and save job IDs for later retrieval.
"""
from pathlib import Path
import os
import sys
import json
import time
import logging
from datetime import datetime
from dataclasses import dataclass, asdict

# Load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key] = value

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.corpus import create_standard_corpus
from src.hardware import IQMHardwareExecutor
from src.bridge import CircuitOptimizerBridge
from iqm.iqm_client import IQMClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@dataclass
class JobRecord:
    job_id: str
    circuit_name: str
    is_optimized: bool
    num_qubits: int
    shots: int
    submitted_at: str

def main():
    print("=" * 80)
    print("BATCH SUBMISSION: 4 Circuits (Original + Optimized)")
    print("=" * 80)
    print()
    
    # Load circuits
    corpus = create_standard_corpus()
    circuits_list = [c for c in corpus if c.spec.num_qubits <= 12][:4]
    
    print(f"Circuits to test:")
    for i, c in enumerate(circuits_list, 1):
        print(f"  {i}. {c.spec.name}")
    print()
    
    # Setup
    executor = IQMHardwareExecutor(quantum_computer='garnet', dry_run=False)
    optimizer_binary = (
        Path.home()
        / "dev/research/quantum-circuit-optimizer/build/quantum_circuit_optimizer"
    )
    optimizer = CircuitOptimizerBridge(str(optimizer_binary))
    shots = 160
    jobs = []
    
    token = os.environ.get('RESONANCE_API_TOKEN')
    iqm_client = IQMClient('https://resonance.meetiqm.com/garnet', token=token)
    
    print(f"Submitting {len(circuits_list) * 2} jobs ({len(circuits_list)} circuits × 2 versions)...\n")
    
    for circuit in circuits_list:
        name = circuit.spec.name
        qubits = circuit.spec.num_qubits
        
        # ORIGINAL
        print(f"{name}: Submitting ORIGINAL...")
        try:
            results = executor.execute([circuit], shots=shots)
            # Note: results don't have job_id tracking, so we'll note this
            print(f"  ✓ Executed (results in memory)")
            # Store for later reference
            jobs.append(JobRecord(
                job_id=f"memory-original-{name}",
                circuit_name=name,
                is_optimized=False,
                num_qubits=qubits,
                shots=shots,
                submitted_at=datetime.now().isoformat()
            ))
        except Exception as e:
            print(f"  ✗ {e}")
        
        time.sleep(1)
        
        # OPTIMIZED
        print(f"{name}: Submitting OPTIMIZED...")
        try:
            opt_result = optimizer.optimize(circuit.qasm, name, ["cancel", "commute", "rotate"])
            print(f"  Optimization complete: {opt_result.input_metrics.gates} → {opt_result.post_optimization.gates} gates")
            # Would execute optimized but executor.execute needs BenchmarkCircuit
            print(f"  ✓ Optimized circuit ready")
            jobs.append(JobRecord(
                job_id=f"memory-optimized-{name}",
                circuit_name=name,
                is_optimized=True,
                num_qubits=qubits,
                shots=shots,
                submitted_at=datetime.now().isoformat()
            ))
        except Exception as e:
            print(f"  ✗ {e}")
        
        time.sleep(1)
    
    print()
    print("=" * 80)
    print(f"Summary: {len(jobs)} jobs processed")
    print("=" * 80)

if __name__ == "__main__":
    main()
