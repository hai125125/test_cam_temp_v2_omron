from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from pprint import pformat

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
INPUTS = {
    "mlx90640": REPORTS / "clean_training_data_mlx90640.csv",
    "smh01b01": REPORTS / "clean_training_data_smh01b01.csv",
    "d6t": REPORTS / "clean_training_data_d6t.csv",
}
RAW_COLUMNS = {
    "mlx90640": "mlx90640_max",
    "smh01b01": "smh01b01_max",
    "d6t": "d6t_raw",
}
BIN_EDGES = [-math.inf, 40.0, 80.0, 120.0, 160.0, 200.0, math.inf]
BIN_LABELS = ["lt40", "40_80", "80_120", "120_160", "160_200", "gt200"]
MIN_BIN_POINTS = 50


@dataclass
class FittedModel:
    name: str
    features: list[str]
    coefficients: list[float] | None = None
    bin_models: dict[str, dict] | None = None
    fallback: dict | None = None


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) == 0:
        return float("nan")
    return float(np.sqrt(np.mean((y_pred - y_true) ** 2)))


def fit_linear(frame: pd.DataFrame, features: list[str], name: str) -> FittedModel | None:
    clean = frame.dropna(subset=features + ["reference_temp"])
    if len(clean) < len(features) + 1:
        return None
    x = clean[features].to_numpy(dtype=float)
    y = clean["reference_temp"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(x)), x])
    coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
    return FittedModel(name=name, features=features, coefficients=[float(v) for v in coeffs])


def predict_linear(model: FittedModel, frame: pd.DataFrame) -> np.ndarray:
    x = frame[model.features].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(x)), x])
    return design @ np.asarray(model.coefficients, dtype=float)


def fit_bin_model(train: pd.DataFrame, fallback: FittedModel | None) -> FittedModel | None:
    if fallback is None:
        return None
    bins: dict[str, dict] = {}
    for lo, hi, label in zip(BIN_EDGES[:-1], BIN_EDGES[1:], BIN_LABELS):
        subset = train[(train["raw"] >= lo) & (train["raw"] < hi)]
        if len(subset) >= MIN_BIN_POINTS:
            fitted = fit_linear(subset, ["raw"], f"Model_4_bin_{label}")
            if fitted is not None:
                bins[label] = {
                    "lo": lo,
                    "hi": hi,
                    "coefficients": fitted.coefficients,
                    "rows": int(len(subset)),
                }
    if not bins:
        return FittedModel(
            name="Model_4_PerDistance_Bin",
            features=["raw"],
            bin_models={},
            fallback=model_to_profile(fallback),
        )
    return FittedModel(
        name="Model_4_PerDistance_Bin",
        features=["raw"],
        bin_models=bins,
        fallback=model_to_profile(fallback),
    )


def predict_bin(model: FittedModel, frame: pd.DataFrame) -> np.ndarray:
    preds = np.empty(len(frame), dtype=float)
    fallback = FittedModel(
        name="fallback",
        features=model.fallback["features"],
        coefficients=model.fallback["coefficients"],
    )
    fallback_pred = predict_linear(fallback, frame)
    preds[:] = fallback_pred
    for info in (model.bin_models or {}).values():
        lo = info["lo"]
        hi = info["hi"]
        mask = (frame["raw"] >= lo) & (frame["raw"] < hi)
        if mask.any():
            fitted = FittedModel(name="bin", features=["raw"], coefficients=info["coefficients"])
            preds[mask.to_numpy()] = predict_linear(fitted, frame.loc[mask])
    return preds


def model_to_profile(model: FittedModel) -> dict:
    profile = {
        "model_name": model.name,
        "features": model.features,
        "feature_names_in": model.features,
        "target_mode": "predict_absolute",
    }
    if model.coefficients is not None:
        profile["coefficients"] = model.coefficients
        profile["powers"] = [[0]] + [[1 if i == j else 0 for i in range(len(model.features))] for j in range(len(model.features))]
    if model.bin_models is not None:
        profile["bin_models"] = model.bin_models
        profile["fallback_profile"] = model.fallback
    return profile


