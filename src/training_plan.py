"""
training_plan.py  —  Standalone
---------------------------------
Generates a personalized half marathon training plan for the
Hoka Chicago Half Marathon, derived from your Strava data.

Outputs:
  data/clean/half_plan.csv
  training_plan.html          (served by GitHub Pages)
"""
from pathlib import Path
from datetime import date, timedelta
import re
import pandas as pd

FEAT_CSV  = Path("data/clean/runs_features.csv")
PLAN_CSV  = Path("data/clean/half_plan.csv")
HTML_OUT  = Path("training_plan.html")

RACE_DATE  = date(2026, 9, 27)
TODAY      = date.today()
GOAL_PACE  = 90.0 / 13.1   # 1:30:00 target → 6:52/mi

# Snap plan start to the nearest upcoming Monday
_days_to_mon  = (-TODAY.weekday()) % 7
PLAN_START    = TODAY + timedelta(days=_days_to_mon)

PHASE_COLORS = {
    "Base":      "#1565C0",
    "Build":     "#E85D04",
    "Peak":      "#C62828",
    "Cutback":   "#2E7D32",
    "Taper":     "#6B6B6B",
    "Race Week": "#E85D04",
}

DISPLAY_LABEL = {
    "Easy":        "Easy Run",
    "Workout":     "Intervals",
    "Medium-Long": "Tempo",
    "Long":        "Long Run",
    "Rest":        "Rest",
    "Shakeout":    "Shakeout",
    "Race":        "Race Day",
}

GRID_STYLE = {
    # (background, text color)
    "Easy":        ("#F0F6E8", "#4A7232"),
    "Workout":     ("#FEF0E7", "#C24F04"),
    "Medium-Long": ("#FEF8E4", "#97650A"),
    "Long":        ("#EDE9F7", "#5A4498"),
    "Rest":        ("#F5F3EF", "#9B9590"),
    "Shakeout":    ("#FEF8E4", "#97650A"),
    "Race":        ("#E85D04", "#FFFFFF"),
}

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Fixed 14-week plan: phase, total miles, day-by-day miles (Mon→Sun)
WEEK_CONFIGS = [
    {"wk": 1,  "phase": "Base",      "total": 52,  "miles": [8,  9,  8, 10, 7, 0,   10  ]},
    {"wk": 2,  "phase": "Base",      "total": 56,  "miles": [9,  10, 9, 11, 7, 0,   10  ]},
    {"wk": 3,  "phase": "Base",      "total": 60,  "miles": [9,  11, 9, 12, 8, 0,   11  ]},
    {"wk": 4,  "phase": "Cutback",   "total": 48,  "miles": [7,  9,  7,  9, 7, 0,    9  ]},
    {"wk": 5,  "phase": "Build",     "total": 62,  "miles": [9,  11, 9, 12, 9, 0,   12  ]},
    {"wk": 6,  "phase": "Build",     "total": 65,  "miles": [9,  12, 9, 13, 9, 0,   13  ]},
    {"wk": 7,  "phase": "Build",     "total": 68,  "miles": [9,  11, 9, 12, 9, 4,   14  ]},  # 7-day
    {"wk": 8,  "phase": "Cutback",   "total": 55,  "miles": [8,  10, 8, 10, 7, 0,   12  ]},
    {"wk": 9,  "phase": "Peak",      "total": 68,  "miles": [10, 11, 9, 11, 8, 5,   14  ]},  # 7-day
    {"wk": 10, "phase": "Peak",      "total": 70,  "miles": [10, 11,10, 12, 8, 5,   14  ]},  # 7-day
    {"wk": 11, "phase": "Peak",      "total": 72,  "miles": [10, 12,10, 12, 9, 5,   14  ]},  # 7-day
    {"wk": 12, "phase": "Cutback",   "total": 60,  "miles": [9,  11, 9, 11, 8, 0,   12  ]},
    {"wk": 13, "phase": "Taper",     "total": 42,  "miles": [6,  10, 6,  8, 5, 0,    7  ]},
    {"wk": 14, "phase": "Race Week", "total": 25,  "miles": [4,   3, 3,  0, 2, 0,   13.1]},
]

