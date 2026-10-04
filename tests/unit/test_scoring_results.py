"""Test score arithmetic, failure precedence, and the caller response contract."""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from kavach.lambdas.rule_executor.result_writer import build_response
from kavach.lambdas.rule_executor.score_computer import compute_scores, handler


def rule(rule_id="r1", passed=True, severity="WARNING", dimension="completeness", **extra):
    return {
        "rule_id": rule_id,
        "passed": passed,
        "severity": severity,
        "dimension": dimension,
        **extra,
    }


def test_weighted_scores_and_dimension_breakdown():
    result = compute_scores(
        [
            rule("r1", weight=3),
            rule("r2", passed=False),
            rule("r3", dimension="accuracy"),
        ]
    )
    assert result == {
        "status": "ALERT",
        "dq_score": 80.0,
        "dimension_scores": {"accuracy": 100.0, "completeness": 75.0},
        "rules_evaluated": 3,
        "rules_passed": 2,
        "rules_failed": 1,
    }


@pytest.mark.parametrize(
    "severity,status", [("CRITICAL", "FAIL"), ("WARNING", "ALERT"), ("INFO", "ALERT")]
)
def test_failed_rule_severity_controls_status(severity, status):
    result = compute_scores([rule(passed=False, severity=severity)])
    assert result["status"] == status
    assert result["dq_score"] == 0


def test_critical_failure_takes_precedence_over_warnings():
    assert (
        compute_scores(
            [
                rule("warning", passed=False),
                rule("critical", passed=False, severity="CRITICAL"),
            ]
        )["status"]
        == "FAIL"
    )


def test_rounded_score_does_not_hide_a_critical_failure():
    result = compute_scores(
        [
            rule("pass", weight=1_000_000),
            rule("fail", passed=False, severity="CRITICAL"),
        ]
    )
    assert result["dq_score"] == 100.0
    assert result["status"] == "FAIL"


def test_all_passed_is_pass_even_for_critical_rules():
    result = compute_scores([rule(severity="CRITICAL")])
    assert result["status"] == "PASS"
    assert result["dq_score"] == 100


def test_large_finite_weights_do_not_overflow():
    assert (
        compute_scores([rule("r1", weight=1e308), rule("r2", passed=False, weight=1e308)])[
            "dq_score"
        ]
        == 50
    )


@pytest.mark.parametrize("weight", [0, -1, True, "1", None, float("inf"), float("nan"), 10**1000])
def test_invalid_weights_are_rejected(weight):
    with pytest.raises((TypeError, ValueError), match="weight"):
        compute_scores([rule(weight=weight)])


@pytest.mark.parametrize(
    "key,value",
    [
        ("passed", "false"),
        ("passed", 1),
        ("passed", None),
        ("severity", "critical"),
        ("severity", None),
        ("rule_id", ""),
        ("rule_id", 2),
        ("dimension", " "),
    ],
)
def test_malformed_rule_fields_are_rejected(key, value):
    with pytest.raises((TypeError, ValueError), match=key):
        compute_scores([rule(**{key: value})])


@pytest.mark.parametrize("key", ["rule_id", "passed", "severity", "dimension"])
def test_missing_required_fields_are_rejected(key):
    result = rule()
    del result[key]
    with pytest.raises((TypeError, ValueError), match=key):
        compute_scores([result])


def test_duplicate_rule_ids_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        compute_scores([rule(), rule()])


@pytest.mark.parametrize("results", [[], None, {}, [None]])
def test_no_evaluations_or_invalid_container_cannot_report_pass(results):
    with pytest.raises((ValueError, TypeError)):
        compute_scores(results)


def test_handler_scores_results_and_rejects_missing_results():
    assert handler({"results": [rule()]}, None)["status"] == "PASS"
    with pytest.raises(ValueError, match="results"):
        handler({}, None)


def test_response_has_utc_timestamp_and_independent_failure_details():
    results = [
        rule("pass"),
        rule("fail", passed=False, expected="<2%", actual="5%", details={"columns": ["email"]}),
    ]
    executed_at = datetime(2026, 10, 4, 9, 0, tzinfo=timezone(timedelta(hours=2)))
    response = build_response("orders", results, executed_at=executed_at)
    assert response["timestamp"] == "2026-10-04T07:00:00Z"
    assert response["dataset"] == "orders"
    assert response["status"] == "ALERT"
    assert response["rules_failed"] == 1
    assert response["failures"] == [results[1]]
    assert json.loads(json.dumps(response)) == response
    response["failures"][0]["details"]["columns"].append("id")
    assert results[1]["details"]["columns"] == ["email"]


def test_passing_response_has_no_failures_and_current_utc_time():
    before = datetime.now(UTC)
    response = build_response("orders", [rule()])
    timestamp = datetime.fromisoformat(response["timestamp"])
    assert before <= timestamp <= datetime.now(UTC)
    assert response["failures"] == []


@pytest.mark.parametrize("dataset", ["", " ", None, 3])
def test_invalid_dataset_is_rejected(dataset):
    with pytest.raises(ValueError, match="dataset"):
        build_response(dataset, [rule()])


@pytest.mark.parametrize("timestamp", [datetime(2026, 10, 4), "2026-10-04"])  # noqa: DTZ001
def test_invalid_execution_timestamp_is_rejected(timestamp):
    with pytest.raises((ValueError, TypeError), match="executed_at"):
        build_response("orders", [rule()], executed_at=timestamp)
