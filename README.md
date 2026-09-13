# Cardinal Grid Notes

Short, reproducible technical notes on U.S. load-forecasting and data-quality problems. One question, one chart, the code behind it. Each note is published first at [cardinalgrid.com/notes](https://cardinalgrid.com/notes), archived on Zenodo with a DOI the same day, and republished on Medium, LinkedIn and Energy Central with the site as the canonical version.

## Published

| # | Note | Published | DOI |
|---|---|---|---|
| 1 | [How well do U.S. balancing authorities forecast their own load? A 2015–2026 scorecard from EIA-930](01-ba-forecast-scorecard-2015-2026/) | 2026-09-10 | [10.5281/zenodo.22698336](https://doi.org/10.5281/zenodo.22698336) |
| 2 | [Seven daily profiles, three, or none? Weekday, day type and weather in the daily load shape of U.S. balancing authorities](03-daily-load-profiles/) | 2026-09-13 | [10.5281/zenodo.22735699](https://doi.org/10.5281/zenodo.22735699) |

Each published note has a web version (`README.md`), an IEEE-format PDF (`paper/paper.pdf`) and, from No. 2, a plain-language version (`story.md`), all generated from the same script and the same numbers.

## Schedule

| # | Note | Target |
|---|---|---|
| 3 | Winter Storm Elliott, revisited with public data | October 2026 |
| 4 | Were the "bad data" flags in the January 2024 Arctic storms really bad data? | November 2026 |
| 5 | Step loads: detecting data-center-scale structural breaks in ERCOT and PJM zonal load | November 2026 |
| 6 | From forecast error to reserve cost: a transparent back-of-envelope for ratepayers | December 2026 |
| 7 | How much of EIA-930 is imputed, and where? | December 2026 |
| 8 | Cold-snap regimes: why one model per season fails, and a probabilistic alternative | January 2027 |
| 9 | State of U.S. load forecasting 2026 | January 2027 |

Titles may change as the analysis is done; dates are target months.

## Layout

```
notes/
  _template-ieee/                     IEEEtran template, figure style and shared bibliography
  01-ba-forecast-scorecard-2015-2026/
    analysis.py                       generates README.md and figures/ from the public data
    paper.py, paper/                  generates the IEEE-format PDF from the same numbers
  03-daily-load-profiles/
    analysis.py, weather.py           EIA-930 shapes and NOAA ISD-Lite temperatures
    paper.py, story.py                IEEE PDF and plain-language version
```

## Reproducing a note

Each folder's docstrings say how. The EIA-930 files come through [ba-forecast-scorecard](https://github.com/cardinalgrid/ba-forecast-scorecard); temperatures come from NOAA's public ISD-Lite files.

## Corrections

Corrections are made here and on the site first, then noted in the changelog of the archived Zenodo record.

## License

Text and figures: CC BY 4.0. Code: Apache-2.0.
