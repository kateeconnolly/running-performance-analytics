"""
features.py  —  Step 2 of 4
-----------------------------
Builds training-load features for each run and classifies effort level
(Easy / Moderate / Hard) from pace tertiles.

Features added
--------------
  rolling_7d_miles    Total miles in the 7 days BEFORE each run
  rolling_28d_miles   Total miles in the 28 days BEFORE each run
  rolling_56d_miles   Total miles in the 56 days BEFORE each run
  days_since_last_run Days elapsed since the previous run (recovery proxy)
  log_distance        log(distance + 1) — longer runs correlate with slower pace
  run_index           Cumulative run count (captures long-term fitness trend)
  month_num           Calendar month 1–12 (seasonal variation)
  effort              Easy / Moderate / Hard based on pace tertiles

Outputs
-------
  data/clean/runs_features.csv   — run-level dataset with all features
  data/clean/weekly_summary.csv  — weekly aggregation for plots
"""
from pathlib import Path
import numpy as np
import pandas as pd

CLEAN   = Path("data/clean/runs_clean.csv")
FEAT    = Path("data/clean/runs_features.csv")
WEEKLY  = Path("data/clean/weekly_summary.csv")
WEATHER = Path("data/clean/weather.csv")


def _add_rolling_load(runs: pd.DataFrame) -> pd.DataFrame:
    """
    Compute rolling mileage windows without data leakage.

    We first aggregate to DAILY totals (handles multiple runs on the same day),
    then compute rolling sums. shift(1) ensures that each window covers only
    the days BEFORE the run date — no future information leaks into features.
    """
    date_floor = runs["date"].dt.normalize()

    # Build a continuous daily series from the first to the last run date
    daily = (
        pd.Series(runs["distance_miles"].values, index=date_floor, name="miles")
        .groupby(level=0)
        .sum()
        .reindex(
            pd.date_range(date_floor.min(), date_floor.max(), freq="D"),
            fill_value=0.0,
        )
    )

    # shift(1) excludes the current day; min_periods=0 avoids NaN at the start
    roll_df = pd.DataFrame(
        {
            "rolling_7d_miles":  daily.rolling(7,  min_periods=0).sum().shift(1).fillna(0),
            "rolling_28d_miles": daily.rolling(28, min_periods=0).sum().shift(1).fillna(0),
            "rolling_56d_miles": daily.rolling(56, min_periods=0).sum().shift(1).fillna(0),
        },
        index=daily.index,
    )

    # Merge rolling values back onto the runs table, matching by calendar date
    runs["_date"] = date_floor
    runs = runs.merge(roll_df, left_on="_date", right_index=True, how="left")
    runs = runs.drop(columns=["_date"])
    return runs


def main() -> None:
    runs = pd.read_csv(CLEAN, parse_dates=["date"])
    runs = runs.sort_values("date").reset_index(drop=True)
    print(f"[2/4] Engineering features for {len(runs):,} runs …")

    # Sequential run counter — a rough proxy for accumulated fitness/experience
    runs["run_index"] = range(len(runs))

    # Log distance: a 10-mile run is harder than 5 miles but not twice as slow;
    # the log scale captures this diminishing relationship
    runs["log_distance"] = np.log1p(runs["distance_miles"])

    # Calendar month captures seasonal pace patterns (hot summers, cold winters)
    runs["month_num"] = runs["date"].dt.month

    # Days since the previous run, bounded at 60 to limit leverage from long breaks
    runs["days_since_last_run"] = (
        runs["date"].diff().dt.days.fillna(0).clip(upper=60)
    )

    # Rolling training-load windows (no leakage — prior days only)
    runs = _add_rolling_load(runs)

    # ── Effort classification from pace tertiles ───────────────────────────────
    # Lower pace (min/mile) = faster running = harder effort.
    # We cut at the 33rd and 67th percentiles of pace across all runs.
    q33 = runs["pace_min_per_mile"].quantile(0.33)
    q67 = runs["pace_min_per_mile"].quantile(0.67)

    runs["effort"] = np.select(
        [
            runs["pace_min_per_mile"] <= q33,   # fastest third → Hard
            runs["pace_min_per_mile"] <= q67,   # middle third  → Moderate
        ],
        ["Hard", "Moderate"],
        default="Easy",
    )

    effort_counts = runs["effort"].value_counts().to_dict()
    print(f"      Pace thresholds: Hard < {q33:.2f}, Moderate < {q67:.2f} min/mile")
    print(f"      Effort split   : {effort_counts}")

    # ── Merge weather features if available ───────────────────────────────────
    if WEATHER.exists():
        weather = pd.read_csv(WEATHER, parse_dates=["date"])
        runs = runs.merge(weather, on="date", how="left")
        n_w = runs["temperature_f"].notna().sum()
        print(f"      Merged weather for {n_w:,} runs  "
              f"(temp: {runs['temperature_f'].min():.0f}–{runs['temperature_f'].max():.0f}°F)")

    FEAT.parent.mkdir(parents=True, exist_ok=True)
    runs.to_csv(FEAT, index=False)
    print(f"      Saved → {FEAT}")

    # ── Weekly summary ─────────────────────────────────────────────────────────
    weekly = (
        runs.set_index("date")
        .resample("W")
        .agg(
            weekly_miles=("distance_miles", "sum"),
            num_runs    =("distance_miles", "count"),
            avg_pace    =("pace_min_per_mile", "mean"),
            longest_run =("distance_miles", "max"),
        )
    )
    weekly = weekly[weekly["num_runs"] > 0].copy()
    weekly["rolling_4wk_miles"] = weekly["weekly_miles"].rolling(4, min_periods=1).sum()
    weekly["rolling_8wk_miles"] = weekly["weekly_miles"].rolling(8, min_periods=1).sum()

    weekly.to_csv(WEEKLY)
    print(f"      Saved → {WEEKLY} ({len(weekly):,} active weeks)")


if __name__ == "__main__":
    main()
