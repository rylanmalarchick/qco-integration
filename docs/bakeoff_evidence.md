# Bake-off evidence: is there a "decoherence-aware compilation" method here?

Decision memo for the post-ACM-TQC rehash. Everything below is from running the
**validated** idle-aware Lindblad model (`src/pulse.py`, cross-checked against
qiskit-dynamics to ~1e-7; full suite 266 passed) over real compiler outputs.
Reproduce with `/tmp/bakeoff.py` (cross-compiler) and the all-to-all control.

## The question under test

The chosen thesis was: *a decoherence/fidelity-aware compiler objective beats a
gate-count objective by a real margin.* For that to be a publishable **method**,
the circuit that **maximizes predicted fidelity** must differ from the one that
**minimizes gate count** — and win by enough to matter.

## Experiment 1 — cross-compiler (QCO C++ vs Qiskit L1/L2/L3)

Each circuit compiled every way, every variant scored by the validated model.
`F` = predicted average-gate state fidelity (idle-aware, ASAP schedule).

| circuit | QCO n / 2q / F | Qiskit-L3 n / 2q / F | count-best | fid-best | margin |
|---|---|---|---|---|---|
| ghz_6  | 7 / 6 / **0.903**  | 28 / 5 / 0.849 | QCO | QCO | 0 |
| ghz_8  | 11 / 10 / **0.830** | 38 / 7 / 0.763 | QCO | QCO | 0 |
| qft_5  | 57 / 32 / **0.615** | 118 / 30 / 0.553 | QCO | QCO | 0 |
| qft_6  | 83 / 47 / **0.476** | 197 / 51 / 0.361 | QCO | QCO | 0 |
| qft_8  | 156 / 92 / **0.196** | 372 / 105 / 0.109 | QCO | QCO | 0 |
| qaoa_6 | 42 / 21 / **0.694** | 100 / 31 / 0.525 | QCO | QCO | 0 |
| qaoa_8 | 64 / 35 / **0.525** | 195 / 55 / 0.311 | QCO | QCO | 0 |
| rand_6x15 | 73 / 21 / **0.679** | 147 / 44 / 0.442 | QCO | QCO | 0 |
| rand_8x20 | 139 / 33 / **0.501** | 195 / 53 / 0.376 | QCO | QCO | 0 |
| rand_6x25 | 123 / 49 / **0.434** | 285 / 82 / 0.214 | QCO | QCO | 0 |

**fidelity-best == count-best in 10/10. Margin 0.0000 everywhere.**

