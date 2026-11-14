"""New educational implementation; not the original CHPC workshop code.

Forecast turbine active power from observations available at each issue time.
The demo is synthetic. A real CSV must contain one regularly sampled turbine.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor


def demo_data(rows: int = 1440) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    time = pd.date_range("2025-01-01", periods=rows, freq="h", tz="UTC")
    phase = np.arange(rows)
    noise = rng.normal(0, 0.5, rows)
    speed = np.clip(7 + 3 * np.sin(phase / 32) + np.sin(phase / 4) + noise, 0, 24)
    power = 2000 * np.clip((speed ** 3 - 3 ** 3) / (12 ** 3 - 3 ** 3), 0, 1)
    power = np.clip(power + rng.normal(0, 25, rows), 0, 2000)
    return pd.DataFrame({"timestamp": time, "wind_speed_mps": speed,
                         "wind_direction_deg": (phase * 2 + 180) % 360,
                         "power_kw": power})


def validate(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timedelta]:
    required = ["timestamp", "wind_speed_mps", "wind_direction_deg", "power_kw"]
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    frame = frame[required].copy()
    # Require explicit timezone information instead of silently interpreting local time.
    raw_times = frame["timestamp"].astype(str)
    if not raw_times.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True).all():
        raise ValueError("Each timestamp must include Z or a UTC offset, e.g. +02:00")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if frame["timestamp"].duplicated().any():
        raise ValueError("Duplicate timestamps; provide one turbine per CSV")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    if len(frame) < 200:
        raise ValueError("At least 200 observations are required")
    for col in required[1:]:
        frame[col] = pd.to_numeric(frame[col], errors="raise")
        if not np.isfinite(frame[col].to_numpy()).all():
            raise ValueError(f"Non-finite values in {col}; resolve gaps before fitting")
    if (frame["wind_speed_mps"] < 0).any():
        raise ValueError("Wind speed must be non-negative")
    if not frame["wind_direction_deg"].between(0, 360).all():
        raise ValueError("Wind direction must be between 0 and 360 degrees")
    intervals = frame["timestamp"].diff().dropna()
    if intervals.nunique() != 1 or intervals.iloc[0] <= pd.Timedelta(0):
        raise ValueError("Timestamps must have a regular positive interval; no silent resampling")
    return frame, intervals.iloc[0]


def features(frame: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    result["wind_speed_mps"] = frame["wind_speed_mps"]
    radians = np.deg2rad(frame["wind_direction_deg"])
    result["direction_sin"] = np.sin(radians)
    result["direction_cos"] = np.cos(radians)
    for lag in (0, 1, 2, 3, 6, 12, 24):
        result[f"power_lag_{lag}"] = frame["power_kw"].shift(lag)
    # All windows end at the forecast issue time, including its known measurement.
    result["power_mean_6"] = frame["power_kw"].rolling(6).mean()
    result["wind_mean_6"] = frame["wind_speed_mps"].rolling(6).mean()
    hours = frame["timestamp"].dt.hour + frame["timestamp"].dt.minute / 60
    result["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    result["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    return result


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    residual = np.asarray(predicted) - np.asarray(actual)
    return {"mae_kw": float(np.mean(np.abs(residual))),
            "rmse_kw": float(np.sqrt(np.mean(residual ** 2)))}


def evaluate(frame: pd.DataFrame, horizon: int = 1) -> tuple[dict, pd.DataFrame]:
    if not isinstance(horizon, int) or not 1 <= horizon <= 24:
        raise ValueError("horizon must be an integer between 1 and 24 sampling intervals")
    frame, interval = validate(frame)
    x = features(frame)
    target = frame["power_kw"].shift(-horizon)
    valid = x.notna().all(axis=1) & target.notna()
    indices = frame.index[valid]
    split = int(len(indices) * 0.8)
    # Purge training rows whose future labels reach the test issue-time interval.
    train_idx, test_idx = indices[:split - horizon], indices[split:]
    if len(train_idx) < 100 or len(test_idx) < 20:
        raise ValueError("Insufficient history for this forecast horizon and held-out test")
    model = RandomForestRegressor(n_estimators=64, min_samples_leaf=4,
                                  random_state=42, n_jobs=1)
    model.fit(x.loc[train_idx], target.loc[train_idx])
    prediction = model.predict(x.loc[test_idx])
    baseline = frame.loc[test_idx, "power_kw"].to_numpy()
    actual = target.loc[test_idx].to_numpy()
    latest = len(frame) - 1
    # This model remains frozen at its training cutoff; it is not retrained on test labels.
    latest_prediction = float(model.predict(x.loc[[latest]])[0])
    summary = {
        "implementation": "new educational Random Forest baseline, not original CHPC code",
        "sampling_interval_seconds": interval.total_seconds(),
        "horizon_steps": horizon, "horizon_seconds": (interval * horizon).total_seconds(),
        "training_rows": len(train_idx), "test_rows": len(test_idx),
        "training_last_target_time": str(frame.loc[train_idx[-1] + horizon, "timestamp"]),
        "test_first_issue_time": str(frame.loc[test_idx[0], "timestamp"]),
        "test_last_target_time": str(frame.loc[test_idx[-1] + horizon, "timestamp"]),
        "random_forest": metrics(actual, prediction),
        "persistence": metrics(actual, baseline),
        "latest_observation_time": str(frame.loc[latest, "timestamp"]),
        "latest_observed_power_kw": float(frame.loc[latest, "power_kw"]),
        "forecast_target_time": str(frame.loc[latest, "timestamp"] + horizon * interval),
        "forecast_power_kw": latest_prediction,
        "limitations": "Single temporal holdout; no live feed, uncertainty calibration or operational validation."
    }
    predictions = pd.DataFrame({
        "issue_time": frame.loc[test_idx, "timestamp"].to_numpy(),
        "target_time": frame.loc[test_idx + horizon, "timestamp"].to_numpy(),
        "actual_power_kw": actual, "prediction_power_kw": prediction,
        "persistence_power_kw": baseline,
    })
    return summary, predictions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true", help="Use clearly labelled synthetic data")
    source.add_argument("--csv", type=Path, help="CSV of one turbine's timestamped observations")
    parser.add_argument("--horizon", type=int, default=1, help="Future sampling intervals, 1-24")
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    frame = demo_data() if args.demo else pd.read_csv(args.csv)
    summary, predictions = evaluate(frame, args.horizon)
    summary["data_mode"] = "SYNTHETIC DEMONSTRATION" if args.demo else "USER-SUPPLIED CSV; provenance not verified"
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    predictions.to_csv(args.output / "test_predictions.csv", index=False)
    if args.demo:
        frame.to_csv(args.output / "synthetic_observations.csv", index=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
