#!/usr/bin/env python3
"""Convert structured referral records into optimizer annual-cap counts.

Input JSON: {"calendar_year": 2025, "referrals": [{"referred_account_type":
"Blue Account", "referral_status": "COMPLETE", "date": "01/15/2025"}, ...]}.
Output JSON: {"status":"ok", "annual_complete_counts": {...}} or a
needs_confirmation response.  This helper does not contact bank systems.
"""
import json
import sys
from collections import Counter
from datetime import date, datetime


def parse_record_date(value):
    if not isinstance(value, str):
        raise ValueError("referral date is missing")
    for layout in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, layout).date()
        except ValueError:
            pass
    raise ValueError("referral date must be MM/DD/YYYY or YYYY-MM-DD")


def canonical_account(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("referred_account_type is missing")
    name = value.strip()
    return name[:-8] if name.endswith(" Account") else name


def main(payload):
    year = payload.get("calendar_year")
    records = payload.get("referrals")
    if not isinstance(year, int) or year < 1:
        return {"status": "needs_confirmation", "blockers": ["calendar_year must be a positive integer."]}
    if not isinstance(records, list):
        return {"status": "needs_confirmation", "blockers": ["referrals must be a list of structured referral records."]}
    counts = Counter()
    blockers = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            blockers.append(f"Referral record {index} must be an object.")
            continue
        if record.get("referral_status") != "COMPLETE":
            continue
        try:
            record_date = parse_record_date(record.get("date"))
            account = canonical_account(record.get("referred_account_type"))
        except ValueError as exc:
            blockers.append(f"Referral record {index}: {exc}.")
            continue
        if record_date.year == year:
            counts[account] += 1
    if blockers:
        return {"status": "needs_confirmation", "blockers": blockers}
    return {"status": "ok", "annual_complete_counts": dict(sorted(counts.items()))}


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(incoming), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status": "needs_confirmation", "blockers": [f"Invalid history input: {exc}"]}, sort_keys=True))
