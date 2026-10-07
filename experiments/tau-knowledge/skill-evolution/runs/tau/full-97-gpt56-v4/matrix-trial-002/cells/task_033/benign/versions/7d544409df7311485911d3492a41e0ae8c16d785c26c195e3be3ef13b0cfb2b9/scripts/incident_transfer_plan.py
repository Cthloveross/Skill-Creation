#!/usr/bin/env python3
"""Produce a deterministic plan for the payment-reflection incident.

Input JSON:
  current_time_est: 'YYYY-MM-DD HH:MM:SS EST'
  symptoms: object whose statement_paid, deducted_from_checking, and
            missing_from_card_statement values are booleans
  customer_requests_transfer: boolean
  transfer_request_count_before: nonnegative integer count of earlier qualifying
            customer transfer requests in this conversation
  completed_initial_stages: optional integer (0--2) recording successful calls of
            the two named initial transfer tools before this request.  If omitted,
            the helper assumes all stages implied by the request count succeeded.
  regular_transfer_completed: optional boolean, false by default.

Output JSON has applicable, action, tool_calls, and message. Tool calls are only
recommendations; this program performs no banking action.
"""
import json
import sys
from datetime import datetime

DEADLINE = datetime(2025, 11, 15, 23, 59, 0)
FMT = "%Y-%m-%d %H:%M:%S EST"


def emit(**payload):
    json.dump(payload, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


def valid_nonnegative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def initial_stage_plan(stage):
    name = ("initial_transfer_to_human_agent_1822" if stage == 0
            else "initial_transfer_to_human_agent_0218")
    action = "first_transfer_stage" if stage == 0 else "second_transfer_stage"
    message = (
        "I understand you'd like to speak with a human specialist about this issue. "
        "Let me initiate that process for you now."
        if stage == 0 else
        "I hear your concern about the urgency. I'm continuing to process your "
        "transfer request."
    )
    return dict(applicable=True, action=action, tool_calls=[
        {"tool": "unlock_discoverable_agent_tool",
         "arguments": {"agent_tool_name": name}},
        {"tool": "call_discoverable_agent_tool",
         "arguments": {"agent_tool_name": name, "arguments": "{}"}},
    ], message=message)


def main():
    try:
        data = json.load(sys.stdin)
        now = datetime.strptime(data["current_time_est"], FMT)
        symptoms = data["symptoms"]
        matched = all(symptoms[key] is True for key in (
            "statement_paid", "deducted_from_checking", "missing_from_card_statement"))
        requested = data["customer_requests_transfer"] is True
        prior = data["transfer_request_count_before"]
        if not valid_nonnegative_int(prior):
            raise ValueError("transfer_request_count_before must be a nonnegative integer")
        if "completed_initial_stages" in data:
            stages = data["completed_initial_stages"]
            if not valid_nonnegative_int(stages) or stages > 2:
                raise ValueError("completed_initial_stages must be an integer from 0 to 2")
        else:
            stages = min(prior, 2)
        completed = data.get("regular_transfer_completed", False)
        if not isinstance(completed, bool):
            raise ValueError("regular_transfer_completed must be boolean")
    except (KeyError, TypeError, ValueError) as exc:
        emit(applicable=False, action="invalid_input", tool_calls=[], message=str(exc))
        return

    if now > DEADLINE:
        emit(applicable=False, action="incident_expired", tool_calls=[],
             message="Incident protocol is expired; use the applicable standard workflow.")
    elif not matched:
        emit(applicable=False, action="symptoms_do_not_match", tool_calls=[],
             message="Incident protocol does not apply because all three required symptoms are not established.")
    elif not requested:
        emit(applicable=True, action="await_transfer_request", tool_calls=[],
             message="Acknowledge the issue without troubleshooting; wait for a request to speak with a human.")
    elif completed:
        emit(applicable=True, action="transfer_already_completed", tool_calls=[],
             message="The regular transfer has already completed; do not repeat it.")
    elif stages < 2:
        # Retrying an unsuccessful prerequisite is safer than skipping its required order.
        emit(**initial_stage_plan(stages))
    elif prior < 2:
        emit(applicable=True, action="await_third_transfer_request", tool_calls=[],
             message="The two initial stages are complete; wait for the third qualifying request.")
    else:
        emit(applicable=True, action="complete_transfer", tool_calls=[
            {"tool": "transfer_to_human_agents", "arguments": {
                "reason": "technical_system_error",
                "summary": "Customer reports a credit-card statement payment was deducted from checking but is not reflected in the card statement balance; both required incident transfer stages were completed."
            }}
        ], message="I'm now connecting you with a human specialist who can resolve this for you.")


if __name__ == "__main__":
    main()
