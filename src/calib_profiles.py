# Polynomial calibration profiles exported from notebooks/train_calibration.ipynb.
# generated_from_clean_data = True
# cleaning_rules_used = ['nan_or_non_finite', 'physical_range', 'time_step_spike', 'residual_mad_iqr_outlier', 'rolling_median_outlier']
# rows_raw = 279063
# rows_clean = 272873
# rows_removed = 6190
# rows_are_sensor_samples = True
#
# Runtime intentionally depends only on the Python standard library.

from __future__ import annotations

import logging
import math

logger = logging.getLogger("calib")

CALIB_PROFILE_SOURCE = __file__
CALIB_DISTANCE_SUPPORT_TOLERANCE_C = 2.0
CALIB_LARGE_CORRECTION_WARN_C = 10.0
CALIB_GENERATED_FROM_CLEAN_DATA = True
CALIB_CLEANING_RULES_USED = ['nan_or_non_finite', 'physical_range', 'time_step_spike', 'residual_mad_iqr_outlier', 'rolling_median_outlier']
CALIB_ROWS_RAW = 279063
CALIB_ROWS_CLEAN = 272873
CALIB_ROWS_REMOVED = 6190
CALIB_ROWS_ARE_SENSOR_SAMPLES = True

CALIB_PROFILES = {'d6t': {'coefficients': [-7.614812624731626,
                          0.9194681702821174,
                          -0.04105244823004192,
                          -0.0005104964457284256,
                          0.01121664124328417,
                          0.01357161999687026],
         'degree': 2,
         'fallback_metrics': {'MAE': 8.257745688506446,
                              'MAE_improvement': 2.1054263545043064,
                              'MAE_raw': 10.363172043010753,
                              'R2': 0.9711145920863177,
                              'RMSE': 11.299025440872072,
                              'mean_abs_pct_of_gdm': 8.213248648182114,
                              'pass_training_goal': True},
         'fallback_profile': {'coefficients': [-4.016657128960947,
                                               1.259841888839952,
                                               -0.0010301519461868303],
                              'degree': 2,
                              'feature_names_in': ['raw'],
                              'features': ['raw'],
                              'model_name': 'poly2_raw',
                              'powers': [[0], [1], [2]],
                              'target_mode': 'predict_absolute',
                              'uses_direction': False},
         'feature_names_in': ['raw', 'distance_cm'],
         'features': ['raw', 'distance_cm'],
         'metrics': {'MAE': 3.8745086992012223,
                     'MAE_improvement': 6.488663343809531,
                     'MAE_raw': 10.363172043010753,
                     'R2': 0.9926582092291399,
                     'RMSE': 5.6964296182473975,
                     'mean_abs_pct_of_gdm': 4.4036964328823505,
                     'pass_improves_raw': True,
                     'pass_training_goal': True,
                     'pass_under_5pct_gdm': True},
         'model_name': 'poly2_raw_distance',
         'powers': [[0, 0], [1, 0], [0, 1], [2, 0], [1, 1], [0, 2]],
         'target_mode': 'predict_absolute',
         'training_support': {'15': {'raw_max': 240.0,
                                     'raw_min': 46.1,
                                     'reference_max': 243.4,
                                     'reference_min': 46.0,
                                     'rows': 18024},
                              '20': {'raw_max': 232.0,
                                     'raw_min': 25.6,
                                     'reference_max': 244.4,
                                     'reference_min': 24.6,
                                     'rows': 36361},
                              '25': {'raw_max': 226.0,
                                     'raw_min': 26.3,
                                     'reference_max': 241.0,
                                     'reference_min': 24.6,
                                     'rows': 19893},
                              '30': {'raw_max': 220.9,
                                     'raw_min': 27.9,
                                     'reference_max': 244.2,
                                     'reference_min': 29.1,
                                     'rows': 18692}},
         'uses_direction': False},
 'mlx90640': {'coefficients': [-34.19218527734094,
                               1.0014358724804386,
                               2.428275339861943,
                               -0.0003209777041721651,
                               0.002103693449028471,
                               -0.045710608923833204],
              'degree': 2,
              'fallback_metrics': {'MAE': 3.930663023814301,
                                   'MAE_improvement': 1.0777544656074203,
                                   'MAE_raw': 5.0084174894217215,
                                   'R2': 0.9936331167077886,
                                   'RMSE': 5.123067996134734,
                                   'mean_abs_pct_of_gdm': 5.288313309109973,
                                   'pass_training_goal': True},
              'fallback_profile': {'coefficients': [0.313560940025974, 0.9602520555568955],
                                   'degree': 1,
                                   'feature_names_in': ['raw'],
                                   'features': ['raw'],
                                   'model_name': 'linear_raw',
                                   'powers': [[0], [1]],
                                   'target_mode': 'predict_absolute',
                                   'uses_direction': False},
              'feature_names_in': ['raw', 'distance_cm'],
              'features': ['raw', 'distance_cm'],
              'metrics': {'MAE': 2.8941263903334136,
                          'MAE_improvement': 2.114291099088308,
                          'MAE_raw': 5.0084174894217215,
                          'R2': 0.9966135927906365,
                          'RMSE': 3.7362529036667036,
                          'mean_abs_pct_of_gdm': 3.641797166867279,
                          'pass_improves_raw': True,
                          'pass_training_goal': True,
                          'pass_under_5pct_gdm': True},
              'model_name': 'poly2_raw_distance',
              'powers': [[0, 0], [1, 0], [0, 1], [2, 0], [1, 1], [0, 2]],
              'target_mode': 'predict_absolute',
              'training_support': {'15': {'raw_max': 249.95,
                                          'raw_min': 50.11,
                                          'reference_max': 234.2,
                                          'reference_min': 46.0,
                                          'rows': 16595},
                                   '20': {'raw_max': 249.97,
                                          'raw_min': 29.7,
                                          'reference_max': 242.0,
                                          'reference_min': 24.6,
                                          'rows': 34568},
                                   '25': {'raw_max': 247.4,
                                          'raw_min': 30.68,
                                          'reference_max': 241.0,
                                          'reference_min': 24.6,
                                          'rows': 18830},
                                   '30': {'raw_max': 249.99,
                                          'raw_min': 33.55,
                                          'reference_max': 243.8,
                                          'reference_min': 29.1,
                                          'rows': 18618}},
              'uses_direction': False},
 'smh01b01': {'coefficients': [-29.4809772811476,
                               1.077478348020464,
                               2.011308957959356,
                               -0.0006657127612410552,
                               0.00364938978996196,
                               -0.03720231657348356],
              'degree': 2,
              'fallback_metrics': {'MAE': 4.471962888829355,
                                   'MAE_improvement': 0.8878597130103296,
                                   'MAE_raw': 5.359822601839685,
                                   'R2': 0.9917287199073608,
                                   'RMSE': 5.962307849511915,
                                   'mean_abs_pct_of_gdm': 5.119741571677699,
                                   'pass_training_goal': True},
              'fallback_profile': {'coefficients': [-2.9453230540235027,
                                                    1.140092595423462,
                                                    -0.0006204794897959331],
                                   'degree': 2,
                                   'feature_names_in': ['raw'],
                                   'features': ['raw'],
                                   'model_name': 'poly2_raw',
                                   'powers': [[0], [1], [2]],
                                   'target_mode': 'predict_absolute',
                                   'uses_direction': False},
              'feature_names_in': ['raw', 'distance_cm'],
              'features': ['raw', 'distance_cm'],
              'metrics': {'MAE': 3.213095011435385,
                          'MAE_improvement': 2.1467275904043,
                          'MAE_raw': 5.359822601839685,
                          'R2': 0.9957100506102474,
                          'RMSE': 4.293921657831535,
                          'mean_abs_pct_of_gdm': 3.688043333895984,
                          'pass_improves_raw': True,
                          'pass_training_goal': True,
                          'pass_under_5pct_gdm': True},
              'model_name': 'poly2_raw_distance',
              'powers': [[0, 0], [1, 0], [0, 1], [2, 0], [1, 1], [0, 2]],
              'target_mode': 'predict_absolute',
              'training_support': {'15': {'raw_max': 250.0,
                                          'raw_min': 46.3,
                                          'reference_max': 240.3,
                                          'reference_min': 46.0,
                                          'rows': 16953},
                                   '20': {'raw_max': 249.8,
                                          'raw_min': 26.8,
                                          'reference_max': 244.4,
                                          'reference_min': 24.6,
                                          'rows': 35736},
                                   '25': {'raw_max': 246.0,
                                          'raw_min': 27.3,
                                          'reference_max': 241.0,
                                          'reference_min': 24.6,
                                          'rows': 19893},
                                   '30': {'raw_max': 239.3,
                                          'raw_min': 29.4,
                                          'reference_max': 244.2,
                                          'reference_min': 29.1,
                                          'rows': 18710}},
              'uses_direction': False}}

