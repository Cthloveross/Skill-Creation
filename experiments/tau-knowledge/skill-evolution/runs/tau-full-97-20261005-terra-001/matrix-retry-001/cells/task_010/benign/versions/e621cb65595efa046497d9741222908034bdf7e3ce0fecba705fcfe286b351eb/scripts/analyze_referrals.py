#!/usr/bin/env python3
"""Analyze referral records for the documented cross-card rolling weekly cap.

Reads one JSON object from stdin and writes one JSON object to stdout.
No network, filesystem input, or account actions are performed.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple


class InputError(ValueError):
    pass


def parse_when(value: Any) -> Tuple[datetime, bool]:
    """Return an orderable timestamp and whether the source was date-only."""
    if not isinstance(value, str) or not value.strip():
        raise InputError("each referral date must be a nonempty string")
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc), True
        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed, False
    except ValueError as exc:
        raise InputError(
            "each referral date must be YYYY-MM-DD or an ISO-8601 timestamp"
        ) from exc


def referral_label(record: Dict[str, Any], index: int) -> str:
    value = record.get("referral_id")
    return str(value) if value not in (None, "") else "record_%d" % (index + 1)


def analyze(payload: Dict[str, Any]) -> Dict[str, Any]:
    referrals = payload.get("referrals")
    if not isinstance(referrals, list):
        raise InputError("referrals must be an array")

    configured_statuses = payload.get("successful_statuses", ["COMPLETE"])
    if not isinstance(configured_statuses, list) or not configured_statuses or not all(
        isinstance(item, str) and item for item in configured_statuses
    ):
        raise InputError("successful_statuses must be a nonempty array of strings")
    successful_statuses = set(configured_statuses)

    normalized: List[Dict[str, Any]] = []
    for index, raw in enumerate(referrals):
        if not isinstance(raw, dict):
            raise InputError("each referral must be an object")
        status = raw.get("referral_status")
        if not isinstance(status, str) or not status.strip():
            raise InputError("each referral requires a nonempty referral_status")
        when, date_only = parse_when(raw.get("date"))
        normalized.append({
            "index": index,
            "referral_id": referral_label(raw, index),
            "status": status.strip(),
            "date": raw["date"],
            "when": when,
            "date_only": date_only,
            "card_type": raw.get("referred_account_type"),
        })

    status_groups: Dict[str, List[str]] = {}
    completed_by_year: Dict[str, int] = {}
    for item in normalized:
        status_groups.setdefault(item["status"], []).append(item["referral_id"])
        if item["status"] in successful_statuses:
            year = str(item["when"].year)
            completed_by_year[year] = completed_by_year.get(year, 0) + 1

    candidates: List[Dict[str, Any]] = []
    rolling_window = timedelta(days=7)
    for rejected in normalized:
        if rejected["status"] != "REJECTED":
            continue
        prior = []
        ambiguous = False
        for success in normalized:
            if success["status"] not in successful_statuses:
                continue
            delta = rejected["when"] - success["when"]
            if timedelta(0) < delta < rolling_window:
                prior.append(success)
            elif delta == timedelta(0) and (rejected["date_only"] or success["date_only"]):
                ambiguous = True
        if len(prior) >= 2:
            confidence = "confirmed"
            if rejected["date_only"] or any(item["date_only"] for item in prior):
                confidence = "date_only_confirmed"
            candidates.append({
                "rejected_referral_id": rejected["referral_id"],
                "rejected_date": rejected["date"],
                "prior_successful_referral_ids": [item["referral_id"] for item in prior],
                "confidence": confidence,
                "explanation": "At least two earlier successful referrals fall within the preceding rolling seven-day interval.",
            })
        elif ambiguous:
            candidates.append({
                "rejected_referral_id": rejected["referral_id"],
                "rejected_date": rejected["date"],
                "prior_successful_referral_ids": [item["referral_id"] for item in prior],
                "confidence": "needs_timestamps",
                "explanation": "Same-day date-only records prevent confirming whether two successful referrals preceded this rejection.",
            })

    records = []
    for item in normalized:
        records.append({
            "referral_id": item["referral_id"],
            "referral_status": item["status"],
            "date": item["date"],
            "referred_account_type": item["card_type"],
        })
    return {
        "records": records,
        "status_groups": status_groups,
        "successful_statuses_used": sorted(successful_statuses),
        "successful_referrals_by_calendar_year": completed_by_year,
        "weekly_limit_candidates": candidates,
        "interpretation_note": (
            "Candidates assess only the documented rolling seven-day cap. "
            "They do not establish other eligibility requirements, applicant activity, "
            "or an undocumented rejection reason."
        ),
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise InputError("input must be a JSON object")
        result = analyze(payload)
        print(json.dumps(result, sort_keys=True))
    except (json.JSONDecodeError, InputError) as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
