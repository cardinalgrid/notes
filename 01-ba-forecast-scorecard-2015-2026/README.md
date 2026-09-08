# How well do U.S. balancing authorities forecast their own load? A 2015–2026 scorecard from EIA-930

**Cardinal Grid Notes · No. 1 · Draft generated 2026-09-08 · Data 2015-07-01 to 2026-06-30 · Code: [`analysis.py`](analysis.py) · Scorer: [ba-forecast-scorecard](https://github.com/cardinalgrid/ba-forecast-scorecard) v0.1.1**

> Status: **draft for review**. Numbers and figures in this note are produced by `analysis.py` from public data; nothing here is typed by hand. The note will be published at [cardinalgrid.com/notes](https://cardinalgrid.com/notes) and archived with a DOI once reviewed.

## The question

Every U.S. balancing authority (BA) publishes, through the U.S. Energy Information Administration's Form EIA-930, two hourly numbers: the demand that actually occurred, and the day-ahead demand forecast the BA itself submitted the morning before. Since July 2015 that pair has been public for every BA in the Lower 48. So the question "how well do operators forecast their own load?" does not need any operator's cooperation. It needs a script.

This matters because the day-ahead forecast is what operators commit generation and buy reserves against. When it is too low, reserves are short. FERC and NERC documented day-ahead load under-forecasts of up to 11.6% at one BA during Winter Storm Elliott, contributing to firm load shed ([FERC/NERC 2023](https://www.ferc.gov/news-events/news/ferc-nerc-release-final-report-lessons-winter-storm-elliott)); NERC's 2025 Long-Term Reliability Assessment states that traditional load forecasting methods may not be sufficient for the load growth ahead ([NERC 2026](https://www.nerc.com/globalassets/our-work/assessments/nerc_ltra_2025.pdf)).

## What was measured

- Source: EIA-930 six-month balance files, 2015-07-01 to 2026-06-30, 72 BAs in the files.
- For each BA-day with at least 20 valid hours: MAPE, bias, RMSE, and the error at the hour of the actual daily peak (`peak_hour_pct_error`, negative = forecast below actual). 206,335 BA-days and 4,945,622 hours were scored.
- Data-quality rules, applied before any error is computed: hours with demand or forecast ≤ 0 are excluded; hours where forecast/demand falls outside [1/2, 2] are flagged as implausible (a zero, a unit error, a stale value) and excluded. 114,326 hours were flagged. EIA-imputed demand values were 0.000% of scored hours.
- Ranking eligibility: at least 180 scored days, mean demand ≥ 500 MW, and a median daily bias within ±25% (beyond that, forecast and demand are not describing the same quantity). 58 BAs report both series; **42 are eligible**.

Full definitions are in the scorer's [README](https://github.com/cardinalgrid/ba-forecast-scorecard#metric-definitions).

## Findings

### 1. Typical day-ahead error is a few percent, with a long tail

Across eligible BAs, the **demand-weighted MAPE is 3.54%**; the median BA sits at 4.20%. The best five: PGE (1.8%), BPAT (2.0%), TVA (2.2%), GCPD (2.4%), ERCO (2.5%). The worst five: LDWP (7.8%), WACM (8.6%), WALC (9.9%), TEPC (11.2%), FPC (22.0%).

![Ranking](figures/fig1_ranking.png)

The tail is not, for the most part, bad forecasting. The BAs with the highest MAPE share a pattern of reported series with unit errors, zeros or stale values that survive the loose implausibility band. This is the reason the scorecard carries a data-quality layer, and it is the subject of Note 6.

### 2. The largest operators

| Rank | BA | Region | MAPE | Bias | Mean abs. error at peak hour | 1-in-100-day under-forecast at peak |
|---|---|---|---|---|---|---|
| 2 | BPAT | NW | 2.01% | 0.10% | 2.15% | 7.0% |
| 3 | TVA | TEN | 2.22% | 0.65% | 2.36% | 6.9% |
| 5 | ERCO | TEX | 2.48% | 0.42% | 2.54% | 8.1% |
| 6 | ISNE | NE | 2.60% | -1.63% | 1.40% | 4.6% |
| 9 | MISO | MIDW | 2.77% | 2.41% | 2.64% | 3.6% |
| 10 | DUK | CAR | 2.81% | 0.49% | 2.97% | 10.1% |
| 11 | NYIS | NY | 2.85% | -2.39% | 2.95% | 8.7% |
| 12 | SOCO | SE | 2.85% | -1.99% | 2.19% | 8.0% |
| 15 | PJM | MIDA | 3.21% | -1.22% | 2.23% | 6.8% |
| 20 | SWPP | CENT | 4.12% | 2.77% | 3.92% | 9.1% |
| 22 | FPL | FLA | 4.22% | -2.22% | 4.48% | 16.6% |
| 24 | CISO | CAL | 4.26% | -1.59% | 3.22% | 28.8% |
| 26 | AZPS | SW | 4.31% | -0.18% | 3.50% | 17.5% |
| 32 | PACE | NW | 4.98% | 3.79% | 4.49% | 20.4% |

![Yearly MAPE](figures/fig2_yearly_major.png)

Two trends in this chart deserve their own note before any conclusion is drawn: the rise in CISO's and SWPP's yearly MAPE since 2023, and AZPS's 2015 value. Each could be forecasting, a change in what the BA reports, or both. 2026 covers January to June only.

### 3. At the peak hour, forecasts lean low

On **59% of eligible BA-days the forecast was below actual demand at the hour of the daily peak.** If forecasts were unbiased, that share would be near 50%, and it has drifted upward since 2019. One eligible BA-day in a hundred under-forecasts the peak by more than **27.4%**. Under-forecasting at the peak is the direction that costs reserves and, in an emergency, load.

![Peak under-forecast share](figures/fig3_peak_under_forecast_share.png)

### 4. Named events

Worst peak-hour under-forecast by any eligible BA during each event window (fixed dates from the public inquiries):

| Event | BA | Worst under-forecast at peak |
|---|---|---|
| July-August 2023 heat wave (ERCOT and Southwest records) | WALC (SW) | 41.0% |
| January 2024 Arctic storms (incl. Winter Storm Heather) | WACM (NW) | 18.4% |
| Winter Storm Elliott | LGEE (MIDW) | 16.4% |
| January 2025 cold wave | LGEE (MIDW) | 13.7% |
| Pacific Northwest heat dome | SCL (NW) | 12.5% |
| Winter Storm Uri | AECI (MIDW) | 6.5% |

![Events](figures/fig4_events.png)

The largest single eligible BA-day miss in the whole period is PACE on 2016-04-02: forecast 50% below a 10,048 MW peak. Single-day extremes can still be data problems; the 1-in-100-day figure above is the robust one.

## What this does not show

- Forecasts are as submitted to EIA and may differ from what operators used internally; EIA's quality checks apply to demand, not forecasts.
- Several small BAs' series contain errors the implausibility band does not catch. Their MAPE says "data or forecast problem", not "forecast problem".
- Event windows are fixed dates, not weather-defined extreme days. Weather attribution comes with v0.2 of the scorer.
- No BA has been contacted for comment. Corrections are welcome: open an issue on the [scorer repository](https://github.com/cardinalgrid/ba-forecast-scorecard/issues).

## Reproduce

```bash
pip install -e ../../ba-forecast-scorecard matplotlib
python analysis.py --rebuild     # downloads the EIA-930 files (~1 GB) and rebuilds everything
```

## Cite

Guerra Filho, R. W. C. (2026). *How well do U.S. balancing authorities forecast their own load? A 2015–2026 scorecard from EIA-930.* Cardinal Grid Notes, No. 1. DOI: to be assigned on publication.

*Text and figures CC BY 4.0; code Apache-2.0. Analyses rely on public data only and represent the author's own views.*
