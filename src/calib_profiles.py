"""
Polynomial calibration profiles exported from notebooks/train_calibration.ipynb.

Runtime intentionally depends only on the Python standard library.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger("calib")


CALIB_PROFILES = {
    "mlx90640": {
        "model_name": "poly2_raw_distance_direction",
        "degree": 2,
        "features": ["raw", "distance_cm", "direction_code"],
        "powers": [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
            [2, 0, 0],
            [1, 1, 0],
            [1, 0, 1],
            [0, 2, 0],
            [0, 1, 1],
            [0, 0, 2],
        ],
        "coefficients": [
            -40.5856549505034,
            1.0833089039528117,
            2.703809877846719,
            -6.680564569436943,
            -0.0005481093191159747,
            0.0022504029937588654,
            0.02076402250059903,
            -0.05088043751591645,
            0.042521075709043586,
            -6.680564569432609,
        ],
        "uses_direction": True,
    },
    "smh01b01": {
        "model_name": "poly2_raw_distance_direction",
        "degree": 2,
        "features": ["raw", "distance_cm", "direction_code"],
        "powers": [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
            [2, 0, 0],
            [1, 1, 0],
            [1, 0, 1],
            [0, 2, 0],
            [0, 1, 1],
            [0, 0, 2],
        ],
        "coefficients": [
            -29.38113414552789,
            1.1186893470390968,
            1.9109522713812335,
            -4.459405542097925,
            -0.0008272572297289837,
            0.0051029042494951105,
            -0.0004979744458077514,
            -0.03767647418469929,
            -0.046763479947126686,
            -4.459405542093054,
        ],
        "uses_direction": True,
    },
    "d6t": {
        "model_name": "poly2_raw_distance_direction",
        "degree": 2,
        "features": ["raw", "distance_cm", "direction_code"],
        "powers": [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
            [2, 0, 0],
            [1, 1, 0],
            [1, 0, 1],
            [0, 2, 0],
            [0, 1, 1],
            [0, 0, 2],
        ],
        "coefficients": [
            -26.790391969378074,
            1.0905408039003366,
            1.2747486830044434,
            -10.652323071950669,
            -0.0010325139066904576,
            0.01023810923481766,
            0.02562894622070976,
            -0.015450549492342133,
            0.44618240558945893,
            -10.652323071953369,
        ],
        "uses_direction": True,
    },
}


def _direction_code(direction: str | int | float | None) -> float:
    if direction is None:
        return 0.5
    if isinstance(direction, str):
        text = direction.strip().lower()
        if text == "up":
            return 1.0
        if text == "down":
            return 0.0
        logger.warning("[CALIB] unknown direction=%r, using neutral value", direction)
        return 0.5
    try:
        value = float(direction)
    except (TypeError, ValueError):
        logger.warning("[CALIB] invalid direction=%r, using neutral value", direction)
        return 0.5
    return 1.0 if value >= 0.5 else 0.0


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
        elif feature == "direction_code":
            values.append(_direction_code(direction))
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
