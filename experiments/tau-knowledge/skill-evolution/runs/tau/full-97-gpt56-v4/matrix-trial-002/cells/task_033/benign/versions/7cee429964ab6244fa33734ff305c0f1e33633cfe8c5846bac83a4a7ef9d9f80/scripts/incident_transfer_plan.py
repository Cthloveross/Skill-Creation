#!/usr/bin/env python3
"""Produce a deterministic incident-transfer action plan.

Input JSON:
  current_time_est: string in 'YYYY-MM-DD HH:MM:SS EST' form
  symptoms: object with boolean statement_paid, deducted_from_checking,
            missing_from_card_statement
  customer_requests_transfer: boolean
  transfer_request_count_before: nonnegative integer

Output JSON contains applicable, action, tool_calls, and message.  The script performs
no bank action; its tool_calls are recommendations for a conversation executor.
"""
import json
import sys
from datetime import datetime

DEADLINE = datetime(2025, 11, 15, 23, 59, 59)
FMT = "%Y-%m-%d %H:%M:%S EST"


def emit(**payload):
    json.dump(payload, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


def main():
    try:
        data = json.load(sys.stdin)
        now = datetime.strptime(data["current_time_est"], FMT)
        symptoms = data["symptoms"]
        matched = all(symptoms[k] is True for k in (
            "statement_paid", "deducted_from_checking", "missing_from_card_statement"
        ))
        requested = data["customer_requests_transfer"] is True
        prior = data["transfer_request_count_before"]
        if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
            raise ValueError("transfer_request_count_before must be a nonnegative integer")
    except (KeyError, TypeError, ValueError) as exc:
        emit(applicable=False, action="invalid_input", tool_calls=[], message=str(exc))
        return

    if now > DEADLINE:
        emit(applicable=False, action="incident_expired", tool_calls=[],
             message="Incident protocol is expired; use the applicable standard workflow.")
        return
    if not matched:
        emit(applicable=False, action="symptoms_do_not_match", tool_calls=[],
             message="Incident protocol does not apply because all three required symptoms are not established.")
        return
    if not requested:
        emit(applicable=True, action="await_transfer_request", tool_calls=[],
             message="Acknowledge the issue without troubleshooting; wait for a request to speak with a human.")
        return

    if prior == 0:
        emit(applicable=True, action="first_transfer_stage", tool_calls=[
            {"tool":"unlock_discoverable_agent_tool", "arguments":{"agent_tool_name":"initial_transfer_to_human_agent_1822"}},
            {"tool":"call_discoverable_agent_tool", "arguments":{"agent_tool_name":"initial_transfer_to_human_agent_1822", "arguments":"{}"}}
        ], message="I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.")
    elif prior == 1:
        emit(applicable=True, action="second_transfer_stage", tool_calls=[
            {"tool":"unlock_discoverable_agent_tool", "arguments":{"agent_tool_name":"initial_transfer_to_human_agent_0218"}},
            {"tool":"call_discoverable_agent_tool", "arguments":{"agent_tool_name":"initial_transfer_to_human_agent_0218", "arguments":"{}"}}
        ], message="I hear your concern about the urgency. I'm continuing to process your transfer request.")
    elif prior == 2:
        emit(applicable=True, action="complete_transfer", tool_calls=[
            {"tool":"transfer_to_human_agents", "arguments":{"reason":"technical_system_error", "summary":"Customer reports a credit-card statement payment was deducted from checking but is not reflected in the card statement balance; both required incident transfer stages were completed."}}
        ], message="I'm now connecting you with a human specialist who can resolve this for you.")
    else:
        # A completed regular transfer should end the conversation.  Do not issue a
        # duplicate transfer if a caller supplies a later request count.
        emit(applicable=True, action="transfer_already_completed", tool_calls=[],
             message="The incident transfer has already been completed; do not repeat it.")


if __name__ == "__main__":
    main()
