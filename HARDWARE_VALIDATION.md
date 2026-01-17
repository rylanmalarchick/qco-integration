# Hardware Validation Guide

This guide explains how to validate QCO-Integration results on real IQM Resonance quantum hardware.

## Overview

The framework supports end-to-end validation by comparing simulated fidelity predictions against real quantum hardware execution. This bridges the simulation-reality gap and provides empirical validation of the optimization strategies.

### What You Get

- **Dry-run credit estimation**: See exactly how many credits will be used before executing
- **Free-tier compatible**: Most experiments fit within the 30 credits/month free tier
- **Hardware execution**: Run optimized circuits on IQM Garnet 20-qubit processor
- **Comparison analysis**: Automated reports comparing simulation vs hardware fidelity

## Quick Start

### Step 1: Check Credit Requirements (FREE, NO CREDENTIALS NEEDED)

```bash
# Estimate credits for default 10 circuits × 10k shots
python experiments/hardware_dryrun.py

# More comprehensive: 20 circuits × 10k shots
python experiments/hardware_dryrun.py --num-circuits 20

# High-volume: 30 circuits × 100k shots (uses ~21 credits)
python experiments/hardware_dryrun.py --num-circuits 30 --shots 100000
```

**Example output:**
```
Total circuits:        10
Shots per circuit:     10,000
Free tier limit:       30 credits/month
Estimated total cost:  0.9 credits
Within free tier:      ✓ YES
```

### Step 2: Sign Up for Free Tier

Go to: https://resonance.meetiqm.com/signup

- Free tier: **30 credits/month**
- No payment method required
- IQM Garnet 20-qubit access
- Instant approval

### Step 3: Get Your Credentials

After signup, retrieve from account:
- **Client ID**
- **Client Secret**

### Step 4: Set Environment Variables

```bash
export IQM_CLIENT_ID='your-client-id'
export IQM_CLIENT_SECRET='your-client-secret'

# Verify it's set
echo $IQM_CLIENT_ID
```

Or add to `.env` file:
```
IQM_CLIENT_ID=your-client-id
IQM_CLIENT_SECRET=your-client-secret
```

### Step 5: Run Hardware Validation

```bash
# Dry-run first (no execution, just checks credentials)
python experiments/hardware_validate.py --dry-run

# Full execution
python experiments/hardware_validate.py --num-circuits 10 --shots 1000

# With custom backend
python experiments/hardware_validate.py --backend IQM_RESONANCE_5Q --shots 5000
```

## Credit Estimates

Based on IQM Resonance pricing model:

| Scenario | Circuits | Shots | Credits | Free Tier? |
|----------|----------|-------|---------|-----------|
| Quick test | 5 | 1,000 | 0.06 | ✓ |
| Standard validation | 10 | 10,000 | 0.9 | ✓ |
| Comprehensive | 20 | 10,000 | 2.0 | ✓ |
| High-volume | 30 | 100,000 | 21.3 | ✓ |
| Maximum free | 30 | 160,000 | 30.0 | ✓ (limit) |

### Credit Calculation

```
Cost per circuit = 0.1 + (gates × 0.001) + (2Q_gates × 0.001)
Total cost = sum(per-circuit costs) × (shots / 10000)
```

For circuits with ~10 gates and ~2 two-qubit gates:
- Base cost: 0.1 credits
- Per 10k shots: ~0.01 credits
- **Total: ~0.11 credits per circuit**

## Hardware Circuit Selection

By default, the validation script selects:

- **2-3 GHZ states** (shallow circuits, good for baseline)
- **2-3 QFT circuits** (medium complexity, many phase gates)
- **2-3 QAOA circuits** (structured optimization, varied sizes)
- **3-5 random circuits** (diverse depths and qubit counts)

All selected circuits fit within IQM Garnet 20-qubit topology.

## Output Files

Results are saved to:

```
experiments/reports/hardware_validation_YYYYMMDD_HHMMSS.json
```

Contains:
- Hardware fidelity measurements
- Simulated fidelity predictions
- Comparison statistics
- Per-circuit breakdown
- Execution metadata

## Example Results

```json
{
  "timestamp": "2026-01-16T19:20:00",
  "num_circuits": 10,
  "circuits": [
    {
      "name": "ghz_4q",
      "hardware_fidelity": 0.9247,
      "simulated_fidelity": 0.9174,
      "difference": 0.0073,
      "shots": 10000,
      "execution_time_ms": 2345
    },
    ...
  ],
  "summary": {
    "mean_hardware_fidelity": 0.8901,
    "mean_simulated_fidelity": 0.8743,
    "mean_difference": 0.0158
  }
}
```

## Troubleshooting

### Credentials Not Found

```
RuntimeError: IQM credentials not configured
```

**Fix:**
```bash
export IQM_CLIENT_ID='your-id'
export IQM_CLIENT_SECRET='your-secret'
python experiments/hardware_validate.py
```

### Exceeding Free Tier

If your experiment exceeds 30 credits:

**Option 1:** Reduce circuit count
```bash
python experiments/hardware_dryrun.py --num-circuits 10 --shots 10000
```

**Option 2:** Reduce shots per circuit
```bash
python experiments/hardware_validate.py --shots 5000
```

**Option 3:** Apply for additional credits (academic/research):
https://ionq.com/programs/research-credits/application

### API Connection Issues

- Verify IQM auth server is accessible: `curl https://auth.resonance.meetiqm.com`
- Check credentials are correct in account settings
- Ensure IQM SDK is installed: `pip install iqm-client`

## Understanding Simulation vs Hardware Differences

Hardware fidelity will typically be **slightly lower** than simulation due to:

1. **Gate calibration errors** - Real pulses have ~0.1-0.6% error
2. **Crosstalk** - Two-qubit gates on adjacent qubits affect each other
3. **Drift** - Qubit parameters change over time
4. **State preparation** - Initial state preparation errors
5. **Measurement errors** - Readout is imperfect

**Expected differences:** 0.5-2% fidelity loss

## Advanced Usage

### Custom Circuit Selection

Edit `experiments/hardware_validate.py` to select specific circuits:

```python
# Select only GHZ circuits
circuits_to_validate = [
    HardwareCircuit(name="ghz_4q", qasm=..., gates=7, depth=4, two_qubit_gates=3),
    HardwareCircuit(name="ghz_8q", qasm=..., gates=14, depth=7, two_qubit_gates=7),
]
```

### Different Backends

IQM Resonance supports multiple backends:

```bash
python experiments/hardware_validate.py --backend IQM_RESONANCE_5Q
python experiments/hardware_validate.py --backend IQM_RESONANCE_10Q
python experiments/hardware_validate.py --backend IQM_RESONANCE_20Q
```

(Check IQM API docs for current available backends)

## References

- **IQM Resonance**: https://resonance.meetiqm.com/
- **IQM Garnet Spec**: https://arxiv.org/abs/2408.12433
- **IQM Client SDK**: https://github.com/iqm-finland/iqm-client
- **Free Tier Pricing**: 30 credits/month at ~$0.01 per circuit

## Support

For issues:
1. Check IQM documentation: https://docs.resonance.meetiqm.com/
2. Review hardware status: https://status.resonance.meetiqm.com/
3. Contact IQM support: support@meetiqm.com
