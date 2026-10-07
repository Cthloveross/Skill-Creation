#!/usr/bin/env python3
"""Select a referral record and return conservative, documented talking points.

Input and output are JSON objects on stdin/stdout. This helper is purely local: it
never reads bank data, performs a banking action, or determines actual eligibility.
"""
import datetime as dt
import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def parse_date(value: Any) -> Optional[dt.date]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def error(reason: str, clarification: str) -> Dict[str, Any]:
    return {"ok": False, "reason": reason, "clarification_needed": clarification}


def select(records: List[Dict[str, Any]], selection: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    mode = selection.get("mode")
    if mode == "id":
        referral_id = selection.get("referral_id")
        matches = [r for r in records if r.get("referral_id") == referral_id]
    elif mode == "card_and_date":
        matches = [
            r for r in records
            if r.get("referred_account_type") == selection.get("card_type")
            and str(r.get("date", "")) == str(selection.get("date", ""))
        ]
    elif mode == "most_recent":
        dated = [(parse_date(r.get("date")), r) for r in records]
        if any(date is None for date, _ in dated):
            return None, error("unparseable_referral_date", "Please identify the friend or card and roughly when they applied.")
        latest_date = max(date for date, _ in dated)
        matches = [record for date, record in dated if date == latest_date]
    else:
        return None, error("unsupported_selection", "Please identify which referral you would like checked.")

    if not matches:
        return None, error("no_matching_referral", "I could not find that referral. Please confirm the card type or approximate application date.")
    if len(matches) != 1:
        return None, error("ambiguous_referral", "I found more than one matching referral. Please provide the card type and approximate application date.")
    return matches[0], None


def talking_points(record: Dict[str, Any]) -> List[str]:
    status = str(record.get("referral_status", "")).upper()
    card_type = str(record.get("referred_account_type", ""))
    points: List[str] = []
    if status == "IN_PROGRESS":
        points.append("The referral is still in progress; approval or initial purchases do not by themselves establish qualification.")
        if card_type == "Silver Rewards Card":
            points.extend([
                "For Silver Rewards, the referred person must be approved and spend at least $750 within 60 days of account opening.",
                "The $75 bonus normally posts one to two billing cycles after that requirement is met.",
            ])
        else:
            points.append("The available policy does not establish this card's specific qualification amount or timing.")
    elif status == "COMPLETE":
        points.append("The referral record is complete.")
        if card_type == "Silver Rewards Card":
            points.append("For Silver Rewards, the normal posting window is one to two billing cycles after the qualifying $750 spend requirement was met.")
        else:
            points.append("Card-specific payout timing is not established by the available policy.")
    elif status == "REJECTED":
        points.append("The referral record is rejected; no rejection cause is available in this record.")
        points.append("Do not attribute the rejection to a policy restriction without a recorded reason or exact successful-bonus timestamps.")
    elif status == "ERROR":
        points.append("The record reports an error and needs technical review; do not infer eligibility or payout.")
    else:
        points.append("The status is not recognized by this helper and needs specialist review.")
    points.append("Across card types, no more than two successful referral bonuses may occur in a rolling seven-day window; date-only records cannot establish that cap.")
    return points


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps(error("invalid_json", "Referral data could not be read; retrieve the referral records again.")))
        return
    records = payload.get("referrals")
    selection = payload.get("selection", {})
    if not isinstance(records, list) or not records:
        print(json.dumps(error("missing_referrals", "No referral records were supplied; retrieve the customer's referrals.")))
        return
    if not all(isinstance(record, dict) for record in records) or not isinstance(selection, dict):
        print(json.dumps(error("invalid_schema", "The referral data format is incomplete; retrieve the referral records again.")))
        return
    record, selection_error = select(records, selection)
    if selection_error:
        print(json.dumps(selection_error, sort_keys=True))
        return
    assert record is not None
    output = {
        "ok": True,
        "selected_referral": {
            "referral_id": record.get("referral_id"),
            "referred_account_type": record.get("referred_account_type"),
            "referral_status": record.get("referral_status"),
            "date": record.get("date"),
        },
        "talking_points": talking_points(record),
        "limitations": [
            "This analysis does not confirm referred-person approval, spending, qualification, payout, or a rejection cause.",
            "The referral date is not assumed to be the qualifying-spend or bonus-posting date.",
        ],
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
