# Cardinal Grid Notes

Short, reproducible technical notes on U.S. load-forecasting and data-quality problems. One question, one chart, the code behind it. Each note is published first at [cardinalgrid.com/notes](https://cardinalgrid.com/notes), archived on Zenodo with a DOI the same day, and republished on Medium, LinkedIn and Energy Central with the site as the canonical version.

## Schedule

| # | Note | Target |
|---|---|---|
| 1 | How well do U.S. balancing authorities forecast their own load? A 2015–2026 scorecard from EIA-930 | October 2026 |
| 2 | Winter Storm Elliott, revisited with public data | October 2026 |
| 3 | Were the "bad data" flags in the January 2024 Arctic storms really bad data? | November 2026 |
| 4 | Step loads: detecting data-center-scale structural breaks in ERCOT and PJM zonal load | November 2026 |
| 5 | From forecast error to reserve cost: a transparent back-of-envelope for ratepayers | December 2026 |
| 6 | How much of EIA-930 is imputed, and where? | December 2026 |
| 7 | Cold-snap regimes: why one model per season fails, and a probabilistic alternative | January 2027 |
| 8 | State of U.S. load forecasting 2026 | January 2027 |

Titles may change as the analysis is done; dates are target months.

## Layout

```
notes/
  01-ba-forecast-scorecard-2015-2026/
    README.md        the note
    notebook.ipynb   reproducible analysis
    data/            pinned snapshot or download script
  02-.../
```

## Reproducing a note

Each folder has a `requirements.txt` and a notebook that downloads (or pins) the public data it uses. Run it top to bottom.

## Corrections

Corrections are made here and on the site first, then noted in the changelog of the archived Zenodo record.

## License

Text and figures: CC BY 4.0. Code: Apache-2.0.
