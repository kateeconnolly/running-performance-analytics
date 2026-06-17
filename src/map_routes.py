"""
map_routes.py  —  Optional / standalone
-----------------------------------------
Parses the full GPS track from every run's .fit.gz or .gpx file, then builds
an interactive Leaflet map (via Folium) with each route drawn as a polyline,
colored by effort level.

Output: figures/routes_map.html
Open it in any browser — no server needed.
"""
from pathlib import Path
import gzip
import io
import xml.etree.ElementTree as ET
from typing import Optional, List, Tuple

import pandas as pd
import folium
from folium.plugins import MiniMap

FEAT_CSV  = Path("data/clean/runs_features.csv")
RAW_CSV   = Path("data/raw/activities.csv")
EXPORT_DIR = Path.home() / "Downloads/export_90678715"
OUT       = Path("figures/routes_map.html")

EFFORT_COLORS = {
    "Easy":     "#2E7D32",   # green
    "Moderate": "#FC4C02",   # strava orange
    "Hard":     "#C62828",   # red
    None:       "#757575",   # grey — no effort label
}

SEMICIRCLES = 2 ** 31 / 180.0   # FIT semicircle → degrees divisor


# ── GPS parsers (full track, not just first point) ────────────────────────────

def _track_from_gpx(path: Path) -> List[Tuple[float, float]]:
    try:
        root = ET.parse(path).getroot()
        for ns in (
            "http://www.topografix.com/GPX/1/1",
            "http://www.topografix.com/GPX/1/0",
            "",
        ):
            tag = f"{{{ns}}}trkpt" if ns else "trkpt"
            pts = root.findall(f".//{tag}")
            if pts:
                return [(float(p.get("lat")), float(p.get("lon"))) for p in pts]
    except Exception:
        pass
    return []


def _track_from_fit(path: Path) -> List[Tuple[float, float]]:
    try:
        import fitparse
        with gzip.open(path, "rb") as f:
            fitfile = fitparse.FitFile(io.BytesIO(f.read()))
        coords = []
        for msg in fitfile.get_messages("record"):
            lat = msg.get_value("position_lat")
            lon = msg.get_value("position_long")
            if lat is not None and lon is not None:
                coords.append((lat / SEMICIRCLES, lon / SEMICIRCLES))
        return coords
    except Exception:
        return []


def _get_track(filename: str) -> List[Tuple[float, float]]:
    path = EXPORT_DIR / filename
    if not path.exists():
        return []
    if filename.endswith(".gpx"):
        return _track_from_gpx(path)
    if filename.endswith(".fit.gz"):
        return _track_from_fit(path)
    return []


def _pace_str(pace: float) -> str:
    mins = int(pace)
    secs = int(round((pace - mins) * 60))
    return f"{mins}:{secs:02d}"


# ── Build map ─────────────────────────────────────────────────────────────────

def main() -> None:
    runs = pd.read_csv(FEAT_CSV, parse_dates=["date"])
    raw  = pd.read_csv(RAW_CSV, usecols=["Activity Date", "Filename"])
    raw["date"] = pd.to_datetime(raw["Activity Date"], format="mixed", errors="coerce")
    raw  = raw.dropna(subset=["date", "Filename"])

    # Map run datetime → filename
    date_to_file = dict(zip(raw["date"], raw["Filename"]))
    runs["_filename"] = runs["date"].map(date_to_file)

    has_file = runs["_filename"].notna()
    print(f"Building route map for {has_file.sum():,} runs with GPS files …")

    # ── Folium map ────────────────────────────────────────────────────────────
    m = folium.Map(
        location=[39.95, -75.16],   # centred on Delaware/Philly home base
        zoom_start=11,
        tiles="CartoDB positron",
    )

    # One FeatureGroup per effort so the layer control can toggle them
    groups = {
        effort: folium.FeatureGroup(name=f"{effort} runs", show=True)
        for effort in ["Hard", "Moderate", "Easy"]
    }
    groups["Unknown"] = folium.FeatureGroup(name="Unknown effort", show=False)

    skipped = 0
    for i, (_, row) in enumerate(runs[has_file].iterrows(), 1):
        if i % 50 == 0 or i == 1:
            print(f"  [{i:>4}/{has_file.sum()}] parsing tracks …", flush=True)

        track = _get_track(str(row["_filename"]))
        if len(track) < 2:
            skipped += 1
            continue

        effort = row.get("effort") if pd.notna(row.get("effort")) else None
        color  = EFFORT_COLORS.get(effort, EFFORT_COLORS[None])
        group  = groups.get(effort or "Unknown", groups["Unknown"])

        dist_str = f"{row['distance_miles']:.1f} mi" if pd.notna(row.get("distance_miles")) else "?"
        pace_str = _pace_str(row["pace_min_per_mile"]) if pd.notna(row.get("pace_min_per_mile")) else "?"
        date_str = row["date"].strftime("%b %-d, %Y")

        popup_html = (
            f"<b>{date_str}</b><br>"
            f"{dist_str} · {pace_str}/mi<br>"
            f"Effort: {effort or '—'}"
        )

        folium.PolyLine(
            track,
            color=color,
            weight=1.8,
            opacity=0.55,
            tooltip=f"{date_str} · {dist_str} · {pace_str}/mi",
            popup=folium.Popup(popup_html, max_width=200),
        ).add_to(group)

    for g in groups.values():
        g.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    MiniMap(toggle_display=True).add_to(m)

    OUT.parent.mkdir(exist_ok=True)
    m.save(str(OUT))
    print(f"\n  Skipped {skipped} tracks with < 2 GPS points (treadmill / no signal)")
    print(f"  Saved → {OUT}")
    print(f"  Open with:  open {OUT}")


if __name__ == "__main__":
    main()
