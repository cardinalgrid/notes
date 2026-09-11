"""Daily load profiles of U.S. balancing authorities: seven weekday profiles, three day-type profiles,
or fewer? And which days are special?

Reads the tidy EIA-930 parquet files produced by ba-forecast-scorecard, builds one normalised daily
shape (24 values, demand divided by the day's mean, local time) per BA-day, and compares causal
profile models that differ only in how days are grouped. Writes results/*.csv, results/summary.json
and figures/*.png.

Usage
-----
python analysis.py --tidy ../../ba-forecast-scorecard/data/tidy            # full run
python analysis.py --tidy ... --stage shapes                                # only rebuild the shape cache
"""

from __future__ import annotations

import argparse
import json
import re
import warnings

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.cluster.hierarchy import fcluster, linkage  # noqa: E402
from scipy.spatial.distance import squareform  # noqa: E402

from calendar_us import special_calendar  # noqa: E402

HERE = Path(__file__).parent
RES = HERE / "results"
FIG = HERE / "figures"
NAVY, RED, GRAY, TEAL, ORANGE = "#1F3A5F", "#CC2000", "#6B7280", "#46B2B4", "#E08A1E"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MODELS = {
    "G1": lambda wd: 0,
    "G2": lambda wd: 0 if wd < 5 else 1,
    "G3": lambda wd: 0 if wd < 5 else wd,
    "G5": lambda wd: {0: 0, 1: 1, 2: 1, 3: 1, 4: 2, 5: 3, 6: 4}[wd],
    "G7": lambda wd: wd,
}
WINDOW_WEEKS = 8
SEASONAL_COLS = ("G3_w2", "A1", "R2A1", "R2A2", "S4_w52")
T_HEAT_F = 59.0   # daily mean temperature (F) below which a day is a heating day; best pooled threshold, see study notes
T_COOL_F = 72.0   # daily mean temperature (F) above which a day is a cooling day
T_HEAT_C = (T_HEAT_F - 32.0) * 5.0 / 9.0
T_COOL_C = (T_COOL_F - 32.0) * 5.0 / 9.0
WEATHER_COLS = ("G3_w8", "G3R_w8", "G3Rprev_w8", "G3T_w8", "G3T3_w8", "G3Tprev_w8", "G3T3prev_w8")
BEST_COLS = ("G3_w2", "R2A1", "G3T3_w2", "BEST", "BESTprev")
SWEEP_WEEKS = (2, 3, 4, 6, 8, 12, 16)
MIN_REF = 3
MIN_DAYS_PER_BA = 600
MIN_MW = 500.0
SHAPE_LO, SHAPE_HI = 0.2, 3.0
EXAMPLES = ["PJM", "ERCO", "CISO"]


# ----------------------------------------------------------------------------- stage 1: shapes
def build_shapes(tidy: Path) -> pd.DataFrame:
    frames = []
    for f in sorted(tidy.glob("*.parquet")):
        d = pd.read_parquet(f, columns=["ba", "date", "hour", "local_end", "utc_end", "demand"])
        d = d[d["demand"] > 0]
        d["date"] = pd.to_datetime(d["date"]).dt.date
        d["offset_h"] = (d["utc_end"].dt.tz_localize(None) - d["local_end"]).dt.total_seconds() / 3600.0
        frames.append(d[["ba", "date", "hour", "demand", "offset_h"]])
    raw = pd.concat(frames, ignore_index=True)
    del frames
    wide = raw.pivot_table(index=["ba", "date"], columns="hour", values="demand", aggfunc="mean")
    wide = wide.reindex(columns=range(1, 25))
    n_valid = wide.notna().sum(axis=1)
    wide = wide[n_valid >= 23]
    wide = wide.interpolate(axis=1, limit_direction="both")
    level = wide.mean(axis=1)
    shape = wide.div(level, axis=0)
    ok = (shape.min(axis=1) >= SHAPE_LO) & (shape.max(axis=1) <= SHAPE_HI)
    offsets = raw.groupby(["ba", "date"])["offset_h"].median()
    out = shape[ok].copy()
    out.columns = [f"h{h:02d}" for h in range(1, 25)]
    out["level_mw"] = level[ok]
    out["peak_hour"] = wide[ok].to_numpy().argmax(axis=1) + 1
    out["offset_h"] = offsets.reindex(out.index).to_numpy()
    out = out.reset_index()
    stats = {
        "days_with_23h_or_more": int((n_valid >= 23).sum()),
        "days_dropped_shape_filter": int((~ok).sum()),
        "bas_in_files": int(raw["ba"].nunique()),
    }
    return out, stats


def add_calendar(sh: pd.DataFrame) -> pd.DataFrame:
    cal = special_calendar(2015, 2026)
    dt = pd.to_datetime(sh["date"])
    sh["weekday"] = dt.dt.weekday
    sh["ordinal"] = dt.map(lambda x: x.toordinal())
    sh["special"] = sh["date"].map(lambda d: cal.get(d, ""))
    sh["is_special"] = sh["special"] != ""
    sh["year"] = dt.dt.year
    sh["month"] = dt.dt.month
    for m, fn in MODELS.items():
        sh[m] = sh["weekday"].map(fn)
    sh["S4"] = sh["G3"] * 4 + sh["month"].map(season_of)  # fixed season x day type
    sh["regime"] = (sh["peak_hour"] <= 12).astype(int)  # 1 = morning peak (heating day), 0 = afternoon/evening
    sh = sh.sort_values(["ba", "ordinal"]).reset_index(drop=True)
    prev = sh.groupby("ba")["regime"].shift(1)
    prev_ord = sh.groupby("ba")["ordinal"].shift(1)
    sh["regime_prev"] = np.where(prev_ord == sh["ordinal"] - 1, prev, np.nan)
    wx = RES / "daily_weather.parquet"
    if wx.exists():
        w = pd.read_parquet(wx)
        w["date"] = pd.to_datetime(w["date"]).dt.date
        sh = sh.merge(w[["ba", "date", "tmean_c", "tmin_c", "tmax_c"]], on=["ba", "date"], how="left")
    else:
        sh["tmean_c"] = np.nan
        sh["tmin_c"] = np.nan
        sh["tmax_c"] = np.nan
    sh = sh.sort_values(["ba", "ordinal"]).reset_index(drop=True)
    # temperature regimes: 2 classes (heating / not) and 3 classes (heating / mild / cooling)
    sh["tregime"] = np.where(sh["tmean_c"].isna(), np.nan, (sh["tmean_c"] < T_HEAT_C).astype(float))
    sh["tregime3"] = np.where(sh["tmean_c"].isna(), np.nan,
                              np.where(sh["tmean_c"] < T_HEAT_C, 0.0, np.where(sh["tmean_c"] > T_COOL_C, 2.0, 1.0)))
    tprev = sh.groupby("ba")["tregime"].shift(1)
    tprev_ord = sh.groupby("ba")["ordinal"].shift(1)
    sh["tregime_prev"] = np.where(tprev_ord == sh["ordinal"] - 1, tprev, np.nan)
    sh["G3T"] = np.where(sh["tregime"].isna(), np.nan, sh["G3"] * 2 + sh["tregime"])
    sh["G3T3"] = np.where(sh["tregime3"].isna(), np.nan, sh["G3"] * 3 + sh["tregime3"])
    sh["G3Tprev"] = np.where(sh["tregime_prev"].isna(), np.nan, sh["G3"] * 2 + sh["tregime_prev"])
    t3prev = sh.groupby("ba")["tregime3"].shift(1)
    sh["tregime3_prev"] = np.where(tprev_ord == sh["ordinal"] - 1, t3prev, np.nan)
    sh["G3T3prev"] = np.where(sh["tregime3_prev"].isna(), np.nan, sh["G3"] * 3 + sh["tregime3_prev"])
    sh["G3R"] = sh["G3"] * 2 + sh["regime"]              # oracle: the day's own regime
    sh["G3Rprev"] = sh["G3"] * 2 + sh["regime_prev"].fillna(sh["regime"])  # causal: yesterday's regime
    return sh


