"""
fetch_weather.py  —  Step 2 of 5
----------------------------------
1. Reads the Filename column from the raw Strava CSV to find GPS files.
2. Parses start lat/lon from each .gpx or .fit.gz activity file.
3. Groups runs into 0.1° location buckets (~7 miles) to minimize API calls —
   most Chicago runs share one bucket; travel runs get their own.
4. Fetches hourly temperature (°F) and relative humidity (%)
   from the Open-Meteo archive API — completely free, no API key required.
5. Matches each run to its weather hour and saves the result.

Output: data/clean/weather.csv
"""
from pathlib import Path
import gzip
import io
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional, Tuple

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
RAW_CSV    = Path("data/raw/activities.csv")
CLEAN_RUNS = Path("data/clean/runs_clean.csv")
WEATHER    = Path("data/clean/weather.csv")

# Where Strava put the activity GPS files (activities/ subfolder of your export)
EXPORT_DIR = Path.home() / "Downloads/export_90678715"

# Round coordinates to this many decimal places for clustering (0.1° ≈ 7 miles)
BUCKET = 1


# ── GPS file parsers ───────────────────────────────────────────────────────────

def _parse_gpx(path: Path) -> Optional[Tuple[float, float]]:
    """Return (lat, lon) of the first trackpoint in a GPX file."""
    try:
        root = ET.parse(path).getroot()
        # Try common GPX namespace variants
        for ns in (
            "http://www.topografix.com/GPX/1/1",
            "http://www.topografix.com/GPX/1/0",
            "",
        ):
            tag = f"{{{ns}}}trkpt" if ns else "trkpt"
            pt  = root.find(f".//{tag}")
            if pt is not None:
                return float(pt.get("lat")), float(pt.get("lon"))
    except Exception:
        pass
    return None


def _parse_fit(path: Path) -> Optional[Tuple[float, float]]:
    """Return (lat, lon) of the first GPS record in a .fit.gz file."""
    try:
        import fitparse
        # FIT stores angles in semicircles; convert to degrees
        SEMICIRCLES = 2 ** 31 / 180.0
        with gzip.open(path, "rb") as f:
            fitfile = fitparse.FitFile(io.BytesIO(f.read()))
        for msg in fitfile.get_messages("record"):
            lat = msg.get_value("position_lat")
            lon = msg.get_value("position_long")
            if lat is not None and lon is not None:
                return lat / SEMICIRCLES, lon / SEMICIRCLES
    except Exception:
        pass
    return None


def _get_coords(filename: str) -> Optional[Tuple[float, float]]:
    path = EXPORT_DIR / filename
    if not path.exists():
        return None
    if filename.endswith(".gpx"):
        return _parse_gpx(path)
    if filename.endswith(".fit.gz"):
        return _parse_fit(path)
    return None


# ── Open-Meteo fetch ───────────────────────────────────────────────────────────

