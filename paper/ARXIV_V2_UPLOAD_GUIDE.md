# arXiv v2 Upload Guide for QCO-Integration

## Paper: "End-to-End Fidelity Analysis of Quantum Circuit Optimization"
- **arXiv ID**: 2601.20871
- **Version**: v2 (adds Lubasch citation per Quantinuum request)

---

## Pre-Upload Checklist

- [x] Lubasch citation added to references.bib
- [x] Citation added in Introduction (line ~41 in main.tex)
- [x] Paper compiles without errors
- [x] Figures included in arxiv_v2/figures/

---

## Step-by-Step Upload Process

### 1. Go to arXiv
```
https://arxiv.org/user/
```
Log in with your arXiv credentials.

### 2. Find Your Submission
- Click "Submissions" in the top menu
- Find "End-to-End Fidelity Analysis of Quantum Circuit Optimization"
- Click "Add Journal Reference or Replacement"

### 3. Select "Replace" (New Version)
- Choose "Replace with a new version"
- NOT "Add journal reference" (that's for after peer review)

### 4. Upload Files
Upload the following files from `~/dev/research/qco-integration/paper/arxiv_v2/`:

```
Required files:
├── main.tex          (source)
├── main.bbl          (bibliography - REQUIRED, not .bib)
├── references.bib    (optional, but include anyway)
└── figures/          (all PDFs)
    ├── architecture.pdf
    ├── baseline_vs_optimized.pdf
    ├── fidelity_waterfall.pdf
    ├── hardware_scaling.pdf
    ├── hardware_validation.pdf
    ├── pass_effectiveness.pdf
    ├── scaling_depth.pdf
    └── scaling_qubits.pdf
```

### 5. Quick Upload Method
```bash
# Create a zip for easy upload
cd ~/dev/research/qco-integration/paper/arxiv_v2
zip -r arxiv_v2_upload.zip main.tex main.bbl references.bib figures/
```
Then upload the zip file directly to arXiv.

### 6. Add Comments for v2
In the "Comments" field, add:
```
v2: Added citation to Lubasch et al. (arXiv:2511.15674) on tensor network 
methods for quantum state preparation. Minor text corrections.
```

### 7. Verify Compilation
- arXiv will compile your paper
- Wait for the preview
- Check that all figures render correctly
- Verify the Lubasch citation appears in the bibliography

### 8. Submit
- Click "Submit" once preview looks good
- v2 will appear on arXiv within 24 hours (usually overnight)

---

## Files Location

```bash
# Source files ready for upload
ls ~/dev/research/qco-integration/paper/arxiv_v2/

# Create upload zip
cd ~/dev/research/qco-integration/paper/arxiv_v2
zip -r arxiv_v2_upload.zip main.tex main.bbl references.bib figures/
```

---

## What Changed in v2

1. **New citation**: Lubasch et al., "Efficient quantum state preparation of 
   multivariate functions using tensor networks," arXiv:2511.15674 (2025)

2. **Location**: Introduction, alongside other gate optimization citations:
   ```latex
   \cite{nam2018automated,kissinger2020reducing,lubasch2025tensor}
   ```

3. **Why**: Researcher at Quantinuum (Lubasch's affiliation) requested the 
   citation as their work is directly related to quantum circuit optimization.

---

## Troubleshooting

**"Missing .bbl file"**: arXiv needs the compiled bibliography. Run:
```bash
cd ~/dev/research/qco-integration/paper/arxiv_v2
pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex
```

**Figures not showing**: Make sure figures/ folder is included and paths in 
main.tex are `figures/filename.pdf` not `../figures/filename.pdf`

**revtex4-2 errors**: arXiv has revtex4-2 installed. If issues, try removing 
unusual options from documentclass.
