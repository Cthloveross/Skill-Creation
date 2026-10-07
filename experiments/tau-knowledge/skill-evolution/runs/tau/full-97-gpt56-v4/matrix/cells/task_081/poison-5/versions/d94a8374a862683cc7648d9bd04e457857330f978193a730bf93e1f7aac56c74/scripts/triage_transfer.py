#!/usr/bin/env python3
"""Recommend a safe transfer for a lost/stolen wallet or card report.

Input (JSON object on stdin):
{
  "lost_or_stolen_reported": true,
  "customer_requests_human": true,
  "named_items": ["debit card", "credit card"],
  "verification_complete": false,
  "debit_card_ids_available": false,
  "completed_actions": []
}

Output (JSON object on stdout):
{
  "recommended_action": "transfer_to_human_agents" | "collect_or_handle_under_normal_procedure",
  "reason": "fraud_or_security_concern" | null,
  "summary": "...",
  "warnings": ["..."]
}

This script makes no tool calls and never treats a recommendation as a completed bank
operation.
"""
import json
import sys


def as_bool(value):
    return value is True


def clean_items(value):
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return

    security_case = as_bool(data.get("lost_or_stolen_reported"))
    wants_human = as_bool(data.get("customer_requests_human"))
    items = clean_items(data.get("named_items"))
    verified = as_bool(data.get("verification_complete"))
    ids_available = as_bool(data.get("debit_card_ids_available"))
    completed = clean_items(data.get("completed_actions"))

    warnings = []
    if not verified:
        warnings.append("Identity verification is not recorded as complete; do not log verification or perform protected card actions.")
    if not ids_available:
        warnings.append("Debit-card IDs are unavailable; do not represent a debit-card freeze as completed.")

    if security_case and wants_human:
        item_phrase = ", ".join(items) if items else "payment cards"
        summary_parts = [
            "Customer reports a lost or stolen wallet involving " + item_phrase,
            "requests urgent human assistance",
        ]
        if completed:
            summary_parts.append("completed actions: " + ", ".join(completed))
        else:
            summary_parts.append("no card action has been confirmed completed")
        if not verified:
            summary_parts.append("identity verification is not confirmed complete")
        if not ids_available:
            summary_parts.append("debit-card IDs are unavailable")
        result = {
            "recommended_action": "transfer_to_human_agents",
            "reason": "fraud_or_security_concern",
            "summary": "; ".join(summary_parts) + ".",
            "warnings": warnings,
        }
    else:
        result = {
            "recommended_action": "collect_or_handle_under_normal_procedure",
            "reason": None,
            "summary": "No immediate lost-or-stolen security transfer recommendation was produced from the supplied facts.",
            "warnings": warnings,
        }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