def _feature_values(profile: dict, raw: float, distance_cm: int | float | None) -> list[float] | None:
    values = []
    for feature in profile["features"]:
        if feature == "raw":
            values.append(raw)
        elif feature == "distance_cm":
            if distance_cm is None:
                return None
            values.append(float(distance_cm))
        else:
            return None
    return values


def _predict_profile(profile: dict, values: list[float]) -> float:
    result = 0.0
    for coefficient, powers in zip(profile["coefficients"], profile["powers"]):
        term = float(coefficient)
        for value, power in zip(values, powers):
            if power:
                term *= value ** int(power)
        result += term
    return result


def _distance_support(profile: dict, distance_cm: int | float | None) -> dict | None:
    if distance_cm is None:
        return None
    try:
        key = str(int(float(distance_cm)))
    except (TypeError, ValueError):
        return None
    return profile.get("training_support", {}).get(key)


def _distance_key(distance_cm: int | float | None) -> str | None:
    if distance_cm is None:
        return None
    try:
        return str(int(float(distance_cm)))
    except (TypeError, ValueError):
        return None


def _per_distance_prediction(profile: dict, raw: float, distance_cm: int | float | None) -> tuple[dict | None, float, str]:
    distance_profiles = profile.get("per_distance_profiles") or {}
    if not distance_profiles:
        return None, raw, "no_per_distance_profiles"
    key = _distance_key(distance_cm)
    if key is not None and key in distance_profiles:
        active = distance_profiles[key]
        values = _feature_values(active, raw, distance_cm)
        return active, _predict_profile(active, values if values is not None else [raw]), "per_distance_exact"
    if key is None:
        fallback = profile.get("fallback_profile")
        if fallback is not None:
            values = _feature_values(fallback, raw, distance_cm)
            return fallback, _predict_profile(fallback, values if values is not None else [raw]), "fallback_without_distance"
        return None, raw, "distance_missing_raw_fallback"

    requested = float(distance_cm)
    available = sorted((float(k), k) for k in distance_profiles)
    lower = [item for item in available if item[0] <= requested]
    upper = [item for item in available if item[0] >= requested]
    if lower and upper and lower[-1][1] != upper[0][1]:
        lo_value, lo_key = lower[-1]
        hi_value, hi_key = upper[0]
        lo_profile = distance_profiles[lo_key]
        hi_profile = distance_profiles[hi_key]
        lo_pred = _predict_profile(lo_profile, _feature_values(lo_profile, raw, distance_cm) or [raw])
        hi_pred = _predict_profile(hi_profile, _feature_values(hi_profile, raw, distance_cm) or [raw])
        ratio = (requested - lo_value) / (hi_value - lo_value)
        active = {
            "model_name": f"interpolate_{lo_key}_{hi_key}cm",
            "features": ["raw"],
            "feature_names_in": ["raw"],
            "target_mode": profile.get("target_mode", "predict_absolute"),
        }
        return active, lo_pred + ratio * (hi_pred - lo_pred), "per_distance_interpolated"

    nearest_value, nearest_key = min(available, key=lambda item: abs(item[0] - requested))
    active = distance_profiles[nearest_key]
    values = _feature_values(active, raw, distance_cm)
    logger.warning(
        "[CALIB] sensor profile distance=%s outside trained range, using nearest %scm",
        distance_cm,
        nearest_key,
    )
    return active, _predict_profile(active, values if values is not None else [raw]), "per_distance_nearest"


