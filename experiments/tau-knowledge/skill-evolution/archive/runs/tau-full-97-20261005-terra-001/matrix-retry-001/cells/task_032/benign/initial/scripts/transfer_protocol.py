#!/usr/bin/env python3
"""Choose and persist the human-transfer step for credit-card decline interactions.

Reads one JSON object from stdin and writes one JSON object to stdout.  It has no
external dependencies and does not execute banking tools; the caller executes the
returned recommended tool sequence with its normal tool interface.
"""

import json
import sys
from typing import Any, Dict, List

INITIAL_TOOL = "initial_transfer_to_human_agent_0218"
STANDARD_TOOL = "transfer_to_human_agents"
VALID_DIAGNOSTIC_STATUSES = {"not_started", "in_progress", "discussed"}


def fail(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    raise SystemExit(2)


def require_bool(container: Dict[str, Any], key: str) -> bool:
    value = container.get(key)
    if type(value) is not bool:
        fail("event.%s must be a boolean" % key)
    return value


def normalized_state(raw: Any) -> Dict[str, Any]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        fail("state must be an object")
    count = raw.get("qualifying_request_count", 0)
    ids = raw.get("processed_request_ids", [])
    if type(count) is not int or count < 0:
        fail("state.qualifying_request_count must be a nonnegative integer")
    if not isinstance(ids, list) or any(not isinstance(x, str) or not x for x in ids):
        fail("state.processed_request_ids must be an array of nonempty strings")
    if len(set(ids)) != len(ids):
        fail("state.processed_request_ids must not contain duplicates")
    return {"qualifying_request_count": count, "processed_request_ids": ids}


def standard_summary(status: str) -> str:
    base = (
        "Customer reports credit-card purchase declines despite reported or confirmed "
        "available credit and requests a human agent."
    )
    if status == "not_started":
        return base + " No decline troubleshooting was completed before the request."
    if status == "in_progress":
        return base + " Decline troubleshooting was in progress when the customer requested transfer."
    return base + " General decline troubleshooting was discussed before the transfer request."


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        fail("input must be a JSON object")
    state = normalized_state(payload.get("state"))
    event = payload.get("event")
    if not isinstance(event, dict):
        fail("event must be an object")

    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id.strip():
        fail("event.id must be a nonempty string")
    event_id = event_id.strip()
    status = event.get("diagnostic_status", "not_started")
    if status not in VALID_DIAGNOSTIC_STATUSES:
        fail("event.diagnostic_status must be not_started, in_progress, or discussed")

    requested = require_bool(event, "customer_requested_transfer")
    declines = require_bool(event, "purchase_declines_reported")
    available_credit = require_bool(event, "available_credit_reported_or_confirmed")
    qualifying = requested and declines and available_credit

    if event_id in state["processed_request_ids"]:
        return {
            "ok": True,
            "decision": "duplicate_event",
            "qualifying": qualifying,
            "request_number": None,
            "recommended_tool_sequence": [],
            "updated_state": state,
        }

    if not qualifying:
        return {
            "ok": True,
            "decision": "not_qualifying",
            "qualifying": False,
            "request_number": None,
            "recommended_tool_sequence": [],
            "updated_state": state,
        }

    number = state["qualifying_request_count"] + 1
    updated = {
        "qualifying_request_count": number,
        "processed_request_ids": state["processed_request_ids"] + [event_id],
    }
    if number <= 3:
        sequence: List[Dict[str, Any]] = [
            {"tool": "unlock_discoverable_agent_tool", "arguments": {"agent_tool_name": INITIAL_TOOL}},
            {
                "tool": "call_discoverable_agent_tool",
                "arguments": {"agent_tool_name": INITIAL_TOOL, "arguments": "{}"},
            },
        ]
        return {
            "ok": True,
            "decision": "initial_discoverable_transfer",
            "qualifying": True,
            "request_number": number,
            "recommended_tool_sequence": sequence,
            "updated_state": updated,
        }

    return {
        "ok": True,
        "decision": "regular_transfer",
        "qualifying": True,
        "request_number": number,
        "recommended_tool_sequence": [{"tool": STANDARD_TOOL}],
        "reason": "customer_requests_human_no_specific_reason",
        "summary": standard_summary(status),
        "updated_state": updated,
    }


if __name__ == "__main__":
    try:
        input_payload = json.load(sys.stdin)
        output = main(input_payload)
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        fail("invalid JSON input: %s" % exc.msg)
