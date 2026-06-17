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
import pandas as pd

FEAT_CSV  = Path("data/clean/runs_features.csv")
PLAN_CSV  = Path("data/clean/half_plan.csv")
HTML_OUT  = Path("training_plan.html")

RACE_DATE = date(2026, 9, 27)   # Hoka Chicago Half — late Sept
TODAY     = date.today()

PHASE_COLORS = {
    "Base":      "#1565C0",
    "Build":     "#E85D04",
    "Peak":      "#C62828",
    "Cutback":   "#2E7D32",
    "Taper":     "#6B6B6B",
    "Race Week": "#E85D04",
}


# ── Formatters ────────────────────────────────────────────────────────────────

def pace_str(mpm: float) -> str:
    t = int(round(mpm * 60))
    return f"{t // 60}:{t % 60:02d}"

def finish_str(mpm: float, dist: float = 13.1) -> str:
    t = int(round(mpm * dist * 60))
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}"


# ── Fitness analysis ──────────────────────────────────────────────────────────

def get_halfs(runs: pd.DataFrame) -> pd.DataFrame:
    return (runs[runs["distance_miles"].between(12.8, 13.5)]
            .sort_values("pace_min_per_mile").reset_index(drop=True))

def recent(runs: pd.DataFrame, weeks: int) -> pd.DataFrame:
    cutoff = runs["date"].max() - pd.Timedelta(weeks=weeks)
    return runs[runs["date"] >= cutoff]

def derive_paces(runs: pd.DataFrame) -> dict:
    halfs = get_halfs(runs)
    rec12 = recent(runs, 12)

    pr    = halfs["pace_min_per_mile"].iloc[0] if len(halfs) else None
    r_half = (halfs.sort_values("date", ascending=False)
              ["pace_min_per_mile"].iloc[0] if len(halfs) else None)
    hard  = rec12[(rec12["effort"] == "Hard") &
                  (rec12["distance_miles"] >= 3)]["pace_min_per_mile"].median()

    if pr and r_half:
        race = pr * 0.55 + r_half * 0.30 + (hard - 0.50) * 0.15
    elif pr:
        race = pr
    else:
        race = hard - 0.40

    return {
        "race":       race,
        "tempo":      race + 0.30,
        "long_run":   race + 0.90,
        "easy":       race + 1.15,
        "recovery":   race + 1.60,
        "pr":         pr,
        "recent_half": r_half,
    }


# ── Plan builder ──────────────────────────────────────────────────────────────

