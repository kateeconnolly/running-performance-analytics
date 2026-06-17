"""
clean_strava.py  —  Step 1 of 4
--------------------------------
Loads the raw Strava bulk-export CSV, filters to running activities,
converts units (km → miles, seconds → minutes), removes impossible rows,
and writes a tidy dataset to data/clean/runs_clean.csv.
"""
from pathlib import Path
import pandas as pd

RAW = Path("data/raw/activities.csv")
OUT = Path("data/clean/runs_clean.csv")


def main() -> None:
    if not RAW.exists():
        raise FileNotFoundError(
            f"\nExpected Strava export at: {RAW}\n"
            "  1. strava.com → Settings → My Account\n"
            "  2. Download or Delete Your Account → Request Your Archive\n"
            "  3. Unzip and copy activities.csv into data/raw/"
        )

    print(f"[1/4] Loading {RAW} …")
    df = pd.read_csv(RAW)
    print(f"      {len(df):,} total activities | {len(df.columns)} columns")

    # ── Filter to running activities ───────────────────────────────────────────
    # Strava uses "Activity Type" in most exports; some use "Sport Type"
    type_col = next(
        (c for c in ("Activity Type", "Sport Type") if c in df.columns), None
    )
    if type_col is None:
        raise KeyError(
            "Expected 'Activity Type' or 'Sport Type' column.\n"
            "Columns found: " + str(list(df.columns[:10])) + " …"
        )
    runs = df[df[type_col].str.strip() == "Run"].copy()
    print(f"      {len(runs):,} running activities")

    # ── Parse timestamp ────────────────────────────────────────────────────────
    # Strava format: "Jun 16, 2026, 6:43:53 PM"
    # format="mixed" tells pandas to infer each row's format rather than warn
    runs["date"] = pd.to_datetime(runs["Activity Date"], format="mixed", errors="coerce")
    bad = runs["date"].isna().sum()
    if bad:
        print(f"      Dropping {bad} rows with unparseable dates")
    runs = runs.dropna(subset=["date"])

    # ── Convert units ──────────────────────────────────────────────────────────
    # The Strava CSV has two "Distance" columns (pandas renames the second to
    # "Distance.1"). The FIRST column is in kilometres regardless of account
    # display settings — confirmed against raw export (Distance × 1000 ≈ Distance.1).
    runs["distance_miles"]    = runs["Distance"] / 1.60934
    runs["moving_time_min"]   = runs["Moving Time"] / 60.0
    runs["pace_min_per_mile"] = runs["moving_time_min"] / runs["distance_miles"]

    # ── Remove impossible rows ─────────────────────────────────────────────────
    n_before = len(runs)
    # Distance: must be > 0.1 mi and < 200 mi (generous ultra cap)
    runs = runs[runs["distance_miles"].between(0.1, 200)]
    # Pace: world record mile ≈ 3:43 min; 30 min/mi is an extreme upper bound
    runs = runs[runs["pace_min_per_mile"].between(3.0, 30.0)]
    print(f"      Removed {n_before - len(runs)} outlier rows → {len(runs):,} clean runs")

    # ── Select and rename output columns ──────────────────────────────────────
    col_map = {
        "date":              "date",
        "Activity Name":     "name",
        "distance_miles":    "distance_miles",
        "moving_time_min":   "moving_time_min",
        "pace_min_per_mile": "pace_min_per_mile",
    }
    # Include optional columns only if they exist in this export
    optional = {
        "Elevation Gain":     "elevation_gain_m",
        "Average Heart Rate": "avg_heart_rate",
        "Max Heart Rate":     "max_heart_rate",
        "Calories":           "calories",
    }
    col_map.update({k: v for k, v in optional.items() if k in runs.columns})

    clean = (
        runs[list(col_map.keys())]
        .rename(columns=col_map)
        .sort_values("date")
        .reset_index(drop=True)
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(OUT, index=False)
    print(f"      Saved → {OUT}")

    span = (clean["date"].max() - clean["date"].min()).days
    print(f"\n      Date range  : {clean['date'].dt.date.min()} → {clean['date'].dt.date.max()} ({span} days)")
    print(f"      Total runs  : {len(clean):,}")
    print(f"      Total miles : {clean['distance_miles'].sum():,.1f}")
    print(f"      Avg pace    : {clean['pace_min_per_mile'].mean():.2f} min/mile")


if __name__ == "__main__":
    main()