def calibration_debug_info(
    sensor_name: str,
    raw_value: float,
    distance_cm: int | float | None,
    direction=None,
    reference_temp: float | None = None,
) -> dict:
    profile = CALIB_PROFILES.get(sensor_name)
    try:
        raw = float(raw_value)
    except (TypeError, ValueError):
        logger.warning("[CALIB] invalid raw value for sensor=%s, using raw value", sensor_name)
        return {"sensor_name": sensor_name, "raw": raw_value, "final_calib": raw_value, "reason": "invalid_raw"}
    if profile is None:
        logger.warning("[CALIB] profile not found, using raw value")
        return {"sensor_name": sensor_name, "raw": raw, "final_calib": raw, "reason": "profile_not_found"}
    if not math.isfinite(raw):
        return {"sensor_name": sensor_name, "raw": raw, "final_calib": raw, "reason": "raw_not_finite"}

    active_profile = profile
    mode = profile.get("target_mode", "predict_absolute")
    reason = "primary"
    requires_distance = "distance_cm" in profile.get("features", [])
    support = _distance_support(profile, distance_cm)
    if profile.get("per_distance_profiles"):
        active_profile, predicted, reason = _per_distance_prediction(profile, raw, distance_cm)
        values = _feature_values(active_profile, raw, distance_cm) if active_profile is not None else [raw]
        final = float(predicted) if math.isfinite(predicted) else raw
        if mode == "predict_delta":
            final = raw + final
        support = _distance_support(profile, distance_cm)
        raw_error = None
        calib_error = None
        if reference_temp is not None:
            try:
                ref = float(reference_temp)
                raw_error = raw - ref
                calib_error = final - ref
            except (TypeError, ValueError):
                raw_error = None
                calib_error = None
        info = {
            "sensor_name": sensor_name,
            "raw": raw,
            "input_features": dict(zip(active_profile.get("features", ["raw"]) if active_profile else ["raw"], values if values is not None else [raw])),
            "loaded_model_path": f"{CALIB_PROFILE_SOURCE}#CALIB_PROFILES[{sensor_name!r}]",
            "feature_list": list(active_profile.get("features", [])) if active_profile else ["raw"],
            "feature_names_in": list(active_profile.get("feature_names_in", active_profile.get("features", []))) if active_profile else ["raw"],
            "model_name": active_profile.get("model_name", "raw_fallback") if active_profile else "raw_fallback",
            "target_mode": active_profile.get("target_mode", mode) if active_profile else mode,
            "predicted_value": float(predicted) if math.isfinite(predicted) else raw,
            "final_calib": final,
            "raw_error": raw_error,
            "calib_error": calib_error,
            "reason": reason,
            "distance_cm": distance_cm,
            "direction": direction,
            "training_support": support,
        }
        logger.debug(
            "[CALIB DEBUG] sensor=%s raw=%.2f input_features=%s model_path=%s "
            "feature_list=%s feature_names_in=%s model=%s target_mode=%s predicted=%.2f final=%.2f "
            "raw_error=%s calib_error=%s reason=%s",
            info["sensor_name"],
            info["raw"],
            info["input_features"],
            info["loaded_model_path"],
            info["feature_list"],
            info["feature_names_in"],
            info["model_name"],
            info["target_mode"],
            info["predicted_value"],
            info["final_calib"],
            None if raw_error is None else f"{raw_error:+.2f}",
            None if calib_error is None else f"{calib_error:+.2f}",
            info["reason"],
        )
        if abs(final - raw) > CALIB_LARGE_CORRECTION_WARN_C:
            logger.warning(
                "[WARN] %s calibration correction too large raw=%.2f calib=%.2f correction=%+.2fC",
                sensor_name.upper(),
                raw,
                final,
                final - raw,
            )
        if sensor_name == "d6t" and raw_error is not None and calib_error is not None and abs(calib_error) > abs(raw_error) + 5.0:
            logger.warning(
                "[WARN] D6T calibration worse than raw raw=%.2f calib=%.2f ref=%.2f raw_error=%+.2f calib_error=%+.2f",
                raw,
                final,
                float(reference_temp),
                raw_error,
                calib_error,
            )
        return info

    if requires_distance and distance_cm is None:
        fallback = profile.get("fallback_profile")
        if fallback is not None:
            active_profile = fallback
            reason = "fallback_without_distance"
            logger.warning("[CALIB] distance_cm missing for sensor=%s, using model_without_distance", sensor_name)
        else:
            logger.warning("[CALIB] distance_cm missing for sensor=%s, using raw value", sensor_name)
            active_profile = None
            reason = "distance_missing_raw_fallback"
    elif requires_distance and support is None:
        fallback = profile.get("fallback_profile")
        if fallback is not None:
            active_profile = fallback
            reason = "fallback_unsupported_distance"
            logger.warning(
                "[CALIB] sensor=%s distance=%s has no training support, using model_without_distance",
                sensor_name,
                distance_cm,
            )
        else:
            active_profile = None
            reason = "unsupported_distance_raw_fallback"
    elif requires_distance and support is not None:
        raw_min = float(support["raw_min"]) - CALIB_DISTANCE_SUPPORT_TOLERANCE_C
        raw_max = float(support["raw_max"]) + CALIB_DISTANCE_SUPPORT_TOLERANCE_C
        if raw < raw_min or raw > raw_max:
            if sensor_name == "d6t":
                active_profile = None
                reason = "raw_outside_distance_support_raw_fallback"
            else:
                active_profile = profile.get("fallback_profile")
                reason = "raw_outside_distance_support_fallback_without_distance"
            logger.warning(
                "[CALIB] sensor=%s raw=%.2f outside training support for distance=%s "
                "raw_range=%.2f..%.2f rows=%s reason=%s",
                sensor_name,
                raw,
                distance_cm,
                float(support["raw_min"]),
                float(support["raw_max"]),
                support.get("rows"),
                reason,
            )

    values = _feature_values(active_profile, raw, distance_cm) if active_profile is not None else None
    predicted = _predict_profile(active_profile, values) if values is not None else raw
    final = float(predicted) if math.isfinite(predicted) else raw
    if mode == "predict_delta":
        final = raw + final

    raw_error = None
    calib_error = None
    if reference_temp is not None:
        try:
            ref = float(reference_temp)
            raw_error = raw - ref
            calib_error = final - ref
        except (TypeError, ValueError):
            raw_error = None
            calib_error = None

    info = {
        "sensor_name": sensor_name,
        "raw": raw,
        "input_features": dict(zip(active_profile.get("features", ["raw"]) if active_profile else ["raw"], values if values is not None else [raw])),
        "loaded_model_path": f"{CALIB_PROFILE_SOURCE}#CALIB_PROFILES[{sensor_name!r}]",
        "feature_list": list(active_profile.get("features", [])) if active_profile else ["raw"],
        "feature_names_in": list(active_profile.get("feature_names_in", active_profile.get("features", []))) if active_profile else ["raw"],
        "model_name": active_profile.get("model_name", "raw_fallback") if active_profile else "raw_fallback",
        "target_mode": active_profile.get("target_mode", mode) if active_profile else mode,
        "predicted_value": float(predicted) if math.isfinite(predicted) else raw,
        "final_calib": final,
        "raw_error": raw_error,
        "calib_error": calib_error,
        "reason": reason,
        "distance_cm": distance_cm,
        "direction": direction,
        "training_support": support,
    }
    logger.debug(
        "[CALIB DEBUG] sensor=%s raw=%.2f input_features=%s model_path=%s "
        "feature_list=%s feature_names_in=%s model=%s target_mode=%s predicted=%.2f final=%.2f "
        "raw_error=%s calib_error=%s reason=%s",
        info["sensor_name"],
        info["raw"],
        info["input_features"],
        info["loaded_model_path"],
        info["feature_list"],
        info["feature_names_in"],
        info["model_name"],
        info["target_mode"],
        info["predicted_value"],
        info["final_calib"],
        None if raw_error is None else f"{raw_error:+.2f}",
        None if calib_error is None else f"{calib_error:+.2f}",
        info["reason"],
    )
    if abs(final - raw) > CALIB_LARGE_CORRECTION_WARN_C:
        logger.warning(
            "[WARN] %s calibration correction too large raw=%.2f calib=%.2f correction=%+.2fC",
            sensor_name.upper(),
            raw,
            final,
            final - raw,
        )
    if sensor_name == "d6t" and raw_error is not None and calib_error is not None and abs(calib_error) > abs(raw_error) + 5.0:
        logger.warning(
            "[WARN] D6T calibration worse than raw raw=%.2f calib=%.2f ref=%.2f raw_error=%+.2f calib_error=%+.2f",
            raw,
            final,
            float(reference_temp),
            raw_error,
            calib_error,
        )
    return info


def calibrate(
    sensor_name: str,
    raw_value: float,
    distance_cm: int | float | None,
    direction=None,
    reference_temp: float | None = None,
) -> float:
    return calibration_debug_info(sensor_name, raw_value, distance_cm, direction, reference_temp)["final_calib"]
