#!/usr/bin/env python3
"""Calculate documented debit-card replacement tier fees and timing.

Reads one JSON object from stdin and writes one JSON object to stdout.
No bank data is accessed and no banking action is performed.
"""
import json
import sys
from datetime import datetime, date, timedelta, timezone

REPLACEMENT_REASONS = {"lost", "stolen", "fraud", "damaged"}
TIERS = {
    "ENTRY": {
        "limit": 2,
        "wait_hours": 48,
        "delivery": {"STANDARD": 0},
        "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25},
        "excess_fee": 25,
    },
    "MID": {
        "limit": 3,
        "wait_hours": 0,
        "delivery": {"STANDARD": 0, "EXPEDITED": 15},
        "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25},
        "excess_fee": 15,
    },
    "PREMIUM": {
        "limit": 5,
        "wait_hours": 0,
        "delivery": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 35},
        "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 15},
        "excess_fee": None,
    },
    "ELITE": {
        "limit": None,
        "wait_hours": 0,
        "delivery": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 0},
        "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 0},
        "excess_fee": None,
    },
}


def parse_datetime(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty ISO date or timestamp")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%m/%d/%Y")
        except ValueError as exc:
            raise ValueError(f"{field} is not a supported date") from exc
    if isinstance(parsed, date) and not isinstance(parsed, datetime):
        parsed = datetime.combine(parsed, datetime.min.time())
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def error(message):
    return {"valid": False, "eligible_to_order": False, "errors": [message]}


def main(payload):
    if not isinstance(payload, dict):
        return error("input must be a JSON object")
    tier_name = str(payload.get("account_class", "")).upper()
    tier = TIERS.get(tier_name)
    if tier is None:
        return error("account_class must be ENTRY, MID, PREMIUM, or ELITE")
    delivery = str(payload.get("delivery_option", "")).upper()
    design = str(payload.get("design", "")).upper()
    if delivery not in tier["delivery"]:
        return error(f"{delivery or 'requested'} delivery is unavailable for {tier_name}")
    if design not in tier["design"]:
        return error("design must be CLASSIC, PREMIUM, or CUSTOM")
    try:
        as_of = parse_datetime(payload.get("as_of"), "as_of")
    except ValueError as exc:
        return error(str(exc))
    cards = payload.get("cards")
    if not isinstance(cards, list):
        return error("cards must be a list")

    cutoff = as_of - timedelta(days=365)
    replacement_dates = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            return error(f"cards[{index}] must be an object")
        if str(card.get("issue_reason", "")).lower() in REPLACEMENT_REASONS:
            try:
                issued = parse_datetime(card.get("date_issued"), f"cards[{index}].date_issued")
            except ValueError as exc:
                return error(str(exc))
            if cutoff <= issued <= as_of:
                replacement_dates.append(issued)

    errors = []
    eligible = True
    wait_ends_at = None
    if tier["wait_hours"]:
        if not payload.get("closed_at"):
            eligible = False
            errors.append("ENTRY replacement requires closed_at to verify the 48-hour waiting period")
        else:
            try:
                closed_at = parse_datetime(payload["closed_at"], "closed_at")
                wait_ends_at = closed_at + timedelta(hours=tier["wait_hours"])
                if as_of < wait_ends_at:
                    eligible = False
                    errors.append("replacement waiting period has not ended")
            except ValueError as exc:
                return error(str(exc))

    excess_fee = 0
    limit = tier["limit"]
    if limit is not None and len(replacement_dates) >= limit:
        if tier["excess_fee"] is not None and payload.get("accept_excess_fee") is True:
            excess_fee = tier["excess_fee"]
        elif tier["excess_fee"] is not None:
            eligible = False
            errors.append("replacement limit reached; customer must explicitly accept the permitted excess fee or wait")
        else:
            eligible = False
            errors.append("replacement limit reached; this tier must wait for an older replacement to age out")

    return {
        "valid": True,
        "eligible_to_order": eligible,
        "account_class": tier_name,
        "replacement_cards_in_last_12_months": len(replacement_dates),
        "replacement_limit": limit,
        "delivery_option": delivery,
        "design": design,
        "delivery_fee": tier["delivery"][delivery],
        "design_fee": tier["design"][design],
        "excess_replacement_fee": excess_fee,
        "total_known_fees": tier["delivery"][delivery] + tier["design"][design] + excess_fee,
        "wait_ends_at": wait_ends_at.isoformat(sep=" ") if wait_ends_at else None,
        "errors": errors,
        "notes": [
            "This quote does not verify live ownership, card/account status, balance, address, pending orders, or customer authorization.",
            "Only delivery_fee and design_fee should be passed to an order tool when those parameters are supported; do not invent an excess-fee parameter.",
        ],
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        result = main(json.loads(raw))
    except json.JSONDecodeError:
        result = error("stdin must contain valid JSON")
    except Exception as exc:  # retain a JSON interface for unexpected bad input
        result = error(f"unable to calculate quote: {exc}")
    print(json.dumps(result, sort_keys=True))
