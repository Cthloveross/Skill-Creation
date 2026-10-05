#!/usr/bin/env python3
"""Select and explain a credit-card referral status.

Reads one JSON object from stdin and writes one JSON object to stdout.  It has
no network or account-tool access and is deliberately limited to supplied
referral metadata.
"""

import json
import sys
from datetime import datetime

VALID_STATUSES = {
    "COMPLETE",
    "IN_PROGRESS",
    "NO_PROGRESS",
    "APPLIED",
    "REJECTED",
    "ERROR",
}


def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def parse_date(value):
    """Return a sortable datetime for supported date representations."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            pass
    return None


def is_silver(account_type):
    return isinstance(account_type, str) and account_type.strip().lower() == "silver rewards card"


def response_for(record):
    status = record["referral_status"]
    card = record["referred_account_type"]
    prefix = "The selected {} referral dated {} is currently {}.".format(
        card, record["date"], status
    )
    do_not_claim = []

    if status == "IN_PROGRESS":
        detail = (
            " This means the referred person has successfully opened the account "
            "and is still working toward the referral-bonus criteria."
        )
        if is_silver(card):
            detail += (
                " For this Silver Rewards Card referral, they must be approved and "
                "spend at least $750 within 60 days of account opening. The bonus "
                "typically posts one to two billing cycles after the $750 requirement "
                "is met, so the posting period has not started merely because the card "
                "is being used. No action is required now other than monitoring the referral."
            )
        else:
            detail += (
                " The card-specific qualification terms were not supplied, so do not "
                "state a spend threshold or expected payout date. Monitor the referral "
                "until it reaches COMPLETE."
            )
        do_not_claim = [
            "Do not say the referred person has met the qualifying criteria.",
            "Do not say a bonus is already due or provide a payout date.",
            "Do not attribute this status to a referral cap without explicit evidence.",
        ]
    elif status == "COMPLETE":
        detail = (
            " COMPLETE means the referred person has met the criteria to receive the "
            "referral bonus under the applicable program terms."
        )
        if is_silver(card):
            detail += (
                " For Silver, the bonus typically posts one to two billing cycles after "
                "the $750 qualifying-spend requirement is met. The referral record alone "
                "does not provide the qualifying-spend date or a precise posting date."
            )
        do_not_claim = [
            "Do not assert that the bonus has already posted.",
            "Do not infer the qualifying-spend date from the referral record date.",
        ]
    elif status == "NO_PROGRESS":
        detail = " NO_PROGRESS means the invitee has not applied yet."
        do_not_claim = ["Do not say an account was opened or a bonus was earned."]
    elif status == "APPLIED":
        detail = " APPLIED means the application was submitted and is awaiting a decision; no manual intervention is needed."
        do_not_claim = ["Do not say the applicant was approved or qualifies for a bonus."]
    elif status == "REJECTED":
        detail = (
            " REJECTED means there are too many referral processes underway. Do not retry "
            "immediately; existing referral activity should be reviewed first."
        )
        do_not_claim = [
            "Do not claim this was specifically the rolling seven-day limit unless that is explicitly supplied.",
            "Do not promise reinstatement.",
        ]
    else:  # ERROR
        detail = (
            " ERROR indicates a processing error. Retry later or escalate internally if "
            "the condition persists."
        )
        do_not_claim = ["Do not promise that a retry or escalation will result in a bonus."]

    return prefix + detail, do_not_claim


def normalized_record(raw, index):
    if not isinstance(raw, dict):
        return None, "Referral at index {} is not an object.".format(index)
    card = raw.get("referred_account_type")
    status = raw.get("referral_status")
    date = raw.get("date")
    if not isinstance(card, str) or not card.strip():
        return None, "Referral at index {} has no card type.".format(index)
    if not isinstance(status, str) or status.strip().upper() not in VALID_STATUSES:
        return None, "Referral at index {} has an unsupported status.".format(index)
    if not isinstance(date, str) or not date.strip():
        return None, "Referral at index {} has no date.".format(index)
    return {
        "referral_id": raw.get("referral_id"),
        "referred_account_type": card.strip(),
        "referral_status": status.strip().upper(),
        "date": date.strip(),
        "_parsed_date": parse_date(date),
    }, None


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "error": "Input must be a JSON object.", "next_step": "Provide a referrals array."}
    raw_referrals = payload.get("referrals")
    if not isinstance(raw_referrals, list) or not raw_referrals:
        return {"ok": False, "error": "No referral records were supplied.", "next_step": "Retrieve the referrer's referral records."}

    referrals = []
    errors = []
    for index, raw in enumerate(raw_referrals):
        record, error = normalized_record(raw, index)
        if error:
            errors.append(error)
        else:
            referrals.append(record)
    if not referrals:
        return {"ok": False, "error": "No usable referral records were supplied.", "details": errors, "next_step": "Obtain records with card type, status, and date."}

    selector = payload.get("selector", {"mode": "most_recent"})
    if not isinstance(selector, dict):
        return {"ok": False, "error": "Selector must be an object.", "next_step": "Use selector.mode most_recent or referral_id."}
    mode = selector.get("mode", "most_recent")

    if mode == "referral_id":
        wanted = selector.get("referral_id")
        matches = [r for r in referrals if r["referral_id"] == wanted]
        if len(matches) != 1:
            return {"ok": False, "error": "The requested referral_id did not identify exactly one referral.", "next_step": "Ask for a valid referral identifier or use another selector."}
        selected = matches[0]
    elif mode == "most_recent":
        dated = [r for r in referrals if r["_parsed_date"] is not None]
        if not dated:
            return {"ok": False, "error": "No referral has a parseable date.", "next_step": "Ask for the card type or referral date."}
        newest_date = max(r["_parsed_date"] for r in dated)
        matches = [r for r in dated if r["_parsed_date"] == newest_date]
        if len(matches) != 1:
            return {"ok": False, "error": "More than one referral is tied for most recent.", "next_step": "Ask for the card type, referral date, or referral identifier."}
        selected = matches[0]
    else:
        return {"ok": False, "error": "Unsupported selector mode.", "next_step": "Use most_recent or referral_id."}

    message, do_not_claim = response_for(selected)
    public_selected = {
        "referred_account_type": selected["referred_account_type"],
        "referral_status": selected["referral_status"],
        "date": selected["date"],
    }
    if selected["referral_id"] is not None:
        public_selected["referral_id"] = selected["referral_id"]

    return {
        "ok": True,
        "selected_referral": public_selected,
        "customer_response": message,
        "do_not_claim": do_not_claim,
        "constraint_note": (
            "Do not calculate the two-successful-bonuses rolling 7-day cap from referral dates alone; "
            "it requires exact successful-bonus timestamps. Silver also has a 7-bonus calendar-year cap, "
            "which requires actual credited-bonus information to assess."
        ),
        "ignored_record_errors": errors,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit({"ok": False, "error": "Invalid JSON input: {}".format(exc.msg), "next_step": "Send one valid JSON object."})
        sys.exit(0)
    emit(main(data))
