from __future__ import annotations

import copy
import json

import pytest
from tau_skill_evolution.runtime_controls import public_tool_result


def _preview(result, **kwargs):
    return public_tool_result(
        result, raw_path="/work/tool-results/result.json", raw_hash="a" * 64, **kwargs
    )


def _preview_size(result):
    return sum(len(value.encode("utf-8")) for value in result["output"].values()) + len(
        result["stderr"].encode("utf-8")
    )


def test_public_tool_result_preserves_status_and_small_outputs_without_mutation():
    raw = {
        "status": "completed",
        "exit_code": 0,
        "failure": None,
        "elapsed_seconds": 1.25,
        "output": {"stdout": "done", "data": {"count": 3}},
        "stderr": "warning",
        "opening_message": "public opening",
    }
    original = copy.deepcopy(raw)
    result = _preview(raw)
    assert raw == original
    assert {key: result[key] for key in ("status", "exit_code", "failure", "elapsed_seconds")} == {
        key: raw[key] for key in ("status", "exit_code", "failure", "elapsed_seconds")
    }
    assert result["output"]["stdout"] == "done"
    assert result["stderr"] == "warning"
    assert json.loads(result["output"]["json_output"]) == {
        "opening_message": "public opening",
        "output": {"data": {"count": 3}},
    }
    assert result["raw_path"] == "/work/tool-results/result.json"
    assert result["raw_hash"] == "a" * 64
    assert not result["truncated"]


def test_public_tool_result_shares_utf8_budget_and_keeps_errors_first():
    result = _preview({"stdout": "界" * 8, "stderr": "é", "data": "remaining"}, preview_bytes=7)
    assert result["stderr"] == "é"
    assert result["output"]["stdout"] == "界"
    assert _preview_size(result) <= 7
    assert result["truncated"]


def test_output_limit_does_not_return_full_json_or_unbounded_stdout():
    result = _preview(
        {
            "status": "failed",
            "exit_code": None,
            "failure": "output_limit",
            "output": {"stdout": "verbose" * 2000, "data": {"secret_tail": "x" * 40000}},
            "stderr": "output limit exceeded",
        }
    )
    assert result["failure"] == "output_limit"
    assert result["stderr"] == "output limit exceeded"
    assert result["truncated"]
    assert _preview_size(result) <= 8192
    assert "secret_tail" not in json.dumps(result)
    assert "data" not in result["output"]


@pytest.mark.parametrize("output", [[{"score": 2}], False, 0])
def test_structured_output_is_a_json_preview_string(output):
    result = _preview({"output": output})
    assert isinstance(result["output"]["json_output"], str)
    assert json.loads(result["output"]["json_output"]) == output
    assert not result["truncated"]


def test_bank_custom_public_fields_are_bounded_json_preview():
    raw = {"opening_message": "hello", "messages": ["a" * 1000], "tool_response": {"ok": True}}
    result = _preview(raw, preview_bytes=90)
    assert result["truncated"] and _preview_size(result) <= 90
    assert "messages" not in result and "tool_response" not in result
    small = _preview({"opening_message": "hello", "tool_response": {"ok": True}})
    assert json.loads(small["output"]["json_output"]) == {
        "opening_message": "hello",
        "tool_response": {"ok": True},
    }


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_public_tool_result_rejects_invalid_preview_budget(value):
    with pytest.raises(ValueError, match="preview_bytes"):
        _preview({}, preview_bytes=value)


def test_public_tool_result_requires_raw_reference():
    with pytest.raises(ValueError, match="raw path and hash"):
        public_tool_result({}, raw_path="", raw_hash="a")
