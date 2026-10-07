#!/usr/bin/env python3
"""Produce a deterministic recommendation for the incident transfer protocol.

Input JSON object:
  current_time_est: string in '%Y-%m-%d %H:%M:%S EST' format
  paid_statement, deducted_from_checking, missing_from_card_statement: booleans
  transfer_request_count: nonnegative integer
  completed_stages: list containing zero or more of 'stage_1', 'stage_2'

Output JSON object includes eligibility, action, tool_calls, customer_message, and notes.
This helper does not call banking tools and does not establish completion of a stage.
"""
import json
import sys
from datetime import datetime

DEADLINE = datetime(2025, 11, 15, 23, 59, 0)
STAGE_1 = "initial_transfer_to_human_agent_1822"
STAGE_2 = "initial_transfer_to_human_agent_0218"


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("current_time_est must be a timestamp string")
    suffix = " EST"
    if not value.endswith(suffix):
        raise ValueError("current_time_est must use the EST suffix")
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S EST")


def stage_calls(tool_name):
    return [
        {"tool": "unlock_discoverable_agent_tool", "arguments": {"agent_tool_name": tool_name}},
        {
            "tool": "call_discoverable_agent_tool",
            "arguments": {"agent_tool_name": tool_name, "arguments": "{}"},
        },
    ]


def plan(data):
    required = ("paid_statement", "deducted_from_checking", "missing_from_card_statement")
    if not all(isinstance(data.get(key), bool) for key in required):
        raise ValueError("the three incident symptom fields must be booleans")
    request_count = data.get("transfer_request_count")
    if not isinstance(request_count, int) or isinstance(request_count, bool) or request_count < 0:
        raise ValueError("transfer_request_count must be a nonnegative integer")
    stages = data.get("completed_stages", [])
    if not isinstance(stages, list) or any(s not in {"stage_1", "stage_2"} for s in stages):
        raise ValueError("completed_stages may contain only stage_1 and stage_2")
    if len(set(stages)) != len(stages):
        raise ValueError("completed_stages must not contain duplicates")

    now = parse_time(data.get("current_time_est"))
    symptoms_match = all(data[key] for key in required)
    eligible = now <= DEADLINE and symptoms_match
    out = {
        "eligible": eligible,
        "incident_window_open": now <= DEADLINE,
        "symptoms_match": symptoms_match,
        "action": "standard_handling",
        "tool_calls": [],
        "customer_message": None,
        "notes": [],
    }
    if not eligible:
        out["notes"].append("Do not use incident transfer tools; use the applicable standard process.")
        return out
    if request_count == 0:
        out["action"] = "await_human_transfer_request"
        out["notes"].append("Do not troubleshoot or verify identity during the incident window.")
        return out

    if request_count == 1:
        if "stage_1" in stages:
            out["action"] = "await_next_request"
            out["notes"].append("First transfer stage is already completed; do not repeat it.")
        else:
            out["action"] = "initial_stage_1"
            out["tool_calls"] = stage_calls(STAGE_1)
            out["customer_message"] = "I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now."
        return out

    if request_count == 2:
        if "stage_1" not in stages:
            out["action"] = "blocked_missing_stage_1"
            out["notes"].append("Do not skip stage 1. Resolve its uncompleted state before advancing.")
        elif "stage_2" in stages:
            out["action"] = "await_next_request"
            out["notes"].append("Second transfer stage is already completed; do not repeat it.")
        else:
            out["action"] = "initial_stage_2"
            out["tool_calls"] = stage_calls(STAGE_2)
            out["customer_message"] = "I hear your concern about the urgency. I'm continuing to process your transfer request."
        return out

    if "stage_1" not in stages or "stage_2" not in stages:
        out["action"] = "blocked_missing_required_stages"
        out["notes"].append("Regular transfer is prohibited until both initial stages completed in order.")
        return out
    out["action"] = "regular_transfer"
    out["tool_calls"] = [{
        "tool": "transfer_to_human_agents",
        "arguments": {
            "reason": "specialized_department_required",
            "summary": "Customer reports a credit-card statement payment was deducted from checking but is not reflected in the card statement balance; both required incident transfer stages were completed.",
        },
    }]
    out["customer_message"] = "I'm now connecting you with a human specialist who can resolve this for you."
    return out


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(plan(data), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