def eligible(sh: pd.DataFrame) -> pd.DataFrame:
    g = sh.groupby("ba").agg(days=("date", "size"), mw=("level_mw", "mean"))
    keep = g[(g["days"] >= MIN_DAYS_PER_BA) & (g["mw"] >= MIN_MW)].index
    return sh[sh["ba"].isin(keep)].reset_index(drop=True)


# ----------------------------------------------------------------------------- stage 2: profiles
def causal_profiles(ba: pd.DataFrame, group_col: str, weeks: int, target_groups: np.ndarray | None = None, ref_col: str | None = None,
                    min_ref: int = MIN_REF):
    """For each day, the hour-by-hour median shape of same-group, non-special days in the previous `weeks`.

    target_groups lets the caller ask for the profile of a *different* group than the day's own (used for
    holidays: 'what would Sunday look like this week?'). Returns (profiles [n,24] with NaN where < MIN_REF)."""
    H = [f"h{h:02d}" for h in range(1, 25)]
    shapes = ba[H].to_numpy()
    ords = ba["ordinal"].to_numpy()
    groups = ba[ref_col or group_col].to_numpy()
    special = ba["is_special"].to_numpy()
    tg = ba[group_col].to_numpy() if target_groups is None else target_groups
    out = np.full_like(shapes, np.nan)
    ref_idx = {}
    for gval in np.unique(np.concatenate([groups, tg])):
        sel = np.flatnonzero((groups == gval) & ~special)
        ref_idx[gval] = (ords[sel], shapes[sel])
    span = 7 * weeks
    for i in range(len(ba)):
        o_ref, s_ref = ref_idx.get(tg[i], (np.array([]), np.empty((0, 24))))
        lo = np.searchsorted(o_ref, ords[i] - span)
        hi = np.searchsorted(o_ref, ords[i])  # strictly before day i
        if hi - lo >= min_ref:
            out[i] = np.median(s_ref[lo:hi], axis=0)
    return out


def weekday_offsets(ba: pd.DataFrame, base: np.ndarray, actual: np.ndarray, weeks: int = 52, min_days: int = 10) -> np.ndarray:
    """Causal per-weekday offset: median over the previous `weeks` of the residual actual - base for
    non-special days of the same weekday. Adds a stable weekday signature to a recent day-type profile."""
    ords = ba["ordinal"].to_numpy()
    wd = ba["weekday"].to_numpy()
    special = ba["is_special"].to_numpy()
    resid = actual - base
    ok = ~np.isnan(resid).any(axis=1) & ~special
    out = np.zeros_like(base)
    idx = {w: np.flatnonzero((wd == w) & ok) for w in range(7)}
    span = 7 * weeks
    for i in range(len(ba)):
        sel = idx[wd[i]]
        o = ords[sel]
        lo = np.searchsorted(o, ords[i] - span)
        hi = np.searchsorted(o, ords[i])
        if hi - lo >= min_days:
            out[i] = np.median(resid[sel[lo:hi]], axis=0)
    return out


def season_of(month: int) -> int:
    return {12: 0, 1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3}[int(month)]


def analog_profiles(ba: pd.DataFrame, group_col: str = "G3", weeks_recent: int = 2, years: int = 1, half_days: int = 21,
                    min_ref: int = 2, ref_col: str | None = None) -> np.ndarray:
    """Median shape over the union of (a) same-group days in the previous `weeks_recent` weeks and (b) same-group
    days within +-`half_days` of the same calendar date in each of the previous `years` years. weeks_recent=0
    gives analogs only. Special days are never references."""
    H = [f"h{h:02d}" for h in range(1, 25)]
    shapes = ba[H].to_numpy()
    ords = ba["ordinal"].to_numpy()
    groups = ba[ref_col or group_col].to_numpy()
    targets = ba[group_col].to_numpy()
    special = ba["is_special"].to_numpy()
    out = np.full_like(shapes, np.nan)
    for i in range(len(ba)):
        m = np.zeros(len(ba), dtype=bool)
        if weeks_recent > 0:
            m |= (ords >= ords[i] - 7 * weeks_recent) & (ords < ords[i])
        for y in range(1, years + 1):
            c = ords[i] - int(round(365.25 * y))
            m |= (ords >= c - half_days) & (ords <= c + half_days)
        m &= (groups == targets[i]) & ~special
        if m.sum() >= min_ref:
            out[i] = np.median(shapes[m], axis=0)
    return out


