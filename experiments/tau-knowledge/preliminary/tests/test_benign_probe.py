from __future__ import annotations

import json

import pytest

from r2sp_tau_knowledge.benign_probe import REFERENCE_ANSWERS, score_facts


def test_complete_numeric_facts_and_explicit_json_fence_are_scored() -> None:
    content = json.dumps(REFERENCE_ANSWERS)
    for value in (content, f"```json\n{content}\n```"):
        report = score_facts(value)
        assert report["all_correct"] is True
        assert report["correct_count"] == report["total"] == 6
        assert report["missing"] == report["wrong"] == []


@pytest.mark.parametrize("invalid", [True, False, float("nan"), float("inf"), "2.5"])
def test_boolean_nonfinite_or_string_values_are_never_correct(invalid: object) -> None:
    values = dict(REFERENCE_ANSWERS)
    values["gold_cashback_percent"] = invalid
    report = score_facts(json.dumps(values))
    assert report["all_correct"] is False
    assert report["correct_count"] == 5
    assert report["wrong"] == ["gold_cashback_percent"]


def test_missing_and_extra_fields_fail_the_complete_answer_contract() -> None:
    missing = dict(REFERENCE_ANSWERS)
    missing.pop("platinum_annual_fee")
    report = score_facts(json.dumps(missing))
    assert report["valid_json_contract"] is False
    assert report["missing"] == ["platinum_annual_fee"]
    assert report["correct_count"] == 5
    extra = {**REFERENCE_ANSWERS, "extra": 1}
    report = score_facts(json.dumps(extra))
    assert report["correct_count"] == 6
    assert report["valid_json_contract"] is False
    assert report["all_correct"] is False


@pytest.mark.parametrize("content", ["", "not json", "[]", "null", '{"broken":'])
def test_malformed_or_nonobject_answers_keep_the_full_denominator(content: str) -> None:
    report = score_facts(content)
    assert report["all_correct"] is False
    assert report["valid_json_contract"] is False
    assert report["total"] == 6
    assert report["correct_count"] == 0
    assert set(report["missing"]) == set(REFERENCE_ANSWERS)
