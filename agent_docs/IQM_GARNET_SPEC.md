# IQM Garnet Hardware Specification

**Source:** Official IQM SDK (https://github.com/iqm-finland/sdk)  
**Reference Paper:** arXiv:2408.12433 - "Technology and Performance Benchmarks of IQM's 20-Qubit Quantum Computer"

## Overview

| Property | Value |
|----------|-------|
| QPU Name | Garnet |
| Qubits | 20 (QB1-QB20) |
| Qubit Type | Superconducting transmon |
| Native Gates | PRX (phased rotation), CZ (controlled-Z) |
| Connectivity | 30 edges (see coupling map below) |
| Median 2Q Gate Fidelity | 99.5% |

## Coupling Map (30 edges)

```python
IQM_GARNET_COUPLING_MAP = [
    ("QB1", "QB2"),
    ("QB1", "QB4"),
    ("QB2", "QB5"),
    ("QB3", "QB4"),
    ("QB3", "QB8"),
    ("QB4", "QB5"),
    ("QB4", "QB9"),
    ("QB5", "QB6"),
    ("QB5", "QB10"),
    ("QB6", "QB7"),
    ("QB6", "QB11"),
    ("QB7", "QB12"),
    ("QB8", "QB9"),
    ("QB8", "QB13"),
    ("QB9", "QB10"),
    ("QB9", "QB14"),
    ("QB10", "QB11"),
    ("QB10", "QB15"),
    ("QB11", "QB12"),
    ("QB11", "QB16"),
    ("QB12", "QB17"),
    ("QB13", "QB14"),
    ("QB14", "QB15"),
    ("QB14", "QB18"),
    ("QB15", "QB16"),
    ("QB15", "QB19"),
    ("QB16", "QB17"),
    ("QB16", "QB20"),
    ("QB18", "QB19"),
    ("QB19", "QB20"),
]
```

## Visual Topology

```
        QB1 ─── QB2
        │       │
        │       │
QB3 ─── QB4 ─── QB5 ─── QB6 ─── QB7
│       │       │       │       │
│       │       │       │       │
QB8 ─── QB9 ─── QB10 ── QB11 ── QB12
│       │       │       │       │
│       │       │       │       │
QB13 ── QB14 ── QB15 ── QB16 ── QB17
        │       │       │
        │       │       │
        QB18 ── QB19 ── QB20
```

## Per-Qubit T1 Times (nanoseconds)

From `fake_garnet.py`:

| Qubit | T1 (ns) |
|-------|---------|
| QB1 | 37,741 |
| QB2 | 32,584 |
| QB3 | 24,468 |
| QB4 | 11,555 |
| QB5 | 34,257 |
| QB6 | 40,051 |
| QB7 | 35,708 |
| QB8 | 25,686 |
| QB9 | 34,113 |
| QB10 | 37,391 |
| QB11 | 25,809 |
| QB12 | 60,725 |
| QB13 | 44,802 |
| QB14 | 48,137 |
| QB15 | 39,052 |
| QB16 | 43,968 |
| QB17 | 36,670 |
| QB18 | 38,151 |
| QB19 | 50,012 |
| QB20 | 54,911 |

## Per-Qubit T2 Times (nanoseconds)

| Qubit | T2 (ns) |
|-------|---------|
| QB1 | 9,180 |
| QB2 | 10,040 |
| QB3 | 10,950 |
| QB4 | 9,670 |
| QB5 | 8,960 |
| QB6 | 10,130 |
| QB7 | 8,590 |
| QB8 | 9,050 |
| QB9 | 9,380 |
| QB10 | 9,820 |
| QB11 | 9,460 |
| QB12 | 9,940 |
| QB13 | 10,070 |
| QB14 | 9,030 |
| QB15 | 9,590 |
| QB16 | 9,710 |
| QB17 | 10,180 |
| QB18 | 9,250 |
| QB19 | 8,270 |
| QB20 | 11,930 |

## Gate Durations

| Gate | Duration (ns) |
|------|---------------|
| PRX (1Q) | 20 |
| CZ (2Q) | 40 |

## Two-Qubit Gate Error Parameters (CZ depolarizing)

| Edge | Error |
|------|-------|
| (QB1, QB2) | 0.00578 |
| (QB1, QB4) | 0.00804 |
| (QB2, QB5) | 0.00749 |
| (QB3, QB4) | 0.00809 |
| (QB8, QB3) | 0.00599 |
| (QB4, QB5) | 0.00431 |
| (QB9, QB4) | 0.00650 |
| (QB5, QB6) | 0.00474 |
| (QB10, QB5) | 0.00339 |
| (QB6, QB7) | 0.00527 |
| (QB11, QB6) | 0.01401 |
| (QB12, QB7) | 0.00294 |
| (QB8, QB9) | 0.00399 |
| (QB8, QB13) | 0.00485 |
| (QB9, QB10) | 0.00638 |
| (QB9, QB14) | 0.00548 |
| (QB10, QB11) | 0.00682 |
| (QB10, QB15) | 0.00961 |
| (QB11, QB12) | 0.00899 |
| (QB16, QB11) | 0.00712 |
| (QB17, QB12) | 0.00407 |
| (QB13, QB14) | 0.00251 |
| (QB14, QB15) | 0.00506 |
| (QB18, QB14) | 0.00420 |
| (QB16, QB15) | 0.00771 |
| (QB19, QB15) | 0.00711 |
| (QB16, QB17) | 0.00643 |
| (QB16, QB20) | 0.00562 |
| (QB18, QB19) | 0.00507 |
| (QB19, QB20) | 0.00578 |

## Single-Qubit Gate Error Parameters (PRX depolarizing)

| Qubit | Error |
|-------|-------|
| QB1 | 0.00085 |
| QB2 | 0.00183 |
| QB3 | 0.00165 |
| QB4 | 0.00111 |
| QB5 | 0.00114 |
| QB6 | 0.00384 |
| QB7 | 0.00265 |
| QB8 | 0.00084 |
| QB9 | 0.00122 |
| QB10 | 0.00113 |
| QB11 | 0.00274 |
| QB12 | 0.00076 |
| QB13 | 0.00089 |
| QB14 | 0.00074 |
| QB15 | 0.00278 |
| QB16 | 0.00067 |
| QB17 | 0.00085 |
| QB18 | 0.00061 |
| QB19 | 0.00069 |
| QB20 | 0.00088 |

## Readout Errors

| Qubit | P(1|0) | P(0|1) |
|-------|--------|--------|
| QB1 | 0.0255 | 0.0260 |
| QB2 | 0.0245 | 0.0240 |
| QB3 | 0.0285 | 0.0245 |
| QB4 | 0.0245 | 0.0240 |
| QB5 | 0.0250 | 0.0255 |
| QB6 | 0.0265 | 0.0275 |
| QB7 | 0.0255 | 0.0260 |
| QB8 | 0.0290 | 0.0250 |
| QB9 | 0.0260 | 0.0245 |
| QB10 | 0.0220 | 0.0245 |
| QB11 | 0.0280 | 0.0245 |
| QB12 | 0.0255 | 0.0250 |
| QB13 | 0.0265 | 0.0255 |
| QB14 | 0.0240 | 0.0245 |
| QB15 | 0.0230 | 0.0245 |
| QB16 | 0.0220 | 0.0255 |
| QB17 | 0.0240 | 0.0240 |
| QB18 | 0.0245 | 0.0260 |
| QB19 | 0.0250 | 0.0255 |
| QB20 | 0.0280 | 0.0285 |

## Usage in Code

```python
# Zero-indexed coupling map for quantum-circuit-optimizer
IQM_GARNET_EDGES_ZERO_INDEXED = [
    (0, 1), (0, 3), (1, 4), (2, 3), (2, 7),
    (3, 4), (3, 8), (4, 5), (4, 9), (5, 6),
    (5, 10), (6, 11), (7, 8), (7, 12), (8, 9),
    (8, 13), (9, 10), (9, 14), (10, 11), (10, 15),
    (11, 16), (12, 13), (13, 14), (13, 17), (14, 15),
    (14, 18), (15, 16), (15, 19), (17, 18), (18, 19),
]
```