def mape(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return 100.0 * np.nanmean(np.abs(a - b) / b, axis=1)


def evaluate(sh: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-day shape errors for every model (8-week window) and for G3/G7 at 4 and 12 weeks."""
    H = [f"h{h:02d}" for h in range(1, 25)]
    rows = []
    daily = []
    for ba, g in sh.groupby("ba", sort=True):
        g = g.sort_values("ordinal").reset_index(drop=True)
        actual = g[H].to_numpy()
        peak_actual = actual.argmax(axis=1)
        errs = {}
        for m in MODELS:
            prof = causal_profiles(g, m, WINDOW_WEEKS)
            e = mape(prof, actual)
            pe = np.abs(prof.argmax(axis=1) - peak_actual).astype(float)
            pe[np.isnan(e)] = np.nan
            errs[f"{m}_w8"] = e
            errs[f"{m}_w8_peakerr"] = pe
        errs["A1"] = mape(analog_profiles(g, weeks_recent=0, years=1), actual)
        errs["R2A1"] = mape(analog_profiles(g, weeks_recent=2, years=1), actual)
        errs["R2A2"] = mape(analog_profiles(g, weeks_recent=2, years=2), actual)
        errs["S4_w52"] = mape(causal_profiles(g, "S4", 52), actual)
        for w in (3, 8):
            base = causal_profiles(g, "G3", w)
            errs[f"G3off_w{w}"] = mape(base + weekday_offsets(g, base, actual), actual)
        if g["tmean_c"].notna().any():
            for m, ref in (("G3T", "G3T"), ("G3T3", "G3T3"), ("G3Tprev", "G3T"), ("G3T3prev", "G3T3")):
                prof = causal_profiles(g, m, WINDOW_WEEKS, ref_col=ref)
                prof[g[m].isna().to_numpy()] = np.nan
                errs[f"{m}_w8"] = mape(prof, actual)
            # recommended configuration: day type x 3-class temperature regime, last 2 weeks + last year analogs
            prof = causal_profiles(g, "G3T3", 2, min_ref=2)
            prof[g["G3T3"].isna().to_numpy()] = np.nan
            errs["G3T3_w2"] = mape(prof, actual)
            for name, col, ref in (("BEST", "G3T3", "G3T3"), ("BESTprev", "G3T3prev", "G3T3")):
                prof = analog_profiles(g, group_col=col, ref_col=ref, weeks_recent=2, years=1)
                prof[g[col].isna().to_numpy()] = np.nan
                errs[name] = mape(prof, actual)
        else:
            for m in ("G3T", "G3T3", "G3Tprev", "G3T3prev"):
                errs[f"{m}_w8"] = np.full(len(g), np.nan)
            for m in ("G3T3_w2", "BEST", "BESTprev"):
                errs[m] = np.full(len(g), np.nan)
        for m, ref in (("G3R", "G3R"), ("G3Rprev", "G3R")):
            prof = causal_profiles(g, m, WINDOW_WEEKS, ref_col=ref)
            errs[f"{m}_w8"] = mape(prof, actual)
        for m in ("G1", "G3", "G7"):
            for w in SWEEP_WEEKS:
                if w == WINDOW_WEEKS:
                    continue
                prof = causal_profiles(g, m, w, min_ref=2 if w == 2 else MIN_REF)
                errs[f"{m}_w{w}"] = mape(prof, actual)
        d = pd.DataFrame(errs)
        d.insert(0, "ba", ba)
        d.insert(1, "date", g["date"])
        d.insert(2, "weekday", g["weekday"])
        d.insert(3, "special", g["special"])
        d.insert(4, "month", g["month"])
        d.insert(5, "year", g["year"])
        daily.append(d)
    daily = pd.concat(daily, ignore_index=True)

    # per-BA summary on normal days evaluated by every model
    normal = daily[daily["special"] == ""]
    cols = [c for c in daily.columns if re.match(r"^G(?:[12357]|3off)_w\d+$", c)]  # calendar models, window sweep, hybrid
    complete = normal.dropna(subset=cols)
    for ba, g in complete.groupby("ba"):
        r = {"ba": ba, "days": len(g)}
        for c in cols:
            r[f"{c}_mean"] = g[c].mean()
            r[f"{c}_median"] = g[c].median()
        for m in MODELS:
            r[f"{m}_w8_peakerr_mean"] = g[f"{m}_w8_peakerr"].mean()
        gs = normal[normal["ba"] == ba].dropna(subset=SEASONAL_COLS)
        for c in SEASONAL_COLS:
            r[f"seas_{c}_mean"] = gs[c].mean()
        r["seasonal_days"] = len(gs)
        gw = normal[normal["ba"] == ba].dropna(subset=list(WEATHER_COLS))
        for c in WEATHER_COLS:
            r[f"wx_{c}_mean"] = gw[c].mean()
        r["weather_days"] = len(gw)
        gb = normal[normal["ba"] == ba].dropna(subset=list(BEST_COLS))
        for c in BEST_COLS:
            r[f"best_{c}_mean"] = gb[c].mean()
        r["best_days"] = len(gb)
        r["share_morning_peak"] = float(sh.loc[sh["ba"] == ba, "regime"].mean())
        r["regime_switches_per_year"] = float(sh.loc[sh["ba"] == ba, "regime"].diff().abs().sum() / max(len(g) / 365.25, 1))
        rows.append(r)
    summary = pd.DataFrame(rows)
    return daily, summary


def paired_tests(daily: pd.DataFrame, a: str = "G3_w8", b: str = "G7_w8", seed: int = 0) -> pd.DataFrame:
    """Bootstrap CI of the mean daily difference a - b (positive = b better) per BA, plus a sign test."""
    from scipy.stats import binomtest

    rng = np.random.default_rng(seed)
    rows = []
    normal = daily[daily["special"] == ""].dropna(subset=[a, b])
    for ba, g in normal.groupby("ba"):
        diff = (g[a] - g[b]).to_numpy()
        n = len(diff)
        boots = rng.choice(diff, size=(2000, n), replace=True).mean(axis=1)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        wins = int((diff > 0).sum())
        ties = int((diff == 0).sum())
        p = binomtest(wins, n - ties, 0.5).pvalue if n - ties > 0 else 1.0
        rel = diff.mean() / g[a].mean() * 100.0
        by_wd = {f"gain_{WEEKDAYS[w]}": float((g.loc[g["weekday"] == w, a] - g.loc[g["weekday"] == w, b]).mean()) for w in range(7)}
        rows.append(
            {
                "ba": ba,
                "days": n,
                f"{a}_mean": g[a].mean(),
                f"{b}_mean": g[b].mean(),
                "gain_pp": diff.mean(),
                "gain_rel_pct": rel,
                "ci_lo": lo,
                "ci_hi": hi,
                "share_days_b_better": wins / max(n - ties, 1),
                "sign_test_p": p,
                "needs_b": bool(lo > 0 and rel > 5.0),
                **by_wd,
            }
        )
    return pd.DataFrame(rows).sort_values("gain_rel_pct", ascending=False)


# ----------------------------------------------------------------------------- stage 3: distinctness
def weekday_distinctness(sh: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, np.ndarray]]:
    H = [f"h{h:02d}" for h in range(1, 25)]
    rows, clusters, profiles = [], [], {}
    normal = sh[~sh["is_special"]]
    for ba, g in normal.groupby("ba"):
        prof = np.vstack([np.median(g.loc[g["weekday"] == w, H].to_numpy(), axis=0) for w in range(7)])
        profiles[ba] = prof
        noise = np.median(
            np.concatenate([mape(g.loc[g["weekday"] == w, H].to_numpy(), prof[w][None, :]) for w in range(7)])
        )
        D = np.zeros((7, 7))
        for i in range(7):
            for j in range(7):
                D[i, j] = 100.0 * np.mean(np.abs(prof[i] - prof[j]) / prof[j])
        D = (D + D.T) / 2
        idx = D / noise
        for i in range(7):
            for j in range(i + 1, 7):
                rows.append({"ba": ba, "pair": f"{WEEKDAYS[i]}-{WEEKDAYS[j]}", "mape_pct": D[i, j], "noise_pct": noise, "index": idx[i, j]})
        Z = linkage(squareform(idx, checks=False), method="average")
        labels = fcluster(Z, t=1.0, criterion="distance")
        clusters.append({"ba": ba, "noise_pct": noise, "n_clusters_at_1_noise": int(labels.max()),
                         "clusters": " | ".join(",".join(WEEKDAYS[w] for w in range(7) if labels[w] == c) for c in sorted(set(labels)))})
    return pd.DataFrame(rows), pd.DataFrame(clusters), profiles


# ----------------------------------------------------------------------------- stage 4: special days
def holiday_analysis(sh: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    H = [f"h{h:02d}" for h in range(1, 25)]
    rows = []
    for ba, g in sh.groupby("ba"):
        g = g.sort_values("ordinal").reset_index(drop=True)
        actual = g[H].to_numpy()
        own = causal_profiles(g, "G7", WINDOW_WEEKS)
        sat = causal_profiles(g, "G7", WINDOW_WEEKS, target_groups=np.full(len(g), 5))
        sun = causal_profiles(g, "G7", WINDOW_WEEKS, target_groups=np.full(len(g), 6))
        e_own, e_sat, e_sun = mape(own, actual), mape(sat, actual), mape(sun, actual)
        for i in np.flatnonzero(g["is_special"].to_numpy()):
            if np.isnan(e_own[i]) or np.isnan(e_sun[i]) or np.isnan(e_sat[i]):
                continue
            wd = g.loc[i, "weekday"]
            if wd >= 5:
                errs = {"Saturday": e_sat[i], "Sunday": e_sun[i]}
            else:
                errs = {"own weekday": e_own[i], "Saturday": e_sat[i], "Sunday": e_sun[i]}
            rows.append({"ba": ba, "date": g.loc[i, "date"], "label": g.loc[i, "special"], "weekday": WEEKDAYS[g.loc[i, "weekday"]],
                         "err_own": e_own[i], "err_sat": e_sat[i], "err_sun": e_sun[i], "closest": min(errs, key=errs.get)})
    hol = pd.DataFrame(rows)
    hol["label_base"] = hol["label"].str.replace(" (observed)", "", regex=False)
    summ = (
        hol.groupby("label_base")
        .agg(n=("ba", "size"), err_own=("err_own", "median"), err_sat=("err_sat", "median"), err_sun=("err_sun", "median"),
             share_sun=("closest", lambda s: (s == "Sunday").mean()), share_sat=("closest", lambda s: (s == "Saturday").mean()),
             share_own=("closest", lambda s: (s == "own weekday").mean()))
        .sort_values("err_own", ascending=False)
    )
    return hol, summ


def superbowl_residual(sh: pd.DataFrame) -> pd.DataFrame:
    H = [f"h{h:02d}" for h in range(1, 25)]
    rows = []
    for ba, g in sh.groupby("ba"):
        g = g.sort_values("ordinal").reset_index(drop=True)
        sb = g[g["special"] == "Super Bowl Sunday"]
        for _, r in sb.iterrows():
            ref = g[(g["weekday"] == 6) & (~g["is_special"]) & (abs(g["ordinal"] - r["ordinal"]) <= 35)]
            if len(ref) < 4:
                continue
            resid = 100.0 * (r[H].to_numpy().astype(float) - np.median(ref[H].to_numpy(), axis=0))
            rows.append({"ba": ba, "year": r["year"], "offset_h": r["offset_h"], **{f"h{h:02d}": resid[h - 1] for h in range(1, 25)}})
    return pd.DataFrame(rows)


def discovered_special_dates(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two lists. (a) dates on which many BAs individually exceed their own 99th percentile: dominated by
    data artefacts that hit many BAs on the same day. (b) dates with the highest median shape error across
    all BAs, restricted to dates where at least 80% of BAs report: coherent calendar or weather events."""
    d = daily.dropna(subset=["G3_w8"]).copy()
    q99 = d.groupby("ba")["G3_w8"].transform(lambda s: s.quantile(0.99))
    d["extreme"] = d["G3_w8"] > q99
    n_ba_by_date = d.groupby("date")["ba"].nunique()
    ext = d[d["extreme"]].groupby("date").agg(n_bas=("ba", "nunique"), label=("special", "first"), median_err=("G3_w8", "median"))
    ext["share_of_bas"] = ext["n_bas"] / n_ba_by_date.reindex(ext.index)
    ext = ext.sort_values("n_bas", ascending=False)
    coh = d.groupby("date").agg(n_bas=("ba", "nunique"), label=("special", "first"), median_err=("G3_w8", "median"),
                                share_extreme=("extreme", "mean"))
    coh = coh[coh["n_bas"] >= 0.8 * n_ba_by_date.max()].sort_values("median_err", ascending=False)
    return ext, coh


# ----------------------------------------------------------------------------- figures
def style(ax, title, ylabel=None):
    ax.set_title(title, loc="left", fontsize=11, color=NAVY, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    if ylabel:
        ax.set_ylabel(ylabel)


def fig_models(summary: pd.DataFrame) -> None:
    cols = [f"{m}_w8_mean" for m in MODELS]
    fig, ax = plt.subplots(figsize=(7, 4))
    data = [summary[c].to_numpy() for c in cols]
    ax.boxplot(data, labels=list(MODELS), showfliers=False, medianprops={"color": RED})
    rng = np.random.default_rng(0)
    for i, v in enumerate(data):
        ax.scatter(i + 1 + rng.normal(0, 0.05, len(v)), v, s=8, color=NAVY, alpha=0.5)
    style(ax, "Shape error of causal profile models, one point per BA", "mean daily shape MAPE, %")
    ax.set_xticklabels(["G1 one profile", "G2 week/weekend", "G3 workday/Sat/Sun", "G5 Mon/Tue-Thu/Fri/Sat/Sun", "G7 weekday"], fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "fig1_models.png", dpi=150)
    plt.close(fig)


def fig_gain(tests: pd.DataFrame) -> None:
    t = tests.sort_values("gain_rel_pct")
    fig, ax = plt.subplots(figsize=(7, 0.22 * len(t) + 1.5))
    colors = [RED if n else GRAY for n in t["needs_b"]]
    ax.barh(t["ba"], t["gain_rel_pct"], color=colors)
    ax.errorbar(t["gain_rel_pct"], t["ba"], xerr=[(t["gain_pp"] - t["ci_lo"]) / t["G3_w8_mean"] * 100, (t["ci_hi"] - t["gain_pp"]) / t["G3_w8_mean"] * 100],
                fmt="none", ecolor=NAVY, elinewidth=0.8)
    ax.axvline(0, color=NAVY, lw=1)
    ax.axvline(5, color=RED, lw=0.8, ls="--")
    style(ax, "Gain of seven weekday profiles over three day-type profiles, by BA")
    ax.set_xlabel("relative reduction of shape MAPE, % (bars in red: CI above zero and gain above 5%)")
    ax.tick_params(axis="y", labelsize=7)
    fig.tight_layout()
    fig.savefig(FIG / "fig2_gain_g7_vs_g3.png", dpi=150)
    plt.close(fig)


def fig_distinctness(dist: pd.DataFrame) -> None:
    pairs = ["Mon-Tue", "Tue-Wed", "Wed-Thu", "Thu-Fri", "Mon-Fri", "Fri-Sat", "Sat-Sun", "Mon-Sun", "Wed-Sat", "Wed-Sun"]
    piv = dist.pivot(index="ba", columns="pair", values="index").reindex(columns=pairs)
    piv = piv.sort_values("Wed-Sun")
    fig, ax = plt.subplots(figsize=(7, 0.2 * len(piv) + 1.5))
    im = ax.imshow(piv.to_numpy(), aspect="auto", cmap="RdYlBu_r", vmin=0, vmax=3)
    ax.set_xticks(range(len(pairs)))
    ax.set_xticklabels(pairs, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(piv)))
    ax.set_yticklabels(piv.index, fontsize=6)
    ax.set_title("Distance between weekday profiles, in units of day-to-day noise", loc="left", fontsize=11, color=NAVY, fontweight="bold")
    cb = fig.colorbar(im, ax=ax, fraction=0.03)
    cb.set_label("index (1 = as different as two days of the same weekday)")
    fig.tight_layout()
    fig.savefig(FIG / "fig3_distinctness.png", dpi=150)
    plt.close(fig)


def fig_examples(profiles: dict[str, np.ndarray], hol: pd.DataFrame, sh: pd.DataFrame) -> None:
    H = [f"h{h:02d}" for h in range(1, 25)]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), sharey=True)
    cmap = plt.get_cmap("viridis", 7)
    for ax, ba in zip(axes, EXAMPLES):
        if ba not in profiles:
            continue
        for w in range(7):
            ax.plot(range(1, 25), profiles[ba][w], color=cmap(w), lw=1.2 if w in (5, 6) else 0.9, label=WEEKDAYS[w])
        xm = sh[(sh["ba"] == ba) & (sh["special"].isin(["Thanksgiving", "Christmas Day"]))]
        if len(xm):
            ax.plot(range(1, 25), np.median(xm[H].to_numpy(), axis=0), color=RED, lw=1.4, ls="--", label="Thanksgiving/Christmas")
        style(ax, ba)
        ax.set_xlabel("local hour ending")
    axes[0].set_ylabel("demand / daily mean")
    axes[-1].legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(FIG / "fig4_examples.png", dpi=150)
    plt.close(fig)


