#!/usr/bin/env python3
"""Summarize referral records and conservatively detect weekly-cap evidence.

Reads one JSON object from stdin with a `referrals` list and writes one JSON object
on stdout. The program is intentionally read-only and uses only the standard library.
"""
import json
import sys
from datetime import datetime, timedelta

DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y",
)


def parse_date(value):
    """Return (datetime, precision) or (None, None) for a supported date string."""
    if not isinstance(value, str) or not value.strip():
        return None, None
    text = value.strip()
    # Python accepts +00:00 but not a trailing Z in every supported version.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            precision = "datetime" if any(token in fmt for token in ("%H", "%z")) else "date"
            return parsed, precision
        except ValueError:
            pass
    return None, None


def normalized_status(value):
    return str(value or "").strip().upper()


def earlier_within_window(completed, rejected):
    """Classify cap support from earlier completed records.

    Returns (confirmed_ids, possible_ids). Date-only evidence is confirmed only
    when calendar dates differ by at most six days, which guarantees a span of
    less than seven 24-hour periods regardless of unrecorded time of day.
    """
    rejected_at, rejected_precision = rejected["_parsed_date"], rejected["_precision"]
    if rejected_at is None:
        return [], []
    confirmed = []
    possible = []
    for item in completed:
        occurred_at, precision = item["_parsed_date"], item["_precision"]
        if occurred_at is None:
            continue
        # Mixed aware/naive timestamps cannot safely be compared.
        if (occurred_at.tzinfo is None) != (rejected_at.tzinfo is None):
            continue
        delta = rejected_at - occurred_at
        if delta.total_seconds() < 0:
            continue
        if precision == "datetime" and rejected_precision == "datetime":
            if delta < timedelta(days=7):
                confirmed.append(item["referral_id"])
        else:
            calendar_days = (rejected_at.date() - occurred_at.date()).days
            if calendar_days <= 6:
                confirmed.append(item["referral_id"])
            elif calendar_days == 7:
                possible.append(item["referral_id"])
    return confirmed, possible


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise SystemExit(json.dumps({"error": "invalid_json", "detail": str(exc)}))
    referrals = payload.get("referrals") if isinstance(payload, dict) else None
    if not isinstance(referrals, list):
        raise SystemExit(json.dumps({"error": "referrals_must_be_a_list"}))

    records = []
    for index, raw in enumerate(referrals):
        if not isinstance(raw, dict):
            raise SystemExit(json.dumps({"error": "referral_must_be_an_object", "index": index}))
        parsed, precision = parse_date(raw.get("date"))
        record = {
            "referral_id": str(raw.get("referral_id", "")),
            "card_type": raw.get("referred_account_type"),
            "status": normalized_status(raw.get("referral_status")),
            "date": raw.get("date"),
            "date_parseable": parsed is not None,
            "_parsed_date": parsed,
            "_precision": precision,
        }
        records.append(record)

    completed = [r for r in records if r["status"] == "COMPLETE"]
    rejected = [r for r in records if r["status"] == "REJECTED"]
    confirmed_rejections = []
    possible_rejections = []
    for item in rejected:
        confirmed, possible = earlier_within_window(completed, item)
        if len(confirmed) >= 2:
            confirmed_rejections.append({
                "rejected_referral_id": item["referral_id"],
                "supporting_complete_referral_ids": confirmed,
            })
        elif len(confirmed) + len(possible) >= 2:
            possible_rejections.append({
                "rejected_referral_id": item["referral_id"],
                "confirmed_supporting_complete_referral_ids": confirmed,
                "date_only_ambiguous_referral_ids": possible,
            })

    public_records = []
    for record in records:
        public_records.append({key: value for key, value in record.items() if not key.startswith("_")})
    counts = {}
    for record in records:
        counts[record["status"] or "UNKNOWN"] = counts.get(record["status"] or "UNKNOWN", 0) + 1
    output = {
        "records": public_records,
        "status_counts": counts,
        "confirmed_weekly_cap_rejections": confirmed_rejections,
        "possible_weekly_cap_rejections": possible_rejections,
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
