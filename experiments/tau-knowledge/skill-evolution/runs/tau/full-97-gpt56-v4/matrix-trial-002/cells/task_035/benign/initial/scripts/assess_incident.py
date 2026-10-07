#!/usr/bin/env python3
"""Assess whether a message appears to match the active reporting incident.

Input JSON: {"timestamp": str, "customer_message": str}
Output JSON: {"active_window": bool, "matching_report_signals": [str],
              "should_use_emergency_protocol": bool, "notes": str}
"""

import json
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

WINDOW_START = datetime(2025, 11, 14, 0, 0, 0)
WINDOW_END = datetime(2025, 11, 18, 23, 59, 59)


def parse_est_timestamp(value: Any) -> Optional[datetime]:
    """Parse common supplied EST timestamp forms without external libraries."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    text = re.sub(r"\s+(?:EST|EDT)$", "", text, flags=re.IGNORECASE)
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            pass
    return None


def find_signals(message: Any) -> List[str]:
    """Return stable signal labels, in a user-facing useful order."""
    if not isinstance(message, str):
        return []
    text = message.lower()
    signals: List[str] = []
    if re.search(r"\b(?:credit\s*)?score\b.*\b(?:drop|dropped|decreas|fall|down)|\b(?:drop|dropped|decreas|fall)\w*\b.*\b(?:credit\s*)?score\b", text):
        signals.append("sudden_credit_score_change")
    if re.search(r"\b(?:delinquen|late payment|past due|60[- ]?day)\w*\b", text):
        signals.append("reported_delinquency")
    if re.search(r"\b(?:credit karma|credit bureau|credit report|credit monitoring|bureau)\b", text):
        signals.append("credit_reporting_alert")
    if re.search(r"\b(?:current|good standing|never missed|autopay|on time)\b", text):
        signals.append("customer_says_account_current")
    if re.search(r"\b(?:rho[ -]?bank|rho)\b", text) and re.search(r"\b(?:credit card|card)\b", text):
        signals.append("rho_bank_credit_card_context")
    return signals


def assess(payload: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = parse_est_timestamp(payload.get("timestamp"))
    active = timestamp is not None and WINDOW_START <= timestamp <= WINDOW_END
    signals = find_signals(payload.get("customer_message"))
    # A delinquency assertion or a score/reporting alert is sufficient incident evidence.
    core = {"reported_delinquency", "sudden_credit_score_change", "credit_reporting_alert"}
    matches = bool(core.intersection(signals)) and (
        "rho_bank_credit_card_context" in signals
        or "customer_says_account_current" in signals
        or "reported_delinquency" in signals
    )
    should_use = bool(active and matches)
    if timestamp is None:
        note = "Timestamp is missing or unsupported; confirm the current EST time before applying this time-limited protocol."
    elif not active:
        note = "The supplied timestamp is outside the active incident window."
    elif matches:
        note = "The report appears consistent with the active erroneous credit-bureau reporting incident."
    else:
        note = "The active window is open, but the message lacks clear incident-reporting signals."
    return {
        "active_window": active,
        "matching_report_signals": signals,
        "should_use_emergency_protocol": should_use,
        "notes": note,
    }


def main() -> None:
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        result = assess(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {
            "active_window": False,
            "matching_report_signals": [],
            "should_use_emergency_protocol": False,
            "notes": "Invalid input: %s" % exc,
        }
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
