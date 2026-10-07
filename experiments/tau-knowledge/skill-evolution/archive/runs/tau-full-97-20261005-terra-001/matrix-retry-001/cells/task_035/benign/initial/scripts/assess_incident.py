#!/usr/bin/env python3
"""Assess whether the packaged emergency credit-bureau incident applies.

Reads JSON from stdin and writes JSON to stdout. This helper does not make
banking-tool calls and must not be treated as an authorization to skip the
incident protocol review.
"""
import json
import re
import sys
from datetime import datetime

WINDOW_START = datetime(2025, 11, 14, 0, 0, 0)
WINDOW_END = datetime(2025, 11, 18, 23, 59, 59)


def parse_est_timestamp(value):
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if cleaned.endswith(" EST"):
        cleaned = cleaned[:-4]
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def has_any(text, patterns):
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def assess(payload):
    opening = payload.get("opening", "")
    if not isinstance(opening, str):
        opening = ""
    timestamp = parse_est_timestamp(payload.get("current_time"))
    text = opening.lower()

    credit_card = has_any(text, [r"credit\s*card", r"card\s*account"])
    delinquency = has_any(text, [r"delinquen", r"late\s+payment", r"past\s+due", r"60[ -]?day"])
    current = has_any(text, [r"never\s+missed", r"payments?\s+(are|is)\s+current", r"good\s+standing", r"autopay", r"paid\s+on\s+time"])
    bureau_impact = has_any(text, [r"credit\s*(karma|bureau|report|score)", r"score\s+dropped", r"score\s+drop", r"reported"])
    rho_bank = has_any(text, [r"rho[ -]?bank"])
    window_active = timestamp is not None and WINDOW_START <= timestamp <= WINDOW_END

    signals = []
    if credit_card:
        signals.append("credit-card issue reported")
    if delinquency:
        signals.append("delinquency reported")
    if current:
        signals.append("customer states payments are current/good standing")
    if bureau_impact:
        signals.append("credit-reporting or score impact reported")
    if rho_bank:
        signals.append("Rho-Bank identified")
    if window_active:
        signals.append("timestamp is inside the incident window")
    elif timestamp is None:
        signals.append("timestamp is missing or not in supported EST format")
    else:
        signals.append("timestamp is outside the incident window")

    applicable = window_active and credit_card and delinquency and current and bureau_impact
    return {
        "applicable": applicable,
        "signals": signals,
        "window_active": window_active,
        "required_actions": ([
            "unlock_discoverable_agent_tool",
            "call_discoverable_agent_tool",
            "transfer_to_human_agents",
        ] if applicable else []),
        "prohibited_actions": ([
            "identity_verification",
            "account_or_transaction_lookup",
            "normal_dispute_before_escalation",
        ] if applicable else []),
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = assess(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {
            "applicable": False,
            "signals": ["invalid input: " + str(exc)],
            "window_active": False,
            "required_actions": [],
            "prohibited_actions": [],
        }
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
