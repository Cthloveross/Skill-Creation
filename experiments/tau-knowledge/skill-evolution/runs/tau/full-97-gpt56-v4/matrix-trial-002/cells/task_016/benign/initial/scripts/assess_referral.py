#!/usr/bin/env python3
"""Create a fact-only assessment for a selected referral.

Input JSON:
{
  "referrals": [{"date": "YYYY-MM-DD" or "MM/DD/YYYY", "card_type": str,
                 "status": str, ...}],
  "selection": {"most_recent": bool} OR
               {"card_type": str, "date": "YYYY-MM-DD" or "MM/DD/YYYY"},
  "card_terms": {card_type: {"qualifying_spend": number,
                              "spend_window_days": integer,
                              "payout_timing": string}}
}

Output JSON contains no inferred customer or referred-person facts. It is an aid for
forming a response after the caller has obtained the underlying records normally.
"""
import json
import sys
from datetime import datetime


def parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def select_referral(referrals, selection):
    if selection.get("most_recent") is True:
        dated = [(parse_date(r.get("date")), r) for r in referrals]
        dated = [(d, r) for d, r in dated if d is not None]
        if not dated:
            return None, "No referral has a usable date; ask the customer to identify the referral."
        latest = max(d for d, _ in dated)
        matches = [r for d, r in dated if d == latest]
        if len(matches) != 1:
            return None, "More than one referral has the latest date; ask for card type or date."
        return matches[0], None

    card_type = selection.get("card_type")
    wanted_date = parse_date(selection.get("date"))
    matches = []
    for referral in referrals:
        if card_type and referral.get("card_type") != card_type:
            continue
        if wanted_date and parse_date(referral.get("date")) != wanted_date:
            continue
        matches.append(referral)
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, "No referral matches the supplied selection; request corrected identifying details."
    return None, "The supplied selection matches multiple referrals; ask a clarifying question."


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": "Invalid JSON input: " + str(exc)}))
        return

    referrals = payload.get("referrals")
    selection = payload.get("selection", {})
    if not isinstance(referrals, list) or not isinstance(selection, dict):
        print(json.dumps({"ok": False, "error": "referrals must be a list and selection must be an object."}))
        return

    referral, error = select_referral(referrals, selection)
    if error:
        print(json.dumps({"ok": False, "error": error, "next_step": "Ask a clarification; do not choose a referral."}))
        return

    card_type = referral.get("card_type")
    status = str(referral.get("status", "UNKNOWN")).upper()
    terms = payload.get("card_terms", {}).get(card_type, {})
    cautions = [
        "Do not infer approval, account-opening date, qualifying spend, or bonus payment from the referral status alone.",
        "Do not calculate a rolling-seven-day cap from date-only records; exact timestamps are required."
    ]
    if status == "IN_PROGRESS":
        assessment = "The referral remains in progress; available record status does not show a completed or paid bonus."
    elif status == "COMPLETE":
        assessment = "The referral record is complete. This alone does not independently prove that a bonus has posted."
    elif status in ("REJECTED", "ERROR"):
        assessment = "The referral record is " + status + "; the status alone does not establish a reason."
    else:
        assessment = "The referral has recorded status " + status + "; no eligibility or payment conclusion follows from that status alone."

    result = {
        "ok": True,
        "selected_referral": {
            "date": referral.get("date"),
            "card_type": card_type,
            "status": referral.get("status")
        },
        "assessment": assessment,
        "applicable_terms": terms,
        "cautions": cautions
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
