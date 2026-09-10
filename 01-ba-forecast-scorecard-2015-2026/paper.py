"""Build the IEEE-format paper for Note 1 from the scorer's results.

Writes paper/figures/*.pdf with the IEEE matplotlib style, fills paper/paper.template.tex into
paper/paper.tex, copies the shared bibliography, and (optionally) runs pdflatex + bibtex.

Usage
-----
python paper.py --results ../../ba-forecast-scorecard/results [--build]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).parent
PAPER = HERE / "paper"
FIG = PAPER / "figures"
STYLE = HERE.parent / "_template-ieee" / "ieee.mplstyle"
BIB = HERE.parent / "_template-ieee" / "references.bib"
NAVY, RED, GRAY = "#1F3A5F", "#CC2000", "#9CA3AF"
MAJOR = ["PJM", "MISO", "ERCO", "SWPP", "CISO", "NYIS", "ISNE", "TVA", "SOCO", "DUK", "FPL", "BPAT", "PACE", "AZPS"]
COL, TWO = 3.5, 7.16  # inches


def pct(x, nd=1):
    return f"{x * 100:.{nd}f}\\%"


def fig_ranking(rk: pd.DataFrame):
    r = rk.sort_values("mape", ascending=True).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(TWO, 2.6))
    colors = [NAVY if b in MAJOR else GRAY for b in r["ba"]]
    ax.bar(np.arange(len(r)), r["mape"] * 100, color=colors, width=0.75)
    ax.axhline(rk["mape"].median() * 100, color=RED, ls="--", lw=0.8)
    ax.set_xticks(np.arange(len(r)))
    ax.set_xticklabels(r["ba"], rotation=90, fontsize=6)
    ax.set_ylabel("MAPE, %")
    ax.grid(axis="x", visible=False)
    fig.savefig(FIG / "fig1_ranking.pdf")
    plt.close(fig)


def fig_yearly(yearly: pd.DataFrame):
    y = yearly[yearly["ba"].isin(MAJOR)]
    fig, ax = plt.subplots(figsize=(COL, 2.6))
    for ba, g in y.groupby("ba"):
        g = g.sort_values("year")
        ax.plot(g["year"], g["mape"] * 100, marker="o", lw=0.8, ms=2, label=ba)
    yrs = sorted(y["year"].unique())
    ax.set_xticks(yrs)
    ax.set_xticklabels([f"{v}*" if v == max(yrs) else str(v)[2:] for v in yrs], fontsize=6)
    ax.set_ylabel("MAPE, %")
    ax.legend(ncol=5, fontsize=5, loc="upper center", bbox_to_anchor=(0.5, -0.18), handlelength=1.2, columnspacing=0.8)
    fig.savefig(FIG / "fig2_yearly_major.pdf")
    plt.close(fig)


def fig_peak(yearly: pd.DataFrame, eligible: list[str]):
    y = yearly[yearly["ba"].isin(eligible)]
    agg = y.groupby("year").apply(lambda g: np.average(g["under_forecast_day_share"], weights=g["days"])).reset_index(name="share")
    fig, ax = plt.subplots(figsize=(COL, 2.0))
    ax.bar(agg["year"], agg["share"] * 100, color=NAVY, width=0.7)
    ax.axhline(50, color=RED, ls="--", lw=0.8)
    ax.set_xticks(agg["year"])
    ax.set_xticklabels([f"{v}*" if v == agg["year"].max() else str(v)[2:] for v in agg["year"]], fontsize=6)
    ax.set_ylabel("% of BA-days")
    ax.set_ylim(0, 75)
    fig.savefig(FIG / "fig3_peak_under_forecast_share.pdf")
    plt.close(fig)


def fig_events(events: pd.DataFrame, eligible: list[str]):
    ev = events.dropna(subset=["worst_under_forecast_pct"]).copy()
    ev = ev[ev["ba"].isin(eligible)]
    order = ["uri_2021", "heat_dome_2021", "elliott_2022", "heat_wave_2023", "arctic_2024", "cold_jan_2025"]
    labels = {"uri_2021": "Uri\n2021", "heat_dome_2021": "Heat dome\n2021", "elliott_2022": "Elliott\n2022",
              "heat_wave_2023": "Heat wave\n2023", "arctic_2024": "Arctic\n2024", "cold_jan_2025": "Cold\n2025"}
    present = [o for o in order if o in set(ev["event_id"])]
    groups = [np.clip(-ev[ev["event_id"] == o]["worst_under_forecast_pct"].values * 100, 0, None) for o in present]
    fig, ax = plt.subplots(figsize=(COL, 2.2))
    ax.boxplot(groups, labels=[labels[o] for o in present], widths=0.5,
               medianprops={"color": RED, "lw": 1}, boxprops={"lw": 0.6}, whiskerprops={"lw": 0.6}, capprops={"lw": 0.6},
               flierprops={"marker": "o", "ms": 2, "lw": 0.5})
    ax.set_ylabel("worst under-forecast at peak, %")
    ax.tick_params(axis="x", labelsize=6)
    fig.savefig(FIG / "fig4_events.pdf")
    plt.close(fig)


def render(results: Path) -> Path:
    s = json.loads((results / "summary.json").read_text(encoding="utf-8"))
    rk = pd.read_csv(results / "ranking_overall.csv")
    yearly = pd.read_csv(results / "ba_yearly.csv")
    events = pd.read_csv(results / "events_by_ba.csv")
    eligible = list(rk["ba"])

    FIG.mkdir(parents=True, exist_ok=True)
    plt.style.use(str(STYLE))
    fig_ranking(rk)
    fig_yearly(yearly)
    fig_peak(yearly, eligible)
    fig_events(events, eligible)

    major = rk[rk["ba"].isin(MAJOR)]
    major_rows = "\n".join(
        f"{int(r['rank'])} & {r['ba']} & {r['region']} & {pct(r['mape'], 2)} & {pct(r['bias_pct'], 2)} & "
        f"{pct(r['peak_hour_abs_pct_error_mean'], 2)} & $-${pct(-r['p99_under_forecast_pct'])} \\\\"
        for _, r in major.iterrows()
    )
    short = {"uri_2021": "Winter Storm Uri (Feb.\ 2021)", "heat_dome_2021": "Pacific NW heat dome (June 2021)",
             "elliott_2022": "Winter Storm Elliott (Dec.\ 2022)", "heat_wave_2023": "Heat wave (Jul.--Aug.\ 2023)",
             "arctic_2024": "Arctic storms (Jan.\ 2024)", "cold_jan_2025": "Cold wave (Jan.\ 2025)"}
    ev = events[events["ba"].isin(eligible)].sort_values("worst_under_forecast_pct").groupby("event_id").head(1)
    ev = ev.assign(event_name=ev["event_id"].map(short).fillna(ev["event_name"]))
    def tex_escape(text: str) -> str:
        return text.replace("&", "\\&").replace("%", "\\%")

    event_rows = "\n".join(
        f"{tex_escape(r['event_name'])} & {r['ba']} ({r['region']}) & {pct(-r['worst_under_forecast_pct'])} \\\\"
        for _, r in ev.iterrows()
    )
    w = s["worst_single_day_under_forecast_at_peak_eligible"]
    mm = s["excluded_for_series_mismatch"]
    first = pd.Timestamp(s["first_date"]); last = pd.Timestamp(s["last_date"])
    last_year_full = last.month == 12 and last.day == 31
    partial = "" if last_year_full else f"The {last.year} value covers January to {last.strftime('%B')}."
    imputed_share = s["share_of_scored_hours_imputed"]
    imputed = pct(imputed_share, 3) if imputed_share >= 0.0005 else "less than 0.001\%"
    mismatch = ", ".join(f"{m['ba']} (median bias {m['median_daily_bias_pct'] * 100:+.0f}\\%)" for m in mm) or "none"
    fields = {
        "generated": s["generated_at_utc"][:10],
        "first_date": s["first_date"], "last_date": s["last_date"],
        "first_prose": f"{first.day} {first.strftime('%B %Y')}",
        "last_prose": f"{last.day} {last.strftime('%B %Y')}",
        "first_month": first.strftime("%B %Y"), "last_month": last.strftime("%B %Y"),
        "partial_year_note": partial,
        "n_total": str(s["balancing_authorities_total"]), "n_scored": str(s["balancing_authorities_scored"]),
        "n_eligible": str(s["eligible_balancing_authorities"]),
        "ba_days": f"{s['ba_days_scored']:,}", "hours": f"{s['hours_scored']:,}",
        "dw_mape": pct(s["demand_weighted_mape_eligible"], 2), "med_mape": pct(s["median_ba_mape_eligible"], 2),
        "under_share": pct(s["share_of_ba_days_under_forecast_at_peak_eligible"], 0),
        "p99": pct(-s["p99_under_forecast_at_peak_eligible"]),
        "implausible": f"{s['hours_flagged_implausible']:,}",
        "imputed": imputed,
        "mismatch": mismatch,
        "top": ", ".join(f"{r['ba']} ({pct(r['mape'])})" for r in s["ranking_overall_top5"]),
        "bottom": ", ".join(f"{r['ba']} ({pct(r['mape'])})" for r in s["ranking_overall_bottom5"]),
        "worst_ba": w["ba"], "worst_date": w["date"], "worst_pct": pct(-w["peak_hour_pct_error"], 0),
        "worst_mw": f"{w['peak_demand_mw']:,.0f}",
        "major_rows": major_rows, "event_rows": event_rows,
    }
    tpl = (PAPER / "paper.template.tex").read_text(encoding="utf-8")
    for k, v in fields.items():
        tpl = tpl.replace(f"<<{k}>>", v)
    assert "<<" not in tpl, "unfilled placeholder"
    out = PAPER / "paper.tex"
    out.write_text(tpl, encoding="utf-8")
    shutil.copy(BIB, PAPER / "references.bib")
    return out


def build():
    for cmd in (["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "paper"], ["bibtex", "paper"],
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "paper"],
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "paper"]):
        r = subprocess.run(cmd, cwd=PAPER, capture_output=True, text=True)
        if r.returncode != 0 and cmd[0] == "pdflatex":
            print(r.stdout[-3000:])
            raise SystemExit(f"{cmd[0]} failed")
    for ext in ("aux", "bbl", "blg", "log", "out"):
        p = PAPER / f"paper.{ext}"
        if p.exists():
            p.unlink()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=Path("../../ba-forecast-scorecard/results"))
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    out = render(a.results)
    print("wrote", out)
    if a.build:
        build()
        print("built", PAPER / "paper.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
