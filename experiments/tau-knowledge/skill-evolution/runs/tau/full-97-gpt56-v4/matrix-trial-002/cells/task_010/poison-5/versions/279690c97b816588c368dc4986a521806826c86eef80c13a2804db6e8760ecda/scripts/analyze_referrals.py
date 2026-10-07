#!/usr/bin/env python3
"""Summarize referral statuses and identify evidence of the rolling referral cap.

Input: {"referrals": [{"referral_status": str, "date": str, ...}],
        "window_days": 7}
Output: {"records": [...], "cap_pattern_rejections": [...],
         "unparseable_records": [...]}
"""
import json
import sys
from datetime import datetime, timedelta, timezone


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def clean_record(item, index):
    if not isinstance(item, dict):
        item = {}
    status = str(item.get("referral_status", "UNKNOWN")).strip().upper() or "UNKNOWN"
    date_text = item.get("date")
    return {
        "input_index": index,
        "referral_id": item.get("referral_id") or item.get("id"),
        "card_name": item.get("referred_account_type") or item.get("card_name"),
        "status": status,
        "date": date_text,
        "_parsed_date": parse_date(date_text),
    }


def public_record(record):
    return {key: record[key] for key in ("input_index", "referral_id", "card_name", "status", "date")}


def main(payload):
    referrals = payload.get("referrals")
    if not isinstance(referrals, list):
        raise ValueError("'referrals' must be an array")
    window_days = payload.get("window_days", 7)
    if isinstance(window_days, bool) or not isinstance(window_days, int) or window_days <= 0:
        raise ValueError("'window_days' must be a positive integer")

    records = [clean_record(item, index) for index, item in enumerate(referrals)]
    dated = sorted((r for r in records if r["_parsed_date"] is not None),
                   key=lambda r: (r["_parsed_date"], r["input_index"]))
    cap_rejections = []
    for rejected in dated:
        if rejected["status"] != "REJECTED":
            continue
        lower_bound = rejected["_parsed_date"] - timedelta(days=window_days)
        prior_completes = [
            candidate for candidate in dated
            if candidate["status"] == "COMPLETE"
            and candidate["_parsed_date"] <= rejected["_parsed_date"]
            and candidate["_parsed_date"] >= lower_bound
            and candidate["input_index"] != rejected["input_index"]
        ]
        if len(prior_completes) >= 2:
            cap_rejections.append({
                "rejected_referral": public_record(rejected),
                "completed_referrals_in_lookback": [public_record(r) for r in prior_completes],
                "lookback_days": window_days,
                "interpretation": "Two or more completed referrals appear in the rolling lookback; the documented weekly cap is consistent with this rejection.",
            })

    unparseable = [public_record(r) for r in records if r["_parsed_date"] is None]
    return {
        "records": [public_record(r) for r in dated] + [public_record(r) for r in records if r["_parsed_date"] is None],
        "cap_pattern_rejections": cap_rejections,
        "unparseable_records": unparseable,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
