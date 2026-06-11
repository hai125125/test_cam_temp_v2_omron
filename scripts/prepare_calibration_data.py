from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

MIN_TEMP = 20.0
MAX_TEMP = 250.0
MAX_STEP_REF = 8.0
MAX_STEP_SENSOR = 15.0
ROBUST_Z_LIMIT = 4.0
ROLLING_WINDOW = 15
ROLLING_DEV_REF = 5.0
ROLLING_DEV_SENSOR = 10.0

SIMPLE_CSV_RE = re.compile(r"^log_(?P<distance>\d+)cm(?:_(?P<session>[^.]+))?\.csv$", re.IGNORECASE)
RANGED_CSV_RE = re.compile(
    r"^log_(?P<distance>\d+)cm_(?P<start>\d+(?:\.\d+)?)_to_"
    r"(?P<end>\d+(?:\.\d+)?)(?:_(?P<session>[^.]+))?\.csv$",
    re.IGNORECASE,
)
SENSORS = {
    "mlx90640": "mlx90640_max",
    "smh01b01": "smh01b01_max",
    "d6t": "d6t_raw",
}
REQUIRED_COLUMNS = ["timestamp", "reference_temp", "mlx90640_max", "smh01b01_max", "d6t_raw"]
DISABLE_RESIDUAL_OUTLIER_FOR_SENSORS = {"d6t"}


def parse_file_meta(path: Path) -> dict | None:
    ranged = RANGED_CSV_RE.match(path.name)
    if ranged:
        start = float(ranged.group("start"))
        end = float(ranged.group("end"))
        return {
            "source_file": path.name,
            "source_path": str(path.relative_to(ROOT)),
            "distance_cm": int(ranged.group("distance")),
            "range_start_c": start,
            "range_end_c": end,
            "direction": "up" if start < end else "down",
            "filename_format": "ranged",
            "csv_format": "training",
        }
    simple = SIMPLE_CSV_RE.match(path.name)
    if simple and not path.stem.endswith("_calib"):
        return {
            "source_file": path.name,
            "source_path": str(path.relative_to(ROOT)),
            "distance_cm": int(simple.group("distance")),
            "range_start_c": np.nan,
            "range_end_c": np.nan,
            "direction": "mixed",
            "filename_format": "simple",
            "csv_format": "training",
        }
    return None


def discover_training_files() -> tuple[list[Path], list[dict]]:
    loaded = []
    skipped = []
    seen_hashes: dict[str, str] = {}
    for path in sorted(ROOT.glob("log_*.csv")):
        meta = parse_file_meta(path)
        if meta is None:
            skipped.append({"source_path": path.name, "reason": "not a training filename"})
            continue
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if content_hash in seen_hashes:
            skipped.append(
                {
                    "source_path": path.name,
                    "reason": f"duplicate content of {seen_hashes[content_hash]}",
                }
            )
            continue
        seen_hashes[content_hash] = path.name
        loaded.append(path)
    return loaded, skipped


