"""Compute completeness and numeric summary statistics for sampled records."""

from collections.abc import Iterable, Mapping, Sequence
from math import isfinite
from numbers import Real
from statistics import mean, median
from typing import Any


def aggregate_dataset_stats(
    records: Iterable[Mapping[str, Any]],
    columns: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Summarize null coverage and finite numeric values in a record sample.

    Missing keys and ``None`` values count as null. NaN and infinite numeric
    values count as non-null values but are excluded from numeric summaries.
    When ``columns`` is omitted, columns are discovered in first-seen order.
    """
    if columns is not None:
        if isinstance(columns, (str, bytes)):
            raise TypeError("columns must be a sequence of column names")
        selected: list[str] = []
        seen: set[str] = set()
        for column in columns:
            if not isinstance(column, str) or not column.strip():
                raise ValueError("column names must be non-empty strings")
            if column not in seen:
                seen.add(column)
                selected.append(column)
    else:
        selected = []
        seen = set()

    null_counts: dict[str, int] = {column: 0 for column in selected}
    non_null_counts: dict[str, int] = {column: 0 for column in selected}
    numeric_values: dict[str, list[float]] = {column: [] for column in selected}
    row_count = 0

    for row_number, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise TypeError(f"record {row_number} must be a mapping")
        row_count += 1
        for column in record:
            if not isinstance(column, str) or not column.strip():
                raise ValueError(f"record {row_number} has an invalid column name")
            if columns is None and column not in seen:
                selected.append(column)
                seen.add(column)
                null_counts[column] = row_count - 1
                non_null_counts[column] = 0
                numeric_values[column] = []

        for column in selected:
            value = record.get(column)
            if value is None:
                null_counts[column] += 1
                continue
            non_null_counts[column] += 1
            if isinstance(value, Real) and not isinstance(value, bool):
                number = float(value)
                if isfinite(number):
                    numeric_values[column].append(number)

    summaries: dict[str, Any] = {}
    for column in selected:
        count = non_null_counts[column]
        numeric = numeric_values[column]
        numeric_summary = None
        if numeric:
            numeric_summary = {
                "count": len(numeric),
                "min": min(numeric),
                "max": max(numeric),
                "mean": mean(numeric),
                "median": median(numeric),
            }
        summaries[column] = {
            "null_count": null_counts[column],
            "non_null_count": count,
            "null_percentage": round(null_counts[column] * 100 / row_count, 2)
            if row_count
            else 0.0,
            "numeric": numeric_summary,
        }

    return {"row_count": row_count, "columns": summaries}
