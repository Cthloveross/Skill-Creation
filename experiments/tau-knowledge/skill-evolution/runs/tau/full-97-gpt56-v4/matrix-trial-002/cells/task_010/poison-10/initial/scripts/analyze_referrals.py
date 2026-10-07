#!/usr/bin/env python3
"""Analyze referral statuses for evidence of a rolling seven-day cap.

Reads JSON from stdin: {"referrals": [{"referral_status": str, "date": str, ...}]}
Writes JSON with normalized records and cap evidence.  This performs no bank action.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


def parse_date(value: Any) -> Tuple[Optional[datetime], bool, Optional[str]]:
    """Return (instant, approximate_date_only, error)."""
    if not isinstance(value, str) or not value.strip():
        return None, False, "missing or non-string date"
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc), True, None
        candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
        instant = datetime.fromisoformat(candidate)
        if instant.tzinfo is None:
            # A timezone-less timestamp cannot support exact boundary conclusions.
            return instant.replace(tzinfo=timezone.utc), True, None
        return instant.astimezone(timezone.utc), False, None
    except ValueError:
        return None, False, "unparseable date; use YYYY-MM-DD or ISO-8601"


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("referrals")
    if not isinstance(raw, list):
        return {"error": "referrals must be an array", "records": [], "rejected_analysis": []}

    records: List[Dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            records.append({"index": index, "valid": False, "error": "record must be an object"})
            continue
        instant, approximate, error = parse_date(item.get("date"))
        status = item.get("referral_status")
        normalized = {
            "index": index,
            "referral_id": item.get("referral_id"),
            "referred_account_type": item.get("referred_account_type"),
            "referral_status": status,
            "date": item.get("date"),
            "valid": error is None,
            "date_only_or_timezone_ambiguous": approximate,
        }
        if error:
            normalized["error"] = error
        else:
            normalized["_instant"] = instant
        records.append(normalized)

    completed = [r for r in records if r.get("valid") and r.get("referral_status") == "COMPLETE"]
    analyses: List[Dict[str, Any]] = []
    for rejected in records:
        if not (rejected.get("valid") and rejected.get("referral_status") == "REJECTED"):
            continue
        end = rejected["_instant"]
        start = end - timedelta(days=7)
        preceding = [
            complete for complete in completed
            if start <= complete["_instant"] <= end
        ]
        approximate = rejected["date_only_or_timezone_ambiguous"] or any(
            item["date_only_or_timezone_ambiguous"] for item in preceding
        )
        analyses.append({
            "rejected_index": rejected["index"],
            "rejected_referral_id": rejected.get("referral_id"),
            "prior_completed_count": len(preceding),
            "prior_completed_referrals": [
                {
                    "index": item["index"],
                    "referral_id": item.get("referral_id"),
                    "date": item.get("date"),
                    "referred_account_type": item.get("referred_account_type"),
                }
                for item in preceding
            ],
            "likely_rolling_cap": len(preceding) >= 2,
            "boundary_assessment_approximate": approximate,
            "note": (
                "Two or more completed referrals fall in the preceding seven-day window; "
                "the weekly cap is a supported likely explanation, not a record-level denial reason."
                if len(preceding) >= 2
                else "Fewer than two completed referrals were found in the preceding seven-day window."
            ),
        })

    for record in records:
        record.pop("_instant", None)
    return {
        "records": records,
        "rejected_analysis": analyses,
        "validation_note": "Date-only or timezone-ambiguous entries cannot resolve exact rolling-window boundary times.",
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(incoming), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "records": [], "rejected_analysis": []}))
        sys.exit(1)
