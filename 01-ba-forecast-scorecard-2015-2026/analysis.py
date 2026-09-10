"""Note 1: How well do U.S. balancing authorities forecast their own load? A 2015-2026 scorecard from EIA-930.

Reproducible analysis. Reads the results produced by `ba-forecast-scorecard` (or rebuilds them from the
public EIA-930 files if `--rebuild` is given), writes the figures used in the note and fills the
numbers into README.md from a template, so that no figure or number in the note is typed by hand.

Usage
-----
pip install ba-forecast-scorecard matplotlib      # or: pip install -e ../../ba-forecast-scorecard
python analysis.py --results ../../ba-forecast-scorecard/results
python analysis.py --rebuild                      # downloads ~1 GB of EIA-930 files, then scores
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).parent
FIG = HERE / "figures"
NAVY, RED, GRAY, TEAL = "#1F3A5F", "#CC2000", "#6B7280", "#46B2B4"
MAJOR = ["PJM", "MISO", "ERCO", "SWPP", "CISO", "NYIS", "ISNE", "TVA", "SOCO", "DUK", "FPL", "BPAT", "PACE", "AZPS"]


def load(results: Path) -> dict[str, pd.DataFrame | dict]:
    return {
        "summary": json.loads((results / "summary.json").read_text(encoding="utf-8")),
        "yearly": pd.read_csv(results / "ba_yearly.csv"),
        "monthly": pd.read_csv(results / "ba_monthly.csv"),
        "ranking": pd.read_csv(results / "ranking_overall.csv"),
        "events": pd.read_csv(results / "events_by_ba.csv"),
    }


def style(ax, title, ylabel=None):
    ax.set_title(title, loc="left", fontsize=12, color=NAVY, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    if ylabel:
        ax.set_ylabel(ylabel)


def fig_ranking(ranking: pd.DataFrame) -> Path:
    r = ranking.sort_values("mape", ascending=False)
    fig, ax = plt.subplots(figsize=(8, 0.28 * len(r) + 1.5))
    colors = [RED if b in MAJOR else GRAY for b in r["ba"]]
    ax.barh(r["ba"], r["mape"] * 100, color=colors)
    ax.axvline(ranking["mape"].median() * 100, color=NAVY, ls="--", lw=1)
    ax.text(ranking["mape"].median() * 100, -0.8, f" median {ranking['mape'].median()*100:.1f}%", color=NAVY, fontsize=9, va="top")
    style(ax, "Day-ahead load forecast error by BA, July 2015 to June 2026")
    ax.set_xlabel("hour-weighted MAPE, %")
    ax.tick_params(axis="y", labelsize=8)
    fig.text(0.01, 0.005, "Red: the largest ISOs/RTOs and utilities. Source: EIA-930 six-month files; scoring by ba-forecast-scorecard.", fontsize=8, color=GRAY)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    out = FIG / "fig1_ranking.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def fig_yearly_major(yearly: pd.DataFrame) -> Path:
    y = yearly[yearly["ba"].isin(MAJOR)]
    fig, ax = plt.subplots(figsize=(9, 5))
    for ba, g in y.groupby("ba"):
        g = g.sort_values("year")
        ax.plot(g["year"], g["mape"] * 100, marker="o", ms=3, lw=1.2, label=ba)
    style(ax, "Yearly MAPE, largest balancing authorities (* = partial year)", "MAPE, %")
    yrs = sorted(y["year"].unique())
    ax.set_xticks(yrs)
    ax.set_xticklabels([f"{v}*" if v == max(yrs) else str(v) for v in yrs])
    ax.legend(ncol=4, fontsize=8, frameon=False)
    fig.tight_layout()
    out = FIG / "fig2_yearly_major.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def fig_peak_bias(yearly: pd.DataFrame, eligible: list[str]) -> Path:
    y = yearly[yearly["ba"].isin(eligible)].copy()
    agg = y.groupby("year").apply(lambda g: np.average(g["under_forecast_day_share"], weights=g["days"])).reset_index(name="share")
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(agg["year"], agg["share"] * 100, color=NAVY)
    ax.axhline(50, color=RED, ls="--", lw=1)
    ax.text(agg["year"].min() - 0.4, 51, "50%: no systematic bias", color=RED, fontsize=9)
    style(ax, "BA-days with the forecast below actual demand at the peak hour", "% of eligible BA-days")
    ax.set_xticks(agg["year"])
    ax.set_xticklabels([f"{v}*" if v == agg["year"].max() else str(v) for v in agg["year"]])
    fig.tight_layout()
    out = FIG / "fig3_peak_under_forecast_share.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def fig_events(events: pd.DataFrame, eligible: list[str]) -> Path:
    ev = events.dropna(subset=["worst_under_forecast_pct"]).copy()
    ev = ev[ev["ba"].isin(eligible)]
    order = ["uri_2021", "heat_dome_2021", "elliott_2022", "heat_wave_2023", "arctic_2024", "cold_jan_2025"]
    ev["event_id"] = pd.Categorical(ev["event_id"], [o for o in order if o in set(ev["event_id"])], ordered=True)
    ev = ev.sort_values("event_id")
    fig, ax = plt.subplots(figsize=(9, 5))
    groups = [np.clip(-g["worst_under_forecast_pct"].values * 100, 0, None) for _, g in ev.groupby("event_id", observed=True)]
    labels = [str(k) for k, _ in ev.groupby("event_id", observed=True)]
    ax.boxplot(groups, labels=labels, vert=True, showfliers=True)
    style(ax, "Worst peak-hour under-forecast per eligible BA, by named event", "worst under-forecast at peak, % (0 = never under)")
    ax.tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    out = FIG / "fig4_events.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def render_readme(d: dict, figs: list[Path]) -> None:
    s = d["summary"]
    rk = d["ranking"]
    eligible = list(rk["ba"])
    ev = d["events"]
    ev = ev[ev["ba"].isin(eligible)]
    worst_by_event = (
        ev.sort_values("worst_under_forecast_pct").groupby("event_id").head(1)[["event_id", "event_name", "ba", "region", "worst_under_forecast_pct"]]
    )
    major = rk[rk["ba"].isin(MAJOR)][["rank", "ba", "region", "mape", "bias_pct", "peak_hour_abs_pct_error_mean", "p99_under_forecast_pct"]]

    def pct(x, nd=1):
        return f"{x*100:.{nd}f}%"

    major_rows = "\n".join(
        f"| {int(r['rank'])} | {r['ba']} | {r['region']} | {pct(r['mape'],2)} | {pct(r['bias_pct'],2)} | {pct(r['peak_hour_abs_pct_error_mean'],2)} | {pct(-r['p99_under_forecast_pct'])} |"
        for _, r in major.iterrows()
    )
    event_rows = "\n".join(
        f"| {r['event_name']} | {r['ba']} ({r['region']}) | {pct(-r['worst_under_forecast_pct'])} |" for _, r in worst_by_event.iterrows()
    )
    top = ", ".join(f"{r['ba']} ({pct(r['mape'])})" for r in s["ranking_overall_top5"])
    bottom = ", ".join(f"{r['ba']} ({pct(r['mape'])})" for r in s["ranking_overall_bottom5"])
    w = s["worst_single_day_under_forecast_at_peak_eligible"]

    last = pd.Timestamp(s["last_date"])
    partial = "" if (last.month == 12 and last.day == 31) else f"{last.year} covers January to {last.strftime('%B')} only."
    tpl = (HERE / "README.template.md").read_text(encoding="utf-8")
    out = tpl.format(
        partial_year_note=partial,
        first_date=s["first_date"],
        last_date=s["last_date"],
        generated=s["generated_at_utc"][:10],
        n_total=s["balancing_authorities_total"],
        n_scored=s["balancing_authorities_scored"],
        n_eligible=s["eligible_balancing_authorities"],
        ba_days=f"{s['ba_days_scored']:,}",
        hours=f"{s['hours_scored']:,}",
        dw_mape=pct(s["demand_weighted_mape_eligible"], 2),
        med_mape=pct(s["median_ba_mape_eligible"], 2),
        under_share=pct(s["share_of_ba_days_under_forecast_at_peak_eligible"], 0),
        top=top,
        bottom=bottom,
        worst_ba=w["ba"],
        worst_date=w["date"],
        worst_pct=pct(-w["peak_hour_pct_error"], 0),
        worst_mw=f"{w['peak_demand_mw']:,.0f}",
        p99=pct(-s["p99_under_forecast_at_peak_eligible"]),
        implausible=f"{s['hours_flagged_implausible']:,}",
        imputed=pct(s["share_of_scored_hours_imputed"], 3),
        major_rows=major_rows,
        event_rows=event_rows,
        version=s["package_version"],
    )
    (HERE / "README.md").write_text(out, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=Path("../../ba-forecast-scorecard/results"))
    ap.add_argument("--rebuild", action="store_true", help="download EIA-930 files and rebuild results with ba-forecast-scorecard")
    a = ap.parse_args()
    if a.rebuild:
        from ba_scorecard.data import build_tidy, load_tidy, periods_between
        from ba_scorecard.scorecard import build

        root = HERE / "data"
        build_tidy(periods_between("2015H2", "2026H1"), root / "raw", root / "tidy")
        build(load_tidy(root / "tidy"), root / "results")
        a.results = root / "results"
    FIG.mkdir(exist_ok=True)
    d = load(a.results)
    eligible = list(d["ranking"]["ba"])
    figs = [fig_ranking(d["ranking"]), fig_yearly_major(d["yearly"]), fig_peak_bias(d["yearly"], eligible), fig_events(d["events"], eligible)]
    render_readme(d, figs)
    print("wrote", [f.name for f in figs], "and README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