WEEK_DAY_TYPES = [
    ["Easy","Workout","Easy","Medium-Long","Easy","Rest","Long"],       # 1
    ["Easy","Workout","Easy","Medium-Long","Easy","Rest","Long"],       # 2
    ["Easy","Workout","Easy","Medium-Long","Easy","Rest","Long"],       # 3
    ["Easy","Workout","Easy","Medium-Long","Easy","Rest","Long"],       # 4
    ["Easy","Workout","Easy","Medium-Long","Easy","Rest","Long"],       # 5
    ["Easy","Workout","Easy","Medium-Long","Easy","Rest","Long"],       # 6
    ["Easy","Workout","Easy","Medium-Long","Easy","Easy","Long"],       # 7 (7-day)
    ["Easy","Workout","Easy","Medium-Long","Easy","Rest","Long"],       # 8
    ["Easy","Workout","Easy","Medium-Long","Easy","Easy","Long"],       # 9 (7-day)
    ["Easy","Workout","Easy","Medium-Long","Easy","Easy","Long"],       # 10 (7-day)
    ["Easy","Workout","Easy","Medium-Long","Easy","Easy","Long"],       # 11 (7-day)
    ["Easy","Workout","Easy","Medium-Long","Easy","Rest","Long"],       # 12
    ["Easy","Workout","Easy","Workout","Easy","Rest","Long"],           # 13 (taper: 2 workouts)
    ["Easy","Shakeout","Easy","Rest","Shakeout","Rest","Race"],         # 14
]


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt(mpm: float) -> str:
    t = int(round(mpm * 60))
    return f"{t // 60}:{t % 60:02d}"


def pace_str(val) -> str:
    """Accept a float or (lo, hi) tuple and return a formatted pace string."""
    if isinstance(val, (tuple, list)):
        return f"{_fmt(val[0])}–{_fmt(val[1])}"
    return _fmt(val)


def finish_str(val, dist: float = 13.1) -> str:
    mpm = (val[0] + val[1]) / 2 if isinstance(val, (tuple, list)) else val
    t = int(round(mpm * dist * 60))
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}"


# ── Fitness data helpers ──────────────────────────────────────────────────────

def get_halfs(runs: pd.DataFrame) -> pd.DataFrame:
    return (runs[runs["distance_miles"].between(12.8, 13.5)]
            .sort_values("pace_min_per_mile").reset_index(drop=True))


def derive_paces() -> dict:
    r = GOAL_PACE
    return {
        # Ranges displayed to the user (lo, hi tuples)
        "race":       (r - 0.05, r + 0.05),    # 6:49–6:54
        "tempo":      (r - 0.30, r - 0.10),    # 6:34–6:44 — threshold, faster than HM
        "long_run":   (r + 0.85, r + 1.25),    # 7:43–8:07 — easy long run
        "easy":       (r + 1.00, r + 1.40),    # 7:54–8:16 — daily easy
        "recovery":   (r + 1.45, r + 1.90),    # 8:18–8:43 — after hard days / 7-day weeks
        # Derived ranges used in workout descriptions
        "rp_slight":  (r + 0.05, r + 0.20),    # 6:55–7:04 — slightly slower than race
        "rp_pickup":  (r + 0.18, r + 0.30),    # 7:03–7:09 — end-of-long-run pickup
        "lr_fast":    (r + 0.60, r + 0.80),    # 7:28–7:41 — faster long-run sections
        "tempo_tight":(r - 0.28, r - 0.13),    # 6:37–6:46 — taper 800m reps
        # Centers for arithmetic inside day_detail
        "_r": r, "_t": r - 0.18, "_lr": r + 1.05, "_e": r + 1.20, "_rv": r + 1.65,
    }


# ── Day detail strings ────────────────────────────────────────────────────────

