"""Schema routing decisions must distinguish new datasets from unchanged ones."""

import json

import pytest

from kavach.lambdas.supervisor.schema_detector import detect_schema_changes, handler


def test_unchanged_schema_ignores_column_order():
    result = detect_schema_changes(
        {"id": "bigint", "email": "string"}, {"email": "string", "id": "bigint"}
    )
    assert result == {
        "is_new_dataset": False,
        "schema_changed": False,
        "requires_reprofiling": False,
        "added_columns": [],
        "removed_columns": [],
        "modified_columns": {},
    }


def test_reports_all_changes_without_mutating_inputs():
    current = {"z": "string", "a": "int", "id": "bigint"}
    stored = {"old": "string", "id": "int"}
    result = detect_schema_changes(current, stored)
    assert result["added_columns"] == ["a", "z"]
    assert result["removed_columns"] == ["old"]
    assert result["modified_columns"] == {"id": {"previous_type": "int", "current_type": "bigint"}}
    assert result["schema_changed"] is True
    assert result["requires_reprofiling"] is True
    assert current == {"z": "string", "a": "int", "id": "bigint"}
    assert stored == {"old": "string", "id": "int"}
    assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize("current", [{}, {"id": "int"}])
def test_missing_baseline_always_requires_profiling(current):
    result = detect_schema_changes(current)
    assert result["is_new_dataset"] is True
    assert result["requires_reprofiling"] is True


def test_explicit_empty_baseline_is_not_a_new_dataset():
    result = detect_schema_changes({}, {})
    assert result["is_new_dataset"] is False
    assert result["requires_reprofiling"] is False


@pytest.mark.parametrize(
    ("current", "stored", "expected"),
    [
        ({"new": "int"}, {}, "added_columns"),
        ({}, {"old": "int"}, "removed_columns"),
        ({"id": "bigint"}, {"id": "int"}, "modified_columns"),
    ],
)
def test_each_change_independently_requires_reprofiling(current, stored, expected):
    result = detect_schema_changes(current, stored)
    assert result[expected]
    assert result["requires_reprofiling"] is True


@pytest.mark.parametrize(
    "schema", [None, [], "id", {"": "int"}, {1: "int"}, {"id": None}, {"id": " "}, {" ": "int"}]
)
def test_invalid_current_schema_is_rejected(schema):
    with pytest.raises((TypeError, ValueError), match="current_schema"):
        detect_schema_changes(schema)


@pytest.mark.parametrize("schema", [[], "id", {"id": 1}, {"": "int"}])
def test_invalid_stored_schema_is_rejected(schema):
    with pytest.raises((TypeError, ValueError), match="stored_schema"):
        detect_schema_changes({"id": "int"}, schema)


def test_handler_compares_supplied_baseline():
    assert (
        handler({"current_schema": {"id": "int"}, "stored_schema": {"id": "int"}}, None)[
            "requires_reprofiling"
        ]
        is False
    )
    assert handler({"current_schema": {}}, None)["is_new_dataset"] is True


@pytest.mark.parametrize("event", [{}, None, [], {"current_schema": None}])
def test_handler_rejects_invalid_events(event):
    with pytest.raises((TypeError, ValueError)):
        handler(event, None)
