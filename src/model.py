"""
model.py  —  Step 3 of 4
-------------------------
Trains a Ridge regression to predict pace (min/mile) from training-load
features. Evaluates on a chronological held-out test set.

Design choices
--------------
  Time-ordered split (not random)
      The test set always lies in the future relative to training data,
      mirroring real deployment and preventing data leakage.

  Ridge over OLS
      The rolling mileage features (7d, 28d, 56d) are highly correlated.
      Ridge's L2 penalty stabilizes coefficient estimates under multicollinearity.

  Features are standardized (zero mean, unit variance) before fitting
      so that coefficients are directly comparable across features.

  No hyperparameter tuning
      This is exploratory analysis, not a production model.

Requires ≥ 20 runs with complete features.

Output: data/clean/predictions.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

FEAT   = Path("data/clean/runs_features.csv")
PREDS  = Path("data/clean/predictions.csv")

# Core features always used
_BASE_FEATURES = [
    "log_distance",         # run length: longer runs → typically slower pace
    "rolling_7d_miles",     # acute load: recent fatigue
    "rolling_28d_miles",    # chronic load: current fitness base
    "days_since_last_run",  # recovery / freshness
    "run_index",            # long-term fitness trend
    "month_num",            # seasonal variation
]
# Weather features included when available
_WEATHER_FEATURES = ["temperature_f", "humidity_pct"]

TARGET     = "pace_min_per_mile"
MIN_RUNS   = 20
TRAIN_FRAC = 0.80


def main() -> None:
    df = pd.read_csv(FEAT, parse_dates=["date"]).sort_values("date").reset_index(drop=True)

    # Add weather features to the model if they were fetched
    weather_cols = [c for c in _WEATHER_FEATURES if c in df.columns and df[c].notna().any()]
    FEATURE_COLS = _BASE_FEATURES + weather_cols
    if weather_cols:
        print(f"      Weather features available: {weather_cols}")

    df = df.dropna(subset=FEATURE_COLS + [TARGET])
    n = len(df)

    if n < MIN_RUNS:
        print(
            f"[3/4] Only {n} runs with complete features (need ≥ {MIN_RUNS}).\n"
            "      Skipping model — run the pipeline again after adding more data."
        )
        return

    print(f"[3/4] Training pace prediction model on {n:,} runs …")

    # ── Chronological train / test split ──────────────────────────────────────
    split_idx = int(n * TRAIN_FRAC)
    train, test = df.iloc[:split_idx], df.iloc[split_idx:]
    print(f"      Train : {len(train):,} runs  ({train['date'].dt.date.min()} → {train['date'].dt.date.max()})")
    print(f"      Test  : {len(test):,} runs  ({test['date'].dt.date.min()} → {test['date'].dt.date.max()})")

    # ── Standardise features ───────────────────────────────────────────────────
    # Fit the scaler ONLY on training data — never on the test set
    scaler  = StandardScaler()
    X_train = scaler.fit_transform(train[FEATURE_COLS])
    X_test  = scaler.transform(test[FEATURE_COLS])
    y_train = train[TARGET].values
    y_test  = test[TARGET].values

    # ── Fit ───────────────────────────────────────────────────────────────────
    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)

    # ── Evaluate ──────────────────────────────────────────────────────────────
    y_hat_train = model.predict(X_train)
    y_hat_test  = model.predict(X_test)

    rmse = np.sqrt(mean_squared_error(y_test, y_hat_test))
    mae  = mean_absolute_error(y_test, y_hat_test)
    r2   = r2_score(y_test, y_hat_test)

    r2_train = r2_score(y_train, y_hat_train)
    print(f"\n  Test-set performance:")
    print(f"    RMSE = {rmse:.3f} min/mile  (~{rmse * 60:.0f} sec/mile)")
    print(f"    MAE  = {mae:.3f} min/mile  (~{mae * 60:.0f} sec/mile)")
    print(f"    R²   = {r2:.3f}   (train R² = {r2_train:.3f})")

    # ── Diagnose generalisation gap ───────────────────────────────────────────
    if r2 < 0:
        # R² < 0 means the model does worse than predicting the test-set mean
        # for every run. This almost always signals distribution shift — the
        # pace distribution in the test period differs meaningfully from the
        # training period. Common causes: a fitness plateau or change, a new
        # training phase, or an injury/recovery period in the test window.
        test_mean_pace  = y_test.mean()
        train_mean_pace = y_train.mean()
        print(
            f"\n  ⚠  Negative R² detected — model does not generalise to the test period.\n"
            f"     Train mean pace : {train_mean_pace:.2f} min/mile\n"
            f"     Test  mean pace : {test_mean_pace:.2f} min/mile\n"
            f"     Δ mean pace     : {test_mean_pace - train_mean_pace:+.2f} min/mile\n"
            f"     This likely reflects a pace distribution shift between the two periods.\n"
            f"     The linear model learned the training-period trend but could not\n"
            f"     extrapolate it into the test period — a known limitation of linear\n"
            f"     regression on non-stationary physiological time series.\n"
            f"     The pace_prediction.png plot will show this divergence visually."
        )

    print(f"\n  Standardised coefficients (|coef| = feature importance):")
    for feat, coef in sorted(zip(FEATURE_COLS, model.coef_), key=lambda x: abs(x[1]), reverse=True):
        direction = "↑ slower" if coef > 0 else "↓ faster"
        print(f"    {feat:<25s}  {coef:+.4f}  {direction}")

    # ── Save predictions ──────────────────────────────────────────────────────
    # Include both train and test predictions so we can plot them in visualize.py
    preds = pd.concat([
        train[["date", TARGET, "effort"]].assign(predicted_pace=y_hat_train, split="train"),
        test [["date", TARGET, "effort"]].assign(predicted_pace=y_hat_test,  split="test"),
    ])
    preds["residual"] = preds[TARGET] - preds["predicted_pace"]

    PREDS.parent.mkdir(parents=True, exist_ok=True)
    preds.to_csv(PREDS, index=False)
    print(f"\n      Saved → {PREDS}")


if __name__ == "__main__":
    main()
