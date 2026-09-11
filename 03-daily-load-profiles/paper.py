"""Build the IEEE-format paper for Note 2 from the results written by analysis.py.

Writes paper/figures/*.pdf with the IEEE matplotlib style, fills paper/paper.template.tex into
paper/paper.tex, copies the shared bibliography, and (optionally) runs pdflatex + bibtex.

Usage
-----
python analysis.py --tidy ../../ba-forecast-scorecard/data/tidy   # first
python paper.py [--build]
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

from analysis import MODELS, WEEKDAYS  # noqa: E402

HERE = Path(__file__).parent
RES = HERE / "results"
PAPER = HERE / "paper"
FIG = PAPER / "figures"
STYLE = HERE.parent / "_template-ieee" / "ieee.mplstyle"
BIB = HERE.parent / "_template-ieee" / "references.bib"
NAVY, RED, GRAY, TEAL, ORANGE = "#1F3A5F", "#CC2000", "#9CA3AF", "#46B2B4", "#E69F00"
COL, TWO = 3.5, 7.16
H = [f"h{h:02d}" for h in range(1, 25)]


def pc(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}\\%"


def tex(s: str) -> str:
    return str(s).replace("&", "\\&").replace("%", "\\%").replace("'", "'")


def fig_models(summary: pd.DataFrame) -> None:
    cols = [f"{m}_w8_mean" for m in MODELS]
    fig, ax = plt.subplots(figsize=(COL, 2.3))
    data = [summary[c].to_numpy() for c in cols]
    ax.boxplot(data, labels=list(MODELS), widths=0.5, showfliers=False,
               medianprops={"color": RED, "lw": 1}, boxprops={"lw": 0.6}, whiskerprops={"lw": 0.6}, capprops={"lw": 0.6})
    rng = np.random.default_rng(0)
    for i, v in enumerate(data):
        ax.scatter(i + 1 + rng.normal(0, 0.05, len(v)), v, s=3, color=NAVY, alpha=0.5, lw=0)
    ax.set_ylabel("daily shape MAPE, %")
    ax.set_xticklabels(["G1", "G2", "G3", "G5", "G7"])
    ax.grid(axis="x", visible=False)
    fig.savefig(FIG / "fig1_models.pdf")
    plt.close(fig)


def fig_distinctness(dist: pd.DataFrame) -> None:
    pairs = ["Mon-Tue", "Tue-Wed", "Wed-Thu", "Thu-Fri", "Mon-Fri", "Fri-Sat", "Sat-Sun", "Mon-Sun", "Wed-Sat", "Wed-Sun"]
    piv = dist.pivot(index="ba", columns="pair", values="index").reindex(columns=pairs).sort_values("Wed-Sun")
    fig, ax = plt.subplots(figsize=(COL, 4.6))
    im = ax.imshow(piv.to_numpy(), aspect="auto", cmap="RdYlBu_r", vmin=0, vmax=2.5)
    ax.set_xticks(range(len(pairs)))
    ax.set_xticklabels(pairs, rotation=90, fontsize=6)
    ax.set_yticks(range(len(piv)))
    ax.set_yticklabels(piv.index, fontsize=4.5)
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label("distinctness index", fontsize=7)
    cb.ax.tick_params(labelsize=6)
    fig.savefig(FIG / "fig2_distinctness.pdf")
    plt.close(fig)


def fig_window(summary: pd.DataFrame, weeks: tuple[int, ...]) -> None:
    fig, ax = plt.subplots(figsize=(COL, 2.2))
    for m, color, label in (("G1", GRAY, "G1 one profile"), ("G3", NAVY, "G3 day type"), ("G7", RED, "G7 weekday")):
        ax.plot(weeks, [summary[f"{m}_w{w}_mean"].mean() for w in weeks], marker="o", color=color, label=label)
    ax.set_xlabel("reference window, weeks")
    ax.set_ylabel("daily shape MAPE, %")
    ax.set_xticks(weeks)
    ax.legend(loc="upper left")
    fig.savefig(FIG / "fig3_window.pdf")
    plt.close(fig)


def fig_regime(sh: pd.DataFrame, tR: pd.DataFrame, tRp: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(TWO, 3.0), gridspec_kw={"width_ratios": [1, 1.3]})
    ax = axes[0]
    for ba, color in (("FPC", RED), ("SOCO", ORANGE), ("PJM", NAVY), ("ERCO", TEAL), ("CISO", GRAY)):
        g = sh[sh["ba"] == ba]
        m = g.groupby("month")["regime"].mean() * 100
        ax.plot(m.index, m.to_numpy(), marker="o", color=color, label=ba)
    ax.set_xlabel("month")
    ax.set_ylabel("morning-peak days, %")
    ax.set_xticks(range(1, 13))
    ax.legend(ncol=2)
    ax = axes[1]
    t = tR.set_index("ba")["gain_rel_pct"].sort_values()
    tp = tRp.set_index("ba")["gain_rel_pct"].reindex(t.index)
    y = np.arange(len(t))
    ax.barh(y + 0.2, t.to_numpy(), height=0.4, color=RED, label="own regime (oracle)")
    ax.barh(y - 0.2, tp.to_numpy(), height=0.4, color=NAVY, label="previous-day regime")
    ax.set_yticks(y)
    ax.set_yticklabels(t.index, fontsize=3.8)
    ax.axvline(0, color=GRAY, lw=0.6)
    ax.set_xlabel("relative reduction of shape MAPE, %")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", alpha=0.25)
    ax.legend(loc="lower right")
    fig.savefig(FIG / "fig4_regime.pdf")
    plt.close(fig)


def fig_superbowl(sb: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(COL, 2.2))
    for off, color, label in ((5.0, NAVY, "Eastern"), (6.0, TEAL, "Central"), (7.0, ORANGE, "Mountain"), (8.0, RED, "Pacific")):
        sel = sb[np.isclose(sb["offset_h"], off)]
        if len(sel) < 10:
            continue
        ax.plot(range(1, 25), sel[H].median(), color=color, label=f"{label}, n={len(sel)}")
    ax.axhline(0, color=GRAY, lw=0.6)
    ax.set_xlabel("local hour ending")
    ax.set_ylabel("residual, % of daily mean")
    ax.legend(ncol=2, loc="lower left")
    fig.savefig(FIG / "fig5_superbowl.pdf")
    plt.close(fig)


def fig_examples(sh: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(COL, 2.2), sharey=True)
    cmap = plt.get_cmap("viridis", 7)
    normal = sh[~sh["is_special"]]
    for ax, ba in zip(axes, ("PJM", "ERCO", "CISO")):
        g = normal[normal["ba"] == ba]
        for w in range(7):
            ax.plot(range(1, 25), np.median(g.loc[g["weekday"] == w, H].to_numpy(), axis=0), color=cmap(w),
                    lw=0.9 if w >= 5 else 0.6, label=WEEKDAYS[w])
        xm = sh[(sh["ba"] == ba) & (sh["special"].isin(["Thanksgiving", "Christmas Day"]))]
        ax.plot(range(1, 25), np.median(xm[H].to_numpy(), axis=0), color=RED, lw=0.9, ls="--", label="Thanksg./Christmas")
        ax.set_title(ba, fontsize=7)
        ax.set_xticks([6, 12, 18, 24])
        ax.tick_params(labelsize=6)
    axes[0].set_ylabel("demand / daily mean", fontsize=7)
    handles, labels = axes[2].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=8, fontsize=5, loc="lower center", bbox_to_anchor=(0.5, -0.02), handlelength=1.2,
               columnspacing=0.8, frameon=False)
    fig.subplots_adjust(bottom=0.3)
    fig.savefig(FIG / "fig6_examples.pdf")
    plt.close(fig)


def fig_temperature(sh: pd.DataFrame, tT: pd.DataFrame, tR: pd.DataFrame, tTp: pd.DataFrame, t_heat: float) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(TWO, 3.0), gridspec_kw={"width_ratios": [1, 1.3]})
    ax = axes[0]
    d = sh.dropna(subset=["tmean_c"])
    bins = np.arange(-15, 36, 2.5)
    for ba, color in (("FPC", RED), ("SOCO", ORANGE), ("PJM", NAVY), ("ERCO", TEAL), ("CISO", GRAY)):
        g = d[d["ba"] == ba]
        m = g.groupby(pd.cut(g["tmean_c"], bins), observed=True)["regime"].agg(["mean", "size"])
        m = m[m["size"] >= 15]
        ax.plot([iv.mid for iv in m.index], m["mean"] * 100, marker="o", color=color, label=ba)
    ax.axvline(t_heat, color=RED, ls="--", lw=0.6)
    ax.set_xlabel("daily mean temperature, $^\\circ$C")
    ax.set_ylabel("morning-peak days, %")
    ax.legend(ncol=2)
    ax = axes[1]
    t = tT.set_index("ba")["gain_rel_pct"].sort_values()
    r = tR.set_index("ba")["gain_rel_pct"].reindex(t.index)
    p = tTp.set_index("ba")["gain_rel_pct"].reindex(t.index)
    y = np.arange(len(t))
    ax.barh(y + 0.27, t.to_numpy(), height=0.27, color=RED, label="temperature, same day")
    ax.barh(y, r.to_numpy(), height=0.27, color=GRAY, label="peak hour, same day")
    ax.barh(y - 0.27, p.to_numpy(), height=0.27, color=NAVY, label="temperature, previous day")
    ax.set_yticks(y)
    ax.set_yticklabels(t.index, fontsize=3.8)
    ax.axvline(0, color=GRAY, lw=0.6)
    ax.set_xlabel("relative reduction of shape MAPE, %")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", alpha=0.25)
    ax.legend(loc="lower right")
    fig.savefig(FIG / "fig7_temperature.pdf")
    plt.close(fig)


def render() -> Path:
    from analysis import SWEEP_WEEKS, add_calendar, eligible

    s = json.loads((RES / "summary.json").read_text(encoding="utf-8"))
    summary = pd.read_csv(RES / "model_errors_by_ba.csv")
    dist = pd.read_csv(RES / "weekday_distinctness.csv")
    tR = pd.read_csv(RES / "g3r_vs_g3.csv")
    tRp = pd.read_csv(RES / "g3rprev_vs_g3.csv")
    tA = pd.read_csv(RES / "r2a1_vs_g3_w2.csv")
    hol = pd.read_csv(RES / "holidays_summary.csv", index_col=0)
    coh = pd.read_csv(RES / "discovered_coherent_dates.csv", index_col=0)
    sb = pd.read_csv(RES / "superbowl_residual.csv")
    tT = pd.read_csv(RES / "g3t_vs_g3.csv")
    tTp = pd.read_csv(RES / "g3tprev_vs_g3.csv")
    stations = pd.read_csv(RES / "weather_stations.csv")
    from weather import BA_STATION
    sh = pd.read_parquet(RES / "daily_shapes.parquet")
    sh["date"] = pd.to_datetime(sh["date"]).dt.date
    sh = eligible(add_calendar(sh))

    FIG.mkdir(parents=True, exist_ok=True)
    plt.style.use(str(STYLE))
    fig_models(summary)
    fig_distinctness(dist)
    fig_window(summary, SWEEP_WEEKS)
    fig_regime(sh, tR, tRp)
    fig_superbowl(sb)
    fig_examples(sh)
    fig_temperature(sh, tT, tR, tTp, s['temperature']['t_heat_c'])

    first, last = pd.Timestamp(s["first_date"]), pd.Timestamp(s["last_date"])
    w = s["window_sensitivity"]
    d = s["distinctness_median_index"]
    r7, ro, rp, se, hy = s["g7_vs_g3"], s["regime_oracle_vs_g3"], s["regime_prevday_vs_g3"], s["seasonal"], s["hybrid_offset"]
    gm = {int(k): float(v) for k, v in se["gain_by_month_pp"].items()}
    build_stats = json.loads((RES / "shape_build_stats.json").read_text())

    desc = {"G1": "one group, 8 weeks", "G2": "week / weekend, 8 weeks", "G3": "workday / Sat. / Sun., 8 weeks",
            "G5": "Mon. / Tue.--Thu. / Fri. / Sat. / Sun., 8 weeks", "G7": "one per weekday, 8 weeks"}
    model_rows = "\n".join(f"{m} & {desc[m]} & {pc(s['model_mean_mape'][m], 2)} \\\\" for m in MODELS)

    season_rows = "\n".join([
        f"R2 & workday/Sat./Sun., prev.\\ 2 wk & {pc(se['means']['G3_w2'], 2)} & -- \\\\",
        f"S4 & season $\\times$ day type, prev.\\ 52 wk & {pc(se['means']['S4_w52'], 2)} & "
        f"${se['S4_vs_G3_w2']['mean_gain_rel_pct']:+.1f}$\\% ({s['bas_eligible'] - se['S4_vs_G3_w2']['bas_ci_below_zero']}/{se['S4_vs_G3_w2']['bas_ci_below_zero']}) \\\\",
        f"A1 & analogs $\\pm 21$ d, prev.\\ year & {pc(se['means']['A1'], 2)} & -- \\\\",
        f"R2+A1 & R2 $\\cup$ A1 & {pc(se['means']['R2A1'], 2)} & ${se['R2A1_vs_G3_w2']['mean_gain_rel_pct']:+.1f}$\\% ({se['R2A1_vs_G3_w2']['bas_ci_above_zero']}/{se['R2A1_vs_G3_w2']['bas_ci_below_zero']}) \\\\",
        f"R2+A2 & R2 $\\cup$ two years of analogs & {pc(se['means']['R2A2'], 2)} & ${se['R2A2_vs_G3_w2']['mean_gain_rel_pct']:+.1f}$\\% \\\\",
    ])

    order = ["Thanksgiving", "Christmas Day", "Christmas Eve", "New Year's Eve", "Day after Thanksgiving", "New Year's Day",
             "Memorial Day", "Labor Day", "Independence Day", "Juneteenth", "Super Bowl Sunday",
             "MLK Day", "Presidents' Day", "Columbus Day", "Veterans Day"]
    hrows = []
    for k in order:
        if k not in hol.index:
            continue
        r = hol.loc[k]
        shares = {"Sun.": r["share_sun"], "Sat.": r["share_sat"], "own": r["share_own"]}
        best = max(shares, key=shares.get)
        own = "--" if k == "Super Bowl Sunday" else pc(r["err_own"])
        hrows.append(f"{tex(k)} & {int(r['n'])} & {own} & {pc(r['err_sat'])} & {pc(r['err_sun'])} & {best} ({shares[best]*100:.0f}\\%) \\\\")
    holiday_rows = "\n".join(hrows)

    top = coh.head(12)
    date_rows = "\n".join(
        f"{pd.Timestamp(dt).strftime('%d %b %Y')} & {WEEKDAYS[pd.Timestamp(dt).weekday()]} & {pc(r['median_err'])} & "
        f"{tex(r['label']) if isinstance(r['label'], str) and r['label'] else '--'} \\\\"
        for dt, r in top.iterrows()
    )
    tg_rank = next((i + 1 for i, (dt, r) in enumerate(coh.iterrows()) if isinstance(r["label"], str) and r["label"] == "Thanksgiving"), None)

    tx = s["temperature"]
    bc = tx["best_config"]
    regime_rows = "\n".join([
        f"G3 & none & {pc(tx['means']['G3_w8'], 2)} & -- & -- \\\\",
        f"G3R & peak hour, same day & {pc(tx['means']['G3R_w8'], 2)} & {pc(s['regime_oracle_vs_g3']['mean_gain_rel_pct'])} & {int((tR['ci_lo'] > 0).sum())} \\\\",
        f"G3Rprev & peak hour, previous day & {pc(tx['means']['G3Rprev_w8'], 2)} & {pc(s['regime_prevday_vs_g3']['mean_gain_rel_pct'])} & {int((tRp['ci_lo'] > 0).sum())} \\\\",
        f"G3T & temp., 2 classes, same day & {pc(tx['means']['G3T_w8'], 2)} & {pc(tx['G3T_vs_G3']['mean_gain_rel_pct'])} & {tx['G3T_vs_G3']['bas_ci_above_zero']} \\\\",
        f"G3T3 & temp., 3 classes, same day & {pc(tx['means']['G3T3_w8'], 2)} & {pc(tx['G3T3_vs_G3']['mean_gain_rel_pct'])} & {tx['G3T3_vs_G3']['bas_ci_above_zero']} \\\\",
        f"G3Tprev & temp., 2 classes, prev.\\ day & {pc(tx['means']['G3Tprev_w8'], 2)} & {pc(tx['G3Tprev_vs_G3']['mean_gain_rel_pct'])} & {tx['G3Tprev_vs_G3']['bas_ci_above_zero']} \\\\",
        f"G3T3prev & temp., 3 classes, prev.\\ day & {pc(tx['means']['G3T3prev_w8'], 2)} & {pc(tx['G3T3prev_vs_G3']['mean_gain_rel_pct'])} & {tx['G3T3prev_vs_G3']['bas_ci_above_zero']} \\\\",
    ])
    icao_name = dict(zip(stations["ICAO"], stations["STATION NAME"].str.title()))
    st_items = [f"{ba} & {BA_STATION[ba]}" for ba in sorted(BA_STATION) if ba in set(summary["ba"])]
    while len(st_items) % 3:
        st_items.append(" & ")
    third = len(st_items) // 3
    station_rows = "\n".join(f"{st_items[i]} & {st_items[i + third]} & {st_items[i + 2 * third]} \\\\" for i in range(third))
    del icao_name
    worst = tA.sort_values("gain_rel_pct").query("ci_hi < 0")["ba"].tolist()
    analog_worst = worst[0] if len(worst) == 1 else ", ".join(worst[:-1]) + " and " + worst[-1]
    two = s["two_cluster_bas"]
    fields = {
        "doi_line": "Draft, not yet published",
        "n_bas": str(s["bas_eligible"]), "n_files": str(build_stats["bas_in_files"]),
        "ba_days": f"{s['ba_days']:,}", "dropped": f"{build_stats['days_dropped_shape_filter']:,}",
        "first_prose": f"{first.day} {first.strftime('%B %Y')}", "last_prose": f"{last.day} {last.strftime('%B %Y')}",
        "first_month": first.strftime("%B %Y"), "last_month": last.strftime("%B %Y"),
        "special_share": pc(s["special_days_share"] * 100),
        "g7_loss": pc(-r7["mean_gain_rel_pct"]), "g5_loss": pc(-s["g5_vs_g3"]["mean_gain_rel_pct"]),
        "ci_below": str(r7["bas_ci_below_zero"]),
        "idx_tue_wed": f"{d['Tue-Wed']:.2f}", "idx_mon_thu": f"{d['Mon-Thu']:.2f}", "idx_thu_fri": f"{d['Thu-Fri']:.2f}",
        "idx_wed_sun": f"{d['Wed-Sun']:.2f}",
        "n_one_cluster": str(s["bas_eligible"] - len(two)), "n_two_clusters": str(len(two)),
        "two_cluster_bas": ", ".join(two),
        "hyb_mon": f"{hy['vs_G3_w3']['gain_by_weekday_pp']['Mon']:.2f}", "hyb_fri": f"{hy['vs_G3_w3']['gain_by_weekday_pp']['Fri']:.2f}",
        "hyb_gain": f"{hy['vs_G3_w3']['mean_gain_rel_pct']:+.1f}\\%",
        "g3_w2": pc(w["G3_w2"], 2), "g3_w16": pc(w["G3_w16"], 2), "g1_w3": pc(w["G1_w3"], 2), "g3_w6": pc(w["G3_w6"], 2),
        "best_weeks": str(s["best_model_window"][1]), "best_mape": pc(min(w.values()), 2),
        "s4_loss": pc(-se["S4_vs_G3_w2"]["mean_gain_rel_pct"], 0), "s4_below": str(se["S4_vs_G3_w2"]["bas_ci_below_zero"]),
        "a1": pc(se["means"]["A1"], 2), "g3_w2_seas": pc(se["means"]["G3_w2"], 2), "r2a1": pc(se["means"]["R2A1"], 2),
        "r2a1_gain": pc(se["R2A1_vs_G3_w2"]["mean_gain_rel_pct"]), "r2a1_up": str(se["R2A1_vs_G3_w2"]["bas_ci_above_zero"]),
        "r2a1_need": str(se["R2A1_vs_G3_w2"]["bas_needing"]), "r2a2_gain": pc(se["R2A2_vs_G3_w2"]["mean_gain_rel_pct"]),
        "gain_spring": f"{np.mean([gm[m] for m in (3, 4, 5, 6)]):.2f}", "gain_other": f"{np.mean([gm[m] for m in (1, 2, 7, 8, 9, 10, 11, 12)]):.2f}",
        "analog_worst": analog_worst,
        "regime_oracle": pc(ro["mean_gain_rel_pct"]), "regime_oracle_n": str(ro["bas_needing"]),
        "regime_top_gain": pc(ro["top"][0]["gain_rel_pct"], 0), "regime_top_ba": ro["top"][0]["ba"],
        "regime_prev": pc(rp["mean_gain_rel_pct"]), "regime_prev_n": str(rp["bas_needing"]),
        "tg_rank": str(tg_rank) if tg_rank else "beyond 25",
        "sb_sat_share": pc(s["sb_sat_share"] * 100, 0),
        "model_rows": model_rows, "season_rows": season_rows, "holiday_rows": holiday_rows, "date_rows": date_rows,
        "regime_rows": regime_rows, "station_rows": station_rows,
        "t_heat": f"{tx['t_heat_c']:.0f}", "t_cool": f"{tx['t_cool_c']:.0f}", "t_agree": pc(tx["regime_agreement_with_peak_hour"] * 100, 0),
        "g3t_gain": pc(tx["G3T_vs_G3"]["mean_gain_rel_pct"]), "g3t_up": str(tx["G3T_vs_G3"]["bas_ci_above_zero"]),
        "g3t3_gain": pc(tx["G3T3_vs_G3"]["mean_gain_rel_pct"]), "g3t3_need": str(tx["G3T3_vs_G3"]["bas_needing"]),
        "g3tprev_gain": pc(tx["G3Tprev_vs_G3"]["mean_gain_rel_pct"]), "g3t3prev_gain": pc(tx["G3T3prev_vs_G3"]["mean_gain_rel_pct"]),
        "cfg_mape": pc(bc["means"]["BEST"], 2), "best_base": pc(bc["means"]["G3_w2"], 2),
        "best_gain": pc(bc["BEST_vs_G3_w2"]["mean_gain_rel_pct"]), "best_up": str(bc["BEST_vs_G3_w2"]["bas_ci_above_zero"]),
        "bestprev_mape": pc(bc["means"]["BESTprev"], 2),
    }
    tpl = (PAPER / "paper.template.tex").read_text(encoding="utf-8")
    for k, v in fields.items():
        tpl = tpl.replace(f"<<{k}>>", v)
    assert "<<" not in tpl, "unfilled placeholder: " + tpl[tpl.index("<<"):tpl.index("<<") + 30]
    out = PAPER / "paper.tex"
    out.write_text(tpl, encoding="utf-8")
    shutil.copy(BIB, PAPER / "references.bib")
    return out


def build() -> None:
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
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    out = render()
    print("wrote", out)
    if a.build:
        build()
        print("built", PAPER / "paper.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
