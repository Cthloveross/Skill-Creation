#!/usr/bin/env python3
"""Analyze referral records without making banking-system calls.

Reads a JSON object from stdin:
  {"referrals": [{"referred_account_type": str,
                   "referral_status": str, "date": str}, ...]}
Writes a JSON object described in SKILL.md to stdout.
"""

import datetime as dt
import json
import sys
from collections import Counter

CARD_TERMS = {
    "Silver Rewards Card": {
        "approval_required": True,
        "qualifying_spend": "$750 within 60 days of account opening",
        "bonus": "75",
        "payout_timing": "normally one to two billing cycles after the spend requirement is met",
        "annual_limit": 7,
    },
    "Platinum Rewards Card": {
        "approval_required": True,
        "qualifying_spend": "$1,500 within 90 days of account opening",
        "bonus": "$100",
        "additional_conditions": "self-referrals and duplicate applications do not qualify",
        "annual_limit": 7,
    },
}


def parse_date(value):
    """Return a date for supported public record formats, else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def fail(message):
    return {"ok": False, "error": message}


def analyze(payload):
    if not isinstance(payload, dict):
        return fail("Input must be a JSON object.")
    referrals = payload.get("referrals")
    if not isinstance(referrals, list):
        return fail("'referrals' must be an array.")

    warnings = []
    normalized = []
    for index, item in enumerate(referrals):
        if not isinstance(item, dict):
            warnings.append("Referral at index %d was not an object and was skipped." % index)
            continue
        card = item.get("referred_account_type")
        status = item.get("referral_status")
        raw_date = item.get("date")
        if not isinstance(card, str) or not card.strip():
            card = "Unknown card"
            warnings.append("Referral at index %d has no usable card type." % index)
        if not isinstance(status, str) or not status.strip():
            status = "UNKNOWN"
            warnings.append("Referral at index %d has no usable status." % index)
        else:
            status = status.strip().upper()
        parsed = parse_date(raw_date)
        if parsed is None:
            warnings.append("Referral at index %d has an unusable date." % index)
        normalized.append({
            "index": index,
            "card": card.strip() if isinstance(card, str) else card,
            "status": status,
            "date": raw_date if isinstance(raw_date, str) else None,
            "parsed_date": parsed,
        })

    counts = Counter(record["status"] for record in normalized)
    record_assessments = []
    pending_terms = []
    for record in normalized:
        assessment = {
            "index": record["index"],
            "card": record["card"],
            "status": record["status"],
            "date": record["date"],
        }
        if record["status"] == "COMPLETE":
            assessment["interpretation"] = "The referral record is complete. A separate payout date is not established by this status alone."
        elif record["status"] == "IN_PROGRESS":
            assessment["interpretation"] = "The referral remains pending; approval and qualifying spend cannot be inferred from this status."
            terms = CARD_TERMS.get(record["card"])
            if terms:
                pending_terms.append({"card": record["card"], "terms": terms})
        elif record["status"] == "REJECTED":
            assessment["interpretation"] = "The referral record is rejected; the record status itself does not name a reason."
        else:
            assessment["interpretation"] = "Use the returned status as recorded; no interpretation is available for this status."
        record_assessments.append(assessment)

    # A rejection is only flagged when two *earlier* complete record dates fall
    # in the prior seven-day interval. Dates are a proxy, not exact timestamps.
    rolling = []
    complete_dated = [r for r in normalized if r["status"] == "COMPLETE" and r["parsed_date"]]
    for record in normalized:
        if record["status"] != "REJECTED" or not record["parsed_date"]:
            continue
        earlier = [
            other for other in complete_dated
            if 0 <= (record["parsed_date"] - other["parsed_date"]).days <= 7
        ]
        if len(earlier) >= 2:
            rolling.append({
                "rejected_record_index": record["index"],
                "rejected_record_date": record["date"],
                "earlier_complete_record_indexes": [item["index"] for item in earlier],
                "interpretation": "The displayed dates are consistent with the cross-card rolling seven-day maximum of two referral bonuses; exact timestamps are required to confirm the cause.",
            })

    return {
        "ok": True,
        "summary": {"total": len(normalized), "by_status": dict(sorted(counts.items()))},
        "records": record_assessments,
        "rolling_window_assessments": rolling,
        "card_terms_for_pending_records": pending_terms,
        "warnings": warnings,
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        result = fail("Invalid JSON input: %s" % exc.msg)
    except Exception as exc:  # stdin failures still return machine-readable JSON
        result = fail("Could not read input: %s" % exc)
    else:
        result = analyze(payload)
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
