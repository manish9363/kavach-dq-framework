"""Compute scores and status from completed rule evaluations, without AWS access."""

from collections.abc import Mapping
from math import fsum, isfinite
from typing import Any


def compute_scores(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return weighted pass percentages overall and for each dimension.

    Each result requires rule_id, dimension, passed (a bool), and severity
    (CRITICAL, WARNING, or INFO). Optional weight defaults to 1 and must be
    finite and positive. A critical failure means FAIL; any other failure means
    ALERT. All passing checks mean PASS. Empty evaluations are rejected.
    """
    if not isinstance(results, list):
        raise TypeError("results must be a list")
    if not results:
        raise ValueError("results must contain at least one evaluated rule")

    seen = set()
    groups: dict[str, list[tuple[bool, float]]] = {}
    evaluations: list[tuple[bool, float]] = []
    failed = critical_failed = 0
    for result in results:
        if not isinstance(result, Mapping):
            raise TypeError("each result must be a mapping")
        for key in ("rule_id", "dimension"):
            value = result.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a non-empty string")
        rule_id = result["rule_id"]
        if rule_id in seen:
            raise ValueError(f"duplicate rule_id: {rule_id}")
        seen.add(rule_id)
        passed = result.get("passed")
        if not isinstance(passed, bool):
            raise TypeError("passed must be a bool")
        severity = result.get("severity")
        if severity not in ("CRITICAL", "WARNING", "INFO"):
            raise ValueError("severity must be CRITICAL, WARNING, or INFO")
        weight = result.get("weight", 1)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise TypeError("weight must be a finite positive number")
        try:
            weight = float(weight)
        except OverflowError as exc:
            raise ValueError("weight must be a finite positive number") from exc
        if not isfinite(weight) or weight <= 0:
            raise ValueError("weight must be a finite positive number")
        evaluation = (passed, weight)
        evaluations.append(evaluation)
        groups.setdefault(result["dimension"], []).append(evaluation)
        if not passed:
            failed += 1
            critical_failed += severity == "CRITICAL"

    def percentage(items: list[tuple[bool, float]]) -> float:
        # Normalize first to avoid overflow when summing large finite weights.
        largest = max(weight for _, weight in items)
        total = fsum(weight / largest for _, weight in items)
        passing = fsum(weight / largest for passed, weight in items if passed)
        return round(100 * (passing / total), 2)

    return {
        "status": "FAIL" if critical_failed else "ALERT" if failed else "PASS",
        "dq_score": percentage(evaluations),
        "dimension_scores": {name: percentage(groups[name]) for name in sorted(groups)},
        "rules_evaluated": len(results),
        "rules_passed": len(results) - failed,
        "rules_failed": failed,
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Accept a direct Lambda event containing results."""
    if not isinstance(event, dict) or "results" not in event:
        raise ValueError("event must contain results")
    return compute_scores(event["results"])
