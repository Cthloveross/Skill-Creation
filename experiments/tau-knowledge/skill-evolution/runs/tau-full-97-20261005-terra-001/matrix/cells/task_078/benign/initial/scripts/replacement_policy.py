#!/usr/bin/env python3
"""Calculate published debit-card replacement policy values.

Reads one JSON object from stdin and writes one JSON object to stdout. It has no
banking side effects. See SKILL.md for the input schema and live checks that are
outside this helper.
"""
import json
import sys
from datetime import date, datetime, timedelta

TIERS = {
    "ENTRY": {
        "limit": 2,
        "delivery": {"STANDARD": 0},
        "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25},
        "post_close_wait_hours": 48,
        "excess_fee": 25,
    },
    "MID": {
        "limit": 3,
        "delivery": {"STANDARD": 0, "EXPEDITED": 15},
        "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25},
        "post_close_wait_hours": 0,
        "excess_fee": 15,
    },
    "PREMIUM": {
        "limit": 5,
        "delivery": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 35},
        "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 15},
        "post_close_wait_hours": 0,
        "excess_fee": None,
    },
    "ELITE": {
        "limit": None,
        "delivery": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 0},
        "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 0},
        "post_close_wait_hours": 0,
        "excess_fee": None,
    },
}
REPLACEMENT_REASONS = {"lost", "stolen", "fraud", "damaged"}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY-MM-DD string")
    try:
        # Permit an ISO datetime returned by a system but calculate by its date.
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"{field} must be ISO date or datetime") from exc


def one_year_before(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # Feb. 29 -> Feb. 28 in a non-leap prior year
        return day.replace(year=day.year - 1, day=28)


def weekday_business_days_after_open(opened, as_of):
    """Count weekdays elapsed after opening through as_of, excluding weekends."""
    if as_of <= opened:
        return 0
    count = 0
    cursor = opened + timedelta(days=1)
    while cursor <= as_of:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def main(payload):
    errors = []
    tier = str(payload.get("account_class", "")).upper()
    delivery = str(payload.get("delivery_option", "")).upper()
    design = str(payload.get("design", "")).upper()
    cards = payload.get("cards", [])

    if tier not in TIERS:
        errors.append("account_class must be ENTRY, MID, PREMIUM, or ELITE")
    if not isinstance(cards, list):
        errors.append("cards must be a list")

    as_of = opened = None
    try:
        as_of = parse_date(payload.get("as_of_date"), "as_of_date")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        opened = parse_date(payload.get("account_opened_date"), "account_opened_date")
    except ValueError as exc:
        errors.append(str(exc))

    if errors:
        return {"valid_input": False, "errors": errors, "blocking_reasons": errors}

    policy = TIERS[tier]
    cutoff = one_year_before(as_of)
    qualifying = []
    card_errors = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            card_errors.append(f"cards[{index}] must be an object")
            continue
        reason = str(card.get("issue_reason", "")).lower()
        if reason not in REPLACEMENT_REASONS:
            continue
        try:
            issued = parse_date(card.get("date_issued"), f"cards[{index}].date_issued")
        except ValueError as exc:
            card_errors.append(str(exc))
            continue
        if cutoff <= issued <= as_of:
            qualifying.append({"issue_reason": reason, "date_issued": issued.isoformat()})

    if card_errors:
        return {"valid_input": False, "errors": card_errors, "blocking_reasons": card_errors}

    delivery_allowed = delivery in policy["delivery"]
    design_allowed = design in policy["design"]
    weekday_age = weekday_business_days_after_open(opened, as_of)
    age_ok = weekday_age >= 3
    count = len(qualifying)
    within_limit = policy["limit"] is None or count < policy["limit"]
    blockers = []
    if not delivery_allowed:
        blockers.append("delivery option is not available for this account tier")
    if not design_allowed:
        blockers.append("design is not recognized")
    if not age_ok:
        blockers.append("account has not been open for at least 3 weekday business days")
    if not within_limit:
        if policy["excess_fee"] is None:
            blockers.append("replacement limit reached; this tier must wait for the rolling window")
        else:
            blockers.append("replacement limit reached; waiting or an excess-replacement option is required")

    return {
        "valid_input": True,
        "as_of_date": as_of.isoformat(),
        "rolling_window_start": cutoff.isoformat(),
        "weekday_business_days_since_open": weekday_age,
        "account_open_age_requirement_met": age_ok,
        "qualifying_replacements_in_window": count,
        "qualifying_replacement_cards": qualifying,
        "replacement_limit": policy["limit"],
        "within_replacement_limit": within_limit,
        "excess_replacement_fee_option": policy["excess_fee"],
        "post_closure_wait_hours": policy["post_close_wait_hours"],
        "delivery_allowed": delivery_allowed,
        "delivery_fee": policy["delivery"].get(delivery),
        "allowed_delivery_options": sorted(policy["delivery"]),
        "design_allowed": design_allowed,
        "design_fee": policy["design"].get(design),
        "allowed_designs": sorted(policy["design"]),
        "blocking_reasons": blockers,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except (ValueError, TypeError) as exc:
        print(json.dumps({"valid_input": False, "errors": [str(exc)], "blocking_reasons": [str(exc)]}, sort_keys=True))