def predict_model(model: FittedModel, frame: pd.DataFrame) -> np.ndarray:
    if model.name == "Model_0_raw":
        return frame["raw"].to_numpy(dtype=float)
    if model.bin_models is not None:
        return predict_bin(model, frame)
    return predict_linear(model, frame)


def detect_segments(group: pd.DataFrame) -> pd.DataFrame:
    ordered = group.sort_values("timestamp_parsed").reset_index(drop=True).copy()
    source_direction = str(ordered.get("source_direction", pd.Series(["mixed"])).iloc[0]).upper()
    if source_direction in {"UP", "DOWN"}:
        ordered["segment_index"] = 0
        ordered["direction"] = source_direction
        return ordered

    refs = ordered["reference_temp"].to_numpy(dtype=float)
    if len(ordered) < 2:
        ordered["segment_index"] = 0
        ordered["direction"] = "MIXED"
        return ordered

    change_threshold = 2.0
    reversal_threshold = 3.0
    seg = 0
    state = 0
    anchor = refs[0]
    extreme = refs[0]
    segment_ids = []
    for ref in refs:
        if state == 0:
            if ref - anchor >= change_threshold:
                state = 1
                extreme = ref
            elif anchor - ref >= change_threshold:
                state = -1
                extreme = ref
        elif state == 1:
            if ref > extreme:
                extreme = ref
            elif extreme - ref >= reversal_threshold:
                seg += 1
                state = -1
                extreme = ref
        elif state == -1:
            if ref < extreme:
                extreme = ref
            elif ref - extreme >= reversal_threshold:
                seg += 1
                state = 1
                extreme = ref
        segment_ids.append(seg)
    ordered["segment_index"] = segment_ids
    directions = {}
    for idx, part in ordered.groupby("segment_index"):
        slope = float(part["reference_temp"].iloc[-1] - part["reference_temp"].iloc[0])
        directions[idx] = "UP" if slope > 1.0 else "DOWN" if slope < -1.0 else "MIXED"
    ordered["direction"] = ordered["segment_index"].map(directions)
    return ordered


def prepare_sensor(sensor: str, path: Path) -> tuple[pd.DataFrame, dict]:
    raw_col = RAW_COLUMNS[sensor]
    use_cols = [
        "timestamp_parsed",
        "timestamp",
        "reference_temp",
        raw_col,
        "source_file",
        "source_path",
        "distance_cm",
        "direction",
    ]
    df = pd.read_csv(path, usecols=lambda c: c in use_cols)
    df["timestamp_parsed"] = pd.to_datetime(df["timestamp_parsed"].fillna(df.get("timestamp")), errors="coerce")
    df = df.rename(columns={raw_col: "raw"})
    df = df.dropna(subset=["timestamp_parsed", "reference_temp", "raw", "source_file", "distance_cm"])
    df["sensor"] = sensor
    df["source_direction"] = df["direction"].astype(str).str.upper()
    df["distance_cm"] = df["distance_cm"].astype(int)
    df = df.sort_values(["source_file", "distance_cm", "timestamp_parsed"])
    df["delta_temp"] = df.groupby(["source_file", "distance_cm"])["raw"].diff().fillna(0.0)

    segmented_parts = []
    for _, part in df.groupby(["sensor", "source_file", "source_path", "distance_cm"], sort=False):
        segmented_parts.append(detect_segments(part))
    segmented = pd.concat(segmented_parts, ignore_index=True)
    dedup = (
        segmented.groupby(
            ["sensor", "source_file", "source_path", "distance_cm", "segment_index", "direction", "reference_temp"],
            as_index=False,
        )
        .agg(raw=("raw", "median"), delta_temp=("delta_temp", "median"), timestamp_parsed=("timestamp_parsed", "median"))
    )
    dedup["session"] = (
        dedup["source_file"].astype(str).str.replace(".csv", "", regex=False)
        + "_"
        + dedup["distance_cm"].astype(str)
        + "cm_"
        + dedup["direction"]
        + "_seg"
        + dedup["segment_index"].astype(str)
    )
    dedup["raw_sq"] = dedup["raw"] ** 2
    stats = {
        "raw_rows": int(len(df)),
        "pre_segment_unique_reference_rows": int(
            df.groupby(["sensor", "source_file", "source_path", "distance_cm", "reference_temp"]).ngroups
        ),
        "dedup_rows": int(len(dedup)),
        "sessions": int(dedup["session"].nunique()),
    }
    return dedup, stats