def _fetch_meteo(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """
    Fetch hourly temperature (°F) and relative humidity (%) for one location.
    Open-Meteo is free, has no rate limits for reasonable use, and requires
    no API key. timezone=auto returns data in the location's local timezone.
    """
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&start_date={start}&end_date={end}"
        "&hourly=temperature_2m,relative_humidity_2m"
        "&temperature_unit=fahrenheit"
        "&timezone=auto"
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read())

    hourly = data["hourly"]
    return pd.DataFrame({
        "datetime":      pd.to_datetime(hourly["time"]),
        "temperature_f": hourly["temperature_2m"],
        "humidity_pct":  hourly["relative_humidity_2m"],
        "lat_bucket":    lat,
        "lon_bucket":    lon,
    })


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    runs = pd.read_csv(CLEAN_RUNS, parse_dates=["date"])
    raw  = pd.read_csv(RAW_CSV, usecols=["Activity Date", "Filename"])
    raw["date"] = pd.to_datetime(raw["Activity Date"], format="mixed", errors="coerce")
    raw = raw.dropna(subset=["date", "Filename"])

    print(f"[2/5] Fetching weather for {len(runs):,} runs …")

    # ── Parse GPS coordinates ──────────────────────────────────────────────────
    # Build date → filename lookup from the raw CSV
    date_to_file = dict(zip(raw["date"], raw["Filename"]))
    runs["_filename"] = runs["date"].map(date_to_file)

    n_files = runs["_filename"].notna().sum()
    print(f"      {n_files:,} runs have GPS files — parsing start coordinates …")

    lats, lons = [], []
    for filename in runs["_filename"]:
        if pd.isna(filename):
            lats.append(None); lons.append(None)
        else:
            coords = _get_coords(str(filename))
            lats.append(coords[0] if coords else None)
            lons.append(coords[1] if coords else None)

    runs["start_lat"] = lats
    runs["start_lon"] = lons
    n_coords = pd.notna(runs["start_lat"]).sum()
    print(f"      Extracted GPS coordinates for {n_coords:,} runs")
    print(f"      (Treadmill / indoor runs with no GPS: {n_files - n_coords:,})")

    # Drop runs with no GPS (treadmill, manual entry)
    geo = runs[runs["start_lat"].notna()].copy()
    geo["lat_bucket"] = geo["start_lat"].round(BUCKET)
    geo["lon_bucket"] = geo["start_lon"].round(BUCKET)

    # ── Fetch weather per location bucket ──────────────────────────────────────
    buckets = (
        geo.groupby(["lat_bucket", "lon_bucket"])["date"]
        .agg(["min", "max", "count"])
        .reset_index()
        .sort_values("count", ascending=False)
    )
    print(f"\n      {len(buckets):,} location buckets found:")
    for _, r in buckets.iterrows():
        print(f"        ({r['lat_bucket']:.1f}, {r['lon_bucket']:.1f})  "
              f"{int(r['count'])} runs  "
              f"{r['min'].date()} → {r['max'].date()}")

    print(f"\n      Making {len(buckets):,} API calls to Open-Meteo …")
    weather_frames = []
    for i, row in buckets.iterrows():
        lat   = row["lat_bucket"]
        lon   = row["lon_bucket"]
        start = row["min"].strftime("%Y-%m-%d")
        end   = row["max"].strftime("%Y-%m-%d")
        try:
            wf = _fetch_meteo(lat, lon, start, end)
            weather_frames.append(wf)
            print(f"        [{len(weather_frames)}/{len(buckets)}] ({lat:.1f}, {lon:.1f})  ✓  {len(wf):,} hourly records")
        except Exception as e:
            print(f"        [{len(weather_frames)+1}/{len(buckets)}] ({lat:.1f}, {lon:.1f})  FAILED: {e}")
        time.sleep(0.4)   # be polite to the free API

    if not weather_frames:
        print("      No weather data fetched — check internet connection.")
        return

    weather = pd.concat(weather_frames, ignore_index=True)

    # ── Match each run to its weather hour ─────────────────────────────────────
    # Round run time down to the nearest hour (e.g. 6:43 AM → 6:00 AM)
    geo["hour"]     = geo["date"].dt.floor("h")
    weather["hour"] = weather["datetime"].dt.floor("h")

    matched = geo[["date", "lat_bucket", "lon_bucket", "hour"]].merge(
        weather[["lat_bucket", "lon_bucket", "hour", "temperature_f", "humidity_pct"]],
        on=["lat_bucket", "lon_bucket", "hour"],
        how="left",
    )

    # Merge back onto ALL runs (non-GPS runs get NaN)
    result = runs[["date"]].merge(
        matched[["date", "temperature_f", "humidity_pct"]],
        on="date", how="left"
    )

    n_matched = result["temperature_f"].notna().sum()
    print(f"\n      Weather matched for {n_matched:,} / {len(runs):,} runs")
    print(f"      Temp range : {result['temperature_f'].min():.0f}°F – {result['temperature_f'].max():.0f}°F")
    print(f"      Humidity   : {result['humidity_pct'].min():.0f}% – {result['humidity_pct'].max():.0f}%")

    WEATHER.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(WEATHER, index=False)
    print(f"      Saved → {WEATHER}")


if __name__ == "__main__":
    main()