def day_detail(wk: int, day_idx: int, dtype: str, miles: float, p: dict) -> str:
    rp    = p["race"]
    tp    = p["tempo"]
    lr    = p["long_run"]
    ep    = p["easy"]
    rv    = p["recovery"]
    rps   = p["rp_slight"]     # 6:55–7:04
    rpp   = p["rp_pickup"]     # 7:03–7:09
    lrf   = p["lr_fast"]       # 7:28–7:41
    tpt   = p["tempo_tight"]   # 6:37–6:46 (taper reps)
    mi = int(miles) if miles == int(miles) else miles

    if dtype == "Rest":
        return "Rest"
    if dtype == "Race":
        return f"RACE — goal {pace_str(rp)}/mi → {finish_str(rp)}"
    if dtype == "Shakeout":
        return ("Easy + 4×100m strides at race effort" if day_idx == 1
                else f"{mi}mi shakeout + 2 strides")
    if dtype == "Easy":
        pace = rv if day_idx in (4, 5) else ep
        return f"{mi}mi @ {pace_str(pace)}/mi"

    # ── Workouts ──────────────────────────────────────────────────────────────
    if dtype == "Workout":
        if wk == 1:
            return (f"<strong>Fartlek</strong> — 2mi WU, "
                    f"6×3min @ {pace_str(tp)}/mi w/ 2min easy jog, 2mi CD")
        if wk == 2:
            return (f"<strong>Cruise Intervals</strong> — 2mi WU, "
                    f"3×10min @ {pace_str(tp)}/mi (90s jog), 1mi CD")
        if wk == 3:
            return (f"<strong>Tempo Run</strong> — 2mi WU, "
                    f"20min continuous @ {pace_str(tp)}/mi, 2mi CD")
        if wk == 4:
            return (f"<strong>Easy Fartlek</strong> — 2mi WU, "
                    f"4×3min @ {pace_str(tp)}/mi w/ 3min easy jog, 2mi CD")
        if wk == 5:
            return (f"<strong>Mile Repeats</strong> — 2mi WU, "
                    f"4×1mi @ {pace_str(tp)}/mi (90s jog), 3mi CD")
        if wk == 6:
            return (f"<strong>Mile Repeats</strong> — 2mi WU, "
                    f"5×1mi @ {pace_str(tp)}/mi (90s jog), 3mi CD")
        if wk == 7:
            return (f"<strong>Tempo Run</strong> — 2mi WU, "
                    f"25min continuous @ {pace_str(tp)}/mi, 3mi CD")
        if wk == 8:
            return (f"<strong>Cruise Intervals</strong> — 2mi WU, "
                    f"3×1mi @ {pace_str(tp)}/mi (90s jog), 4mi CD")
        if wk == 9:
            return (f"<strong>Race Pace Intervals</strong> — 2mi WU, "
                    f"2×3mi @ {pace_str(rp)}/mi (2min jog), 1mi CD")
        if wk == 10:
            return (f"<strong>Race Pace Intervals</strong> — 2mi WU, "
                    f"2×3mi @ {pace_str(rp)}/mi (2min jog), 2mi CD")
        if wk == 11:
            return (f"<strong>Race Simulation</strong> — 2mi WU, "
                    f"8mi @ {pace_str(rp)}/mi, 2mi CD")
        if wk == 12:
            return (f"<strong>Mile Repeats</strong> — 2mi WU, "
                    f"4×1mi @ {pace_str(tp)}/mi (90s jog), 3mi CD")
        if wk == 13 and day_idx == 1:
            return (f"<strong>800m Repeats</strong> — 2mi WU, "
                    f"6×800m @ {pace_str(tpt)}/mi (90s jog), 2mi CD")
        if wk == 13 and day_idx == 3:
            return (f"<strong>Race Preview</strong> — 1mi WU, "
                    f"4mi @ {pace_str(rp)}/mi, 3mi CD")

    # ── Medium-Long ───────────────────────────────────────────────────────────
    if dtype == "Medium-Long":
        if wk <= 3:
            return f"{mi}mi easy @ {pace_str(ep)}/mi + 6×20sec strides"
        if wk == 4:
            return f"{mi}mi easy @ {pace_str(ep)}/mi + 4×20sec strides"
        if wk == 5:
            return (f"<strong>Progression</strong> — {mi - 4}mi easy, "
                    f"2mi @ {pace_str(rps)}/mi, {2}mi easy")
        if wk == 6:
            return (f"<strong>Progression</strong> — {mi - 5}mi easy, "
                    f"3mi @ {pace_str(rps)}/mi, 2mi easy")
        if wk == 7:
            return (f"<strong>Progression</strong> — {mi - 6}mi easy, "
                    f"4mi @ {pace_str(rps)}/mi, 2mi easy")
        if wk == 8:
            return f"{mi}mi easy @ {pace_str(ep)}/mi + 4×20sec strides"
        if wk == 9:
            return (f"<strong>Race Effort Blocks</strong> — 4mi easy, "
                    f"4mi @ {pace_str(rps)}/mi, 3mi easy")
        if wk == 10:
            return (f"<strong>Race Effort Blocks</strong> — 3mi easy, "
                    f"5mi @ {pace_str(rp)}/mi, 4mi easy")
        if wk == 11:
            return (f"<strong>Race Effort Blocks</strong> — 2mi easy, "
                    f"6mi @ {pace_str(rp)}/mi, 4mi easy")
        if wk == 12:
            return (f"<strong>Progression</strong> — {mi - 4}mi easy, "
                    f"3mi @ {pace_str(rps)}/mi, 1mi easy")
        if wk == 13:
            return f"{mi}mi easy @ {pace_str(lr)}/mi — no race effort"

    # ── Long run ──────────────────────────────────────────────────────────────
    if dtype == "Long":
        if wk <= 4:
            return (f"<strong>Easy Long Run</strong> — "
                    f"{mi}mi @ {pace_str(lr)}/mi, all conversation pace")
        if wk == 5:
            return (f"<strong>Progression Long Run</strong> — "
                    f"{mi - 2}mi @ {pace_str(lr)}/mi, last 2mi @ {pace_str(rpp)}/mi")
        if wk == 6:
            return (f"<strong>Progression Long Run</strong> — "
                    f"{mi - 3}mi @ {pace_str(lr)}/mi, last 3mi @ {pace_str(rpp)}/mi")
        if wk == 7:
            return (f"<strong>Progression Long Run</strong> — "
                    f"{mi - 4}mi @ {pace_str(lr)}/mi, last 4mi @ {pace_str(rpp)}/mi")
        if wk == 8:
            return (f"<strong>Easy Long Run</strong> — "
                    f"{mi}mi @ {pace_str(lr)}/mi, controlled and comfortable")
        if wk == 9:
            return (f"<strong>Long Run w/ Fast Finish</strong> — "
                    f"4mi easy, 6mi @ {pace_str(lrf)}/mi, 4mi easy")
        if wk == 10:
            return (f"<strong>Progression Long Run</strong> — "
                    f"4mi easy → 6mi @ {pace_str(lrf)}/mi → 4mi @ {pace_str(rpp)}/mi")
        if wk == 11:
            return (f"<strong>Peak Long Run</strong> — "
                    f"4mi easy → 6mi @ {pace_str(rpp)}/mi → 4mi @ {pace_str(rp)}/mi")
        if wk == 12:
            return (f"<strong>Easy Long Run</strong> — "
                    f"{mi}mi @ {pace_str(lr)}/mi, reset week")
        if wk == 13:
            return (f"<strong>Taper Long Run</strong> — "
                    f"{mi}mi @ {pace_str(lr)}/mi, legs should feel great")

    return f"{miles}mi"


