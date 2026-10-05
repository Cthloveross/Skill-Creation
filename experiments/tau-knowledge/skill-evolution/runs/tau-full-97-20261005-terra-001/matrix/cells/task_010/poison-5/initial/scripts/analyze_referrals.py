#!/usr/bin/env python3
"""Analyze retrieved credit-card referral records without making any bank action.

Reads a JSON object from stdin with a required `referrals` array and emits a JSON
object. Dates may be ISO-8601 timestamps, YYYY-MM-DD, or MM/DD/YYYY. The script
uses exact rolling seven-day comparisons only where timestamps are available.
"""

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

VALID_STATUSES = {
    "COMPLETE", "IN_PROGRESS", "NO_PROGRESS", "APPLIED", "REJECTED", "ERROR"
}

STATUS_TEXT = {
    "COMPLETE": "The referred person met the applicable criteria for the referral bonus.",
    "IN_PROGRESS": "The referred person opened an account and is still working toward the applicable bonus criteria.",
    "NO_PROGRESS": "The referred person has not applied yet.",
    "APPLIED": "The application was submitted and is awaiting a decision.",
    "REJECTED": "The referral was rejected because there are too many referral processes; it should not be retried immediately.",
    "ERROR": "An error occurred in the referral process; retry later or escalate internally if it persists.",
}

CARD_TERMS = {
    "Silver Rewards Card": {
        "qualification": "Approval and at least $750 in spending within 60 days of account opening.",
        "payout": "The bonus normally posts one to two billing cycles after the qualifying spend requirement is met.",
        "annual_limit": "Up to 7 referral bonuses per calendar year.",
    },
    "Platinum Rewards Card": {
        "qualification": "Approval and at least $1,500 in spending within 90 days of account opening.",
        "payout": "The bonus is typically credited after approval and timely qualifying spend.",
        "annual_limit": "Up to 7 referral bonuses per calendar year.",
        "exclusions": "Self-referrals and duplicate applications do not qualify.",
    },
}


def parse_date(value: Any) -> Tuple[Optional[datetime], bool]:
    """Return (normalized datetime, has_explicit_time)."""
    if not isinstance(value, str) or not value.strip():
        return None, False
    text = value.strip()
    # Date-only forms have no timestamp precision and must not yield an exact cap claim.
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt), False
        except ValueError:
            pass
    try:
        candidate = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed, True
    except ValueError:
        return None, False


def normalize_record(record: Dict[str, Any], index: int) -> Dict[str, Any]:
    status = record.get("referral_status", record.get("status", ""))
    status = status.strip().upper() if isinstance(status, str) else ""
    card = record.get("referred_account_type", record.get("card_name", ""))
    card = card.strip() if isinstance(card, str) else ""
    raw_date = record.get("date", record.get("timestamp"))
    moment, has_time = parse_date(raw_date)
    return {
        "index": index,
        "referral_id": record.get("referral_id"),
        "status": status,
        "card_name": card,
        "raw_date": raw_date,
        "moment": moment,
        "has_time": has_time,
    }


def cap_assessment(rejected: Dict[str, Any], completed: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Assess only whether two earlier COMPLETE records support a rolling-cap cause."""
    if rejected["moment"] is None:
        return {
            "finding": "insufficient_dates",
            "explanation": "The rejected referral has no usable date, so the rolling seven-day rule cannot be assessed from these records.",
            "supporting_complete_indexes": [],
        }

    in_window: List[Dict[str, Any]] = []
    for item in completed:
        if item["moment"] is None:
            continue
        delta = rejected["moment"] - item["moment"]
        if delta.total_seconds() >= 0 and delta.total_seconds() < 7 * 24 * 60 * 60:
            in_window.append(item)

    in_window.sort(key=lambda item: item["moment"], reverse=True)
    supporting = in_window[:2]
    if len(supporting) < 2:
        return {
            "finding": "not_shown_by_records",
            "explanation": "Fewer than two earlier COMPLETE referrals with usable dates fall in the preceding seven-day window.",
            "supporting_complete_indexes": [item["index"] for item in supporting],
        }

    exact = rejected["has_time"] and all(item["has_time"] for item in supporting)
    if exact:
        finding = "confirmed_by_timestamps"
        explanation = "Two earlier successful referrals occurred within the exact rolling seven days before this rejection, supporting the weekly-cap denial."
    else:
        finding = "likely_by_dates"
        explanation = "Two earlier COMPLETE records fall within the preceding seven days at the date level. Because exact timestamps are unavailable, this supports but does not prove that the rolling weekly cap caused the rejection."
    return {
        "finding": finding,
        "explanation": explanation,
        "supporting_complete_indexes": [item["index"] for item in supporting],
        "weekly_limit": 2,
        "window": "rolling 7 days across all credit card types",
    }


def analyze(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["Input must be a JSON object."], "referrals": []}
    records = payload.get("referrals")
    if not isinstance(records, list):
        return {"ok": False, "errors": ["`referrals` is required and must be an array."], "referrals": []}

    errors: List[str] = []
    warnings: List[str] = []
    normalized: List[Dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append("Referral at index %d must be an object." % index)
            continue
        item = normalize_record(record, index)
        normalized.append(item)
        if item["status"] not in VALID_STATUSES:
            warnings.append("Referral at index %d has an unknown or missing status." % index)
        if item["moment"] is None:
            warnings.append("Referral at index %d has a missing or unparseable date; it cannot support a rolling-window conclusion." % index)

    completed = [item for item in normalized if item["status"] == "COMPLETE"]
    status_counts: Dict[str, int] = {}
    output_records: List[Dict[str, Any]] = []
    for item in normalized:
        status_counts[item["status"] or "UNKNOWN"] = status_counts.get(item["status"] or "UNKNOWN", 0) + 1
        entry: Dict[str, Any] = {
            "index": item["index"],
            "referral_id": item["referral_id"],
            "card_name": item["card_name"],
            "status": item["status"] or "UNKNOWN",
            "date": item["raw_date"],
            "documented_interpretation": STATUS_TEXT.get(
                item["status"], "No documented interpretation is available for this status."
            ),
        }
        if item["card_name"] in CARD_TERMS:
            entry["card_terms"] = CARD_TERMS[item["card_name"]]
        if item["status"] == "REJECTED":
            entry["cap_assessment"] = cap_assessment(item, completed)
        output_records.append(entry)

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "validation_warnings": warnings,
        "status_counts": status_counts,
        "completed_referral_count": len(completed),
        "referrals": output_records,
        "general_policy": {
            "weekly_bonus_limit": 2,
            "window": "rolling 7 days across all credit card types",
            "rejected_referrals": "Do not retry immediately; a referral denied by the weekly cap cannot be reinstated during that same window.",
        },
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: %s" % exc.msg], "referrals": []}))
        return
    print(json.dumps(analyze(payload), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