def build_plan(runs: pd.DataFrame, paces: dict) -> pd.DataFrame:
    weeks_out = max(10, min((RACE_DATE - TODAY).days // 7, 18))

    # Use 8-week 75th-percentile for base — more robust than a 4-week mean
    # which gets dragged down by a single low week or incomplete current week
    rec8 = recent(runs, 8)
    weekly_totals = (rec8.groupby(pd.Grouper(key="date", freq="W"))
                     ["distance_miles"].sum())
    base_mi   = max(weekly_totals.quantile(0.75), 48)   # floor at 48 — user says ~50 now
    rec8_long = (rec8.groupby(pd.Grouper(key="date", freq="W"))
                 ["distance_miles"].max().mean())

    rp, tp, lr, ep = paces["race"], paces["tempo"], paces["long_run"], paces["easy"]
    rows = []

    for wk in range(1, weeks_out + 1):
        wk_start    = TODAY + timedelta(weeks=wk - 1)
        is_cutback  = wk % 4 == 0 and wk < weeks_out - 1
        is_taper    = wk == weeks_out - 1
        is_race_wk  = wk == weeks_out

        progress = min((wk - 1) / max(weeks_out - 3, 1), 1.0)

        if is_race_wk:
            total, long, phase = 25, 5, "Race Week"
        elif is_taper:
            total, long, phase = 42, 10, "Taper"
        elif is_cutback:
            # Cutback weeks stay high — ~82% — you don't need 28-mile recovery weeks
            total = round(max(44, base_mi * 0.82 + progress * 6))
            long  = round(max(10, rec8_long * 0.85), 1)
            phase = "Cutback"
        else:
            total = round(min(65, base_mi + progress * 15))
            long  = round(min(14, rec8_long + progress * 2.5), 1)
            phase = ("Base" if wk <= 3 else "Build" if wk <= 7 else "Peak")

        # Key workout
        if is_race_wk:
            workout = f"RACE — Hoka Chicago Half · goal {pace_str(rp)}/mi → {finish_str(rp)}"
            detail  = (f"Mon: 4mi easy · Tue: 3mi easy + 4×100m strides · "
                       f"Wed: 3mi easy · Thu: off · Fri: 20min shakeout · Sat: off · "
                       f"Sun: RACE. Go get it.")
        elif is_taper:
            workout = f"10mi long w/ 3mi @ {pace_str(rp)}/mi in the middle"
            detail  = (f"Drop volume to ~42mi, keep intensity. "
                       f"One quality session mid-week: 6×800m @ {pace_str(rp - 0.15)}/mi. "
                       f"Mon/Wed/Fri easy 5–6mi. Sat easy 5mi. Legs should feel antsy by Sunday.")
        elif is_cutback:
            workout = f"{int(long)}mi easy @ {pace_str(lr)}/mi"
            detail  = (f"Still running 6 days but everything easy. "
                       f"One shortened quality session: 3mi tempo @ {pace_str(tp)}/mi. "
                       f"Mon–Sat: 6–8mi easy. Sun: {int(long)}mi long. Let the adaptation land.")
        elif wk <= 3:
            tm = 3 + (wk - 1)
            workout = f"Tempo: 2mi warmup + {tm}mi @ {pace_str(tp)}/mi + 1mi cool"
            detail  = (f"6 days running. Mon/Wed/Fri: 7–8mi easy @ {pace_str(ep)}/mi. "
                       f"Tue: tempo workout above. Thu: 10mi easy medium-long. "
                       f"Sun: {long}mi long @ {pace_str(lr)}/mi, no pace work yet.")
        elif wk <= 7:
            reps = 4 + (wk - 4)
            workout = f"Cruise intervals: {reps}×1mi @ {pace_str(tp)}/mi, 90s jog"
            detail  = (f"6 days running. Mon/Fri: 7mi easy. Wed: 10mi easy. "
                       f"Tue: intervals above. Thu: 10–11mi medium-long. "
                       f"Sun: {long}mi long, last 3mi @ {pace_str(lr - 0.20)}/mi. "
                       f"Start practicing race fueling — gel every 4 miles.")
        else:
            workout = f"Race-specific: 2mi warmup + 7mi @ {pace_str(rp + 0.10)}/mi + 1mi cool"
            detail  = (f"6 days running. Mon/Fri: 7–8mi easy. Wed: 10mi easy. "
                       f"Tue: workout above. Thu: 10mi with strides. "
                       f"Sun: {long}mi long with 4–5mi @ {pace_str(rp + 0.15)}/mi in the middle. "
                       f"Wear race shoes. Simulate race morning. Nail the fueling.")

        rows.append({
            "week": wk, "week_of": wk_start.strftime("%b %-d"),
            "phase": phase, "total_miles": total, "long_run_mi": long,
            "key_workout": workout, "detail": detail,
        })

    return pd.DataFrame(rows)


# ── HTML generation ───────────────────────────────────────────────────────────

def render_html(paces: dict, halfs: pd.DataFrame, plan: pd.DataFrame) -> str:
    pace_cards = [
        ("Recovery",   paces["recovery"], "After hard days / doubles"),
        ("Easy",       paces["easy"],     "~80% of your weekly miles"),
        ("Long Run",   paces["long_run"], "Default long run effort"),
        ("Tempo",      paces["tempo"],    "Comfortably hard — ~20K effort"),
        ("Race Pace",  paces["race"],     f"Goal → {finish_str(paces['race'])}"),
    ]

    cards_html = ""
    for label, mpm, desc in pace_cards:
        is_race = label == "Race Pace"
        bg   = "#E85D04" if is_race else "#FFFFFF"
        ink  = "#FFFFFF" if is_race else "#111111"
        mut  = "rgba(255,255,255,0.75)" if is_race else "#6B6B6B"
        cards_html += f"""
      <div class="pace-card" style="background:{bg}; color:{ink};">
        <div class="pace-label" style="color:{mut};">{label}</div>
        <div class="pace-val">{pace_str(mpm)}<span>/mi</span></div>
        <div class="pace-desc" style="color:{mut};">{desc}</div>
      </div>"""

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

    plan_rows_html = ""
    detail_cards_html = ""
    for _, r in plan.iterrows():
        color = PHASE_COLORS.get(r["phase"], "#555")
        plan_rows_html += f"""
        <tr>
          <td style="font-weight:600; color:#111;">{int(r['week'])}</td>
          <td>{r['week_of']}</td>
          <td><span class="badge" style="background:{color}18; color:{color}; border: 1px solid {color}40;">{r['phase']}</span></td>
          <td style="font-weight:600;">{int(r['total_miles'])} mi</td>
          <td>{r['long_run_mi']:.0f} mi</td>
          <td style="font-size:0.82rem; color:#333;">{r['key_workout']}</td>
        </tr>"""

        detail_cards_html += f"""
      <div class="detail-card">
        <div class="detail-header">
          <span class="detail-week">Week {int(r['week'])} · {r['week_of']}</span>
          <span class="badge" style="background:{color}18; color:{color}; border:1px solid {color}40;">{r['phase']}</span>
          <span class="detail-miles">{int(r['total_miles'])} mi · Long: {r['long_run_mi']:.0f} mi</span>
        </div>
        <div class="detail-key">🎯 {r['key_workout']}</div>
        <div class="detail-body">{r['detail']}</div>
      </div>"""

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
    h1,h2,h3,h4,nav .wordmark {{ font-family: 'Space Grotesk', sans-serif; }}

    nav {{
      position: sticky; top: 0; z-index: 100;
      background: rgba(245,243,239,0.88); backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border);
      padding: 0 2rem; height: 52px;
      display: flex; align-items: center; justify-content: space-between;
    }}
    .wordmark {{ font-weight:700; font-size:0.92rem; color:var(--ink); text-decoration:none; }}
    .wordmark span {{ color:var(--orange); }}
    .back-link {{ font-size:0.82rem; font-weight:500; color:var(--muted); text-decoration:none; transition: color .15s; }}
    .back-link:hover {{ color:var(--ink); }}

    .hero {{
      background: var(--ink); color: #fff;
      padding: 5rem 2rem 4rem; text-align: center;
      position: relative; overflow: hidden;
    }}
    .hero h1 {{ font-size: clamp(2rem, 6vw, 3.8rem); font-weight:700; letter-spacing:-0.03em; line-height:1.1; margin-bottom:0.6rem; }}
    .hero h1 em {{ font-style:normal; color:var(--orange); }}
    .hero-sub {{ font-size:1rem; color:#A0A0A0; margin-bottom:2.5rem; }}

    .hero-stats {{
      display: inline-flex; flex-wrap: wrap; justify-content: center;
      gap: 0; border: 1px solid rgba(255,255,255,0.1);
      border-radius: 12px; overflow: hidden;
    }}
    .hstat {{ padding: 0.9rem 1.4rem; border-right: 1px solid rgba(255,255,255,0.1); text-align:center; }}
    .hstat:last-child {{ border-right: none; }}
    .hstat-num {{ display:block; font-family:'Space Grotesk',sans-serif; font-size:1.5rem; font-weight:700; color:#fff; letter-spacing:-0.02em; line-height:1.1; }}
    .hstat-label {{ display:block; font-size:0.7rem; color:#707070; text-transform:uppercase; letter-spacing:0.07em; margin-top:0.2rem; }}

    main {{ max-width: 1100px; margin: 0 auto; padding: 4rem 1.5rem; }}
    section {{ margin-bottom: 4.5rem; }}
    .sh {{ margin-bottom: 1.6rem; }}
    .sh h2 {{ font-size:1.3rem; font-weight:700; letter-spacing:-0.02em; margin-bottom:0.25rem; }}
    .sh p {{ font-size:0.9rem; color:var(--muted); }}

    .pace-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 1rem;
    }}
    .pace-card {{
      border-radius: 14px; padding: 1.4rem 1.2rem;
      box-shadow: 0 2px 8px rgba(0,0,0,.06);
    }}
    .pace-label {{ font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.4rem; }}
    .pace-val {{ font-family:'Space Grotesk',sans-serif; font-size:2rem; font-weight:700; letter-spacing:-0.03em; line-height:1; }}
    .pace-val span {{ font-size:0.9rem; font-weight:500; margin-left:2px; opacity:0.7; }}
    .pace-desc {{ font-size:0.78rem; margin-top:0.5rem; }}

    .badge {{
      display: inline-block; border-radius: 20px;
      padding: 0.2rem 0.65rem; font-size:0.72rem; font-weight:600;
    }}

    table {{ width:100%; border-collapse:collapse; font-size:0.875rem; }}
    th {{ text-align:left; padding:0.5rem 0.75rem; color:var(--muted); font-weight:500; border-bottom:2px solid var(--border); font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; }}
    td {{ padding:0.6rem 0.75rem; border-bottom:1px solid #F0EDE8; vertical-align:middle; }}
    tr:last-child td {{ border-bottom:none; }}
    .table-wrap {{ background:var(--card); border-radius:16px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.06); overflow-x:auto; }}

    .detail-card {{
      background: var(--card); border-radius:14px;
      padding:1.4rem 1.5rem; margin-bottom:0.75rem;
      box-shadow: 0 2px 8px rgba(0,0,0,.05);
    }}
    .detail-header {{ display:flex; align-items:center; gap:0.75rem; flex-wrap:wrap; margin-bottom:0.65rem; }}
    .detail-week {{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:0.9rem; }}
    .detail-miles {{ font-size:0.8rem; color:var(--muted); margin-left:auto; }}
    .detail-key {{ font-size:0.88rem; font-weight:600; color:var(--ink); margin-bottom:0.4rem; }}
    .detail-body {{ font-size:0.83rem; color:var(--muted); line-height:1.7; }}

    footer {{ background:var(--ink); color:#555; text-align:center; padding:2rem; font-size:0.82rem; }}
    footer a {{ color:#888; }}
    @media (max-width:600px) {{
      .hstat {{ padding:0.75rem 1rem; }}
      .hstat-num {{ font-size:1.2rem; }}
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
      <span class="hstat-num">{len(plan)}</span>
      <span class="hstat-label">Weeks</span>
    </div>
    <div class="hstat">
      <span class="hstat-num">{int(plan[plan["phase"].isin(["Build","Peak"])]["total_miles"].max())}</span>
      <span class="hstat-label">Peak Miles</span>
    </div>
  </div>
</header>

<main>

  <section>
    <div class="sh">
      <h2>Personal Training Paces</h2>
      <p>Derived from your half marathon history and recent hard-effort runs — not a generic calculator.</p>
    </div>
    <div class="pace-grid">{cards_html}
    </div>
  </section>

  <section>
    <div class="sh">
      <h2>Half Marathon History</h2>
      <p>All runs between 12.8–13.5 miles, fastest first.</p>
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
      <h2>Week-by-Week Plan</h2>
      <p>14 weeks · 6 running days/week · cutback weeks stay at 44–50mi (you don't need 28-mile recovery).</p>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Wk</th><th>Week of</th><th>Phase</th><th>Miles</th><th>Long</th><th>Key Workout</th></tr></thead>
        <tbody>{plan_rows_html}
        </tbody>
      </table>
    </div>
  </section>

  <section>
    <div class="sh">
      <h2>Daily Breakdown</h2>
      <p>What each week actually looks like, day by day.</p>
    </div>
    {detail_cards_html}
  </section>

  <section>
    <div class="sh"><h2>Notes</h2></div>
    <div class="table-wrap" style="padding:1.5rem 1.75rem;">
      <p style="font-size:0.88rem; color:#333; line-height:1.9; margin-bottom:0.6rem;">
        <strong>Easy really means easy.</strong> If easy pace feels embarrassingly slow, your hard days are working.
        No faster than {pace_str(paces["easy"])}/mi on recovery days.
      </p>
      <p style="font-size:0.88rem; color:#333; line-height:1.9; margin-bottom:0.6rem;">
        <strong>Fuel every long run ≥ 10 miles.</strong> Gel every 4 miles, same brand you'll race with.
        Your gut needs training too.
      </p>
      <p style="font-size:0.88rem; color:#333; line-height:1.9; margin-bottom:0.6rem;">
        <strong>Chicago weather is in your favor.</strong> Your Strava data shows you run ~15–20 sec/mi slower
        above 70°F. Late September in Chicago typically runs 55–65°F — optimal race conditions.
      </p>
      <p style="font-size:0.88rem; color:#333; line-height:1.9;">
        <strong>The taper feels terrible.</strong> You'll feel slow, heavy, and anxious in weeks 13–14.
        That's normal. Trust the process.
      </p>
    </div>
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
    paces = derive_paces(runs)
    halfs = get_halfs(runs)
    plan  = build_plan(runs, paces)

    weeks_out = (RACE_DATE - TODAY).days // 7
    print(f"\nHoka Chicago Half — {RACE_DATE.strftime('%B %-d, %Y')}  ({weeks_out} weeks out)")
    print(f"PR: {pace_str(paces['pr'])}/mi  |  Goal: {pace_str(paces['race'])}/mi → {finish_str(paces['race'])}\n")
    print(f"{'Wk':<4} {'Week of':<10} {'Phase':<10} {'Miles':<7} {'Long':<6}  Key Workout")
    print("─" * 80)
    for _, r in plan.iterrows():
        print(f"{int(r['week']):<4} {r['week_of']:<10} {r['phase']:<10} "
              f"{int(r['total_miles']):<7} {r['long_run_mi']:<6.0f}  {r['key_workout']}")

    PLAN_CSV.parent.mkdir(parents=True, exist_ok=True)
    plan.to_csv(PLAN_CSV, index=False)

    html = render_html(paces, halfs, plan)
    HTML_OUT.write_text(html)

    print(f"\n  → {PLAN_CSV}")
    print(f"  → {HTML_OUT}")


if __name__ == "__main__":
    main()
