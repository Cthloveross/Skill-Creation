#!/usr/bin/env python3
"""Calculate checking referral rolling and annual capacities.

Input JSON object:
  as_of: ISO-8601 datetime (required; a date-only value is accepted as midnight)
  referrals: list of objects with referral_status, referred_account_type, and
             date or timestamp (ISO-8601, YYYY-MM-DD, or MM/DD/YYYY)
  annual_caps: optional object mapping exact account-type labels to nonnegative caps
  complete_status: optional status name, default "COMPLETE"

Output JSON object:
  as_of, rolling_window, annual_by_account, invalid_records, and assumptions.
"""
import json
import sys
from datetime import datetime, timedelta, timezone


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing timestamp")
    text = value.strip()
    exact = True
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        exact = False
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc), exact
    if len(text) == 10 and text[2] == "/" and text[5] == "/":
        exact = False
        return datetime.strptime(text, "%m/%d/%Y").replace(tzinfo=timezone.utc), exact
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        # A time without an offset has a clock value but no reliable zone.
        exact = False
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc), exact


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of, as_of_exact = parse_time(payload.get("as_of"))
    referrals = payload.get("referrals", [])
    if not isinstance(referrals, list):
        raise ValueError("referrals must be a list")
    caps = payload.get("annual_caps", {})
    if not isinstance(caps, dict):
        raise ValueError("annual_caps must be an object")
    normalized_caps = {}
    for account, cap in caps.items():
        if not isinstance(account, str) or not isinstance(cap, int) or cap < 0:
            raise ValueError("annual_caps must map account strings to nonnegative integers")
        normalized_caps[account] = cap

    complete_status = payload.get("complete_status", "COMPLETE")
    if not isinstance(complete_status, str):
        raise ValueError("complete_status must be a string")

    cutoff = as_of - timedelta(days=9)
    complete = []
    invalid = []
    timestamp_precision = as_of_exact
    for index, record in enumerate(referrals):
        if not isinstance(record, dict):
            invalid.append({"index": index, "reason": "record is not an object"})
            continue
        if record.get("referral_status") != complete_status:
            continue
        account = record.get("referred_account_type")
        if not isinstance(account, str) or not account.strip():
            invalid.append({"index": index, "reason": "completed record has no account type"})
            continue
        raw_time = record.get("timestamp", record.get("date"))
        try:
            event_time, is_exact = parse_time(raw_time)
        except ValueError as exc:
            invalid.append({"index": index, "reason": str(exc)})
            continue
        timestamp_precision = timestamp_precision and is_exact
        if event_time > as_of:
            invalid.append({"index": index, "reason": "completed referral is dated after as_of"})
            continue
        complete.append((account, event_time, index))

    in_window = [item for item in complete if item[1] >= cutoff]
    annual_counts = {}
    for account, event_time, _ in complete:
        if event_time.year == as_of.year:
            annual_counts[account] = annual_counts.get(account, 0) + 1

    account_names = sorted(set(annual_counts) | set(normalized_caps))
    annual_report = {}
    for account in account_names:
        count = annual_counts.get(account, 0)
        cap = normalized_caps.get(account)
        annual_report[account] = {
            "completed_in_calendar_year": count,
            "annual_cap": cap,
            "remaining_capacity": None if cap is None else max(0, cap - count),
            "at_or_over_cap": None if cap is None else count >= cap,
        }

    return {
        "as_of": as_of.isoformat(),
        "rolling_window": {
            "start_inclusive": cutoff.isoformat(),
            "end_inclusive": as_of.isoformat(),
            "completed_bonus_count": len(in_window),
            "cap": 2,
            "remaining_capacity": max(0, 2 - len(in_window)),
            "completed_record_indexes": [item[2] for item in in_window],
            "exact_timestamp_assurance": timestamp_precision,
        },
        "annual_by_account": annual_report,
        "invalid_records": invalid,
        "assumptions": [
            "Only records whose status equals complete_status are counted as received bonuses.",
            "A completed bonus exactly nine days before as_of is included; policy requires it to be more than nine days old to age out.",
            "Date-only or timezone-free values reduce exact timestamp assurance and require confirmation for boundary cases.",
        ],
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
