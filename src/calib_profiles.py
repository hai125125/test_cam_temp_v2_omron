"""
Polynomial calibration profiles exported from notebooks/train_calibration.ipynb.

Runtime intentionally depends only on the Python standard library.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger("calib")


CALIB_PROFILES = {'d6t': {'coefficients': [-21.221351419065076,
                          0.9889857679609844,
                          0.9906965660576291,
                          -0.0007175965889241187,
                          0.010475909398695804,
                          -0.008197083894232321],
         'degree': 2,
         'features': ['raw', 'distance_cm'],
         'model_name': 'poly2_raw_distance',
         'powers': [[0, 0], [1, 0], [0, 1], [2, 0], [1, 1], [0, 2]],
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
    try:
        raw = float(raw_value)
    except (TypeError, ValueError):
        logger.warning("[CALIB] invalid raw value for sensor=%s, using raw value", sensor_name)
        return raw_value

    if profile is None:
        logger.warning("[CALIB] profile not found, using raw value")
        return raw
    if not math.isfinite(raw):
        return raw

    values = []
    for feature in profile["features"]:
        if feature == "raw":
            values.append(raw)
        elif feature == "distance_cm":
            if distance_cm is None:
                logger.warning("[CALIB] distance_cm missing for sensor=%s, using raw value", sensor_name)
                return raw
            values.append(float(distance_cm))
        else:
            logger.warning("[CALIB] unknown feature=%s for sensor=%s, using raw value", feature, sensor_name)
            return raw

    result = 0.0
    for coefficient, powers in zip(profile["coefficients"], profile["powers"]):
        term = float(coefficient)
        for value, power in zip(values, powers):
            if power:
                term *= value ** int(power)
        result += term
    return float(result) if math.isfinite(result) else raw
