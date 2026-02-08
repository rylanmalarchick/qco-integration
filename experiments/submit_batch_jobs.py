#!/usr/bin/env python3
"""
Submit original + optimized circuits as batch jobs without waiting.
Save job IDs to file for later retrieval.
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

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@dataclass
class JobSubmission:
    """Track a submitted job"""
    job_id: str
    circuit_name: str
    circuit_type: str
    is_optimized: bool
    num_qubits: int
    shots: int
    submitted_at: str

def main():
    print("=" * 80)
    print("BATCH SUBMISSION: Original + Optimized Circuits to IQM Hardware")
    print("=" * 80)
    print()
    
    # Load corpus
    corpus = create_standard_corpus()
    circuits_list = [c for c in corpus if c.spec.num_qubits <= 12][:4]  # First 4
    
    print(f"Selected {len(circuits_list)} circuits:")
    for i, circuit in enumerate(circuits_list, start=1):
        print(f"  {i}. {circuit.spec.name} ({circuit.spec.num_qubits} qubits, {circuit.spec.circuit_type.value})")
    print()
    
    # Initialize hardware executor and optimizer
    executor = IQMHardwareExecutor(quantum_computer='garnet', dry_run=False)
    optimizer_binary = (
        Path.home()
        / "dev/research/quantum-circuit-optimizer/build/quantum_circuit_optimizer"
    )
    optimizer = CircuitOptimizerBridge(str(optimizer_binary))
    
    shots = 160
    submissions = []
    
    print("Submitting jobs (non-blocking)...")
    print()
    
    for circuit in circuits_list:
        name = circuit.spec.name
        circuit_type = circuit.spec.circuit_type.value
        
        # Submit ORIGINAL circuit
        print(f"[{name}] Submitting ORIGINAL...")
        try:
            from iqm.iqm_client import IQMClient
            token = os.environ.get('RESONANCE_API_TOKEN')
            client = IQMClient('https://resonance.meetiqm.com/garnet', token=token)
            
            qasm_circuit = executor._qasm_to_qiskit(circuit.qasm)
            if not qasm_circuit.data or qasm_circuit.data[-1][0].name != 'measure':
                qasm_circuit.measure_all()
                
            from qiskit import transpile
            from iqm.iqm_client.models import RunRequest
            backend_obj = client.get_backend()
            transpiled = transpile(qasm_circuit, backend=backend_obj)
            job = backend_obj.run(transpiled, shots=shots)
            job_id = job.job_id()
            
            submissions.append(JobSubmission(
                job_id=job_id,
                circuit_name=name,
                circuit_type=circuit_type,
                is_optimized=False,
                num_qubits=circuit.spec.num_qubits,
                shots=shots,
                submitted_at=datetime.now().isoformat()
            ))
            print(f"  ✓ Job {job_id[:20]}...")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            continue
        
        time.sleep(0.5)
        
        # Submit OPTIMIZED circuit
        print(f"[{name}] Submitting OPTIMIZED...")
        try:
            opt_result = optimizer.optimize(circuit.qasm, circuit.spec.name, ["cancel", "commute", "rotate"])
            
            from iqm.iqm_client import IQMClient
            token = os.environ.get('RESONANCE_API_TOKEN')
            client = IQMClient('https://resonance.meetiqm.com/garnet', token=token)
            
            qasm_circuit = executor._qasm_to_qiskit(opt_result.output_qasm)
            if not qasm_circuit.data or qasm_circuit.data[-1][0].name != 'measure':
                qasm_circuit.measure_all()
                
            from qiskit import transpile
            backend_obj = client.get_backend()
            transpiled = transpile(qasm_circuit, backend=backend_obj)
            job = backend_obj.run(transpiled, shots=shots)
            job_id = job.job_id()
            
            submissions.append(JobSubmission(
                job_id=job_id,
                circuit_name=name,
                circuit_type=circuit_type,
                is_optimized=True,
                num_qubits=circuit.spec.num_qubits,
                shots=shots,
                submitted_at=datetime.now().isoformat()
            ))
            print(f"  ✓ Job {job_id[:20]}...")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            continue
        
        time.sleep(0.5)
    
    print()
    print("=" * 80)
    print(f"Submitted {len(submissions)} jobs")
    print("=" * 80)
    print()
    
    # Save job IDs for later retrieval
    output_file = PROJECT_ROOT / "experiments" / "reports" / f"batch_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with output_file.open('w') as f:
        json.dump([asdict(s) for s in submissions], f, indent=2)
    
    print(f"Job IDs saved to: {output_file}")
    print()
    print("Next steps:")
    print("1. Wait for jobs to complete (check IQM queue)")
    print("2. Run: python experiments/retrieve_batch_results.py <json_file>")
    print()

if __name__ == "__main__":
    main()