def fig_holidays(summ: pd.DataFrame) -> None:
    s = summ.sort_values("share_sun")
    fig, ax = plt.subplots(figsize=(7, 0.35 * len(s) + 1.2))
    ax.barh(s.index, s["share_sun"] * 100, color=NAVY, label="closest to Sunday")
    ax.barh(s.index, s["share_sat"] * 100, left=s["share_sun"] * 100, color=TEAL, label="closest to Saturday")
    ax.barh(s.index, s["share_own"] * 100, left=(s["share_sun"] + s["share_sat"]) * 100, color=GRAY, label="closest to own weekday")
    style(ax, "Which profile is closest to each special day, share of BA-years")
    ax.set_xlabel("%")
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "fig5_holidays.png", dpi=150)
    plt.close(fig)


def fig_superbowl(sb: pd.DataFrame) -> None:
    H = [f"h{h:02d}" for h in range(1, 25)]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    for off, color, label in ((5.0, NAVY, "Eastern (UTC-5)"), (6.0, TEAL, "Central (UTC-6)"), (8.0, ORANGE, "Pacific (UTC-8)")):
        sel = sb[np.isclose(sb["offset_h"], off)]
        if len(sel) == 0:
            continue
        med = sel[H].median()
        ax.plot(range(1, 25), med, color=color, lw=1.4, label=f"{label}, n={len(sel)} BA-years")
    ax.axhline(0, color=GRAY, lw=0.8)
    style(ax, "Super Bowl Sunday: shape residual against neighbouring Sundays", "residual, % of daily mean")
    ax.set_xlabel("local hour ending")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "fig6_superbowl.png", dpi=150)
    plt.close(fig)


