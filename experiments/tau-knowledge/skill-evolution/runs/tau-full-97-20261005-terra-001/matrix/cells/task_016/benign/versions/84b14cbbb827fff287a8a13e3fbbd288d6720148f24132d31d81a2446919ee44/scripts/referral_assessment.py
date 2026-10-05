#!/usr/bin/env python3
"""Select and summarize one existing credit-card referral record.

Reads one JSON object from stdin and writes one JSON object to stdout.  This
program is deliberately read-only: it makes no tool calls and does not infer
whether a referral has met spending or other card-specific requirements.
"""

import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

STATUS_GUIDANCE = {
    "COMPLETE": "The referred person met the criteria; the bonus is granted under applicable program terms.",
    "IN_PROGRESS": "The account was opened and the referred person is still working toward the referral criteria; monitor until the criteria are met.",
    "NO_PROGRESS": "The referred person has not applied; the referrer may remind them to start an application using the referral link.",
    "APPLIED": "The application is awaiting a decision; no manual intervention is needed.",
    "REJECTED": "Too many referral processes are underway; do not retry immediately and review existing referral activity.",
    "ERROR": "An error occurred; retry later or escalate internally if the condition persists.",
}


def parse_date(value: Any) -> Optional[datetime]:
    """Parse supported record dates, returning None for absent/invalid values."""
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def error(code: str, message: str) -> Dict[str, Any]:
    return {"ok": False, "error": code, "message": message}


def select_records(referrals: List[Dict[str, Any]], selector: Dict[str, Any]) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    """Return matching records or a formatted error.

    An exact referral ID takes priority. Card/date selection must resolve to one
    record. Most-recent selection is allowed only with boolean true and rejects
    ties, missing dates, and an empty list.
    """
    referral_id = selector.get("referral_id")
    card_name = selector.get("card_name")
    date = selector.get("date")
    most_recent = selector.get("most_recent", False)

    if referral_id is not None:
        matches = [r for r in referrals if r.get("referral_id") == referral_id]
        return matches, None

    if most_recent is True:
        dated = [(parse_date(r.get("date")), r) for r in referrals]
        if not dated or any(parsed is None for parsed, _ in dated):
            return None, error("invalid_dates", "Most-recent selection requires a valid date on every candidate record.")
        newest = max(parsed for parsed, _ in dated)
        return [record for parsed, record in dated if parsed == newest], None

    if isinstance(card_name, str) or isinstance(date, str):
        matches = referrals
        if isinstance(card_name, str):
            matches = [r for r in matches if r.get("referred_account_type") == card_name]
        if isinstance(date, str):
            matches = [r for r in matches if r.get("date") == date]
        return matches, None

    return None, error("missing_selector", "Provide referral_id, card_name/date, or confirmed most_recent=true.")


def assess(payload: Dict[str, Any]) -> Dict[str, Any]:
    referrals = payload.get("referrals")
    selector = payload.get("selector")
    if not isinstance(referrals, list) or not all(isinstance(item, dict) for item in referrals):
        return error("invalid_referrals", "referrals must be an array of objects.")
    if not isinstance(selector, dict):
        return error("invalid_selector", "selector must be an object.")

    matches, selection_error = select_records(referrals, selector)
    if selection_error:
        return selection_error
    assert matches is not None
    if not matches:
        return error("no_matching_referral", "No referral matches the supplied selector.")
    if len(matches) != 1:
        return error("ambiguous_selection", "The selector matches multiple referrals; obtain a more specific identifier.")

    selected = matches[0]
    status = selected.get("referral_status")
    if not isinstance(status, str) or status not in STATUS_GUIDANCE:
        return {
            "ok": False,
            "error": "unsupported_status",
            "message": "The selected referral has no recognized status.",
            "selected": selected,
        }
    return {
        "ok": True,
        "selected": selected,
        "status": status,
        "status_guidance": STATUS_GUIDANCE[status],
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(error("invalid_json", f"Input is not valid JSON: {exc.msg}")))
        return
    if not isinstance(payload, dict):
        print(json.dumps(error("invalid_input", "Top-level input must be a JSON object.")))
        return
    print(json.dumps(assess(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