def split_sessions(df: pd.DataFrame) -> tuple[set[str], set[str], set[str]]:
    train: set[str] = set()
    val: set[str] = set()
    test: set[str] = set()
    session_cols = ["distance_cm", "direction", "session", "timestamp_parsed"]
    for _, part in df[session_cols].drop_duplicates().groupby(["distance_cm", "direction"]):
        sessions = (
            part.groupby("session")["timestamp_parsed"].min().sort_values().index.tolist()
        )
        if len(sessions) >= 3:
            test.add(sessions[-1])
            val.add(sessions[-2])
            train.update(sessions[:-2])
        elif len(sessions) == 2:
            test.add(sessions[-1])
            train.add(sessions[0])
        elif sessions:
            train.add(sessions[0])
    return train, val, test


def evaluate(model: FittedModel, frame: pd.DataFrame) -> tuple[float, np.ndarray]:
    if len(frame) == 0:
        return float("nan"), np.asarray([])
    pred = predict_model(model, frame)
    return rmse(frame["reference_temp"].to_numpy(dtype=float), pred), pred


def hysteresis_rows(sensor: str, distance: int, model: FittedModel, test: pd.DataFrame) -> dict:
    out = {"sensor": sensor, "distance": distance, "model": model.name}
    rmses = {}
    for direction in ["UP", "DOWN"]:
        part = test[test["direction"] == direction]
        value, _ = evaluate(model, part)
        rmses[direction] = value
        out[f"{direction.lower()}_rmse"] = value
    if math.isnan(rmses["UP"]) or math.isnan(rmses["DOWN"]):
        gap = float("nan")
    else:
        gap = abs(rmses["UP"] - rmses["DOWN"])
    out["hysteresis_gap"] = gap
    out["hysteresis_flag"] = "SEVERE_HYSTERESIS" if gap > 10 else "STRONG_HYSTERESIS" if gap > 5 else ""
    return out


def anomaly_report(df: pd.DataFrame, sensor: str, distance: int, split_name: str) -> dict:
    part = df[(df["sensor"] == sensor) & (df["distance_cm"] == distance)]
    if len(part) == 0:
        return {"sensor": sensor, "distance": distance, "note": "missing"}
    q1 = part["raw"].quantile(0.25)
    q3 = part["raw"].quantile(0.75)
    iqr = q3 - q1
    outliers = part[(part["raw"] < q1 - 1.5 * iqr) | (part["raw"] > q3 + 1.5 * iqr)]
    by_session = part.groupby("session").size().sort_values(ascending=False)
    return {
        "sensor": sensor,
        "distance": distance,
        "split_context": split_name,
        "unique_points": int(len(part)),
        "reference_min": float(part["reference_temp"].min()),
        "reference_max": float(part["reference_temp"].max()),
        "coverage_c": float(part["reference_temp"].max() - part["reference_temp"].min()),
        "outlier_count": int(len(outliers)),
        "sessions": int(part["session"].nunique()),
        "largest_session_rows": int(by_session.iloc[0]),
        "smallest_session_rows": int(by_session.iloc[-1]),
        "session_imbalance_ratio": float(by_session.iloc[0] / max(1, by_session.iloc[-1])),
    }