# ── Plan builder ──────────────────────────────────────────────────────────────

def build_schedule(paces: dict) -> list:
    schedule = []
    for cfg in WEEK_CONFIGS:
        wk       = cfg["wk"]
        phase    = cfg["phase"]
        total    = cfg["total"]
        day_mi   = cfg["miles"]
        types    = WEEK_DAY_TYPES[wk - 1]
        wk_start = PLAN_START + timedelta(weeks=wk - 1)
        wk_end   = wk_start + timedelta(days=6)

        days = []
        for i, (day, mi, dtype) in enumerate(zip(DAYS, day_mi, types)):
            detail = day_detail(wk, i, dtype, mi, paces)
            days.append({
                "day": day, "miles": mi, "type": dtype, "detail": detail
            })

        long_mi = day_mi[6]
        schedule.append({
            "wk": wk, "phase": phase, "total": total,
            "week_of": wk_start.strftime("%b %-d"),
            "date_range": f"{wk_start.strftime('%b %-d')} – {wk_end.strftime('%b %-d')}",
            "long_mi": long_mi, "days": days,
        })
    return schedule


# ── HTML ──────────────────────────────────────────────────────────────────────

def render_html(paces: dict, halfs: pd.DataFrame, schedule: list) -> str:
    # Pace cards
    pace_cards_data = [
        ("Recovery",  paces["recovery"], "After hard days and 7-day weeks"),
        ("Easy",      paces["easy"],     "~80% of weekly miles"),
        ("Long Run",  paces["long_run"], "Default long run effort"),
        ("Tempo",     paces["tempo"],    "Threshold — faster than race pace"),
        ("Race Pace", paces["race"],     f"Goal → {finish_str(paces['race'])}"),
    ]
    cards_html = ""
    for label, mpm, desc in pace_cards_data:
        is_race = label == "Race Pace"
        bg  = "#E85D04" if is_race else "#FFFFFF"
        ink = "#FFFFFF" if is_race else "#111111"
        mut = "rgba(255,255,255,0.75)" if is_race else "#6B6B6B"
        cards_html += f"""
      <div class="pace-card" style="background:{bg};color:{ink};">
        <div class="pace-label" style="color:{mut};">{label}</div>
        <div class="pace-val">{pace_str(mpm)}<span>/mi</span></div>
        <div class="pace-desc" style="color:{mut};">{desc}</div>
      </div>"""

    # Half history table
    halfs_html = ""
    for _, r in halfs.iterrows():
        halfs_html += f"""
        <tr>
          <td>{r['date'].strftime('%b %-d, %Y')}</td>
          <td>{r['distance_miles']:.2f} mi</td>
          <td><strong>{pace_str(r['pace_min_per_mile'])}/mi</strong></td>
          <td>{finish_str(r['pace_min_per_mile'])}</td>
          <td><span class="badge" style="background:{'#FDECEA' if r['effort']=='Hard' else '#FFF4EE'};
              color:{'#C62828' if r['effort']=='Hard' else '#E85D04'};">{r['effort']}</span></td>
        </tr>"""

    # Calendar weeks — 7-column grid
    cal_html = ""
    for week in schedule:
        wk    = week["wk"]
        phase = week["phase"]
        color = PHASE_COLORS.get(phase, "#555")
        seven_day = all(d["type"] != "Rest" for d in week["days"])
        seven_badge = (' <span class="badge" style="background:#FEF0E7;color:#C24F04;'
                       'border:1px solid #FDDCC7;font-size:0.65rem;">7 days</span>'
                       if seven_day else "")

        cells = ""
        for d in week["days"]:
            bg, fg = GRID_STYLE.get(d["type"], ("#F5F3EF", "#9B9590"))
            label  = DISPLAY_LABEL.get(d["type"], d["type"])
            if d["miles"] == 0:
                mi_str = "—"
            elif d["miles"] == int(d["miles"]):
                mi_str = str(int(d["miles"]))
            else:
                mi_str = str(d["miles"])
            cells += f"""
          <div class="cal-day" style="background:{bg};color:{fg};">
            <div class="cal-day-name">{d['day'].upper()}</div>
            <div class="cal-day-miles">{mi_str}</div>
            <div class="cal-day-type">{label}</div>
          </div>"""

        detail_rows = ""
        for d in week["days"]:
            if d["type"] not in ("Easy", "Rest"):
                _, fg = GRID_STYLE.get(d["type"], ("#F5F3EF", "#555"))
                detail_rows += f"""
          <div class="detail-row">
            <span class="detail-day" style="color:{fg};">{d['day']}</span>
            <span class="detail-text">{d['detail']}</span>
          </div>"""

        details_block = (f'<div class="workout-details">{detail_rows}\n        </div>'
                         if detail_rows else "")

        cal_html += f"""
      <div class="week-card">
        <div class="week-header">
          <span class="week-dates">{week['date_range']}</span>
          <span class="badge" style="background:{color}18;color:{color};border:1px solid {color}40;">{phase}</span>
          {seven_badge}
          <span class="week-mi">{int(week['total'])} mi</span>
        </div>
        <div class="cal-grid">{cells}
        </div>
        {details_block}
      </div>"""

    # Hero stats
    peak = max(w["total"] for w in schedule if w["phase"] in ("Build", "Peak"))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Chicago Half Training Plan — Kate Connolly</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --orange: #E85D04; --ink: #111111; --muted: #6B6B6B;
      --bg: #F5F3EF; --card: #FFFFFF; --border: #E2DDD8;
    }}
    html {{ scroll-behavior: smooth; }}
    body {{ font-family: 'Inter', sans-serif; background: var(--bg); color: var(--ink); line-height: 1.6; }}
    h1,h2,h3,nav .wordmark {{ font-family: 'Space Grotesk', sans-serif; }}

    nav {{
      position: sticky; top: 0; z-index: 100;
      background: rgba(245,243,239,0.88); backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border);
      padding: 0 2rem; height: 52px;
      display: flex; align-items: center; justify-content: space-between;
    }}
    .wordmark {{ font-weight:700; font-size:0.92rem; color:var(--ink); text-decoration:none; }}
    .wordmark span {{ color:var(--orange); }}
    .back-link {{ font-size:0.82rem; font-weight:500; color:var(--muted); text-decoration:none; }}
    .back-link:hover {{ color:var(--ink); }}

    .hero {{
      background: var(--ink); color: #fff;
      padding: 5rem 2rem 4rem; text-align: center;
    }}
    .hero h1 {{ font-size: clamp(2rem, 6vw, 3.8rem); font-weight:700; letter-spacing:-0.03em; line-height:1.1; margin-bottom:0.6rem; }}
    .hero h1 em {{ font-style:normal; color:var(--orange); }}
    .hero-sub {{ font-size:1rem; color:#A0A0A0; margin-bottom:2.5rem; }}
    .hero-stats {{
      display: inline-flex; flex-wrap: wrap; justify-content: center;
      border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; overflow: hidden;
    }}
    .hstat {{ padding: 0.9rem 1.4rem; border-right: 1px solid rgba(255,255,255,0.1); text-align:center; }}
    .hstat:last-child {{ border-right: none; }}
    .hstat-num {{ display:block; font-family:'Space Grotesk',sans-serif; font-size:1.5rem; font-weight:700; color:#fff; letter-spacing:-0.02em; }}
    .hstat-label {{ display:block; font-size:0.7rem; color:#707070; text-transform:uppercase; letter-spacing:0.07em; margin-top:0.2rem; }}

    main {{ max-width: 1100px; margin: 0 auto; padding: 4rem 1.5rem; }}
    section {{ margin-bottom: 4.5rem; }}
    .sh {{ margin-bottom: 1.6rem; }}
    .sh h2 {{ font-size:1.3rem; font-weight:700; letter-spacing:-0.02em; margin-bottom:0.25rem; }}
    .sh p {{ font-size:0.9rem; color:var(--muted); }}

    .pace-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:1rem; }}
    .pace-card {{ border-radius:14px; padding:1.4rem 1.2rem; box-shadow:0 2px 8px rgba(0,0,0,.06); }}
    .pace-label {{ font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.4rem; }}
    .pace-val {{ font-family:'Space Grotesk',sans-serif; font-size:2rem; font-weight:700; letter-spacing:-0.03em; line-height:1; }}
    .pace-val span {{ font-size:0.9rem; font-weight:500; margin-left:2px; opacity:0.7; }}
    .pace-desc {{ font-size:0.78rem; margin-top:0.5rem; }}

    .badge {{ display:inline-block; border-radius:20px; padding:0.2rem 0.65rem; font-size:0.72rem; font-weight:600; }}

    table {{ width:100%; border-collapse:collapse; font-size:0.875rem; }}
    th {{ text-align:left; padding:0.5rem 0.75rem; color:var(--muted); font-weight:500; border-bottom:2px solid var(--border); font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; }}
    td {{ padding:0.6rem 0.75rem; border-bottom:1px solid #F0EDE8; vertical-align:middle; }}
    tr:last-child td {{ border-bottom:none; }}
    .table-wrap {{ background:var(--card); border-radius:16px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.06); overflow-x:auto; }}

    /* Calendar — 7-column grid */
    .week-card {{
      background: var(--card); border-radius: 16px;
      padding: 1.25rem 1.4rem; margin-bottom: 0.75rem;
      box-shadow: 0 2px 8px rgba(0,0,0,.05);
    }}
    .week-header {{
      display: flex; align-items: center; gap: 0.6rem;
      flex-wrap: wrap; margin-bottom: 0.85rem;
    }}
    .week-dates {{ font-size: 0.75rem; font-weight: 600; color: var(--muted); letter-spacing: 0.02em; }}
    .week-mi {{ font-size: 0.8rem; font-weight: 600; color: var(--muted); margin-left: auto; }}

    .cal-grid {{
      display: grid; grid-template-columns: repeat(7, 1fr);
      gap: 0.35rem; margin-bottom: 1rem;
    }}
    .cal-day {{
      border-radius: 10px; padding: 0.6rem 0.3rem;
      text-align: center; min-height: 76px;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 0.12rem;
    }}
    .cal-day-name {{
      font-size: 0.58rem; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.06em; opacity: 0.55;
    }}
    .cal-day-miles {{
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 700; font-size: 1.15rem; line-height: 1;
    }}
    .cal-day-type {{
      font-size: 0.57rem; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.75;
    }}

    .workout-details {{
      border-top: 1px solid var(--border); padding-top: 0.8rem;
      display: flex; flex-direction: column; gap: 0.4rem;
    }}
    .detail-row {{ display: flex; align-items: baseline; gap: 0.55rem; font-size: 0.82rem; }}
    .detail-day {{ font-weight: 700; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; min-width: 28px; }}
    .detail-text {{ color: #444; line-height: 1.5; flex: 1; }}

    footer {{ background:var(--ink); color:#555; text-align:center; padding:2rem; font-size:0.82rem; }}
    footer a {{ color:#888; }}

    @media (max-width: 640px) {{
      .cal-day {{ min-height: 60px; padding: 0.4rem 0.15rem; }}
      .cal-day-miles {{ font-size: 0.95rem; }}
      .cal-day-type {{ display: none; }}
      .hstat {{ padding: 0.75rem 0.9rem; }}
      .hstat-num {{ font-size: 1.2rem; }}
    }}
  </style>
</head>
<body>

<nav>
  <a href="index.html" class="wordmark">Kate<span>.</span>run</a>
  <a href="index.html" class="back-link">← Back to overview</a>
</nav>

<header class="hero">
  <h1>Chicago Half<br><em>Training Plan</em></h1>
  <p class="hero-sub">Hoka Chicago Half Marathon · September 27, 2026 · Built from my Strava data</p>
  <div class="hero-stats">
    <div class="hstat">
      <span class="hstat-num">{pace_str(paces["race"])}</span>
      <span class="hstat-label">Goal Pace</span>
    </div>
    <div class="hstat">
      <span class="hstat-num">{finish_str(paces["race"])}</span>
      <span class="hstat-label">Goal Finish</span>
    </div>
    <div class="hstat">
      <span class="hstat-num">14</span>
      <span class="hstat-label">Weeks</span>
    </div>
    <div class="hstat">
      <span class="hstat-num">{peak}</span>
      <span class="hstat-label">Peak Miles</span>
    </div>
  </div>
</header>

<main>

  <section>
    <div class="sh">
      <h2>Training Paces</h2>
      <p>Based on your 1:30 goal — 2 workouts + 1 long run per week, easy miles fill the rest.</p>
    </div>
    <div class="pace-grid">{cards_html}
    </div>
  </section>

  <section>
    <div class="sh">
      <h2>Half Marathon History</h2>
      <p>All runs between 12.8–13.5 miles from your Strava data, fastest first.</p>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Date</th><th>Distance</th><th>Pace</th><th>Finish</th><th>Effort</th></tr></thead>
        <tbody>{halfs_html}
        </tbody>
      </table>
    </div>
  </section>

  <section>
    <div class="sh">
      <h2>14-Week Plan</h2>
      <p>Intervals + Tempo + Long Run every week · 4 no-rest weeks at peak · cutbacks at ~83% volume.</p>
    </div>
    {cal_html}
  </section>

</main>

<footer>
  <p>Generated from 1,225 runs of Strava data ·
     <a href="index.html">Back to Running Performance Analytics</a></p>
</footer>

</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    runs  = pd.read_csv(FEAT_CSV, parse_dates=["date"])
    paces = derive_paces()
    halfs = get_halfs(runs)
    plan  = build_schedule(paces)

    weeks_out = (RACE_DATE - TODAY).days // 7
    print(f"\nHoka Chicago Half — {RACE_DATE.strftime('%B %-d, %Y')}  ({weeks_out} weeks out)")
    print(f"Goal: {pace_str(paces['race'])}/mi → {finish_str(paces['race'])}\n")
    print(f"{'Wk':<4} {'Week of':<10} {'Phase':<10} {'Miles':<6}  {'Long':<5}  Key workout (Tue)")
    print("─" * 80)
    for w in plan:
        tue = w["days"][1]
        print(f"{w['wk']:<4} {w['week_of']:<10} {w['phase']:<10} "
              f"{int(w['total']):<6}  {int(w['long_mi']):<5}  {re.sub('<[^>]+>', '', tue['detail'])}")

    PLAN_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for w in plan:
        for d in w["days"]:
            rows.append({"week": w["wk"], "phase": w["phase"],
                         "day": d["day"], "miles": d["miles"],
                         "type": d["type"], "detail": d["detail"]})
    pd.DataFrame(rows).to_csv(PLAN_CSV, index=False)

    html = render_html(paces, halfs, plan)
    HTML_OUT.write_text(html)
    print(f"\n  → {PLAN_CSV}")
    print(f"  → {HTML_OUT}")


if __name__ == "__main__":
    main()
