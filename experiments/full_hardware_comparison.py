#!/usr/bin/env python3
"""
Full Hardware Comparison: Execute all 4 circuits in both original and optimized forms.
Submits 8 jobs total without synchronous waiting - saves job IDs for async retrieval.

This is the complete validation experiment.
"""
from pathlib import Path
import os
import sys
import json
import time
import logging
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import Optional


# Load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key] = value

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.corpus import create_standard_corpus
from src.hardware import IQMHardwareExecutor
from src.bridge import CircuitOptimizerBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@dataclass
class SubmittedJob:
    """Track a submitted job for later retrieval"""
    job_index: int
    circuit_name: str
    version: str  # "original" or "optimized"
    num_qubits: int
    circuit_type: str
    has_optimization_data: bool = False
    optimization_metrics: Optional[dict] = None
    submitted_at: Optional[str] = None
    execution_time_ms: Optional[float] = None
    fidelity: Optional[float] = None
    result_counts: Optional[dict] = None

def main():
    print("=" * 80)
    print("FULL HARDWARE COMPARISON: Original vs Optimized Circuits")
    print("=" * 80)
    print()
    
    # Load circuits
    corpus = create_standard_corpus()
    circuits_list = [c for c in corpus if c.spec.num_qubits <= 12][:4]
    
    print(f"Testing {len(circuits_list)} circuits in both forms (8 total executions):\n")
    for i, c in enumerate(circuits_list, 1):
        print(f"  {i}. {c.spec.name:12} - {c.spec.num_qubits}Q {c.spec.circuit_type.value}")
    print()
    
    # Setup
    executor = IQMHardwareExecutor(quantum_computer='garnet', dry_run=False)
    optimizer_binary = (
        Path.home()
        / "dev/research/quantum-circuit-optimizer/build/quantum_circuit_optimizer"
    )
    optimizer = CircuitOptimizerBridge(str(optimizer_binary))
    passes = ["cancel", "commute", "rotate"]
    shots = 160
    
    submitted_jobs = []
    job_index = 1
    
    print("EXECUTION PLAN")
    print("=" * 80)
    print(f"Shots per circuit: {shots}")
    print(f"Passes: {', '.join(passes)}")
    print(f"Expected credits: ~{len(circuits_list) * 2 * shots / 1000:.1f}")
    print()
    
    print("SUBMITTING JOBS")
    print("=" * 80)
    print()
    
    for circuit in circuits_list:
        name = circuit.spec.name
        qubits = circuit.spec.num_qubits
        circuit_type = circuit.spec.circuit_type.value
        
        # ========== ORIGINAL CIRCUIT ==========
        print(f"Job {job_index}: {name} [ORIGINAL]")
        try:
            # Convert BenchmarkCircuit to HardwareCircuit for execution
            from src.hardware import HardwareCircuit
            
            hw_circuit = HardwareCircuit(
                name=circuit.spec.name,
                qasm=circuit.qasm,
                gates=circuit.metadata.get('gates', 0),
                depth=circuit.metadata.get('depth', 0),
                two_qubit_gates=circuit.metadata.get('two_qubit_gates', 0),
            )
            
            start = time.time()
            results = executor.execute([hw_circuit], shots=shots)
            elapsed_ms = (time.time() - start) * 1000
            
            result = results[0]
            fidelity = result.compute_fidelity()
            
            print(f"  ✓ Executed in {elapsed_ms:.0f}ms")
            print(f"  Fidelity: {fidelity:.4f}")
            
            submitted_jobs.append(SubmittedJob(
                job_index=job_index,
                circuit_name=name,
                version="original",
                num_qubits=qubits,
                circuit_type=circuit_type,
                has_optimization_data=False,
                submitted_at=datetime.now().isoformat(),
                execution_time_ms=elapsed_ms,
                fidelity=fidelity,
            ))
            job_index += 1
            
        except Exception as e:
            logger.error(f"  Error: {e}")
            print(f"  ✗ Failed: {e}\n")
        
        time.sleep(0.5)
        
        # ========== OPTIMIZED CIRCUIT ==========
        print(f"Job {job_index}: {name} [OPTIMIZED]")
        try:
            # Step 1: Optimize
            orig_qasm = circuit.qasm
            logger.info(f"  Optimizing with passes: {passes}")
            opt_result = optimizer.optimize(orig_qasm, passes)
            
            orig_metrics = opt_result.input_metrics
            opt_metrics = opt_result.post_optimization
            
            gate_reduction = 100 * (1 - opt_metrics.gates / orig_metrics.gates)
            depth_reduction = 100 * (1 - opt_metrics.depth / orig_metrics.depth)
            
            print(f"  Optimization: {orig_metrics.gates} → {opt_metrics.gates} gates ({gate_reduction:+.1f}%)")
            print(f"               Depth {orig_metrics.depth} → {opt_metrics.depth} ({depth_reduction:+.1f}%)")
            
            # Step 2: Execute optimized circuit on hardware
            # Create HardwareCircuit object from optimized QASM
            from src.hardware import HardwareCircuit
            
            opt_circuit = HardwareCircuit(
                name=f"{name}_optimized",
                qasm=opt_result.output_qasm,
                gates=opt_metrics.gates,
                depth=opt_metrics.depth,
                two_qubit_gates=opt_metrics.two_qubit_gates,
            )
            
            # Execute on hardware
            start_exec = time.time()
            opt_hw_results = executor.execute([opt_circuit], shots=shots)
            elapsed_ms = (time.time() - start_exec) * 1000
            
            opt_result_obj = opt_hw_results[0]
            fidelity = opt_result_obj.compute_fidelity()
            
            print(f"  ✓ Executed in {elapsed_ms:.0f}ms")
            print(f"  Fidelity: {fidelity:.4f}")
            
            submitted_jobs.append(SubmittedJob(
                job_index=job_index,
                circuit_name=name,
                version="optimized",
                num_qubits=qubits,
                circuit_type=circuit_type,
                has_optimization_data=True,
                optimization_metrics={
                    "original_gates": orig_metrics.gates,
                    "optimized_gates": opt_metrics.gates,
                    "gate_reduction": float(gate_reduction),
                    "original_depth": orig_metrics.depth,
                    "optimized_depth": opt_metrics.depth,
                    "depth_reduction": float(depth_reduction),
                    "original_2q_gates": orig_metrics.two_qubit_gates,
                    "optimized_2q_gates": opt_metrics.two_qubit_gates,
                },
                submitted_at=datetime.now().isoformat(),
                execution_time_ms=elapsed_ms,
                fidelity=fidelity,
            ))
            job_index += 1
            
        except Exception as e:
            logger.error(f"  Error: {e}")
            print(f"  ✗ Failed: {e}\n")
        
        time.sleep(0.5)
        print()
    
    # Save results
    print("=" * 80)
    print(f"RESULTS: Executed {len(submitted_jobs)} of 8 jobs")
    print("=" * 80)
    print()
    
    output_file = PROJECT_ROOT / "experiments" / "reports" / f"full_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Prepare report
    report = {
        "title": "Full Hardware Comparison: Original vs Optimized Circuits",
        "timestamp": datetime.now().isoformat(),
        "device": "IQM Resonance Garnet (20Q)",
        "configuration": {
            "circuits_tested": len(circuits_list),
            "jobs_executed": len(submitted_jobs),
            "shots_per_circuit": shots,
            "optimization_passes": passes,
        },
        "jobs": [asdict(job) for job in submitted_jobs],
        "summary": {}
    }
    
    # Compute summary
    if submitted_jobs:
        originals = [j for j in submitted_jobs if j.version == "original"]
        optimizeds = [j for j in submitted_jobs if j.version == "optimized"]
        
        if originals and optimizeds:
            avg_fidelity_original = sum(j.fidelity for j in originals) / len(originals) if originals else 0
            avg_fidelity_optimized = sum(j.fidelity for j in optimizeds) / len(optimizeds) if optimizeds else 0
            
            report["summary"] = {
                "original_circuits": len(originals),
                "optimized_circuits": len(optimizeds),
                "avg_fidelity_original": float(avg_fidelity_original),
                "avg_fidelity_optimized": float(avg_fidelity_optimized),
                "fidelity_improvement": float(avg_fidelity_optimized - avg_fidelity_original),
            }
    
    with output_file.open('w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Results saved to: {output_file}\n")
    
    # Print summary table
    print("SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Circuit':<12} {'Type':<8} {'Version':<10} {'Fidelity':<10}")
    print("-" * 80)
    for job in submitted_jobs:
        print(f"{job.circuit_name:<12} {job.circuit_type:<8} {job.version:<10} {job.fidelity:.4f}")
    print()

if __name__ == "__main__":
    main()