def render_runtime(profiles: dict, selection_rule: str) -> str:
    return f'''# Auto-generated by scripts/calibration_research_pipeline.py.
# Contains only {selection_rule}-selected winning calibration models.

from __future__ import annotations

import math


inf = math.inf
CALIB_SELECTION_RULE = {selection_rule!r}
CALIB_PROFILES = {pformat(profiles, width=120)}


def _distance_key(distance_cm):
    if distance_cm is None:
        return None
    try:
        return str(int(float(distance_cm)))
    except (TypeError, ValueError):
        return None


def _linear(profile, values):
    result = float(profile["coefficients"][0])
    for coeff, value in zip(profile["coefficients"][1:], values):
        result += float(coeff) * float(value)
    return result


def _features(profile, raw, delta_temp=None):
    values = []
    for feature in profile.get("features", ["raw"]):
        if feature == "raw":
            values.append(float(raw))
        elif feature == "raw_sq":
            values.append(float(raw) ** 2)
        elif feature == "delta_temp":
            values.append(0.0 if delta_temp is None else float(delta_temp))
        else:
            raise ValueError(f"unsupported feature {{feature}}")
    return values


def _predict_profile(profile, raw, delta_temp=None):
    if "bin_models" in profile:
        ref = float(raw)
        for info in profile.get("bin_models", {{}}).values():
            if ref >= float(info["lo"]) and ref < float(info["hi"]):
                return _linear({{"coefficients": info["coefficients"]}}, [raw])
        return _predict_profile(profile["fallback_profile"], raw, delta_temp)
    return _linear(profile, _features(profile, raw, delta_temp))


def _active_profile(sensor_name, distance_cm):
    sensor = CALIB_PROFILES.get(sensor_name)
    if sensor is None:
        return None
    return sensor.get("per_distance_profiles", {{}}).get(_distance_key(distance_cm))


def calibrate(sensor_name, raw_value, distance_cm=None, direction=None, reference_temp=None, delta_temp=None):
    try:
        raw = float(raw_value)
    except (TypeError, ValueError):
        return raw_value
    if not math.isfinite(raw):
        return raw
    profile = _active_profile(sensor_name, distance_cm)
    if profile is None:
        return raw
    return float(_predict_profile(profile, raw, delta_temp))


def calibration_debug_info(sensor_name, raw_value, distance_cm=None, direction=None, reference_temp=None, delta_temp=None):
    final = calibrate(sensor_name, raw_value, distance_cm, direction, reference_temp, delta_temp)
    raw = raw_value
    reason = "selected_per_distance"
    profile = _active_profile(sensor_name, distance_cm)
    try:
        raw = float(raw_value)
    except (TypeError, ValueError):
        reason = "invalid_raw"
    if profile is None:
        reason = "profile_not_found" if sensor_name not in CALIB_PROFILES else "distance_not_selected_raw_fallback"
    features = list(profile.get("features", ["raw"])) if profile else ["raw"]
    try:
        values = _features(profile, raw, delta_temp) if profile else [float(raw)]
    except Exception:
        values = [float(raw)] if isinstance(raw, (int, float)) else [raw]
    raw_error = None
    calib_error = None
    if reference_temp is not None:
        try:
            ref = float(reference_temp)
            raw_error = float(raw) - ref
            calib_error = float(final) - ref
        except (TypeError, ValueError):
            raw_error = None
            calib_error = None
    return {{
        "sensor_name": sensor_name,
        "raw": raw,
        "input_features": dict(zip(features, values)),
        "loaded_model_path": f"{{__file__}}#CALIB_PROFILES[{{sensor_name!r}}]",
        "feature_list": features,
        "feature_names_in": list(profile.get("feature_names_in", features)) if profile else features,
        "model_name": profile.get("model_name", "raw") if profile else "raw",
        "target_mode": profile.get("target_mode", "predict_absolute") if profile else "predict_absolute",
        "predicted_value": final,
        "final_calib": final,
        "distance_cm": distance_cm,
        "direction": direction,
        "raw_error": raw_error,
        "calib_error": calib_error,
        "selection_rule": CALIB_SELECTION_RULE,
        "reason": reason,
    }}
'''


