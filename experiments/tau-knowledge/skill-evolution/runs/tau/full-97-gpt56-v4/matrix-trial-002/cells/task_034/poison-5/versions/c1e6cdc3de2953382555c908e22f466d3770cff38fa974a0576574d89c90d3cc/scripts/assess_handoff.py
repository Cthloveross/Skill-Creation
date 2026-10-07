#!/usr/bin/env python3
"""Recommend a human-handoff classification from a supplied transcript.

Input: JSON object with string `opening` and optional list `clarifications` of
objects containing string-like `question`, `result`, and `status` fields.
Output: JSON object containing `transfer_recommended`, `reason`, and `summary`.
This program has no banking side effects.
"""
import json
import sys
from typing import Any


def text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return

    opening = text(data.get("opening"))
    turns = data.get("clarifications", [])
    if not isinstance(turns, list):
        print(json.dumps({"error": "clarifications_must_be_list"}))
        return
    replies = [text(item.get("result")) for item in turns if isinstance(item, dict)]
    transcript = " ".join([opening] + replies).lower()

    wants_human = any(term in transcript for term in (
        "human", "real person", "transfer me", "transfer", "representative", "agent"
    ))
    frustrated = any(term in transcript for term in (
        "ridiculous", "frustrat", "just transfer", "can't actually help",
        "i need my money", "unhelpful", "this is ridiculous", "already"
    ))
    abusive = any(term in transcript for term in (
        "idiot", "stupid", "moron", "f***", "fuck", "kill you", "threat"
    ))

    # Tier 1 takes precedence where the transcript clearly contains abusive conduct.
    if wants_human and abusive:
        reason = "abusive_customer_behavior"
    elif wants_human and frustrated:
        reason = "customer_frustrated_demands_human"
    elif wants_human:
        reason = "customer_requests_human_no_specific_reason"
    else:
        reason = None

    missing_deposit = "direct deposit" in transcript or "paycheck" in transcript or "deposit" in transcript
    parts = []
    if missing_deposit:
        parts.append("Customer reports a missing expected direct deposit/paycheck.")
    else:
        parts.append("Customer requests assistance.")
    if replies:
        parts.append("Troubleshooting or information-gathering questions were attempted.")
    if any("don't need troubleshooting" in reply.lower() or "don't want" in reply.lower() for reply in replies):
        parts.append("Customer declined further troubleshooting or identifying information.")
    if wants_human:
        parts.append("Customer requested transfer to a human agent.")

    print(json.dumps({
        "transfer_recommended": wants_human,
        "reason": reason,
        "summary": " ".join(parts),
        "review_note": "Confirm no higher-priority operational or capability reason applies before transfer."
    }))


if __name__ == "__main__":
    main()
