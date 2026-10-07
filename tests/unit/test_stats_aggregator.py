"""Dataset profile summaries must be deterministic and safe for sparse samples."""

import json

import pytest

from kavach.lambdas.rule_generator.stats_aggregator import aggregate_dataset_stats


def test_aggregates_completeness_and_numeric_summaries():
    result = aggregate_dataset_stats(
        [
            {"id": 1, "amount": 10.0, "email": "a@example.com"},
            {"id": 2, "amount": None, "email": None},
            {"id": 3, "amount": 30.0},
        ]
    )
    assert result["row_count"] == 3
    assert result["columns"]["amount"] == {
        "null_count": 1,
        "non_null_count": 2,
        "null_percentage": 33.33,
        "numeric": {"count": 2, "min": 10.0, "max": 30.0, "mean": 20.0, "median": 20.0},
    }
    assert result["columns"]["email"]["null_count"] == 2
    assert result["columns"]["email"]["numeric"] is None
    assert json.loads(json.dumps(result)) == result


def test_requested_columns_count_absent_fields_as_null():
    result = aggregate_dataset_stats([{"id": 1}, {"id": 2, "score": 4}], ["score", "id"])
    assert list(result["columns"]) == ["score", "id"]
    assert result["columns"]["score"]["null_count"] == 1
    assert result["columns"]["id"]["numeric"]["mean"] == 1.5


def test_inferred_columns_count_rows_before_first_observation_as_null():
    result = aggregate_dataset_stats([{"id": 1}, {"id": 2, "late": 5}])
    assert result["columns"]["late"]["null_count"] == 1
    assert result["columns"]["late"]["null_percentage"] == 50.0


def test_empty_sample_has_zero_percentage_and_no_numeric_summary():
    assert aggregate_dataset_stats([], ["id"]) == {
        "row_count": 0,
        "columns": {
            "id": {
                "null_count": 0,
                "non_null_count": 0,
                "null_percentage": 0.0,
                "numeric": None,
            }
        },
    }


def test_boolean_and_non_finite_values_are_not_numeric_samples():
    result = aggregate_dataset_stats(
        [{"value": True}, {"value": float("nan")}, {"value": float("inf")}]
    )
    assert result["columns"]["value"]["non_null_count"] == 3
    assert result["columns"]["value"]["numeric"] is None


@pytest.mark.parametrize("records", [[1], [None], ["not a record"]])
def test_rejects_non_mapping_records(records):
    with pytest.raises(TypeError, match="record 1"):
        aggregate_dataset_stats(records)


@pytest.mark.parametrize("columns", ["id", [""], [1]])
def test_rejects_invalid_column_selection(columns):
    with pytest.raises((TypeError, ValueError)):
        aggregate_dataset_stats([], columns)
