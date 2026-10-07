"""Adaptive thresholds should resist spikes and reject unsafe history inputs."""

import pytest

from kavach.lambdas.rule_generator.threshold_calculator import compute_adaptive_thresholds


def test_uses_median_and_mad_to_limit_spike_influence():
    result = compute_adaptive_thresholds([9, 10, 10, 10, 11, 1000], min_samples=6)
    assert result["center"] == 10.0
    assert result["spread"] == pytest.approx(0.7413)
    assert result["upper_bound"] < 15
    assert result["sample_count"] == 6


def test_minimum_delta_provides_tolerance_for_constant_baseline():
    result = compute_adaptive_thresholds([5, 5, 5], min_samples=3, minimum_delta=0.25)
    assert result["lower_bound"] == 4.75
    assert result["upper_bound"] == 5.25
    assert result["spread"] == 0.0


def test_rejects_insufficient_and_invalid_history_values():
    with pytest.raises(ValueError, match="at least 3"):
        compute_adaptive_thresholds([1, 2], min_samples=3)
    with pytest.raises(TypeError, match="must be numeric"):
        compute_adaptive_thresholds([1, "2"], min_samples=2)
    with pytest.raises(ValueError, match="must be finite"):
        compute_adaptive_thresholds([1, float("nan")], min_samples=2)


@pytest.mark.parametrize("sensitivity", [0, -1, float("inf"), float("nan")])
def test_rejects_invalid_sensitivity(sensitivity):
    with pytest.raises((TypeError, ValueError), match="sensitivity"):
        compute_adaptive_thresholds([1, 2, 3], min_samples=3, sensitivity=sensitivity)


def test_rejects_boolean_as_sample_count_or_metric():
    with pytest.raises(ValueError, match="min_samples"):
        compute_adaptive_thresholds([1], min_samples=True)
    with pytest.raises(TypeError, match="must be numeric"):
        compute_adaptive_thresholds([True], min_samples=1)
