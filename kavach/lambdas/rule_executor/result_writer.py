"""Build a DQ response payload. Persistence remains a separate integration."""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from kavach.lambdas.rule_executor.score_computer import compute_scores


def build_response(
    dataset: str,
    results: list[dict[str, Any]],
    *,
    executed_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a scored response with failed checks and a UTC execution timestamp.

    Supply an aware executed_at datetime to preserve the execution time across
    retries. Otherwise the builder uses the current time. Failure details are
    copied so modifying the response cannot mutate the caller's evaluations.
    """
    if not isinstance(dataset, str) or not dataset.strip():
        raise ValueError("dataset must be a non-empty string")
    scores = compute_scores(results)
    timestamp = executed_at if executed_at is not None else datetime.now(UTC)
    if not isinstance(timestamp, datetime):
        raise TypeError("executed_at must be a datetime")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("executed_at must include a timezone")
    return {
        "dataset": dataset,
        "timestamp": timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        **scores,
        "failures": [deepcopy(result) for result in results if not result["passed"]],
    }
