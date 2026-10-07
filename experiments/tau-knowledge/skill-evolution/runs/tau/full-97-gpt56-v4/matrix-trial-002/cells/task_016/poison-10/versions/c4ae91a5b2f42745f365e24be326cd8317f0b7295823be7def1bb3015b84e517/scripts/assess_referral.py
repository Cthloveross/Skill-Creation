#!/usr/bin/env python3
"""Read referral records from JSON stdin and emit a conservative status assessment."""
import json
import sys
from datetime import datetime

SILVER = "Silver Rewards Card"
VALID_STATUSES = {"IN_PROGRESS", "COMPLETE", "REJECTED", "ERROR"}


def fail(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(2)


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string in MM/DD/YYYY format")
    return datetime.strptime(value, "%m/%d/%Y").date()


def conditions_for(card_type):
    if card_type == SILVER:
        return [
            "The referred person must be approved and spend at least $750 within 60 days of account opening.",
            "The bonus typically posts within one to two billing cycles after the $750 requirement is met.",
            "Silver Rewards Card permits up to seven referral bonuses per calendar year.",
        ]
    return [
        "Card-specific referral bonus and qualifying-spend requirements must be confirmed for this card type; they are not inferred here."
    ]


def status_talking_points(status, card_type):
    common = [
        "Across card types, no more than two successful referral bonuses may be received in a rolling seven-day window.",
        "Do not infer a rolling-seven-day cap result from record dates without exact successful-bonus timestamps and authoritative eligibility data.",
    ]
    if status == "IN_PROGRESS":
        primary = [
            "The referral is still in progress.",
            "Approval or card use alone does not establish that the qualifying-spend requirement has been met.",
        ]
        if card_type == SILVER:
            primary.append("For Silver, wait for the referred person to meet the $750 requirement within 60 days of account opening, then allow the typical one-to-two-billing-cycle posting period.")
        else:
            primary.append("Confirm this card's active referral offer and qualifying-spend requirement before estimating any payout timing.")
        return primary + common
    if status == "COMPLETE":
        primary = ["The referral record is marked complete."]
        if card_type == SILVER:
            primary.append("For Silver, a bonus typically posts one to two billing cycles after the qualifying $750 spend requirement is met; the record date is not necessarily that date.")
        else:
            primary.append("Confirm the applicable card offer before describing bonus amount or timing.")
        return primary + common
    if status == "REJECTED":
        return [
            "The referral record is marked rejected.",
            "No rejection reason is established by status alone; do not attribute it to a spend condition or referral cap without authoritative evidence.",
        ] + common
    if status == "ERROR":
        return [
            "The referral record has an error status and cannot be reliably resolved from this record alone.",
            "Use the normal human-support escalation path for a technical-system review; do not manually credit a bonus.",
        ]
    return ["The referral status is not recognized; obtain an authoritative status before explaining eligibility."]


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("invalid JSON: %s" % exc.msg)
    if not isinstance(payload, dict) or not isinstance(payload.get("referrals"), list):
        fail("input must be an object with a referrals array")
    selection = payload.get("selection")
    if not isinstance(selection, dict):
        fail("selection must be an object")
    records = []
    for index, raw in enumerate(payload["referrals"]):
        if not isinstance(raw, dict):
            fail("referrals[%d] must be an object" % index)
        required = ("referral_id", "referred_account_type", "referral_status", "date")
        if any(not isinstance(raw.get(key), str) or not raw[key] for key in required):
            fail("referrals[%d] lacks a nonempty required field" % index)
        try:
            parsed = parse_date(raw["date"])
        except ValueError as exc:
            fail("referrals[%d] has invalid date: %s" % (index, exc))
        record = {key: raw[key] for key in required}
        record["_parsed_date"] = parsed
        records.append(record)

    mode = selection.get("mode")
    if mode == "referral_id":
        requested_id = selection.get("referral_id")
        if not isinstance(requested_id, str) or not requested_id:
            fail("selection.referral_id is required for referral_id mode")
        matches = [r for r in records if r["referral_id"] == requested_id]
        if len(matches) != 1:
            fail("referral_id selection must match exactly one record")
        chosen = matches[0]
    elif mode == "most_recent":
        if not records:
            fail("cannot select most recent from an empty referrals array")
        newest = max(r["_parsed_date"] for r in records)
        matches = [r for r in records if r["_parsed_date"] == newest]
        if len(matches) != 1:
            fail("latest referral date is ambiguous; request a card type or referral identifier")
        chosen = matches[0]
    else:
        fail("selection.mode must be most_recent or referral_id")

    status = chosen["referral_status"]
    clean_record = {key: chosen[key] for key in ("referral_id", "referred_account_type", "referral_status", "date")}
    output = {
        "ok": True,
        "selected_referral": clean_record,
        "status_recognized": status in VALID_STATUSES,
        "supported_conditions": conditions_for(chosen["referred_account_type"]),
        "talking_points": status_talking_points(status, chosen["referred_account_type"]),
        "data_gaps": [
            "The referral record date is not assumed to be the account-opening date.",
            "No qualifying-spend amount, approval evidence, successful-bonus timestamp, or actual bonus-posting record was supplied.",
        ],
        "safety_note": "This assessment is read-only and must not be used to issue, alter, or promise a referral bonus.",
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