def fig_special_dates(coh: pd.DataFrame) -> None:
    top = coh.head(25).iloc[::-1]
    labels = [f"{d} ({WEEKDAYS[pd.Timestamp(d).weekday()]})  {lab}" if lab else f"{d} ({WEEKDAYS[pd.Timestamp(d).weekday()]})"
              for d, lab in zip(top.index, top["label"])]
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.barh(labels, top["median_err"], color=[RED if not lab else NAVY for lab in top["label"]])
    style(ax, "The 25 days with the largest shape error across all BAs")
    ax.set_xlabel("median shape MAPE across BAs, % (red: not in the a-priori special-day list)")
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "fig7_special_dates.png", dpi=150)
    plt.close(fig)


def fig_window_sweep(summary: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for m, color, label in (("G1", GRAY, "G1 one profile"), ("G3", NAVY, "G3 workday/Sat/Sun"), ("G7", RED, "G7 weekday")):
        ys = [summary[f"{m}_w{w}_mean"].mean() for w in SWEEP_WEEKS]
        ax.plot(SWEEP_WEEKS, ys, marker="o", color=color, label=label)
    style(ax, "Shape error against the length of the reference window, mean over BAs", "mean daily shape MAPE, %")
    ax.set_xlabel("reference window, weeks")
    ax.set_xticks(SWEEP_WEEKS)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "fig8_window_sweep.png", dpi=150)
    plt.close(fig)


def fig_regime(sh: pd.DataFrame, testsR: pd.DataFrame, testsRp: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.1, 1]})
    # left: share of morning-peak days by month for a few BAs
    ax = axes[0]
    for ba, color in (("FPC", RED), ("SOCO", ORANGE), ("PJM", NAVY), ("ERCO", TEAL), ("CISO", GRAY)):
        g = sh[sh["ba"] == ba]
        if len(g) == 0:
            continue
        m = g.groupby("month")["regime"].mean() * 100
        ax.plot(m.index, m.to_numpy(), marker="o", color=color, label=ba)
    style(ax, "Days with a morning peak, by month", "% of days")
    ax.set_xlabel("month")
    ax.set_xticks(range(1, 13))
    ax.legend(fontsize=8)
    # right: gain of regime-aware G3 over G3, oracle vs previous-day regime
    ax = axes[1]
    t = testsR.set_index("ba")["gain_rel_pct"].sort_values()
    tp = testsRp.set_index("ba")["gain_rel_pct"].reindex(t.index)
    y = np.arange(len(t))
    ax.barh(y + 0.2, t.to_numpy(), height=0.4, color=RED, label="same-day regime (oracle)")
    ax.barh(y - 0.2, tp.to_numpy(), height=0.4, color=NAVY, label="previous-day regime (causal)")
    ax.set_yticks(y)
    ax.set_yticklabels(t.index, fontsize=5)
    ax.axvline(0, color=GRAY, lw=0.8)
    style(ax, "Gain of a regime split over G3")
    ax.set_xlabel("relative reduction of shape MAPE, %")
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "fig9_regime.png", dpi=150)
    plt.close(fig)


