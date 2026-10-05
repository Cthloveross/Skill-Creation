#!/usr/bin/env python3
"""Plan the next action for the credit-card payment-posting incident.

Input JSON schema:
{
  "current_time": string,
  "paid_statement": boolean,
  "deducted_from_checking": boolean,
  "missing_from_statement_balance": boolean,
  "transfer_request_number": nonnegative integer,
  "completed_initial_steps": integer from 0 through 2,
  "regular_transfer_completed": boolean
}

The script writes one JSON object to stdout. It has no side effects and does not
call any runtime tools.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

EST = timezone(timedelta(hours=-5), name="EST")
CUTOFF = datetime(2025, 11, 15, 23, 59, 59, tzinfo=EST)


def parse_runtime_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("current_time must be a nonempty timestamp string")
    text = value.strip()
    if text.endswith(" EST"):
        naive = datetime.strptime(text[:-4], "%Y-%m-%d %H:%M:%S")
        return naive.replace(tzinfo=EST)
    # Permit ISO 8601 timestamps supplied by a runtime, including a trailing Z.
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("current_time must be ISO-8601 or YYYY-MM-DD HH:MM:SS EST") from exc
    if parsed.tzinfo is None:
        # A timestamp explicitly described as EST elsewhere in the runtime may be
        # supplied without an offset; treat a naive timestamp as EST deterministically.
        parsed = parsed.replace(tzinfo=EST)
    return parsed.astimezone(EST)


def invalid(message: str) -> Dict[str, Any]:
    return {"status": "invalid_input", "incident_applicable": False, "message": message}


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    required_bools = (
        "paid_statement",
        "deducted_from_checking",
        "missing_from_statement_balance",
        "regular_transfer_completed",
    )
    for field in required_bools:
        if not isinstance(payload.get(field), bool):
            return invalid(f"{field} must be boolean")

    request_number = payload.get("transfer_request_number")
    completed_steps = payload.get("completed_initial_steps")
    if isinstance(request_number, bool) or not isinstance(request_number, int) or request_number < 0:
        return invalid("transfer_request_number must be a nonnegative integer")
    if isinstance(completed_steps, bool) or not isinstance(completed_steps, int) or completed_steps not in (0, 1, 2):
        return invalid("completed_initial_steps must be 0, 1, or 2")

    try:
        current = parse_runtime_time(payload.get("current_time"))
    except ValueError as exc:
        return invalid(str(exc))

    symptoms_match = (
        payload["paid_statement"]
        and payload["deducted_from_checking"]
        and payload["missing_from_statement_balance"]
    )
    active = current <= CUTOFF
    applicable = symptoms_match and active
    base = {
        "incident_applicable": applicable,
        "symptoms_match": symptoms_match,
        "within_incident_window": active,
        "cutoff_est": "2025-11-15 23:59:59 EST",
    }

    if not applicable:
        base.update({
            "status": "standard_handling_required",
            "next_operation": None,
            "message": "The incident protocol is not applicable; do not use its staged transfer tools.",
        })
        return base

    if request_number == 0:
        if completed_steps != 0 or payload["regular_transfer_completed"]:
            base.update({
                "status": "state_inconsistent",
                "next_operation": None,
                "message": "Transfer completion state exists without a recorded transfer request.",
            })
        else:
            base.update({
                "status": "await_transfer_request",
                "next_operation": None,
                "message": "Wait for an explicit customer request for a human transfer.",
            })
        return base

    if payload["regular_transfer_completed"]:
        if completed_steps != 2 or request_number < 3:
            base.update({
                "status": "state_inconsistent",
                "next_operation": None,
                "message": "A regular transfer cannot be complete before two internal steps and a third request.",
            })
        else:
            base.update({
                "status": "regular_transfer_already_complete",
                "next_operation": None,
                "message": "Do not duplicate an already completed regular transfer.",
            })
        return base

    if request_number == 1:
        if completed_steps == 0:
            base.update({
                "status": "ready",
                "next_operation": "unlock_and_call_first_internal_tool",
                "agent_tool_name": "initial_transfer_to_human_agent_1822",
                "message": "Unlock this tool, then call it; do not use the regular transfer tool.",
            })
        elif completed_steps == 1:
            base.update({
                "status": "internal_step_already_complete",
                "next_operation": None,
                "message": "The first internal step is complete; await a second request.",
            })
        else:
            base.update({
                "status": "state_inconsistent",
                "next_operation": None,
                "message": "The second internal step cannot precede the second request.",
            })
        return base

    if request_number == 2:
        if completed_steps == 1:
            base.update({
                "status": "ready",
                "next_operation": "unlock_and_call_second_internal_tool",
                "agent_tool_name": "initial_transfer_to_human_agent_0218",
                "message": "Unlock this tool, then call it; do not use the regular transfer tool.",
            })
        elif completed_steps == 2:
            base.update({
                "status": "internal_step_already_complete",
                "next_operation": None,
                "message": "Both internal steps are complete; await a third request.",
            })
        else:
            base.update({
                "status": "state_inconsistent",
                "next_operation": None,
                "message": "The first internal step must complete before the second request is processed.",
            })
        return base

    # The third and any later request can be completed only after both internal steps.
    if completed_steps == 2:
        base.update({
            "status": "ready",
            "next_operation": "regular_human_transfer",
            "message": "Call transfer_to_human_agents with a concise customer-disclosed summary.",
        })
    else:
        base.update({
            "status": "state_inconsistent",
            "next_operation": None,
            "message": "Both required internal steps must complete before regular transfer.",
        })
    return base


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("input must be a JSON object")
        result = main(incoming)
    except (json.JSONDecodeError, ValueError) as exc:
        result = invalid(str(exc))
    print(json.dumps(result, sort_keys=True))
