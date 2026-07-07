"""Decision-quality helpers shared by engine v2 models."""

from __future__ import annotations

import math


def iq_decision_noise(iq: float) -> float:
    """Return a normalized decision-noise factor for IQ-driven choices.

    IQ below 100 keeps the old linear behavior. IQ above 100 continues to
    reduce noise with diminishing returns, so elite players stay slightly
    exploratory instead of becoming fully deterministic.
    """
    value = max(1.0, float(iq))
    if value <= 100.0:
        return max(0.01, (100.0 - value) / 100.0)
    return max(0.003, 0.01 * math.exp(-(value - 100.0) / 35.0))


def iq_temperature_factor(
    iq: float,
    *,
    floor: float,
    low_iq_range: float,
    elite_discount: float = 0.25,
) -> float:
    """Temperature multiplier for IQ-driven softmax choices.

    Low IQ raises temperature linearly. IQ above 100 lowers the temperature with
    diminishing returns, so 120/130 IQ matters without removing exploration.
    """
    value = max(1.0, float(iq))
    low_iq_noise = max(0.0, (100.0 - min(value, 100.0)) / 100.0)
    factor = floor + low_iq_noise * low_iq_range
    if value > 100.0:
        elite = 1.0 - math.exp(-(value - 100.0) / 35.0)
        factor *= 1.0 - max(0.0, min(0.75, elite_discount)) * elite
    return max(floor * (1.0 - max(0.0, min(0.75, elite_discount))), factor)
