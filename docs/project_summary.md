# Project Summary: Running Performance Analytics

## Data Source

Personal running activity data exported from [Strava](https://www.strava.com) via the bulk account export (Settings → My Account → Download or Delete Your Account). The export delivers a single CSV with one row per activity and columns for distance, elapsed time, moving time, heart rate, elevation, and metadata.

Raw data and all derived CSVs are excluded from this repository via `.gitignore`.

---

## Cleaning

| Step | Detail |
|---|---|
| Activity filter | Rows where `Activity Type ≠ "Run"` are dropped |
| Unit conversion | Strava's first `Distance` column is in km; divided by 1.60934 for miles. `Moving Time` (seconds) divided by 60 for minutes |
| Outlier removal | Rows with pace outside [3, 30] min/mile removed. Bounds span from just below the world record mile (3:43) to well above brisk walking |

---

## Feature Engineering

Rolling mileage windows are computed on a daily-aggregated mileage series. A `shift(1)` ensures each window covers only days **prior** to the run, preventing leakage from future data into model features.

| Feature | Rationale |
|---|---|
| `log_distance` | Longer runs are typically paced more conservatively; log scale captures diminishing returns |
| `rolling_7d_miles` | Acute training load — recent fatigue |
| `rolling_28d_miles` | Chronic training load — fitness base |
| `rolling_56d_miles` | Structural fitness trend over ~2 months |
| `days_since_last_run` | Recovery / freshness proxy, capped at 60 days |
| `run_index` | Sequential count of runs — rough proxy for accumulated fitness |
| `month_num` | Seasonal variation in pace (weather, daylight hours) |

---

## Run Classification

Each run is labelled **Hard**, **Moderate**, or **Easy** based on its pace relative to the full dataset's 33rd and 67th pace percentiles. Lower pace (min/mile) = faster running = higher relative effort:

- **Hard** — fastest third (pace ≤ 33rd percentile)
- **Moderate** — middle third
- **Easy** — slowest third (pace ≥ 67th percentile)

This is a data-driven, *relative* classification. It does not use heart rate, power, or perceived exertion. A "Hard" run is fast relative to this athlete's own pace distribution — not necessarily a physiologically hard workout.

---

## Pace Prediction Model

### Algorithm

Ridge regression (L2-regularised linear model). Ridge was chosen over ordinary least squares because the rolling mileage features (`7d`, `28d`, `56d`) are strongly correlated, inflating OLS coefficient variance. The L2 penalty stabilises estimates under multicollinearity.

### Train / Test Split

The dataset is split chronologically at the 80th percentile run by date. The test set always lies in the **future** relative to training data, matching real deployment conditions. A random split would allow future fitness state to contaminate training data.

### Evaluation

Model performance is reported on the held-out test set only (RMSE, MAE, R²). Standardised coefficients (features scaled to zero mean / unit variance) are printed to allow direct comparison of feature associations.

### Results and interpretation

On the test set (most recent ~20% of runs), the model achieves a **negative R²**, meaning it predicts pace less accurately than simply using the test-set mean pace for every run. The training R² is low but positive (~0.09), creating a large generalisation gap.

The most likely explanation is **distribution shift**: the pace distribution in the test period differs meaningfully from the training period. The `run_index` feature (sequential run count) captures a trend in the training data — for example, pace gradually slowing or speeding up over the 2021–2025 training window — and that trend does not extrapolate into the 2025–2026 test window.

This is a genuine and informative finding. It illustrates a key challenge in modeling physiological time series with linear methods: running pace is non-stationary (training cycles, injury, life changes), and a single linear trend fitted over years of data will generalize poorly to any period where behavior changes.

### Caveats

- **Associative, not causal.** The model identifies statistical associations between training-load features and pace. It does not establish that higher mileage *causes* faster pace.
- **Missing confounders.** Terrain, weather, race conditions, illness, and shoe choice are not in this dataset and may explain substantial variance.
- **Linear approximation.** The relationship between training load and performance has nonlinear dynamics (overtraining, taper, recovery) that Ridge regression cannot capture.
- **Non-stationarity.** Pace distributions shift over a multi-year training history in ways a single linear model cannot track.
- **Single athlete.** Findings are not generalisable beyond the individual dataset.

---

## Limitations

- Treadmill runs may have less accurate distance/pace than GPS-tracked outdoor runs.
- Heart rate is only available for runs recorded with a compatible sensor.
- Dataset size constrains model reliability; R² should be interpreted conservatively.
- The 33rd/67th percentile effort thresholds are fixed at dataset-wide quantiles, so they shift as the training history grows.

---

## Potential Extensions

- Incorporate heart rate (when available) for physiology-grounded effort zones (e.g., Garmin/Polar HR zones).
- Pull historical weather data via an open API to control for temperature and humidity.
- Apply a LOESS smoother or Gaussian process regression to capture nonlinear load–pace relationships.
- Build an interactive Streamlit or Dash dashboard for real-time training analysis.
- Extend to multiple athletes to enable cross-sectional analysis.
