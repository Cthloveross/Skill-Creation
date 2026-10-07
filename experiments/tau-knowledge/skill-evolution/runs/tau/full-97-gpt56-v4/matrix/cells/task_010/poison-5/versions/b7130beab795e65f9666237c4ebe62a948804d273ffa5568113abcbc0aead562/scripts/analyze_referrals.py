#!/usr/bin/env python3
"""Summarize referral statuses and date-level rolling-cap indicators.

Input (stdin): {"referrals": [{"referral_status": str, "date": str, ...}]}
Output (stdout): JSON object described in SKILL.md.
"""
import json
import sys
from collections import Counter
from datetime import date, datetime


def parse_date(value):
    """Return a date for common ISO/MM-DD formats, or None without guessing."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # Permit a timestamp that begins with an ISO calendar date, but discard time.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def compact(record):
    """Keep only non-sensitive fields relevant to an explanatory summary."""
    return {
        "referral_status": record.get("referral_status"),
        "date": record.get("date"),
        "referred_account_type": record.get("referred_account_type"),
    }


def analyze(referrals):
    if not isinstance(referrals, list):
        raise ValueError("referrals must be a JSON array")

    warnings = []
    counts = Counter()
    complete_dated = []
    completed = []
    rejected = []
    in_progress = []

    for index, raw in enumerate(referrals):
        if not isinstance(raw, dict):
            warnings.append("Ignored non-object referral at index %d." % index)
            continue
        status = raw.get("referral_status")
        status = status.strip().upper() if isinstance(status, str) else "UNKNOWN"
        counts[status] += 1
        entry = compact({**raw, "referral_status": status})
        parsed = parse_date(raw.get("date"))
        if raw.get("date") is None:
            warnings.append("A referral record has no date; exact rolling-window analysis is unavailable.")
        elif parsed is None:
            warnings.append("A referral record has an unrecognized date format; exact rolling-window analysis is unavailable.")

        if status == "COMPLETE":
            completed.append(entry)
            if parsed is not None:
                complete_dated.append(parsed)
        elif status == "IN_PROGRESS":
            in_progress.append(entry)
        elif status == "REJECTED":
            prior = []
            if parsed is not None:
                prior = [d for d in complete_dated if 0 <= (parsed - d).days <= 7]
                # Include COMPLETE entries appearing later in an unsorted input.
                prior = []  # calculated after all records are collected below
            rejected.append((entry, parsed))

    # Evaluate after collecting all COMPLETE records so input order cannot affect results.
    rejected_output = []
    for entry, rejected_date in rejected:
        if rejected_date is None:
            possible_count = None
            definite_count = None
            likely = False
            supported = False
        else:
            # A date gap of one through six days is unambiguously earlier and
            # less than seven 24-hour periods, regardless of missing times.
            # Same-day and seven-calendar-day gaps need timestamps to decide.
            gaps = [(rejected_date - d).days for d in complete_dated]
            possible_count = sum(0 <= gap <= 7 for gap in gaps)
            definite_count = sum(1 <= gap <= 6 for gap in gaps)
            likely = possible_count >= 2
            supported = definite_count >= 2
        rejected_output.append({
            **entry,
            "possible_prior_complete_count_7d": possible_count,
            "definite_prior_complete_count_7d_from_dates": definite_count,
            "rolling_cap_likely_from_dates": likely,
            "rolling_cap_supported_by_dates": supported,
        })

    if any(parse_date(r.get("date")) is not None for r in referrals if isinstance(r, dict)):
        warnings.append("Same-day or seven-calendar-day gaps require timestamps for exact rolling-window ordering; gaps of one through six days are unambiguous.")

    return {
        "input_record_count": len(referrals),
        "status_counts": dict(sorted(counts.items())),
        "completed": completed,
        "in_progress": in_progress,
        "rejected": rejected_output,
        "warnings": list(dict.fromkeys(warnings)),
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(analyze(payload.get("referrals")), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
