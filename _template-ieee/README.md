# IEEE template

Each note is published in two forms from the same analysis: a `README.md` for the web, and a `paper/paper.pdf` typeset with the IEEE `IEEEtran` class (conference format, two columns). The PDF is the version deposited on Zenodo and, when applicable, submitted to TechRxiv or an IEEE PES conference.

| File | Purpose |
|---|---|
| `template.tex` | Starting point for a new note's `paper/paper.tex`. |
| `ieee.mplstyle` | Matplotlib style for IEEE figures: 3.5 in single-column width, 7.16 in double-column, Times 8 pt, PDF output. |
| `references.bib` | Shared bibliography of public sources. |

## Build

```bash
cd paper
pdflatex paper && bibtex paper && pdflatex paper && pdflatex paper
```

Figures should be exported as PDF at `\columnwidth` (3.5 in) or `\textwidth` (7.16 in, inside `figure*`), without titles inside the figure; the caption states what is shown, the source and the period.
