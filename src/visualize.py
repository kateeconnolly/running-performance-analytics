"""
visualize.py  —  Step 4 of 4
------------------------------
Reads the cleaned and feature-engineered datasets, then saves
publication-quality training figures to figures/.

Figures generated
-----------------
  weekly_mileage.png         Weekly mileage bars + 4-week rolling average
  rolling_mileage.png        4-week and 8-week rolling training load
  long_run_progression.png   Longest run per week over time
  pace_distribution.png      Pace histogram / KDE with effort-zone shading
  pace_over_time.png         All runs coloured by effort level + trend
  pace_prediction.png        Actual vs. predicted pace (only if model ran)
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import seaborn as sns

FEAT    = Path("data/clean/runs_features.csv")
WEEKLY  = Path("data/clean/weekly_summary.csv")
PREDS   = Path("data/clean/predictions.csv")
FIG_DIR = Path("figures")

# ── Colour palette ─────────────────────────────────────────────────────────────
STRAVA  = "#FC4C02"   # Strava orange — familiar to fitness-tech audiences
BLUE    = "#1565C0"
GREEN   = "#2E7D32"
RED     = "#C62828"
DARK    = "#212121"
LGRAY   = "#EEEEEE"

EFFORT_COLORS = {"Easy": GREEN, "Moderate": STRAVA, "Hard": RED}
EFFORT_ORDER  = ["Hard", "Moderate", "Easy"]


def _base_style() -> None:
    plt.rcParams.update({
        "figure.facecolor":  "white",
        "axes.facecolor":    "white",
        "axes.edgecolor":    "#BDBDBD",
        "axes.grid":         True,
        "grid.color":        LGRAY,
        "grid.linewidth":    0.8,
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "font.family":       "sans-serif",
        "font.size":         11,
        "axes.titlesize":    14,
        "axes.titleweight":  "bold",
        "axes.labelsize":    11,
        "legend.frameon":    False,
        "legend.fontsize":   10,
    })


def _date_axis(ax: plt.Axes, interval: int = 3) -> None:
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=interval))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha="right")


def _pace_fmt(val: float, _) -> str:
    """Convert decimal minutes to MM:SS string (e.g. 9.5 → '9:30')."""
    mins = int(val)
    secs = int(round((val - mins) * 60))
    return f"{mins}:{secs:02d}"


def _save(fig: plt.Figure, name: str) -> None:
    path = FIG_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"      Saved → {path}")


# ══════════════════════════════════════════════════════════════════════════════
def plot_weekly_mileage(weekly: pd.DataFrame) -> None:
    """Bar chart of weekly miles with a rolling 4-week average overlay."""
    fig, ax = plt.subplots(figsize=(14, 5))

    ax.bar(weekly.index, weekly["weekly_miles"],
           color=STRAVA, alpha=0.75, width=5, zorder=2, label="Weekly miles")
    ax.plot(weekly.index, weekly["rolling_4wk_miles"] / 4,
            color=DARK, linewidth=2.2, label="4-week avg / week", zorder=3)

    ax.set_title("Weekly Running Mileage")
    ax.set_ylabel("Miles")
    _date_axis(ax)
    ax.legend()
    plt.tight_layout()
    _save(fig, "weekly_mileage.png")


# ══════════════════════════════════════════════════════════════════════════════
def plot_rolling_mileage(weekly: pd.DataFrame) -> None:
    """Overlapping 4-week and 8-week rolling mileage totals."""
    fig, ax = plt.subplots(figsize=(14, 5))

    ax.fill_between(weekly.index, weekly["rolling_4wk_miles"], alpha=0.12, color=BLUE)
    ax.fill_between(weekly.index, weekly["rolling_8wk_miles"], alpha=0.08, color=STRAVA)
    ax.plot(weekly.index, weekly["rolling_4wk_miles"],
            color=BLUE,   linewidth=2.2, label="4-week rolling total")
    ax.plot(weekly.index, weekly["rolling_8wk_miles"],
            color=STRAVA, linewidth=2.2, label="8-week rolling total", linestyle="--")

    ax.set_title("Rolling Training Load")
    ax.set_ylabel("Total Miles")
    _date_axis(ax)
    ax.legend()
    plt.tight_layout()
    _save(fig, "rolling_mileage.png")


# ══════════════════════════════════════════════════════════════════════════════
def plot_long_run(weekly: pd.DataFrame) -> None:
    """Scatter of longest run per week with a linear trend line."""
    fig, ax = plt.subplots(figsize=(14, 5))

    ax.scatter(weekly.index, weekly["longest_run"],
               color=BLUE, s=55, zorder=3, alpha=0.85, label="Longest run")

    if len(weekly) >= 4:
        # Fit a straight line to see if long runs are trending up over time
        x_num = (weekly.index - weekly.index[0]).days.values
        z = np.polyfit(x_num, weekly["longest_run"].values, 1)
        ax.plot(weekly.index, np.poly1d(z)(x_num),
                color=STRAVA, linewidth=2, linestyle="--", label="Trend")

    ax.set_title("Long Run Progression")
    ax.set_ylabel("Distance (miles)")
    _date_axis(ax)
    ax.legend()
    plt.tight_layout()
    _save(fig, "long_run_progression.png")


# ══════════════════════════════════════════════════════════════════════════════
def plot_pace_distribution(runs: pd.DataFrame) -> None:
    """KDE of pace with effort-zone shading."""
    q33 = runs["pace_min_per_mile"].quantile(0.33)
    q67 = runs["pace_min_per_mile"].quantile(0.67)
    x_min = runs["pace_min_per_mile"].min() - 0.3
    x_max = runs["pace_min_per_mile"].max() + 0.3

    fig, ax = plt.subplots(figsize=(10, 5))

    # Shade effort zones behind the KDE curve
    ax.axvspan(x_min, q33,  alpha=0.10, color=RED,   zorder=1, label=f"Hard  (< {_pace_fmt(q33, None)}/mi)")
    ax.axvspan(q33,  q67,   alpha=0.10, color=STRAVA, zorder=1, label=f"Moderate")
    ax.axvspan(q67,  x_max, alpha=0.10, color=GREEN,  zorder=1, label=f"Easy  (> {_pace_fmt(q67, None)}/mi)")

    # Kernel density estimate
    sns.kdeplot(
        runs["pace_min_per_mile"], ax=ax,
        color=DARK, linewidth=2.2, fill=True, alpha=0.06,
    )

    # Dashed lines at the thresholds
    for val, color in [(q33, RED), (q67, GREEN)]:
        ax.axvline(val, color=color, linewidth=1.5, linestyle="--")

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_pace_fmt))
    ax.set_title("Pace Distribution with Effort Zones")
    ax.set_xlabel("Pace (min/mile)   faster ←")
    ax.set_ylabel("Density")
    ax.set_xlim(x_min, x_max)
    ax.legend()
    plt.tight_layout()
    _save(fig, "pace_distribution.png")


# ══════════════════════════════════════════════════════════════════════════════
def plot_pace_over_time(runs: pd.DataFrame) -> None:
    """Scatter of all runs coloured by effort level, with a rolling average."""
    fig, ax = plt.subplots(figsize=(14, 5))

    for effort in EFFORT_ORDER:
        subset = runs[runs["effort"] == effort]
        # Dot size scales with run distance so long runs stand out
        ax.scatter(
            subset["date"], subset["pace_min_per_mile"],
            color=EFFORT_COLORS[effort],
            s=subset["distance_miles"] * 6,
            alpha=0.65, edgecolors="white", linewidths=0.3,
            label=f"{effort} ({len(subset)} runs)", zorder=3,
        )

    # 30-day rolling average — resample to daily first to handle gaps
    pace_series = runs.set_index("date")["pace_min_per_mile"].resample("D").mean()
    smooth = pace_series.rolling(30, min_periods=3).mean().dropna()
    if len(smooth) > 2:
        ax.plot(smooth.index, smooth, color=DARK, linewidth=2.2,
                label="30-day avg", zorder=4)

    # Flip y-axis: lower number = faster = visually "higher"
    ax.invert_yaxis()
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_pace_fmt))
    ax.set_title("Pace Over Time  (dot size ∝ distance · colour = effort level)")
    ax.set_ylabel("Pace (min/mile)   ← faster")
    _date_axis(ax)
    ax.legend(markerscale=1.2)
    plt.tight_layout()
    _save(fig, "pace_over_time.png")


# ══════════════════════════════════════════════════════════════════════════════
def plot_pace_prediction(preds: pd.DataFrame) -> None:
    """Actual vs. predicted pace scatter with a perfect-prediction diagonal."""
    fig, ax = plt.subplots(figsize=(7, 7))

    SPLIT_COLORS = {"train": BLUE, "test": RED}
    for split, grp in preds.groupby("split"):
        ax.scatter(
            grp["pace_min_per_mile"], grp["predicted_pace"],
            color=SPLIT_COLORS[split], alpha=0.65, s=45,
            edgecolors="white", linewidths=0.4,
            label=f"{split.capitalize()} set  (n={len(grp)})", zorder=3,
        )

    # y = x diagonal — perfect model would put all points on this line
    lo = min(preds["pace_min_per_mile"].min(), preds["predicted_pace"].min()) - 0.2
    hi = max(preds["pace_min_per_mile"].max(), preds["predicted_pace"].max()) + 0.2
    ax.plot([lo, hi], [lo, hi], color=DARK, linewidth=1.5,
            linestyle="--", label="Perfect prediction  (y = x)", zorder=2)

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_pace_fmt))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_pace_fmt))
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_title("Actual vs. Predicted Pace\n(Ridge Regression)")
    ax.set_xlabel("Actual pace (min/mile)")
    ax.set_ylabel("Predicted pace (min/mile)")
    ax.set_aspect("equal", adjustable="box")
    ax.legend()
    plt.tight_layout()
    _save(fig, "pace_prediction.png")


# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    for p in (FEAT, WEEKLY):
        if not p.exists():
            raise FileNotFoundError(f"{p} not found — run pipeline.py first.")

    runs   = pd.read_csv(FEAT,   parse_dates=["date"])
    weekly = pd.read_csv(WEEKLY, parse_dates=["date"], index_col="date")

    print(f"[4/4] Generating figures for {len(runs):,} runs …")
    _base_style()
    FIG_DIR.mkdir(exist_ok=True)

    plot_weekly_mileage(weekly)
    plot_rolling_mileage(weekly)
    plot_long_run(weekly)
    plot_pace_distribution(runs)
    plot_pace_over_time(runs)

    if PREDS.exists():
        preds = pd.read_csv(PREDS, parse_dates=["date"])
        plot_pace_prediction(preds)
    else:
        print("      Skipping pace_prediction.png (no predictions file — model skipped)")

    print(f"\n  All figures saved to {FIG_DIR}/")


if __name__ == "__main__":
    main()
