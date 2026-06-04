# Polynomial calibration profiles exported from notebooks/train_calibration.ipynb.
# generated_from_clean_data = True
# cleaning_rules_used = ['nan_or_non_finite', 'physical_range', 'time_step_spike', 'residual_mad_iqr_outlier', 'rolling_median_outlier']
# rows_raw = 177661
# rows_clean = 149687
# rows_removed = 27974
#
# Runtime intentionally depends only on the Python standard library.

from __future__ import annotations

import logging
import math

logger = logging.getLogger("calib")

CALIB_GENERATED_FROM_CLEAN_DATA = True
CALIB_CLEANING_RULES_USED = ['nan_or_non_finite', 'physical_range', 'time_step_spike', 'residual_mad_iqr_outlier', 'rolling_median_outlier']
CALIB_ROWS_RAW = 177661
CALIB_ROWS_CLEAN = 149687
CALIB_ROWS_REMOVED = 27974

CALIB_PROFILES = {'d6t': {'coefficients': [-9.84530151920214e-05,
                          0.0035530407343142855,
                          -0.0016106348200278712,
                          0.0009299834555085026,
                          0.0829000455110917,
                          -0.021161448472879176,
                          6.68453012100988e-06,
                          -0.00020760146310167422,
                          -0.00046652373812186164,
                          -0.0004571370740245528],
         'degree': 3,
         'features': ['raw', 'distance_cm'],
         'model_name': 'poly3_raw_distance',
         'powers': [[0, 0], [1, 0], [0, 1], [2, 0], [1, 1], [0, 2], [3, 0], [2, 1], [1, 2], [0, 3]],
         'uses_direction': False},
 'mlx90640': {'coefficients': [-34.34946435333897,
                               1.0119537439912476,
                               2.4023395611228,
                               -0.00038512684074554215,
                               0.0022401033032342643,
                               -0.04535268845853138],
              'degree': 2,
              'features': ['raw', 'distance_cm'],
              'model_name': 'poly2_raw_distance',
              'powers': [[0, 0], [1, 0], [0, 1], [2, 0], [1, 1], [0, 2]],
              'uses_direction': False},
 'smh01b01': {'coefficients': [-31.63826840667755,
                               1.0880293774226277,
                               2.1722125734711017,
                               -0.0007283192288536355,
                               0.003791205535310538,
                               -0.04087391368038329],
              'degree': 2,
              'features': ['raw', 'distance_cm'],
              'model_name': 'poly2_raw_distance',
              'powers': [[0, 0], [1, 0], [0, 1], [2, 0], [1, 1], [0, 2]],
              'uses_direction': False}}

def calibrate(sensor_name: str, raw_value: float, distance_cm: int | float | None, direction=None) -> float:
    profile = CALIB_PROFILES.get(sensor_name)
    try: raw = float(raw_value)
    except (TypeError, ValueError):
        logger.warning("[CALIB] invalid raw value for sensor=%s, using raw value", sensor_name); return raw_value
    if profile is None:
        logger.warning("[CALIB] profile not found, using raw value"); return raw
    if not math.isfinite(raw): return raw
    values = []
    for feature in profile["features"]:
        if feature == "raw": values.append(raw)
        elif feature == "distance_cm":
            if distance_cm is None:
                logger.warning("[CALIB] distance_cm missing for sensor=%s, using raw value", sensor_name); return raw
            values.append(float(distance_cm))
        else:
            logger.warning("[CALIB] unknown feature=%s for sensor=%s, using raw value", feature, sensor_name); return raw
    result = 0.0
    for coefficient, powers in zip(profile["coefficients"], profile["powers"]):
        term = float(coefficient)
        for value, power in zip(values, powers):
            if power: term *= value ** int(power)
        result += term
    return float(result) if math.isfinite(result) else raw
