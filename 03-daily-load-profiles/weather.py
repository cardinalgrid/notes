"""Daily temperature per balancing authority from NOAA ISD-Lite hourly observations.

One representative airport station is assigned to each BA (the main load centre, or the largest city
in the service area). Hourly air temperature is downloaded from the public ISD-Lite files
(https://www.ncei.noaa.gov/pub/data/noaa/isd-lite/), converted to the BA's local time using the UTC
offset observed in the EIA-930 data for that day, and aggregated to daily mean, minimum and maximum.

Usage
-----
python weather.py            # downloads what is missing into data/isd/ and writes results/daily_weather.parquet
"""

from __future__ import annotations

import gzip
import io
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).parent
DATA = HERE / "data" / "isd"
RES = HERE / "results"
BASE = "https://www.ncei.noaa.gov/pub/data/noaa/isd-lite/{year}/{usaf}-{wban}-{year}.gz"
YEARS = range(2015, 2027)

# BA -> ICAO of the representative station. Station identifiers are resolved from isd-history.csv.
BA_STATION = {
    "AEC": "KMGM", "AECI": "KSGF", "AVA": "KGEG", "AZPS": "KPHX", "BANC": "KSMF", "BPAT": "KPDX",
    "CISO": "KLAX", "CPLE": "KRDU", "CPLW": "KAVL", "DUK": "KCLT", "EPE": "KELP", "ERCO": "KDFW",
    "FMPP": "KMCO", "FPC": "KMCO", "FPL": "KMIA", "GCPD": "KMWH", "IPCO": "KBOI", "ISNE": "KBOS",
    "JEA": "KJAX", "LDWP": "KLAX", "LGEE": "KSDF", "MISO": "KIND", "NEVP": "KLAS", "NWMT": "KBIL",
    "NYIS": "KJFK", "PACE": "KSLC", "PACW": "KPDX", "PGE": "KPDX", "PJM": "KPHL", "PNM": "KABQ",
    "PSCO": "KDEN", "PSEI": "KSEA", "SC": "KCHS", "SCEG": "KCAE", "SCL": "KSEA", "SOCO": "KATL",
    "SRP": "KPHX", "SWPP": "KOKC", "TEC": "KTPA", "TEPC": "KTUS", "TPWR": "KSEA", "TVA": "KBNA",
    "WACM": "KDEN", "WALC": "KPHX",
}


def resolve_stations() -> pd.DataFrame:
    hist = DATA / "isd-history.csv"
    if not hist.exists():
        r = requests.get("https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv", timeout=120)
        r.raise_for_status()
        hist.write_bytes(r.content)
    h = pd.read_csv(hist, dtype=str)
    h = h[(h["CTRY"] == "US") & h["ICAO"].isin(set(BA_STATION.values()))].copy()
    h["BEGIN"] = h["BEGIN"].astype(int)
    h["END"] = h["END"].astype(int)
    h = h[(h["BEGIN"] <= 20150701) & (h["END"] >= 20250101) & (h["USAF"] != "999999")]  # history file lags; files are fetched per year
    h = h.sort_values("BEGIN").groupby("ICAO").head(1)
    missing = set(BA_STATION.values()) - set(h["ICAO"])
    if missing:
        raise SystemExit(f"no station with full coverage for {sorted(missing)}")
    return h[["ICAO", "USAF", "WBAN", "STATION NAME", "STATE", "LAT", "LON"]].reset_index(drop=True)


def fetch(usaf: str, wban: str, year: int) -> Path | None:
    dest = DATA / f"{usaf}-{wban}-{year}.gz"
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    url = BASE.format(year=year, usaf=usaf, wban=wban)
    for attempt in range(3):
        r = requests.get(url, timeout=120)
        if r.status_code == 200:
            dest.write_bytes(r.content)
            return dest
        if r.status_code == 404:
            return None
        time.sleep(3 * (attempt + 1))
    return None


def read_hourly(path: Path) -> pd.DataFrame:
    """ISD-Lite fixed columns: year month day hour temp(0.1 C) dewp slp wdir wspd sky p1 p6."""
    txt = gzip.open(path, "rt").read()
    df = pd.read_csv(io.StringIO(txt), sep=r"\s+", header=None, usecols=[0, 1, 2, 3, 4],
                     names=["y", "m", "d", "h", "temp"], engine="python")
    df = df[df["temp"] != -9999]
    df["utc"] = pd.to_datetime(dict(year=df["y"], month=df["m"], day=df["d"], hour=df["h"]), utc=True)
    df["temp_c"] = df["temp"] / 10.0
    return df[["utc", "temp_c"]]


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    stations = resolve_stations()
    stations.to_csv(RES / "weather_stations.csv", index=False)
    hourly: dict[str, pd.DataFrame] = {}
    for _, st in stations.iterrows():
        parts = []
        for y in YEARS:
            p = fetch(st["USAF"], st["WBAN"], y)
            if p is not None:
                parts.append(read_hourly(p))
        hourly[st["ICAO"]] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["utc", "temp_c"])
        print(f"{st['ICAO']} {st['STATION NAME']}: {len(hourly[st['ICAO']]):,} hourly observations")

    # local time per BA-day from the EIA-930 offsets recorded in the shape cache
    sh = pd.read_parquet(RES / "daily_shapes.parquet", columns=["ba", "date", "offset_h"])
    sh["date"] = pd.to_datetime(sh["date"])
    rows = []
    for ba, icao in BA_STATION.items():
        obs = hourly[icao]
        if obs.empty:
            continue
        g = sh[sh["ba"] == ba]
        if g.empty:
            continue
        off = int(round(g["offset_h"].median()))  # hours behind UTC (standard time and DST blend; see note)
        local = obs["utc"].dt.tz_localize(None) - pd.Timedelta(hours=off)
        day = pd.DataFrame({"date": local.dt.normalize(), "temp_c": obs["temp_c"].to_numpy()})
        agg = day.groupby("date")["temp_c"].agg(tmean_c="mean", tmin_c="min", tmax_c="max", n_hours="size").reset_index()
        agg = agg[agg["n_hours"] >= 18]
        agg.insert(0, "ba", ba)
        agg.insert(1, "station", icao)
        rows.append(agg)
    out = pd.concat(rows, ignore_index=True)
    out["date"] = out["date"].dt.date
    out.to_parquet(RES / "daily_weather.parquet", index=False)
    print(f"daily weather: {len(out):,} BA-days for {out['ba'].nunique()} BAs -> results/daily_weather.parquet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
