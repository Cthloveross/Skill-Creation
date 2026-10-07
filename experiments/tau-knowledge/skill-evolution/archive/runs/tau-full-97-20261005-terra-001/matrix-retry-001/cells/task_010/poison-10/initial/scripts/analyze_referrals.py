#!/usr/bin/env python3
"""Analyze credit-card referral statuses and date-based rolling-cap evidence.

Reads one JSON object from stdin and writes one JSON object to stdout.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

KNOWN_STATUSES = {
    "COMPLETE",
    "IN_PROGRESS",
    "NO_PROGRESS",
    "APPLIED",
    "REJECTED",
    "ERROR",
}


def parse_time(value: Any) -> Tuple[Optional[datetime], Optional[str], Optional[str]]:
    """Return parsed UTC-naive datetime, precision, and an error message."""
    if not isinstance(value, str) or not value.strip():
        return None, None, "must be a non-empty date or ISO-8601 timestamp"
    raw = value.strip()
    try:
        if len(raw) == 10:
            return datetime.strptime(raw, "%Y-%m-%d"), "date", None
        iso_value = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        parsed = datetime.fromisoformat(iso_value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed, "timestamp", None
    except ValueError:
        return None, None, "must be YYYY-MM-DD or an ISO-8601 timestamp"


def public_record(record: Dict[str, Any], index: int, when: datetime, precision: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "index": index,
        "status": str(record.get("referral_status", "")).strip().upper(),
        "date": record.get("date"),
        "date_precision": precision,
        "normalized_time": when.isoformat(),
    }
    for key in ("referral_id", "referred_account_type"):
        if key in record:
            result[key] = record[key]
    return result


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    current, current_precision, current_error = parse_time(payload.get("current_time"))
    if current_error:
        return {
            "validation_errors": [{"field": "current_time", "message": current_error}],
            "accepted_record_count": 0,
            "status_counts": {},
            "records": [],
            "completed_in_current_rolling_7_days": [],
            "weekly_cap_indicated_now": None,
            "rejection_window_analysis": [],
        }

    referrals = payload.get("referrals")
    if not isinstance(referrals, list):
        return {
            "validation_errors": [{"field": "referrals", "message": "must be an array"}],
            "accepted_record_count": 0,
            "status_counts": {},
            "records": [],
            "completed_in_current_rolling_7_days": [],
            "weekly_cap_indicated_now": None,
            "rejection_window_analysis": [],
        }

    accepted: List[Tuple[int, Dict[str, Any], datetime, str]] = []
    for index, record in enumerate(referrals):
        if not isinstance(record, dict):
            errors.append({"index": index, "message": "referral must be an object"})
            continue
        status = str(record.get("referral_status", "")).strip().upper()
        if status not in KNOWN_STATUSES:
            errors.append({"index": index, "field": "referral_status", "message": "unknown or missing status"})
            continue
        when, precision, date_error = parse_time(record.get("date"))
        if date_error:
            errors.append({"index": index, "field": "date", "message": date_error})
            continue
        accepted.append((index, record, when, precision or "date"))

    counts = Counter(str(record.get("referral_status", "")).strip().upper() for _, record, _, _ in accepted)
    rolling_start = current - timedelta(days=7)
    current_completes = [
        public_record(record, index, when, precision)
        for index, record, when, precision in accepted
        if str(record.get("referral_status", "")).strip().upper() == "COMPLETE"
        and rolling_start <= when <= current
    ]

    rejected_analyses: List[Dict[str, Any]] = []
    for index, record, rejected_at, rejected_precision in accepted:
        if str(record.get("referral_status", "")).strip().upper() != "REJECTED":
            continue
        prior_start = rejected_at - timedelta(days=7)
        prior_completes = [
            public_record(candidate, candidate_index, completed_at, completed_precision)
            for candidate_index, candidate, completed_at, completed_precision in accepted
            if str(candidate.get("referral_status", "")).strip().upper() == "COMPLETE"
            and prior_start <= completed_at <= rejected_at
        ]
        has_date_only = rejected_precision == "date" or any(
            item["date_precision"] == "date" for item in prior_completes
        )
        rejected_analyses.append({
            "index": index,
            "referral_id": record.get("referral_id"),
            "rejection_date": record.get("date"),
            "prior_completed_count_in_7_day_window": len(prior_completes),
            "prior_completed_referrals": prior_completes,
            "consistent_with_two_bonus_weekly_cap": len(prior_completes) >= 2,
            "ordering_caveat": (
                "Date-only values cannot establish the exact ordering of events on the same date."
                if has_date_only
                else None
            ),
        })

    return {
        "validation_errors": errors,
        "current_time": payload.get("current_time"),
        "current_time_precision": current_precision,
        "accepted_record_count": len(accepted),
        "status_counts": dict(sorted(counts.items())),
        "records": [public_record(record, index, when, precision) for index, record, when, precision in accepted],
        "completed_in_current_rolling_7_days": current_completes,
        "weekly_cap_indicated_now": len(current_completes) >= 2,
        "current_window_precision_caveat": (
            "At least one value uses a calendar date rather than an exact timestamp."
            if current_precision == "date" or any(item["date_precision"] == "date" for item in current_completes)
            else None
        ),
        "rejection_window_analysis": rejected_analyses,
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(main(incoming), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"validation_errors": [{"field": "input", "message": str(exc)}]}))
