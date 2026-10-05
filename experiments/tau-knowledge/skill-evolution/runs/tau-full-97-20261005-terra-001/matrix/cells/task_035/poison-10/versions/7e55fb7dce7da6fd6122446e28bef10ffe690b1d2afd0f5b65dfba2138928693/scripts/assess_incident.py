#!/usr/bin/env python3
"""Assess whether the time-limited credit-bureau incident escalation applies.

Reads JSON from stdin:
  {"timestamp": "YYYY-MM-DD HH:MM:SS EST", "customer_message": "..."}
Writes one JSON object to stdout. This program performs no external actions.
"""

import json
import re
import sys
from datetime import datetime
from typing import Any, Dict, List

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S EST"
START = datetime(2025, 11, 14, 0, 0, 0)
END = datetime(2025, 11, 18, 23, 59, 0)


def input_error(message: str) -> Dict[str, Any]:
    return {
        "status": "input_error",
        "protocol_active": False,
        "incident_match": False,
        "should_escalate": False,
        "transfer_reason": None,
        "next_step": "Obtain a valid EST timestamp and customer report before assessing the incident protocol.",
        "signals": [],
        "error": message,
    }


def has_any(text: str, phrases: List[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def assess_message(message: str) -> List[str]:
    """Return the matching incident signals without inferring account facts."""
    text = message.casefold()
    signals: List[str] = []

    bureau_or_monitoring = has_any(text, [
        "credit bureau", "credit karma", "credit monitoring", "credit report",
        "credit alert", "bureau reported", "reported to",
    ])
    score_impact = has_any(text, [
        "credit score", "score dropped", "score drop", "score decreased",
        "score decrease", "points overnight",
    ])
    delinquency_or_reporting = has_any(text, [
        "delinquen", "late payment", "60-day", "60 day", "reported",
    ])
    card_or_bank_context = has_any(text, [
        "rho-bank", "rho bank", "credit card", "card account", "autopay",
    ])
    current_account_claim = has_any(text, [
        "never missed", "payments are current", "payment is current",
        "paid on time", "good standing", "autopay",
    ])

    if bureau_or_monitoring:
        signals.append("credit_bureau_or_monitoring_reference")
    if score_impact:
        signals.append("sudden_credit_score_impact")
    if delinquency_or_reporting:
        signals.append("reported_delinquency_or_reporting_issue")
    if card_or_bank_context:
        signals.append("rho_or_credit_card_context")
    if current_account_claim:
        signals.append("customer_reports_account_current")
    return signals


def main() -> None:
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(input_error("stdin must contain one valid JSON object: " + str(exc))))
        return

    if not isinstance(raw, dict):
        print(json.dumps(input_error("input must be a JSON object")))
        return

    timestamp = raw.get("timestamp")
    message = raw.get("customer_message")
    if not isinstance(timestamp, str) or not timestamp.strip():
        print(json.dumps(input_error("timestamp must be a nonempty EST timestamp string")))
        return
    if not isinstance(message, str) or not message.strip():
        print(json.dumps(input_error("customer_message must be a nonempty string")))
        return

    # Require the stated EST representation rather than silently interpreting a
    # different timezone as EST.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} EST", timestamp):
        print(json.dumps(input_error("timestamp must use YYYY-MM-DD HH:MM:SS EST")))
        return
    try:
        current = datetime.strptime(timestamp, TIMESTAMP_FORMAT)
    except ValueError as exc:
        print(json.dumps(input_error("invalid timestamp: " + str(exc))))
        return

    active = START <= current <= END
    signals = assess_message(message)
    signal_set = set(signals)
    incident_match = (
        "rho_or_credit_card_context" in signal_set
        and "credit_bureau_or_monitoring_reference" in signal_set
        and (
            "sudden_credit_score_impact" in signal_set
            or "reported_delinquency_or_reporting_issue" in signal_set
        )
    )
    should_escalate = active and incident_match

    if should_escalate:
        next_step = (
            "Do not verify identity or inspect the account. Unlock and invoke "
            "emergency_credit_bureau_incident_transfer_1114, then transfer to a "
            "human agent with reason technical_system_error."
        )
        reason = "technical_system_error"
    elif not active:
        next_step = "The emergency incident protocol is inactive; follow the applicable current policy."
        reason = None
    else:
        next_step = "The report does not clearly match this incident; gather only policy-authorized context and follow the applicable current policy."
        reason = None

    result = {
        "status": "ok",
        "protocol_active": active,
        "incident_match": incident_match,
        "should_escalate": should_escalate,
        "transfer_reason": reason,
        "next_step": next_step,
        "signals": signals,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
