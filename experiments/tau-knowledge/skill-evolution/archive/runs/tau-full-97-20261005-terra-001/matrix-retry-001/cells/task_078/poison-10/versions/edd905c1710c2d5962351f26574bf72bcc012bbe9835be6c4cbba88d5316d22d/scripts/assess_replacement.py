#!/usr/bin/env python3
"""Calculate replacement-card terms from supplied account card history.

Reads one JSON object from stdin and emits one JSON object on stdout.  This is
purely a planning helper: it does not call tools, charge fees, or place orders.
"""

import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal

TIERS = {
    "ENTRY": {
        "limit": 2,
        "wait_hours": 48,
        "delivery": {"STANDARD": "0"},
        "design": {"CLASSIC": "0", "PREMIUM": "10", "CUSTOM": "25"},
        "excess": "25",
    },
    "MID": {
        "limit": 3,
        "wait_hours": 0,
        "delivery": {"STANDARD": "0", "EXPEDITED": "15"},
        "design": {"CLASSIC": "0", "PREMIUM": "10", "CUSTOM": "25"},
        "excess": "15",
    },
    "PREMIUM": {
        "limit": 5,
        "wait_hours": 0,
        "delivery": {"STANDARD": "0", "EXPEDITED": "0", "RUSH": "35"},
        "design": {"CLASSIC": "0", "PREMIUM": "0", "CUSTOM": "15"},
        "excess": None,
    },
    "ELITE": {
        "limit": None,
        "wait_hours": 0,
        "delivery": {"STANDARD": "0", "EXPEDITED": "0", "RUSH": "0"},
        "design": {"CLASSIC": "0", "PREMIUM": "0", "CUSTOM": "0"},
        "excess": None,
    },
}
COUNTED_REASONS = {"lost", "stolen", "fraud", "damaged"}


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty date string")
    value = value.strip()
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field} must use ISO-8601, YYYY-MM-DD, or MM/DD/YYYY")


def money(value):
    return format(Decimal(value).quantize(Decimal("0.01")), ".2f")


def result_error(message):
    return {
        "ok": False,
        "replacement_count": None,
        "limit": None,
        "oldest_counted_issue_date": None,
        "wait_until": None,
        "allowed_delivery": [],
        "delivery_fee": None,
        "design_fee": None,
        "excess_replacement_fee": None,
        "blocking_reasons": [message],
    }


def assess(payload):
    tier_name = payload.get("account_tier")
    if tier_name not in TIERS:
        return result_error("account_tier must be ENTRY, MID, PREMIUM, or ELITE")
    tier = TIERS[tier_name]
    try:
        today = parse_date(payload.get("now"), "now")
    except ValueError as exc:
        return result_error(str(exc))

    requested_delivery = payload.get("requested_delivery")
    requested_design = payload.get("requested_design")
    cards = payload.get("cards")
    if not isinstance(cards, list):
        return result_error("cards must be an array of card history records")

    counted_dates = []
    cutoff = today - timedelta(days=365)
    malformed = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            malformed.append(f"cards[{index}] is not an object")
            continue
        if card.get("issue_reason") in COUNTED_REASONS:
            try:
                issued = parse_date(card.get("date_issued"), f"cards[{index}].date_issued")
            except ValueError as exc:
                malformed.append(str(exc))
                continue
            if cutoff <= issued <= today:
                counted_dates.append(issued)
    if malformed:
        return result_error("; ".join(malformed))

    blocking = []
    if requested_delivery not in tier["delivery"]:
        blocking.append("requested delivery is not available for this account tier")
    if requested_design not in tier["design"]:
        blocking.append("requested design is not available for this account tier")

    wait_until = None
    if tier["wait_hours"]:
        closed_at = payload.get("closed_at")
        if not closed_at:
            blocking.append("closure timestamp is required for this tier's post-closure waiting period")
        else:
            try:
                close_day = parse_date(closed_at, "closed_at")
                wait_until = (close_day + timedelta(hours=tier["wait_hours"])).isoformat()
                if today < parse_date(wait_until, "wait_until"):
                    blocking.append("post-closure waiting period has not elapsed")
            except ValueError as exc:
                blocking.append(str(exc))

    counted_dates.sort()
    count = len(counted_dates)
    at_limit = tier["limit"] is not None and count >= tier["limit"]
    excess = tier["excess"] if at_limit else None
    if at_limit and tier["excess"] is None:
        blocking.append("replacement limit reached; this tier requires waiting for the oldest replacement to leave the rolling 12-month window")

    earliest_limit_date = None
    if at_limit and counted_dates:
        earliest_limit_date = (counted_dates[0] + timedelta(days=365)).isoformat()

    delivery_fee = tier["delivery"].get(requested_delivery)
    design_fee = tier["design"].get(requested_design)
    return {
        "ok": not blocking,
        "replacement_count": count,
        "limit": tier["limit"],
        "oldest_counted_issue_date": counted_dates[0].isoformat() if counted_dates else None,
        "wait_until": wait_until,
        "limit_wait_until": earliest_limit_date,
        "allowed_delivery": sorted(tier["delivery"].keys()),
        "delivery_fee": money(delivery_fee) if delivery_fee is not None else None,
        "design_fee": money(design_fee) if design_fee is not None else None,
        "excess_replacement_fee": money(excess) if excess is not None else None,
        "blocking_reasons": blocking,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        output = assess(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        output = result_error(str(exc))
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
