"""Derive robust adaptive bounds from historical metric observations."""

from collections.abc import Iterable
from math import isfinite
from numbers import Real
from statistics import median
from typing import Any

_MAD_NORMAL_SCALE = 1.4826


def compute_adaptive_thresholds(
    historical_values: Iterable[Real],
    *,
    sensitivity: float = 3.0,
    min_samples: int = 7,
    minimum_delta: float = 0.0,
) -> dict[str, Any]:
    """Return median-centered bounds using the median absolute deviation.

    The robust MAD scale limits the influence of isolated historical spikes.
    ``minimum_delta`` provides a domain-specific tolerance when a metric has
    little or no historical variation. At least ``min_samples`` finite numeric
    observations are required; the caller selects the intended baseline window.
    """
    if isinstance(min_samples, bool) or not isinstance(min_samples, int) or min_samples < 1:
        raise ValueError("min_samples must be a positive integer")
    if isinstance(sensitivity, bool) or not isinstance(sensitivity, Real):
        raise TypeError("sensitivity must be a finite positive number")
    if not isfinite(float(sensitivity)) or sensitivity <= 0:
        raise ValueError("sensitivity must be a finite positive number")
    if isinstance(minimum_delta, bool) or not isinstance(minimum_delta, Real):
        raise TypeError("minimum_delta must be a finite non-negative number")
    if not isfinite(float(minimum_delta)) or minimum_delta < 0:
        raise ValueError("minimum_delta must be a finite non-negative number")

    values: list[float] = []
    for index, value in enumerate(historical_values, start=1):
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"historical value {index} must be numeric")
        number = float(value)
        if not isfinite(number):
            raise ValueError(f"historical value {index} must be finite")
        values.append(number)
    if len(values) < min_samples:
        raise ValueError(f"at least {min_samples} historical values are required")

    center = median(values)
    mad = median(abs(value - center) for value in values)
    spread = _MAD_NORMAL_SCALE * mad
    tolerance = max(float(sensitivity) * spread, float(minimum_delta))
    return {
        "center": center,
        "spread": spread,
        "lower_bound": center - tolerance,
        "upper_bound": center + tolerance,
        "sample_count": len(values),
        "method": "median_absolute_deviation",
    }