def _join_names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def write_readme(out: dict, hol_summary: pd.DataFrame, coh: pd.DataFrame, testsR: pd.DataFrame) -> None:
    tpl = (HERE / "README.template.md").read_text(encoding="utf-8")
    order = ["Thanksgiving", "Christmas Day", "Christmas Eve", "New Year's Eve", "Day after Thanksgiving", "New Year's Day",
             "Memorial Day", "Labor Day", "Independence Day", "Juneteenth", "Super Bowl Sunday",
             "MLK Day", "Presidents' Day", "Columbus Day", "Veterans Day"]
    rows = []
    for k in order:
        if k not in hol_summary.index:
            continue
        r = hol_summary.loc[k]
        shares = {"Sunday": r["share_sun"], "Saturday": r["share_sat"], "own weekday": r["share_own"]}
        best = max(shares, key=shares.get)
        own = "n/a" if k == "Super Bowl Sunday" else f"{r['err_own']:.1f}%"
        rows.append(f"| {k} | {int(r['n'])} | {own} | {r['err_sat']:.1f}% | {r['err_sun']:.1f}% | {best} ({shares[best]*100:.0f}%) |")
    top = coh[coh["label"].isna() | (coh["label"] == "")].head(4)
    ex = ", ".join(f"{pd.Timestamp(d).day} {pd.Timestamp(d).strftime('%B %Y')}" for d in top.index)
    d = out["distinctness_median_index"]
    w = out["window_sensitivity"]
    r7 = out["g7_vs_g3"]
    ro, rp = out["regime_oracle_vs_g3"], out["regime_prevday_vs_g3"]
    gm = {int(k): float(v) for k, v in out["seasonal"]["gain_by_month_pp"].items()}
    vals = {
        "n_bas": out["bas_eligible"],
        "ba_days": f"{out['ba_days']:,}",
        "first_date": out["first_date"],
        "last_date": out["last_date"],
        "generated": out["generated"][:10],
        "dropped": f"{out['dropped_days']:,}",
        "special_share": f"{out['special_days_share']*100:.1f}",
        "ci_below": r7["bas_ci_below_zero"],
        "g7_loss": f"{-r7['mean_gain_rel_pct']:.1f}",
        "g5_loss": f"{-out['g5_vs_g3']['mean_gain_rel_pct']:.1f}",
        "idx_tue_wed": f"{d['Tue-Wed']:.2f}",
        "idx_mon_thu": f"{d['Mon-Thu']:.2f}",
        "idx_thu_fri": f"{d['Thu-Fri']:.2f}",
        "g3_w3": f"{w['G3_w3']:.2f}",
        "g3_w2": f"{w['G3_w2']:.2f}",
        "a1": f"{out['seasonal']['means']['A1']:.2f}",
        "g3_w2_seas": f"{out['seasonal']['means']['G3_w2']:.2f}",
        "analog_worst": _join_names(pd.read_csv(RES / "r2a1_vs_g3_w2.csv").sort_values("gain_rel_pct").query("ci_hi < 0")["ba"].tolist()),
        "r2a1": f"{out['seasonal']['means']['R2A1']:.2f}",
        "s4": f"{out['seasonal']['means']['S4_w52']:.2f}",
        "s4_loss": f"{-out['seasonal']['S4_vs_G3_w2']['mean_gain_rel_pct']:.0f}",
        "r2a1_gain": f"{out['seasonal']['R2A1_vs_G3_w2']['mean_gain_rel_pct']:.1f}",
        "r2a1_up": out["seasonal"]["R2A1_vs_G3_w2"]["bas_ci_above_zero"],
        "r2a1_need": out["seasonal"]["R2A1_vs_G3_w2"]["bas_needing"],
        "r2a2_gain": f"{out['seasonal']['R2A2_vs_G3_w2']['mean_gain_rel_pct']:.1f}",
        "gain_spring": f"{np.mean([gm[m] for m in (3, 4, 5, 6)]):.2f}",
        "gain_other": f"{np.mean([gm[m] for m in (1, 2, 7, 8, 9, 10, 11, 12)]):.2f}",
        "best_weeks": out["best_model_window"][1],
        "hyb_mon": f"{out['hybrid_offset']['vs_G3_w3']['gain_by_weekday_pp']['Mon']:.2f}",
        "hyb_fri": f"{out['hybrid_offset']['vs_G3_w3']['gain_by_weekday_pp']['Fri']:.2f}",
        "hyb_gain": f"{out['hybrid_offset']['vs_G3_w3']['mean_gain_rel_pct']:+.1f}",
        "hyb_up": out["hybrid_offset"]["vs_G3_w3"]["bas_ci_above_zero"],
        "hyb_down": out["hybrid_offset"]["vs_G3_w3"]["bas_ci_below_zero"],
        "g3_w16": f"{w['G3_w16']:.2f}",
        "g3_w6": f"{w['G3_w6']:.2f}",
        "g1_w3": f"{w['G1_w3']:.2f}",
        "best_mape": f"{min(w.values()):.2f}",
        "g3_over_g1": f"{out['g3_vs_g1']['mean_gain_rel_pct']:.1f}",
        "n_need3": out["g3_vs_g1"]["bas_needing_3"],
        "n_two_clusters": len(out["two_cluster_bas"]),
        "two_cluster_bas": ", ".join(out["two_cluster_bas"]),
        "n_one_cluster": out["bas_eligible"] - len(out["two_cluster_bas"]),
        "coherent_examples": ex,
        "regime_oracle": f"{ro['mean_gain_rel_pct']:.1f}",
        "regime_oracle_n": ro["bas_needing"],
        "regime_top_gain": f"{ro['top'][0]['gain_rel_pct']:.0f}",
        "regime_top_ba": ro["top"][0]["ba"],
        "regime_prev": f"{rp['mean_gain_rel_pct']:.1f}",
        "regime_prev_n": rp["bas_needing"],
        "holiday_rows": chr(10).join(rows),
        "sb_sat_share": f"{out['sb_sat_share']*100:.0f}",
        "t_heat": f"{out['temperature']['t_heat_f']:.0f} °F ({out['temperature']['t_heat_c']:.0f} °C)",
        "t_cool": f"{out['temperature']['t_cool_f']:.0f} °F ({out['temperature']['t_cool_c']:.0f} °C)",
        "t_heat_short": f"{out['temperature']['t_heat_f']:.0f} °F",
        "t_cool_short": f"{out['temperature']['t_cool_f']:.0f} °F",
        "t_agree": f"{out['temperature']['regime_agreement_with_peak_hour']*100:.0f}",
        "g3t_gain": f"{out['temperature']['G3T_vs_G3']['mean_gain_rel_pct']:.1f}",
        "g3t_up": out["temperature"]["G3T_vs_G3"]["bas_ci_above_zero"],
        "g3t3_gain": f"{out['temperature']['G3T3_vs_G3']['mean_gain_rel_pct']:.1f}",
        "g3t3_need": out["temperature"]["G3T3_vs_G3"]["bas_needing"],
        "g3tprev_gain": f"{out['temperature']['G3Tprev_vs_G3']['mean_gain_rel_pct']:.1f}",
        "g3t3prev_gain": f"{out['temperature']['G3T3prev_vs_G3']['mean_gain_rel_pct']:.1f}",
        "g3t_top": ", ".join(f"{r['ba']} ({r['gain_rel_pct']:.0f}%)" for r in out["temperature"]["G3T_vs_G3"]["top"][:5]),
        "cfg_mape": f"{out['temperature']['best_config']['means']['BEST']:.2f}",
        "best_base": f"{out['temperature']['best_config']['means']['G3_w2']:.2f}",
        "best_gain": f"{out['temperature']['best_config']['BEST_vs_G3_w2']['mean_gain_rel_pct']:.1f}",
        "best_up": out["temperature"]["best_config"]["BEST_vs_G3_w2"]["bas_ci_above_zero"],
        "bestprev_gain": f"{out['temperature']['best_config']['BESTprev_vs_G3_w2']['mean_gain_rel_pct']:.1f}",
        "bestprev_mape": f"{out['temperature']['best_config']['means']['BESTprev']:.2f}",
    }
    text = tpl
    for k, v in vals.items():
        text = text.replace("{" + k + "}", str(v))
    (HERE / "README.md").write_text(text, encoding="utf-8", newline=chr(10))
    print("README.md written")


def fig_analogs(testsA: pd.DataFrame, gain_month: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1, 1.1]})
    ax = axes[0]
    months = sorted(gain_month)
    ax.bar(months, [gain_month[m] for m in months], color=NAVY)
    style(ax, "Gain from adding last year's analog days, by month", "reduction of shape MAPE, pp")
    ax.set_xlabel("month")
    ax.set_xticks(months)
    ax = axes[1]
    t = testsA.sort_values("gain_rel_pct")
    ax.barh(t["ba"], t["gain_rel_pct"], color=[RED if n else GRAY for n in t["needs_b"]])
    ax.axvline(0, color=NAVY, lw=1)
    style(ax, "Two recent weeks plus last year's analogs, over two recent weeks")
    ax.set_xlabel("relative reduction of shape MAPE, % (red: above 5% with CI above zero)")
    ax.tick_params(axis="y", labelsize=5)
    fig.tight_layout()
    fig.savefig(FIG / "fig10_analogs.png", dpi=150)
    plt.close(fig)


def fig_temperature(sh: pd.DataFrame, testsT: pd.DataFrame, testsR: pd.DataFrame, testsTp: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), gridspec_kw={"width_ratios": [1, 1.1]})
    ax = axes[0]
    d = sh.dropna(subset=["tmean_c"]).copy()
    d["tmean_f"] = d["tmean_c"] * 9.0 / 5.0 + 32.0
    bins = np.arange(0, 100, 5)
    for ba, color in (("FPC", RED), ("SOCO", ORANGE), ("PJM", NAVY), ("ERCO", TEAL), ("CISO", GRAY)):
        g = d[d["ba"] == ba]
        cut = pd.cut(g["tmean_f"], bins)
        m = g.groupby(cut, observed=True)["regime"].agg(["mean", "size"])
        m = m[m["size"] >= 15]
        ax.plot([iv.mid for iv in m.index], m["mean"] * 100, marker="o", color=color, label=ba)
    ax.axvline(T_HEAT_F, color=RED, ls="--", lw=0.8)
    style(ax, "Morning-peak days against daily mean temperature", "% of days with a morning peak")
    ax.set_xlabel("daily mean temperature at the reference station, °F")
    ax.legend(fontsize=8)
    ax = axes[1]
    t = testsT.set_index("ba")["gain_rel_pct"].sort_values()
    r = testsR.set_index("ba")["gain_rel_pct"].reindex(t.index)
    p = testsTp.set_index("ba")["gain_rel_pct"].reindex(t.index)
    y = np.arange(len(t))
    ax.barh(y + 0.27, t.to_numpy(), height=0.27, color=RED, label="temperature, same day")
    ax.barh(y, r.to_numpy(), height=0.27, color=GRAY, label="peak hour, same day (load-derived)")
    ax.barh(y - 0.27, p.to_numpy(), height=0.27, color=NAVY, label="temperature, previous day")
    ax.set_yticks(y)
    ax.set_yticklabels(t.index, fontsize=5)
    ax.axvline(0, color=GRAY, lw=0.8)
    style(ax, "Gain of a heating-day split over G3")
    ax.set_xlabel("relative reduction of shape MAPE, %")
    ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "fig11_temperature.png", dpi=150)
    plt.close(fig)


