#!/usr/bin/env python3
"""Assess debit-card replacement terms from supplied tier and card history.

The script reads one JSON object from stdin and emits one JSON object to stdout.
It is deterministic, performs no banking calls, and changes no records.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

COUNTED_REASONS = {"lost", "stolen", "fraud", "damaged"}
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


def parse_time(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty date or timestamp string")
    value = value.strip()
    if len(value) == 10:
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%m/%d/%Y")
        except ValueError as exc:
            raise ValueError(
                f"{field} must be ISO-8601, YYYY-MM-DD, or MM/DD/YYYY"
            ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def money(value):
    return format(Decimal(value).quantize(Decimal("0.01")), ".2f")


def failure(message):
    return {
        "ok": False,
        "blocking_reasons": [message],
        "replacement_count": None,
        "limit": None,
        "oldest_counted_issue_date": None,
        "allowed_delivery": [],
        "delivery_fee": None,
        "design_fee": None,
        "excess_replacement_fee": None,
        "wait_until": None,
        "limit_wait_until": None,
    }


def assess(payload):
    tier_name = payload.get("account_tier")
    if tier_name not in TIERS:
        return failure("account_tier must be ENTRY, MID, PREMIUM, or ELITE")
    tier = TIERS[tier_name]

    try:
        now = parse_time(payload.get("now"), "now")
    except ValueError as exc:
        return failure(str(exc))

    cards = payload.get("cards")
    if not isinstance(cards, list):
        return failure("cards must be an array")

    delivery = payload.get("requested_delivery")
    design = payload.get("requested_design")
    blocking = []
    if delivery not in tier["delivery"]:
        blocking.append("requested delivery is not available for this account tier")
    if design not in tier["design"]:
        blocking.append("requested design is not available for this account tier")

    cutoff = now - timedelta(days=365)
    counted = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            return failure(f"cards[{index}] must be an object")
        if card.get("issue_reason") not in COUNTED_REASONS:
            continue
        try:
            issued = parse_time(card.get("date_issued"), f"cards[{index}].date_issued")
        except ValueError as exc:
            return failure(str(exc))
        if cutoff <= issued <= now:
            counted.append(issued)
    counted.sort()

    wait_until = None
    if tier["wait_hours"]:
        try:
            closed_at = parse_time(payload.get("closed_at"), "closed_at")
        except ValueError as exc:
            blocking.append(str(exc))
        else:
            eligible_at = closed_at + timedelta(hours=tier["wait_hours"])
            wait_until = eligible_at.isoformat()
            if now < eligible_at:
                blocking.append("post-closure waiting period has not elapsed")

    limit = tier["limit"]
    at_limit = limit is not None and len(counted) >= limit
    excess_fee = tier["excess"] if at_limit else None
    limit_wait_until = None
    if at_limit and counted:
        limit_wait_until = (counted[0] + timedelta(days=365)).isoformat()
    if at_limit and tier["excess"] is None:
        blocking.append("replacement limit reached; this tier requires waiting")

    return {
        "ok": not blocking,
        "blocking_reasons": blocking,
        "replacement_count": len(counted),
        "limit": limit,
        "oldest_counted_issue_date": (
            counted[0].date().isoformat() if counted else None
        ),
        "allowed_delivery": sorted(tier["delivery"]),
        "delivery_fee": (
            money(tier["delivery"][delivery])
            if delivery in tier["delivery"] else None
        ),
        "design_fee": (
            money(tier["design"][design])
            if design in tier["design"] else None
        ),
        "excess_replacement_fee": (
            money(excess_fee) if excess_fee is not None else None
        ),
        "wait_until": wait_until,
        "limit_wait_until": limit_wait_until,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = assess(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        result = failure(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
