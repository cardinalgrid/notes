# IEEE template for Cardinal Grid Notes

Every note has two outputs generated from the same analysis script and the same numbers:

1. **Web version**: `README.md` in the note folder, rendered by GitHub and republished on cardinalgrid.com, Medium and LinkedIn. Lighter voice, figures at web size.
2. **Paper version**: `paper/paper.pdf`, built with the IEEE `IEEEtran` class (two columns, Times 10 pt). This is the file deposited on Zenodo with the DOI and, when applicable, submitted to TechRxiv or an IEEE PES conference.

## Files

| File | Purpose |
|---|---|
| `template.tex` | Starting point for a new note's `paper/paper.tex`. Conference mode of `IEEEtran`. |
| `ieee.mplstyle` | Matplotlib style: 3.5 in single-column figures, Times 8 pt, no in-figure titles. |
| `references.bib` | Shared bibliography of public sources (FERC, NERC, DOE, EIA, LBNL). Copy or extend. |

## Rules

- **Figures**: width `\columnwidth` (3.5 in) or `\textwidth` (7.16 in, with `figure*`). No title inside the figure; the caption says what it shows, the source and the period. Export PDF, not PNG. Fonts 7–9 pt.
- **Tables**: `booktabs`, caption above, units in the header.
- **Voice**: impersonal and declarative. No "we think", no "it needs a script". Define each term on first use and reuse it unchanged.
- **Numbers**: never typed by hand. The analysis script writes them into the `.tex` from `summary.json`.
- **Claims**: every factual statement about the grid cites a public document in `references.bib`.
- **Limitations**: a dedicated subsection, always.
- **Author line**: name, "Cardinal Grid (independent open initiative)", ORCID, contact email. No employer affiliation unless authorized in writing.

## Build

```bash
cd paper
pdflatex paper && bibtex paper && pdflatex paper && pdflatex paper
```

On this machine, strip the `node.exe` entry from PATH first (MiKTeX quirk):
`export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v 'node.exe' | paste -sd:)`.

## Submitting

- **Zenodo**: upload `paper.pdf` as a new record of type *publication / technical note* in the `cardinal-grid` community; link the GitHub folder and the scorer DOI as related identifiers.
- **TechRxiv**: same PDF; choose the IEEE PES subject; the DOI from TechRxiv is additional to Zenodo's.
- **IEEE PES General Meeting**: five pages maximum in this format; submission site opens 6 October 2026, deadline 10 November 2026.