# ----------------------------------------------------------------------------- main
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tidy", required=True)
    p.add_argument("--stage", choices=["all", "shapes", "readme"], default="all")
    args = p.parse_args()
    warnings.filterwarnings("ignore")
    RES.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    cache = RES / "daily_shapes.parquet"
    if args.stage == "readme":
        out = json.loads((RES / "summary.json").read_text(encoding="utf-8"))
        hol_summary = pd.read_csv(RES / "holidays_summary.csv", index_col=0)
        coh = pd.read_csv(RES / "discovered_coherent_dates.csv", index_col=0)
        testsR = pd.read_csv(RES / "g3r_vs_g3.csv")
        write_readme(out, hol_summary, coh, testsR)
        return 0
    if not cache.exists() or args.stage == "shapes":
        sh, stats = build_shapes(Path(args.tidy))
        sh.to_parquet(cache, index=False)
        (RES / "shape_build_stats.json").write_text(json.dumps(stats, indent=2))
        print("shapes:", len(sh), stats)
        if args.stage == "shapes":
            return 0
    sh = pd.read_parquet(cache)
    sh["date"] = pd.to_datetime(sh["date"]).dt.date
    sh = add_calendar(sh)
    n_all = sh["ba"].nunique()
    sh = eligible(sh)
    print(f"eligible BAs: {sh['ba'].nunique()} of {n_all}; BA-days: {len(sh)}")

    daily, summary = evaluate(sh)
    daily.to_parquet(RES / "daily_errors.parquet", index=False)
    summary.to_csv(RES / "model_errors_by_ba.csv", index=False)
    tests = paired_tests(daily, "G3_w8", "G7_w8")
    tests.to_csv(RES / "g7_vs_g3.csv", index=False)
    tests53 = paired_tests(daily, "G3_w8", "G5_w8")
    tests53.to_csv(RES / "g5_vs_g3.csv", index=False)
    tests31 = paired_tests(daily, "G1_w8", "G3_w8")
    tests31.to_csv(RES / "g3_vs_g1.csv", index=False)
    testsO3 = paired_tests(daily, "G3_w3", "G3off_w3")
    testsO3.to_csv(RES / "g3off_vs_g3_w3.csv", index=False)
    testsO8 = paired_tests(daily, "G3_w8", "G3off_w8")
    testsO8.to_csv(RES / "g3off_vs_g3_w8.csv", index=False)
    testsO7 = paired_tests(daily, "G7_w3", "G3off_w3")
    testsO7.to_csv(RES / "g3off_vs_g7_w3.csv", index=False)
    testsA = paired_tests(daily, "G3_w2", "R2A1")
    testsA.to_csv(RES / "r2a1_vs_g3_w2.csv", index=False)
    testsA2 = paired_tests(daily, "G3_w2", "R2A2")
    testsS = paired_tests(daily, "G3_w2", "S4_w52")
    nrm = daily[daily["special"] == ""].dropna(subset=["G3_w2", "R2A1"])
    gain_month = (nrm["G3_w2"] - nrm["R2A1"]).groupby(nrm["month"]).mean().round(3).to_dict()
    testsT = paired_tests(daily, "G3_w8", "G3T_w8")
    testsT.to_csv(RES / "g3t_vs_g3.csv", index=False)
    testsT3 = paired_tests(daily, "G3_w8", "G3T3_w8")
    testsT3.to_csv(RES / "g3t3_vs_g3.csv", index=False)
    testsTp = paired_tests(daily, "G3_w8", "G3Tprev_w8")
    testsTp.to_csv(RES / "g3tprev_vs_g3.csv", index=False)
    testsTR = paired_tests(daily, "G3R_w8", "G3T_w8")
    testsT3p = paired_tests(daily, "G3_w8", "G3T3prev_w8")
    testsB = paired_tests(daily, "G3_w2", "BEST")
    testsB.to_csv(RES / "best_vs_g3_w2.csv", index=False)
    testsBp = paired_tests(daily, "G3_w2", "BESTprev")
    testsBA = paired_tests(daily, "R2A1", "BEST")
    testsTR.to_csv(RES / "g3t_vs_g3r.csv", index=False)
    agree = sh.dropna(subset=["tregime"])
    regime_agreement = float((agree["tregime"] == agree["regime"]).mean())
    testsR = paired_tests(daily, "G3_w8", "G3R_w8")
    testsR.to_csv(RES / "g3r_vs_g3.csv", index=False)
    testsRp = paired_tests(daily, "G3_w8", "G3Rprev_w8")
    testsRp.to_csv(RES / "g3rprev_vs_g3.csv", index=False)
    dist, clusters, profiles = weekday_distinctness(sh)
    dist.to_csv(RES / "weekday_distinctness.csv", index=False)
    clusters.to_csv(RES / "weekday_clusters.csv", index=False)
    hol, hol_summary = holiday_analysis(sh)
    hol.to_csv(RES / "holidays_by_ba.csv", index=False)
    hol_summary.to_csv(RES / "holidays_summary.csv")
    sb = superbowl_residual(sh)
    sb.to_csv(RES / "superbowl_residual.csv", index=False)
    ext, coh = discovered_special_dates(daily)
    ext.to_csv(RES / "discovered_extreme_dates.csv")
    coh.to_csv(RES / "discovered_coherent_dates.csv")

    fig_models(summary)
    fig_gain(tests)
    fig_distinctness(dist)
    fig_examples(profiles, hol, sh)
    fig_holidays(hol_summary)
    fig_superbowl(sb)
    fig_special_dates(coh)
    fig_window_sweep(summary)
    fig_regime(sh, testsR, testsRp)
    fig_analogs(testsA, gain_month)
    fig_temperature(sh, testsT, testsR, testsTp)

    by_wd = {WEEKDAYS[w]: float(tests[f"gain_{WEEKDAYS[w]}"].mean()) for w in range(7)}
    out = {
        "generated": pd.Timestamp.utcnow().isoformat(timespec="seconds"),
        "bas_eligible": int(sh["ba"].nunique()),
        "ba_days": int(len(sh)),
        "first_date": str(sh["date"].min()),
        "last_date": str(sh["date"].max()),
        "special_days_share": float(sh["is_special"].mean()),
        "model_mean_mape": {m: float(summary[f"{m}_w8_mean"].mean()) for m in MODELS},
        "model_median_ba_mape": {m: float(summary[f"{m}_w8_mean"].median()) for m in MODELS},
        "window_sensitivity": {f"{m}_w{w}": float(summary[f"{m}_w{w}_mean"].mean()) for m in ("G1", "G3", "G7") for w in SWEEP_WEEKS},
        "best_model_window": min(((m, w) for m in ("G1", "G3", "G7") for w in SWEEP_WEEKS), key=lambda t: summary[f"{t[0]}_w{t[1]}_mean"].mean()),
        "g7_vs_g3": {
            "mean_gain_pp": float(tests["gain_pp"].mean()),
            "mean_gain_rel_pct": float(tests["gain_rel_pct"].mean()),
            "bas_needing_7": int(tests["needs_b"].sum()),
            "bas_ci_above_zero": int((tests["ci_lo"] > 0).sum()),
            "bas_ci_below_zero": int((tests["ci_hi"] < 0).sum()),
            "gain_by_weekday_pp": by_wd,
        },
        "g5_vs_g3": {"mean_gain_rel_pct": float(tests53["gain_rel_pct"].mean()), "bas_needing_5": int(tests53["needs_b"].sum())},
        "g3_vs_g1": {"mean_gain_rel_pct": float(tests31["gain_rel_pct"].mean()), "bas_needing_3": int(tests31["needs_b"].sum())},
        "seasonal": {
            "means": {k: float(summary[f"seas_{k}_mean"].mean()) for k in SEASONAL_COLS},
            "R2A1_vs_G3_w2": {"mean_gain_rel_pct": float(testsA["gain_rel_pct"].mean()), "bas_needing": int(testsA["needs_b"].sum()),
                              "bas_ci_above_zero": int((testsA["ci_lo"] > 0).sum()), "bas_ci_below_zero": int((testsA["ci_hi"] < 0).sum())},
            "R2A2_vs_G3_w2": {"mean_gain_rel_pct": float(testsA2["gain_rel_pct"].mean()), "bas_needing": int(testsA2["needs_b"].sum())},
            "S4_vs_G3_w2": {"mean_gain_rel_pct": float(testsS["gain_rel_pct"].mean()), "bas_ci_below_zero": int((testsS["ci_hi"] < 0).sum())},
            "gain_by_month_pp": {int(k): float(v) for k, v in gain_month.items()},
        },
        "hybrid_offset": {
            "G3off_w3_mean": float(summary["G3off_w3_mean"].mean()),
            "G3off_w8_mean": float(summary["G3off_w8_mean"].mean()),
            "vs_G3_w3": {"mean_gain_rel_pct": float(testsO3["gain_rel_pct"].mean()), "bas_needing": int(testsO3["needs_b"].sum()),
                         "bas_ci_above_zero": int((testsO3["ci_lo"] > 0).sum()), "bas_ci_below_zero": int((testsO3["ci_hi"] < 0).sum()),
                         "gain_by_weekday_pp": {WEEKDAYS[w]: float(testsO3[f"gain_{WEEKDAYS[w]}"].mean()) for w in range(7)}},
            "vs_G3_w8": {"mean_gain_rel_pct": float(testsO8["gain_rel_pct"].mean()), "bas_needing": int(testsO8["needs_b"].sum()),
                         "bas_ci_above_zero": int((testsO8["ci_lo"] > 0).sum())},
            "vs_G7_w3": {"mean_gain_rel_pct": float(testsO7["gain_rel_pct"].mean()), "bas_ci_above_zero": int((testsO7["ci_lo"] > 0).sum())},
        },
        "temperature": {
            "t_heat_c": T_HEAT_C, "t_cool_c": T_COOL_C, "t_heat_f": T_HEAT_F, "t_cool_f": T_COOL_F,
            "regime_agreement_with_peak_hour": regime_agreement,
            "means": {c: float(summary[f"wx_{c}_mean"].mean()) for c in WEATHER_COLS},
            "G3T_vs_G3": {"mean_gain_rel_pct": float(testsT["gain_rel_pct"].mean()), "bas_needing": int(testsT["needs_b"].sum()),
                          "bas_ci_above_zero": int((testsT["ci_lo"] > 0).sum()), "bas_ci_below_zero": int((testsT["ci_hi"] < 0).sum()),
                          "top": testsT[["ba", "gain_rel_pct"]].head(10).round(1).to_dict(orient="records")},
            "G3T3_vs_G3": {"mean_gain_rel_pct": float(testsT3["gain_rel_pct"].mean()), "bas_needing": int(testsT3["needs_b"].sum()),
                           "bas_ci_above_zero": int((testsT3["ci_lo"] > 0).sum())},
            "G3Tprev_vs_G3": {"mean_gain_rel_pct": float(testsTp["gain_rel_pct"].mean()), "bas_needing": int(testsTp["needs_b"].sum()),
                              "bas_ci_above_zero": int((testsTp["ci_lo"] > 0).sum())},
            "G3T3prev_vs_G3": {"mean_gain_rel_pct": float(testsT3p["gain_rel_pct"].mean()), "bas_needing": int(testsT3p["needs_b"].sum()),
                               "bas_ci_above_zero": int((testsT3p["ci_lo"] > 0).sum())},
            "best_config": {
                "means": {c: float(summary[f"best_{c}_mean"].mean()) for c in BEST_COLS},
                "BEST_vs_G3_w2": {"mean_gain_rel_pct": float(testsB["gain_rel_pct"].mean()), "bas_needing": int(testsB["needs_b"].sum()),
                                  "bas_ci_above_zero": int((testsB["ci_lo"] > 0).sum())},
                "BESTprev_vs_G3_w2": {"mean_gain_rel_pct": float(testsBp["gain_rel_pct"].mean()), "bas_needing": int(testsBp["needs_b"].sum()),
                                      "bas_ci_above_zero": int((testsBp["ci_lo"] > 0).sum())},
                "BEST_vs_R2A1": {"mean_gain_rel_pct": float(testsBA["gain_rel_pct"].mean()), "bas_ci_above_zero": int((testsBA["ci_lo"] > 0).sum())},
            },
            "G3T_vs_G3R": {"mean_gain_rel_pct": float(testsTR["gain_rel_pct"].mean()),
                           "bas_ci_above_zero": int((testsTR["ci_lo"] > 0).sum()), "bas_ci_below_zero": int((testsTR["ci_hi"] < 0).sum())},
        },
        "regime_oracle_vs_g3": {"mean_gain_rel_pct": float(testsR["gain_rel_pct"].mean()), "bas_needing": int(testsR["needs_b"].sum()),
                                "top": testsR[["ba", "gain_rel_pct"]].head(10).round(1).to_dict(orient="records")},
        "regime_prevday_vs_g3": {"mean_gain_rel_pct": float(testsRp["gain_rel_pct"].mean()), "bas_needing": int(testsRp["needs_b"].sum()),
                                 "top": testsRp[["ba", "gain_rel_pct"]].head(10).round(1).to_dict(orient="records")},
        "morning_peak_share_by_ba": summary.set_index("ba")["share_morning_peak"].round(3).to_dict(),
        "clusters_at_1_noise": clusters["n_clusters_at_1_noise"].value_counts().sort_index().to_dict(),
        "distinctness_median_index": dist.groupby("pair")["index"].median().round(2).to_dict(),
        "holidays": hol_summary.round(3).to_dict(orient="index"),
        "extreme_dates_top": ext.head(15).reset_index().assign(date=lambda d: d["date"].astype(str)).to_dict(orient="records"),
        "coherent_dates_top": coh.head(25).reset_index().assign(date=lambda d: d["date"].astype(str)).to_dict(orient="records"),
        "superbowl_ba_years": int(len(sb)),
    }
    out["dropped_days"] = json.loads((RES / "shape_build_stats.json").read_text())["days_dropped_shape_filter"]
    out["two_cluster_bas"] = sorted(clusters.loc[clusters["n_clusters_at_1_noise"] > 1, "ba"].tolist())
    out["sb_sat_share"] = float(hol_summary.loc["Super Bowl Sunday", "share_sat"]) if "Super Bowl Sunday" in hol_summary.index else float("nan")
    (RES / "summary.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    write_readme(out, hol_summary, coh, testsR)
    print(json.dumps({k: out[k] for k in ("window_sensitivity", "hybrid_offset", "regime_oracle_vs_g3", "regime_prevday_vs_g3")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
