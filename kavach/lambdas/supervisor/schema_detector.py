"""Compare current vs stored schema, detect column changes.

Schemas map column names to type strings. Names and types are compared exactly;
callers should use the same source-specific type representation for both schemas.
"""

from collections.abc import Mapping
from typing import Any


def _validate_schema(schema: Mapping[str, str], label: str) -> dict[str, str]:
    if not isinstance(schema, Mapping):
        raise TypeError(f"{label} must map column names to type strings")
    for name, data_type in schema.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{label} column names must be non-empty strings")
        if not isinstance(data_type, str) or not data_type.strip():
            raise ValueError(f"{label} column types must be non-empty strings")
    return dict(schema)


def detect_schema_changes(
    current_schema: Mapping[str, str],
    stored_schema: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a deterministic, JSON-compatible schema diff.

    A missing stored schema denotes a new dataset and always requires profiling,
    including when its current schema is empty. An explicitly stored empty schema
    is an existing baseline. Column order does not affect the comparison.
    """
    current = _validate_schema(current_schema, "current_schema")
    is_new_dataset = stored_schema is None
    stored = {} if is_new_dataset else _validate_schema(stored_schema, "stored_schema")

    added = sorted(current.keys() - stored.keys())
    removed = sorted(stored.keys() - current.keys())
    modified = {
        name: {"previous_type": stored[name], "current_type": current[name]}
        for name in sorted(current.keys() & stored.keys())
        if current[name] != stored[name]
    }
    schema_changed = bool(added or removed or modified)
    return {
        "is_new_dataset": is_new_dataset,
        "schema_changed": schema_changed,
        "requires_reprofiling": is_new_dataset or schema_changed,
        "added_columns": added,
        "removed_columns": removed,
        "modified_columns": modified,
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle direct Lambda invocations with current_schema and stored_schema.

    Stored metadata must be supplied by the caller; this helper performs no AWS
    reads or writes. Invalid payloads fail rather than report an unchanged schema.
    """
    if not isinstance(event, dict) or "current_schema" not in event:
        raise ValueError("event must contain current_schema")
    return detect_schema_changes(event["current_schema"], event.get("stored_schema"))
