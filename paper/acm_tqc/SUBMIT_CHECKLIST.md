# Submit to ACM TQC — Checklist

**Paper:** End-to-End Fidelity Analysis of Quantum Circuit Optimization: From Gate-Level Transformations to Pulse-Level Control  
**Journal:** ACM Transactions on Quantum Computing  
**arXiv preprint:** 2601.20871  
**Target date:** ~Mar 10, 2026

---

## Before you open the browser

### 1. Push repos to GitHub

```bash
cd ~/dev/research/qco-integration && git push origin master
cd ~/dev/research/quantum-circuit-optimizer && git push origin master
```

Verify both are public:
- https://github.com/rylanmalarchick/qco-integration
- https://github.com/rylanmalarchick/quantum-circuit-optimizer

### 2. Recompile the paper (just in case)

```bash
cd ~/dev/research/qco-integration/paper/acm_tqc
latexmk -pdf main.tex
latexmk -pdf cover_letter.tex
```

No warnings, no overfull boxes. If something changed, re-audit.

---

## Submission portal

**URL:** https://mc.manuscriptcentral.com/tqc

Create an account if you do not have one. Use `malarchr@erau.edu`.

---

## Fill out the form

| Field | Value |
|-------|-------|
| Article type | Research Article |
| Title | End-to-End Fidelity Analysis of Quantum Circuit Optimization: From Gate-Level Transformations to Pulse-Level Control |
| Authors | Rylan Malarchick |
| Affiliation | Department of Engineering Physics, Embry-Riddle Aeronautical University, Daytona Beach, FL, USA |
| Email | malarchr@erau.edu |
| ORCID | 0009-0005-9290-2187 |
| Keywords | quantum circuit optimization, quantum compilation, pulse-level simulation, Lindblad master equation, superconducting qubits, NISQ, compiler comparison, ablation study |
| Prior publication | arXiv:2601.20871 (preprint, substantially revised) |
| Conflicts of interest | None |
| AI disclosure | Yes. Claude (Anthropic) used for code development and manuscript drafting. Author takes full responsibility for all content. |

---

## Upload files

| File | Path | Notes |
|------|------|-------|
| Manuscript PDF | `paper/acm_tqc/main.pdf` | 23 pages, compiled from `main.tex` |
| Manuscript source | `paper/acm_tqc/main.tex` | Single file, all refs inline via `thebibliography` |
| Cover letter | `paper/acm_tqc/cover_letter.pdf` | |
| Figures (9 used) | `paper/acm_tqc/figures/` | Upload these individually: |
| | `architecture.pdf` | |
| | `pass_effectiveness.pdf` | |
| | `fidelity_waterfall.pdf` | |
| | `scaling_qubits.pdf` | |
| | `compiler_comparison_2q.pdf` | |
| | `compiler_heatmap_2q.pdf` | |
| | `ablation_cumulative.pdf` | |
| | `ablation_leave_one_out.pdf` | |
| | `hardware_validation.pdf` | |

Do NOT upload: `baseline_vs_optimized.pdf`, `compiler_comparison_overall.pdf`, `hardware_scaling.pdf`, `scaling_depth.pdf`. These are in the figures folder but not referenced in the paper.

If the portal asks for a single zip instead of individual files:
```bash
cd ~/dev/research/qco-integration/paper/acm_tqc
mkdir -p submission_pkg
cp main.tex main.pdf cover_letter.pdf submission_pkg/
cp figures/architecture.pdf figures/pass_effectiveness.pdf figures/fidelity_waterfall.pdf figures/scaling_qubits.pdf figures/compiler_comparison_2q.pdf figures/compiler_heatmap_2q.pdf figures/ablation_cumulative.pdf figures/ablation_leave_one_out.pdf figures/hardware_validation.pdf submission_pkg/
cd submission_pkg && zip ../submission.zip *
```

---

## After you hit submit

### Update arXiv

```bash
# From paper/acm_tqc/, build the arXiv source zip
mkdir -p /tmp/arxiv_v2
cp main.tex /tmp/arxiv_v2/
cp figures/architecture.pdf figures/pass_effectiveness.pdf figures/fidelity_waterfall.pdf figures/scaling_qubits.pdf figures/compiler_comparison_2q.pdf figures/compiler_heatmap_2q.pdf figures/ablation_cumulative.pdf figures/ablation_leave_one_out.pdf figures/hardware_validation.pdf /tmp/arxiv_v2/
cd /tmp/arxiv_v2 && tar czf ~/arxiv_v2_upload.tar.gz *
```

Go to https://arxiv.org/abs/2601.20871 → Replace → upload the tarball. Add a note: "Substantially revised: real pipeline data, compiler comparison, ablation study, hardware validation."

### Record it

```
Submitted to ACM TQC on [DATE].
Manuscript Central confirmation #: [NUMBER]
arXiv v2 updated on [DATE].
```

---

## Quick sanity check (run right before submitting)

```bash
cd ~/dev/research/qco-integration
.venv/bin/python -m pytest tests/ -q --tb=no        # 252 passed
cd paper/acm_tqc && latexmk -pdf main.tex            # 23 pages, 0 warnings
grep -c 'bibitem{' main.tex                           # 44
grep -c 'includegraphics' main.tex                    # 9
grep -c 'Description{' main.tex                       # 9
grep 'orcid{' main.tex                                # present
grep 'github.com' main.tex                            # 2 URLs
```

All should pass. If any fail, do not submit until fixed.
