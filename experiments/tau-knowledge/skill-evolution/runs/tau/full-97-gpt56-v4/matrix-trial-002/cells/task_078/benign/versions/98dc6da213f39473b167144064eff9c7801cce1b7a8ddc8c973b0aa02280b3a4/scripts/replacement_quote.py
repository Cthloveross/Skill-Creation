#!/usr/bin/env python3
"""Calculate a debit-card replacement quote from runtime-supplied JSON.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
only recommends a quote; it cannot place or authorize an order.
"""
import json
import sys
from datetime import datetime, timedelta

REPLACEMENT_REASONS = {"lost", "stolen", "fraud", "damaged"}
RULES = {
    "ENTRY": {
        "delivery": {"STANDARD": 0},
        "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25},
        "limit": 2, "excess_fee": 25, "wait_hours": 48,
        "best_free": "STANDARD",
    },
    "MID": {
        "delivery": {"STANDARD": 0, "EXPEDITED": 15},
        "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25},
        "limit": 3, "excess_fee": 15, "wait_hours": 0,
        "best_free": "STANDARD",
    },
    "PREMIUM": {
        "delivery": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 35},
        "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 15},
        "limit": 5, "excess_fee": None, "wait_hours": 0,
        "best_free": "EXPEDITED",
    },
    "ELITE": {
        "delivery": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 0},
        "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 0},
        "limit": None, "excess_fee": None, "wait_hours": 0,
        "best_free": "RUSH",
    },
}


def parse_timestamp(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date or datetime string")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(normalized, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"{field} is not a supported ISO date/datetime") from exc


def main(data):
    tier = str(data.get("tier", "")).upper()
    if tier not in RULES:
        raise ValueError("tier must be ENTRY, MID, PREMIUM, or ELITE")
    rules = RULES[tier]
    now = parse_timestamp(data.get("now"), "now")
    requested_delivery = str(data.get("delivery", "BEST_FREE")).upper()
    delivery = rules["best_free"] if requested_delivery == "BEST_FREE" else requested_delivery
    design = str(data.get("design", "CLASSIC")).upper()
    if delivery not in rules["delivery"]:
        raise ValueError(f"{delivery} delivery is unavailable for {tier}")
    if design not in rules["design"]:
        raise ValueError("design must be CLASSIC, PREMIUM, or CUSTOM")

    counted = []
    for card in data.get("cards", []):
        if not isinstance(card, dict) or str(card.get("issue_reason", "")).lower() not in REPLACEMENT_REASONS:
            continue
        issued = parse_timestamp(card.get("date_issued"), "cards[].date_issued")
        if now - timedelta(days=365) <= issued <= now:
            counted.append({"issue_reason": str(card["issue_reason"]).lower(), "date_issued": issued.date().isoformat()})

    blocks = []
    wait_until = None
    if rules["wait_hours"]:
        if data.get("closure_at") is None:
            blocks.append("Entry replacements require closure_at to verify the mandatory 48-hour wait.")
        else:
            wait_until = parse_timestamp(data["closure_at"], "closure_at") + timedelta(hours=rules["wait_hours"])
            if now < wait_until:
                blocks.append("Entry replacement cannot be ordered until the 48-hour post-closure wait ends.")

    limit_reached = rules["limit"] is not None and len(counted) >= rules["limit"]
    excess_fee = 0
    if limit_reached:
        if rules["excess_fee"] is None:
            blocks.append("Replacement limit has been reached; this tier must wait for the oldest replacement to leave the 12-month window.")
        else:
            excess_fee = rules["excess_fee"]

    free_delivery_options = [name for name, fee in rules["delivery"].items() if fee == 0]
    return {
        "tier": tier,
        "selected_delivery": delivery,
        "selected_design": design,
        "delivery_fee": rules["delivery"][delivery],
        "design_fee": rules["design"][design],
        "excess_replacement_fee_if_applicable": excess_fee,
        "known_total_fee": rules["delivery"][delivery] + rules["design"][design] + excess_fee,
        "free_delivery_options": free_delivery_options,
        "best_free_delivery": rules["best_free"],
        "replacement_count_last_12_months": len(counted),
        "counted_replacements": counted,
        "replacement_limit": rules["limit"],
        "limit_reached_before_new_order": limit_reached,
        "wait_until": wait_until.isoformat() if wait_until else None,
        "blocking_conditions": blocks,
        "eligible_to_order_now": not blocks,
        "warning": "Eligibility also requires runtime verification of account status/type/age/balance, no active or pending card, valid US address, successful closure, and an order-tool-supported treatment of any excess fee."
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