def load_raw_data(paths: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames = []
    file_rows = []
    for path in paths:
        meta = parse_file_meta(path)
        data = pd.read_csv(path)
        missing = set(REQUIRED_COLUMNS) - set(data.columns)
        if missing:
            raise ValueError(f"{path.name} missing columns: {sorted(missing)}")
        out = data[REQUIRED_COLUMNS].copy()
        out["d6t_calib_old"] = np.nan
        out["diff_d6t_report_raw"] = np.nan
        out["diff_d6t_report_calib"] = np.nan
        out["report_result"] = np.nan
        for key, value in meta.items():
            out[key] = value
        frames.append(out)
        file_rows.append({**meta, "rows": len(out)})
    if not frames:
        raise RuntimeError("No calibration training CSV files found")

    raw = pd.concat(frames, ignore_index=True)
    numeric = [
        "reference_temp",
        "mlx90640_max",
        "smh01b01_max",
        "d6t_raw",
        "distance_cm",
    ]
    for column in numeric:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    raw["timestamp_parsed"] = pd.to_datetime(raw["timestamp"], errors="coerce")
    for sensor, raw_col in SENSORS.items():
        raw[f"diff_{sensor}_raw"] = raw[raw_col] - raw["reference_temp"]
    return raw, pd.DataFrame(file_rows)


def append_reason(reasons: pd.Series, mask: pd.Series, reason: str) -> pd.Series:
    mask = mask.fillna(False)
    reasons.loc[mask] = np.where(
        reasons.loc[mask].astype(str).str.len().gt(0),
        reasons.loc[mask].astype(str) + "|" + reason,
        reason,
    )
    return reasons


def finite_mask(data: pd.DataFrame, columns: list[str]) -> pd.Series:
    values = data[columns].to_numpy(dtype=float)
    return pd.Series(np.isfinite(values).all(axis=1), index=data.index)


def mark_iqr_outliers(values: pd.Series, limit: float = 1.5) -> pd.Series:
    q1 = values.quantile(0.25)
    q3 = values.quantile(0.75)
    iqr = q3 - q1
    if not np.isfinite(iqr) or iqr == 0:
        return pd.Series(False, index=values.index)
    return values.lt(q1 - limit * iqr) | values.gt(q3 + limit * iqr)


def mark_robust_outliers(values: pd.Series) -> pd.Series:
    values = pd.to_numeric(values, errors="coerce")
    valid = values.dropna()
    if len(valid) < 8:
        return pd.Series(False, index=values.index)
    median = valid.median()
    mad = (valid - median).abs().median()
    if np.isfinite(mad) and mad > 0:
        return (0.6745 * (values - median) / mad).abs().gt(ROBUST_Z_LIMIT).fillna(False)
    return mark_iqr_outliers(values)


def clean_sensor(data: pd.DataFrame, sensor: str, raw_col: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    primary = ["reference_temp", "distance_cm", raw_col]
    candidate = data[primary].notna().all(axis=1) & finite_mask(data, primary)
    working = data.loc[candidate].copy()
    reasons = pd.Series("", index=working.index, dtype="object")

    range_mask = (
        working["reference_temp"].lt(MIN_TEMP)
        | working["reference_temp"].gt(MAX_TEMP)
        | working[raw_col].lt(MIN_TEMP)
        | working[raw_col].gt(MAX_TEMP)
    )
    reasons = append_reason(reasons, range_mask, "physical_range")

    ordered = working.sort_values(["source_path", "timestamp_parsed", "timestamp"], kind="mergesort")
    step_mask = pd.Series(False, index=working.index)
    rolling_mask = pd.Series(False, index=working.index)
    for _, group in ordered.groupby("source_path", sort=False):
        for column, step_limit, rolling_limit in (
            ("reference_temp", MAX_STEP_REF, ROLLING_DEV_REF),
            (raw_col, MAX_STEP_SENSOR, ROLLING_DEV_SENSOR),
        ):
            step_mask.loc[group.index] |= group[column].diff().abs().gt(step_limit).fillna(False)
            rolling = group[column].rolling(
                ROLLING_WINDOW,
                center=True,
                min_periods=max(5, ROLLING_WINDOW // 3),
            ).median()
            rolling_mask.loc[group.index] |= (group[column] - rolling).abs().gt(rolling_limit).fillna(False)
    reasons = append_reason(reasons, step_mask, "time_step_spike")
    reasons = append_reason(reasons, rolling_mask, "rolling_median_outlier")

    diff_col = f"diff_{sensor}_raw"
    working[diff_col] = working[raw_col] - working["reference_temp"]
    if sensor not in DISABLE_RESIDUAL_OUTLIER_FOR_SENSORS:
        residual_mask = pd.Series(False, index=working.index)
        # A whole session may have a real offset caused by distance or hysteresis.
        # Detect isolated residual anomalies within each session instead of
        # rejecting a valid session because it differs from older sessions.
        for _, group in working.groupby(["source_path", "distance_cm"], dropna=False):
            residual_mask.loc[group.index] |= mark_robust_outliers(group[diff_col])
        reasons = append_reason(reasons, residual_mask, "residual_mad_iqr_outlier")

    working["sensor"] = sensor
    working["reject_reason"] = reasons.replace("", np.nan)
    rejected = working[working["reject_reason"].notna()].copy()
    clean = working[working["reject_reason"].isna()].copy()
    stats = {
        "sensor": sensor,
        "rows_raw": int(len(working)),
        "rows_clean": int(len(clean)),
        "rows_removed": int(len(rejected)),
        "rows_skipped_missing_sensor": int((~candidate).sum()),
        "removed_pct": float(len(rejected) / len(working) * 100) if len(working) else 0.0,
    }
    return clean, rejected, stats


def main() -> None:
    paths, skipped = discover_training_files()
    raw, file_summary = load_raw_data(paths)
    clean_by_sensor = {}
    rejected_parts = []
    stats = []
    for sensor, raw_col in SENSORS.items():
        clean, rejected, sensor_stats = clean_sensor(raw, sensor, raw_col)
        clean_by_sensor[sensor] = clean
        rejected_parts.append(rejected)
        stats.append(sensor_stats)

    rejected = pd.concat(rejected_parts, ignore_index=True)
    rejected_columns = [
        "sensor",
        "source_file",
        "source_path",
        "timestamp",
        "distance_cm",
        "direction",
        "csv_format",
        "reference_temp",
        "mlx90640_max",
        "smh01b01_max",
        "d6t_raw",
        "reject_reason",
    ]
    rejected[rejected_columns].to_csv(REPORTS / "rejected_samples.csv", index=False)
    for sensor, clean in clean_by_sensor.items():
        clean.drop(columns=["reject_reason"]).to_csv(
            REPORTS / f"clean_training_data_{sensor}.csv",
            index=False,
        )
    pd.DataFrame(stats).to_csv(REPORTS / "calibration_cleaning_stats.csv", index=False)
    file_summary.to_csv(REPORTS / "calibration_training_file_summary.csv", index=False)
    pd.DataFrame(skipped).to_csv(REPORTS / "calibration_skipped_files.csv", index=False)

    print(f"Loaded training files: {len(paths)}")
    for path in paths:
        print(f"  {path.name}")
    for row in stats:
        print(
            f"{row['sensor']}: raw={row['rows_raw']} clean={row['rows_clean']} "
            f"removed={row['rows_removed']} ({row['removed_pct']:.2f}%)"
        )


if __name__ == "__main__":
    main()