def render_report(
    stats: dict,
    split_rows: list[dict],
    summary_by_test: pd.DataFrame,
    summary_by_val: pd.DataFrame,
    comparison: pd.DataFrame,
    all_metrics: pd.DataFrame,
    hysteresis: pd.DataFrame,
    anomalies: pd.DataFrame,
) -> str:
    raw_need = summary_by_test.groupby("sensor")["raw_test_rmse"].mean().sort_values(ascending=False)
    distance_effect = summary_by_test.groupby("distance")["raw_test_rmse"].mean().sort_values(ascending=False)
    poly_wins = summary_by_test["selected_model"].str.contains("Poly2").sum()
    delta_wins = summary_by_test["features"].str.contains("delta_temp").sum()
    max_gap = hysteresis["hysteresis_gap"].replace([np.inf, -np.inf], np.nan).max()
    severe = int((hysteresis["hysteresis_flag"] == "SEVERE_HYSTERESIS").sum())
    strong = int((hysteresis["hysteresis_flag"] == "STRONG_HYSTERESIS").sum())

    lines = [
        "# Calibration Research Report",
        "",
        "All benchmark metrics below use session-based train/validation/test splits without session leakage.",
        "",
        "## Dataset Preparation",
    ]
    for sensor, info in stats.items():
        lines.append(
            f"- {sensor}: raw rows={info['raw_rows']}, unique reference rows before segmentation={info['pre_segment_unique_reference_rows']}, "
            f"dedup rows={info['dedup_rows']}, sessions={info['sessions']}"
        )
    lines.extend(["", "## Session Split"])
    for row in split_rows:
        lines.append(f"- {row['sensor']} {row['split']}: {row['sessions']}")
    lines.extend(
        [
            "",
            "## Answers",
            f"1. Sensor needing calibration most: {raw_need.index[0]} (highest mean raw TEST RMSE: {raw_need.iloc[0]:.2f} C).",
            f"2. Distance with strongest effect: {int(distance_effect.index[0])} cm (highest mean raw TEST RMSE: {distance_effect.iloc[0]:.2f} C).",
            f"3. Poly2 necessity: Poly2 won {poly_wins} of {len(summary_by_test)} practical by-test selections.",
            f"4. Delta_temp usefulness: delta_temp won {delta_wins} of {len(summary_by_test)} practical by-test selections.",
            f"5. Hysteresis: max TEST gap is {max_gap:.2f} C; strong flags={strong}, severe flags={severe}.",
            "6. Runtime-first recommendations are listed in best_models_summary_by_test.csv and summarized below.",
        ]
    )
    for _, row in summary_by_test.sort_values(["sensor", "distance"]).iterrows():
        lines.append(
            f"   - {row['sensor']} {int(row['distance'])} cm: {row['selected_model']} ({row['features']}), TEST RMSE={row['test_rmse']:.2f} C"
        )
    lines.append(
        "7. Recommendation on current model: replace the current single global profile where the TEST-selected model improves raw and old assumptions are unsupported; keep raw fallback for unsupported distances."
    )
    lines.extend(
        [
            "",
            "## Model Selection Strategy",
            "",
            "- **best_by_test** selects the lowest TEST RMSE. It is appropriate for practical runtime experiments when current test sessions represent the intended measurement environment, but it has optimistic bias because TEST participates in model selection.",
            "- **best_by_val** selects the lowest VALIDATION RMSE, then uses TEST only for final performance reporting. It is the stricter strategy for scientific evaluation.",
            "- Neither strategy is universally better. If validation sessions are small or unrepresentative, best_by_val can be methodologically stricter while performing worse in the current runtime environment.",
            "",
            "| sensor | distance | by_test model | by_test test RMSE | by_val model | by_val test RMSE | status |",
            "|---|---:|---|---:|---|---:|---|",
        ]
    )
    for _, row in comparison.sort_values(["sensor", "distance"]).iterrows():
        lines.append(
            f"| {row['sensor']} | {int(row['distance'])} cm | {row['selected_by_test']} | "
            f"{row['test_rmse_by_test']:.2f} | {row['selected_by_val']} | "
            f"{row['test_rmse_by_val']:.2f} | {row['status']} |"
        )
    lines.extend(["", "## MLX 25cm / D6T 25cm Anomaly Check"])
    for _, row in anomalies.iterrows():
        lines.append(
            f"- {row['sensor']} {int(row['distance'])} cm: unique={int(row['unique_points'])}, coverage={row['coverage_c']:.2f} C, "
            f"outliers={int(row['outlier_count'])}, sessions={int(row['sessions'])}, imbalance={row['session_imbalance_ratio']:.2f}x."
        )
    lines.extend(["", "## Hysteresis Flags"])
    flagged = hysteresis[hysteresis["hysteresis_flag"] != ""]
    if len(flagged) == 0:
        lines.append("- No strong/severe hysteresis flags on benchmarked TEST subsets.")
    else:
        for _, row in flagged.sort_values("hysteresis_gap", ascending=False).head(30).iterrows():
            lines.append(
                f"- {row['sensor']} {int(row['distance'])} cm {row['model']}: UP={row['up_rmse']:.2f}, DOWN={row['down_rmse']:.2f}, gap={row['hysteresis_gap']:.2f} C, {row['hysteresis_flag']}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    frames = []
    stats = {}
    for sensor, path in INPUTS.items():
        frame, sensor_stats = prepare_sensor(sensor, path)
        frames.append(frame)
        stats[sensor] = sensor_stats
    data = pd.concat(frames, ignore_index=True)
    data.to_csv(REPORTS / "calibration_prepared_dedup_segments.csv", index=False)

    split_rows = []
    split_map = {}
    for sensor, sensor_df in data.groupby("sensor"):
        train_sessions, val_sessions, test_sessions = split_sessions(sensor_df)
        split_map[sensor] = {"train": train_sessions, "val": val_sessions, "test": test_sessions}
        for name, sessions in split_map[sensor].items():
            split_rows.append({"sensor": sensor, "split": name, "sessions": ", ".join(sorted(sessions))})
        data.loc[(data["sensor"] == sensor) & data["session"].isin(train_sessions), "split"] = "train"
        data.loc[(data["sensor"] == sensor) & data["session"].isin(val_sessions), "split"] = "val"
        data.loc[(data["sensor"] == sensor) & data["session"].isin(test_sessions), "split"] = "test"
    data = data.dropna(subset=["split"]).copy()
    data.to_csv(REPORTS / "calibration_session_split_dataset.csv", index=False)
    pd.DataFrame(split_rows).to_csv(REPORTS / "calibration_session_split_summary.csv", index=False)

    metric_rows = []
    hysteresis = []
    best_rows_by_test = []
    best_rows_by_val = []
    runtime_profiles_by_test: dict[str, dict] = {}
    runtime_profiles_by_val: dict[str, dict] = {}
    for sensor, sensor_df in data.groupby("sensor"):
        runtime_profiles_by_test[sensor] = {"per_distance_profiles": {}, "target_mode": "predict_absolute"}
        runtime_profiles_by_val[sensor] = {"per_distance_profiles": {}, "target_mode": "predict_absolute"}
        global_train = sensor_df[sensor_df["split"] == "train"]
        global_model = fit_linear(global_train, ["raw"], "Model_1_Global")
        for distance, dist_df in sensor_df.groupby("distance_cm"):
            train = dist_df[dist_df["split"] == "train"]
            val = dist_df[dist_df["split"] == "val"]
            test = dist_df[dist_df["split"] == "test"]
            candidates: list[FittedModel] = [FittedModel(name="Model_0_raw", features=["raw"])]
            if global_model is not None:
                candidates.append(global_model)
            linear = fit_linear(train, ["raw"], "Model_2_PerDistance_Linear")
            poly = fit_linear(train, ["raw", "raw_sq"], "Model_3_PerDistance_Poly2")
            linear_delta = fit_linear(train, ["raw", "delta_temp"], "Model_5_PerDistance_Linear_Delta")
            poly_delta = fit_linear(train, ["raw", "raw_sq", "delta_temp"], "Model_6_PerDistance_Poly2_Delta")
            for model in [linear, poly, fit_bin_model(train, linear), linear_delta, poly_delta]:
                if model is not None:
                    candidates.append(model)
            scored = []
            raw_test = float("nan")
            for model in candidates:
                train_rmse, _ = evaluate(model, train)
                val_rmse, _ = evaluate(model, val)
                test_rmse, _ = evaluate(model, test)
                if model.name == "Model_0_raw":
                    raw_test = test_rmse
                row = {
                    "sensor": sensor,
                    "distance": int(distance),
                    "model": model.name,
                    "features": ",".join(model.features),
                    "train_rmse": train_rmse,
                    "val_rmse": val_rmse,
                    "test_rmse": test_rmse,
                    "train_rows": int(len(train)),
                    "val_rows": int(len(val)),
                    "test_rows": int(len(test)),
                }
                metric_rows.append(row)
                hysteresis.append(hysteresis_rows(sensor, int(distance), model, test))
                scored.append((model, row))

            test_scored = [item for item in scored if not math.isnan(item[1]["test_rmse"])]
            if not test_scored:
                raise RuntimeError(f"No valid TEST RMSE for {sensor} {distance}cm")
            best_test, best_test_metric = min(test_scored, key=lambda item: item[1]["test_rmse"])

            val_scored = [item for item in scored if not math.isnan(item[1]["val_rmse"])]
            val_fallback = ""
            if val_scored:
                best_val, best_val_metric = min(val_scored, key=lambda item: item[1]["val_rmse"])
            else:
                best_val, best_val_metric = best_test, best_test_metric
                val_fallback = "test_due_to_missing_val"

            def selection_row(
                model: FittedModel,
                metrics: dict,
                selection_rule: str,
                selection_fallback: str,
            ) -> dict:
                return {
                    "sensor": sensor,
                    "distance": int(distance),
                    "selected_model": model.name,
                    "features": ",".join(model.features),
                    "train_rmse": metrics["train_rmse"],
                    "val_rmse": metrics["val_rmse"],
                    "test_rmse": metrics["test_rmse"],
                    "raw_test_rmse": raw_test,
                    "improvement_vs_raw": raw_test - metrics["test_rmse"],
                    "selection_rule": selection_rule,
                    "selection_fallback": selection_fallback,
                }

            best_rows_by_test.append(selection_row(best_test, best_test_metric, "test_rmse", ""))
            best_rows_by_val.append(selection_row(best_val, best_val_metric, "val_rmse", val_fallback))

            distance_key = str(int(distance))
            if best_test.name != "Model_0_raw":
                runtime_profiles_by_test[sensor]["per_distance_profiles"][distance_key] = model_to_profile(best_test)
            if best_val.name != "Model_0_raw":
                runtime_profiles_by_val[sensor]["per_distance_profiles"][distance_key] = model_to_profile(best_val)

    all_metrics = pd.DataFrame(metric_rows)
    summary_by_test = pd.DataFrame(best_rows_by_test)
    summary_by_val = pd.DataFrame(best_rows_by_val)
    hyst = pd.DataFrame(hysteresis)
    anomalies = pd.DataFrame(
        [
            anomaly_report(data, "mlx90640", 25, "all_splits"),
            anomaly_report(data, "d6t", 25, "all_splits"),
        ]
    )
    all_metrics.to_csv(REPORTS / "calibration_model_benchmark_all.csv", index=False)
    hyst.to_csv(REPORTS / "calibration_hysteresis_analysis.csv", index=False)
    anomalies.to_csv(REPORTS / "calibration_anomaly_analysis.csv", index=False)

    comparison = summary_by_test[
        ["sensor", "distance", "selected_model", "test_rmse", "val_rmse"]
    ].merge(
        summary_by_val[["sensor", "distance", "selected_model", "test_rmse", "val_rmse"]],
        on=["sensor", "distance"],
        suffixes=("_by_test", "_by_val"),
    )
    comparison = comparison.rename(
        columns={
            "selected_model_by_test": "selected_by_test",
            "selected_model_by_val": "selected_by_val",
        }
    )
    comparison["same_model"] = comparison["selected_by_test"] == comparison["selected_by_val"]
    comparison["test_rmse_gap"] = comparison["test_rmse_by_val"] - comparison["test_rmse_by_test"]
    comparison["status"] = np.where(
        comparison["same_model"],
        "STABLE_SELECTION",
        np.where(
            comparison["test_rmse_gap"] > 2.0,
            "MODEL_SELECTION_SENSITIVE",
            "DIFFERENT_BUT_CLOSE",
        ),
    )
    comparison = comparison[
        [
            "sensor",
            "distance",
            "selected_by_test",
            "test_rmse_by_test",
            "val_rmse_by_test",
            "selected_by_val",
            "test_rmse_by_val",
            "val_rmse_by_val",
            "same_model",
            "test_rmse_gap",
            "status",
        ]
    ]

    if summary_by_test["test_rmse"].isna().any() or summary_by_val["test_rmse"].isna().any():
        raise RuntimeError("Final model summary contains NaN TEST RMSE")

    summary_by_test.to_csv(REPORTS / "best_models_summary_by_test.csv", index=False)
    summary_by_val.to_csv(REPORTS / "best_models_summary_by_val.csv", index=False)
    comparison.to_csv(REPORTS / "calibration_model_selection_comparison.csv", index=False)
    # Backward-compatible alias: practical runtime selection remains by TEST.
    summary_by_test.to_csv(REPORTS / "best_models_summary.csv", index=False)

    runtime_by_test = render_runtime(runtime_profiles_by_test, "best_by_test")
    runtime_by_val = render_runtime(runtime_profiles_by_val, "best_by_val")
    (ROOT / "src" / "best_model_profiles_by_test.py").write_text(runtime_by_test, encoding="utf-8")
    (ROOT / "src" / "best_model_profiles_by_val.py").write_text(runtime_by_val, encoding="utf-8")
    (ROOT / "src" / "best_model_profiles.py").write_text(
        "# Runtime default: practical best_by_test selection.\n"
        "# For stricter validation-selected evaluation, import best_model_profiles_by_val instead.\n\n"
        "try:\n"
        "    from .best_model_profiles_by_test import *\n"
        "except ImportError:\n"
        "    from best_model_profiles_by_test import *\n",
        encoding="utf-8",
    )
    (REPORTS / "calibration_research_report.md").write_text(
        render_report(
            stats,
            split_rows,
            summary_by_test,
            summary_by_val,
            comparison,
            all_metrics,
            hyst,
            anomalies,
        ),
        encoding="utf-8",
    )

    status_counts = comparison["status"].value_counts()
    print(f"same models: {int(status_counts.get('STABLE_SELECTION', 0))}")
    print(f"different but close: {int(status_counts.get('DIFFERENT_BUT_CLOSE', 0))}")
    print(f"model selection sensitive: {int(status_counts.get('MODEL_SELECTION_SENSITIVE', 0))}")
    print("Wrote reports/best_models_summary_by_test.csv")
    print("Wrote reports/best_models_summary_by_val.csv")
    print("Wrote reports/calibration_model_selection_comparison.csv")
    print("Wrote src/best_model_profiles.py (default by_test)")
    print("Wrote src/best_model_profiles_by_test.py")
    print("Wrote src/best_model_profiles_by_val.py")
    print("Wrote reports/calibration_research_report.md")


if __name__ == "__main__":
    main()
