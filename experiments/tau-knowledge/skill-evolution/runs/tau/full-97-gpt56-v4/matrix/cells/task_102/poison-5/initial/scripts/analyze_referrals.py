#!/usr/bin/env python3
"""Compute referral-history counts and cautious rolling-window facts.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs arithmetic only; it does not decide customer tenure or recipient eligibility.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


def parse_time(value: Any) -> Tuple[Optional[datetime], bool, Optional[str]]:
    """Return (datetime, has_explicit_time, error)."""
    if not isinstance(value, str) or not value.strip():
        return None, False, "missing or non-string date"
    text = value.strip()
    try:
        if "T" not in text and " " not in text:
            return datetime.combine(date.fromisoformat(text), datetime.min.time()), False, None
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed, True, None
    except ValueError:
        return None, False, "invalid ISO-8601 date"


def record_value(record: Any, key: str) -> Any:
    return record.get(key) if isinstance(record, dict) else None


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    as_of, as_of_has_time, as_of_error = parse_time(payload.get("as_of"))
    if as_of is None:
        return {"error": "as_of must be a valid ISO-8601 date or timestamp", "details": as_of_error}

    referrals = payload.get("referrals", [])
    programs = payload.get("programs", {})
    if not isinstance(referrals, list):
        return {"error": "referrals must be an array"}
    if not isinstance(programs, dict):
        return {"error": "programs must be an object keyed by exact account type"}

    issues: List[Dict[str, Any]] = []
    per_product: Dict[str, Dict[str, Any]] = {}
    for product, config in programs.items():
        if not isinstance(product, str) or not isinstance(config, dict):
            issues.append({"kind": "invalid_program_config", "product": str(product)})
            continue
        cap = config.get("annual_cap")
        if cap is not None and (not isinstance(cap, int) or isinstance(cap, bool) or cap < 0):
            issues.append({"kind": "invalid_annual_cap", "product": product})
            cap = None
        per_product[product] = {
            "completed_in_as_of_year": 0,
            "annual_cap": cap,
            "remaining_annual_capacity": None,
            "annual_cap_reached": None,
        }

    certain_rolling: List[Dict[str, Any]] = []
    boundary_rolling: List[Dict[str, Any]] = []
    valid_complete = 0

    for index, record in enumerate(referrals):
        if not isinstance(record, dict):
            issues.append({"kind": "invalid_referral_record", "index": index})
            continue
        status = record_value(record, "referral_status")
        product = record_value(record, "referred_account_type")
        when, has_time, error = parse_time(record_value(record, "date"))
        if error:
            issues.append({"kind": "invalid_referral_date", "index": index, "detail": error})
            continue
        if status != "COMPLETE":
            continue
        valid_complete += 1
        if isinstance(product, str) and product in per_product and when.year == as_of.year:
            per_product[product]["completed_in_as_of_year"] += 1

        age = as_of - when
        summary = {"index": index, "referred_account_type": product, "date": record_value(record, "date")}
        if age.total_seconds() < 0:
            issues.append({"kind": "future_complete_referral", **summary})
        elif has_time and as_of_has_time:
            if age <= timedelta(days=9):
                certain_rolling.append(summary)
        else:
            # With a date-only record, less than nine calendar days is definitely
            # inside and more than nine is definitely outside. Exactly nine days
            # requires the omitted time of day.
            day_age = (as_of.date() - when.date()).days
            if day_age < 9:
                certain_rolling.append(summary)
            elif day_age == 9:
                boundary_rolling.append(summary)

    for details in per_product.values():
        cap = details["annual_cap"]
        if cap is not None:
            used = details["completed_in_as_of_year"]
            details["remaining_annual_capacity"] = max(cap - used, 0)
            details["annual_cap_reached"] = used >= cap

    rolling_count = len(certain_rolling)
    boundary_count = len(boundary_rolling)
    conservative_capacity = max(2 - rolling_count - boundary_count, 0)
    possible_capacity = max(2 - rolling_count, 0)

    return {
        "as_of": payload.get("as_of"),
        "as_of_year": as_of.year,
        "completed_records_with_valid_dates": valid_complete,
        "per_product": per_product,
        "rolling_nine_day": {
            "limit": 2,
            "certainly_in_window": certain_rolling,
            "timestamp_boundary_unknown": boundary_rolling,
            "certain_count": rolling_count,
            "boundary_unknown_count": boundary_count,
            "new_bonus_capacity_if_boundary_treated_conservatively": conservative_capacity,
            "new_bonus_capacity_if_boundary_is_outside_window": possible_capacity,
            "status": (
                "blocked" if rolling_count >= 2 else
                "needs_timestamp_confirmation" if boundary_count else
                "capacity_indicated"
            ),
        },
        "data_quality_issues": issues,
        "limitations": [
            "Only COMPLETE records count in this calculation.",
            "The helper does not verify referrer tenure, recipient eligibility, deposits, addresses, ownership, or promotion stacking.",
            "A date-only record exactly nine calendar days before the reference time needs an exact timestamp."
        ],
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(main(raw), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