Caveat (why this alone isn't conclusive): QCO routed to the rich iqm-garnet
topology while Qiskit was forced onto a *linear* coupling map, so part of QCO's
win is SWAP overhead I imposed on Qiskit, not the objective. Hence the control.

## Experiment 2 — control, Qiskit all-to-all (no routing penalty)

Topology held fixed across L1/L2/L3 (Qiskit's most generous case). Within one
compiler, does higher fidelity ever come from a *longer* circuit?

| circuit | L1 (n/2q/F) | L2 | L3 | fid-best == count-best? |
|---|---|---|---|---|
| qft_5 | 65/26/0.669 | 75/20/0.669 | 75/20/0.669 | tie (0.669 both) |
| qft_6 | 93/39/0.552 | 104/30/0.550 | 104/30/0.550 | YES |
| qft_8 | 156/68/0.350 | 174/56/0.331 | 174/56/0.331 | YES |
| qaoa_6 | 50/18/0.707 | 61/18/0.686 | 61/18/0.686 | YES |
| rand_6x15 | 68/16/0.752 | 50/14/0.789 | 50/14/0.789 | YES |
| rand_8x20 | 97/20/0.689 | 81/19/0.717 | 81/19/0.717 | YES |

**Fidelity never rewards a longer circuit.** No schedulable lever of any size.

## Conclusion: the method thesis is dead, but one finding sharpened

1. **NO-GO (method):** fidelity-optimal compilation = count-optimal compilation.
   There is no "decoherence-aware objective beats gate-count" effect to publish.
   The one variant that *could* win is **noise-adaptive layout** (qubit/edge
   selection by per-qubit error) — that's Murali et al. 2019, already cited in
   the paper. Reinventing it = ACM TQC reject reasons 1 (no new technique) & 4
   (already known) all over again.

2. **What got sharper (real, physically grounded now):**
   **two-qubit gate count, not total gate count, is the fidelity-relevant proxy.**
   Cleanest proof — qft_5, all-to-all: **Qiskit-L2 has 10 MORE total gates than
   L1 (75 vs 65) but 6 FEWER 2q gates (20 vs 26), and identical fidelity 0.669.**
   The extra single-qubit gates are ~free; the 2q reduction is what pays. The
   original paper *asserted* this from a circular exp-decay heuristic; it is now
   demonstrable from a qiskit-dynamics-validated model.

## Assets actually in hand for a pivoted paper

- A validated, **O(#gates) scalable** end-to-end gate→pulse fidelity model
  (per-gate Lindblad + calibrated depolarizing + idle decoherence; runs where
  full 2^n density-matrix sim cannot). Directly answers AE reason 2 (tiny
  circuits).
- The **2q-metric refutation** with validated backing (above).
- A **hardware feasibility frontier**: which circuit sizes are even worth running
  on Garnet (qft_8 F≈0.20; ≥1000-gate circuits collapse to ~0 from 2q error).

## Candidate honest theses (no new-algorithm claim)

- **A. Methods/validation paper.** "A validated, scalable end-to-end fidelity
  model for compiler evaluation," with the 2q-metric result as the headline
  finding. Achievable now; moderate-novelty venue.
- **B. Negative/characterization result.** "Gate-count and fidelity objectives
  coincide on NISQ hardware — when does compilation stop helping?" The feasibility
  frontier is the contribution. Honest, less common framing.
- **C. Keep hunting** for a real lever (e.g. an explicitly 2q-aware objective
  that changes compiler *output*, not just the scoreboard) before committing —
  open-ended, may not pay off (this round didn't).

Author's note: A is the safest real paper; B is the most distinctive if framed as
a rigorous negative result; C is the only path back to a "new technique" claim
but carries real risk. None of these is mine to choose — they change what the
paper *is*.

## Update (2026-06-01): C hunted to exhaustion — three leads, all dead-or-published

Per the "keep hunting C" directive, three distinct method levers were built and
tested with the validated model:

1. **Decoherence-aware scheduling** — fidelity-best == gate-count-best in 10/10
   circuits (all-to-all control confirms). No schedulable lever. DEAD.
2. **Approximation interior-optimum** — real (+11-21% on QFT via an interior
   approximation_degree that beats both exact and over-approximated, scoring
   end-to-end = algorithmic x hardware fidelity). But this is BQSKit **QUEST**
   (arXiv:2108.12714) and **COGNAC** (arXiv:2311.02769). PUBLISHED.
3. **DD-aware idle-filling under non-Markovian 1/f** — built a validated
   filter-function dephasing model (src/noise_spectrum.py; 14/14 tests, white
   limit reproduces exp(-t/T2) exactly and is DD-invariant, 1/f makes DD help).
   Circuit-level: DD idle-filling gives +0.042 mean / +0.094 max fidelity over
   8/8 circuits, with a white-noise control returning EXACTLY 0 (proves the gain
   is real non-Markovian physics, gate-error-costed). But this is **GraphDD**
   (PRX Quantum 6, 010332 / arXiv:2409.05962) + existing Qiskit DD passes.
   PUBLISHED (and more advanced: handles crosstalk, scales linearly).

Verdict: every C lever that actually *works* is already in the literature.
Pursuing C as a "new technique" re-earns ACM TQC reject reasons 1 & 4. The
non-Markovian model is a genuine ASSET but its honest contribution is "a
validated scalable end-to-end model" = thesis A. RECOMMENDATION: converge to A,
fold the validated Lindblad + filter-function model + the 2q-metric finding into
a methods/validation paper, and cite QUEST/COGNAC/GraphDD as the prior art the
model is built to *evaluate*, not reinvent.
