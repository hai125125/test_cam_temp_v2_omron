"""
Polynomial calibration profiles exported from notebooks/train_calibration.ipynb.

Runtime intentionally depends only on the Python standard library.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger("calib")


CALIB_PROFILES = {'d6t': {'coefficients': [-16.92450271847372,
                          0.9745090637076343,
                          0.6589181844258359,
                          -0.0006825904996607957,
                          0.010745195446769829,
                          -0.001792696462029092],
         'degree': 2,
         'features': ['raw', 'distance_cm'],
         'model_name': 'poly2_raw_distance',
         'powers': [[0, 0], [1, 0], [0, 1], [2, 0], [1, 1], [0, 2]],
         'uses_direction': False},
 'mlx90640': {'coefficients': [-35.23442578360595,
                               1.014546922035408,
                               2.470899252041475,
                               -0.00039141618075655416,
                               0.002199737020703779,
                               -0.046688261184431895],
              'degree': 2,
              'features': ['raw', 'distance_cm'],
              'model_name': 'poly2_raw_distance',
              'powers': [[0, 0], [1, 0], [0, 1], [2, 0], [1, 1], [0, 2]],
              'uses_direction': False},
 'smh01b01': {'coefficients': [-29.455197794695085,
                               1.0813858712535604,
                               2.0025564596892167,
                               -0.0007115659139305119,
                               0.0038918329765350035,
                               -0.037545899412998504],
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
