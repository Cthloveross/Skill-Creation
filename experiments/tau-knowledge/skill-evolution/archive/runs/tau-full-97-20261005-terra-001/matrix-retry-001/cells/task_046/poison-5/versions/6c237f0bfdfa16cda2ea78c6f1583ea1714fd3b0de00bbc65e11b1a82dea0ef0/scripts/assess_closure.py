#!/usr/bin/env python3
"""Assess documented credit-card closure prerequisites from structured facts.

Input: JSON object described in SKILL.md.
Output: JSON object with eligible, blockers, input_errors, facts, and rewards_value.
This helper does not call banking tools or make changes.
"""

import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}
CASHBACK_CARD_TYPES = {
    "Bronze Rewards Card",
    "Silver Rewards Card",
    "Gold Rewards Card",
    "Platinum Rewards Card",
    "Diamond Elite Card",
    "Crypto-Cash Back",
    "Business Bronze Rewards Card",
    "Business Silver Rewards Card",
    "Green Rewards Card",
    "Silver Zoom Card",
    "Business Gold Rewards Card",
    "Business Platinum Rewards Card",
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    match = re.match(r"^\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})", value)
    if not match:
        raise ValueError("date must begin with YYYY-MM-DD or MM/DD/YYYY")
    text = match.group(1)
    fmt = "%Y-%m-%d" if "-" in text else "%m/%d/%Y"
    return datetime.strptime(text, fmt).date()


def parse_money(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        return Decimal(cleaned)
    raise ValueError("current_balance must be a number or money string")


def parse_points(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().lower().replace("points", "").strip()
    try:
        points = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("reward_points must be numeric")
    if points < 0:
        raise ValueError("reward_points cannot be negative")
    return points


def main(payload):
    if not isinstance(payload, dict):
        return {"eligible": False, "blockers": [], "input_errors": ["input must be a JSON object"]}

    blockers = []
    errors = []
    facts = {}

    # Balance
    if "current_balance" not in payload:
        errors.append("missing current_balance")
    else:
        try:
            balance = parse_money(payload["current_balance"])
            facts["current_balance"] = format(balance, ".2f")
            if balance != Decimal("0"):
                blockers.append({"code": "nonzero_balance", "message": "Outstanding balance must be exactly $0.00."})
        except (ValueError, InvalidOperation):
            errors.append("invalid current_balance")

    # Account age, accepting an explicit age or two dates.
    age_days = payload.get("account_age_days")
    if age_days is None and "opened_date" in payload and "current_date" in payload:
        try:
            age_days = (parse_date(payload["current_date"]) - parse_date(payload["opened_date"])).days
        except ValueError as exc:
            errors.append("invalid account date: " + str(exc))
    if age_days is None:
        errors.append("provide account_age_days or both opened_date and current_date")
    elif not isinstance(age_days, (int, float)) or isinstance(age_days, bool) or int(age_days) != age_days:
        errors.append("account_age_days must be an integer")
    else:
        age_days = int(age_days)
        facts["account_age_days"] = age_days
        if age_days < 0:
            errors.append("account_age_days cannot be negative")
        elif age_days < 60:
            blockers.append({"code": "account_too_new", "message": "Account must be open at least 60 days."})

    # Disputes must be affirmatively known to be absent.
    disputes = payload.get("pending_disputes")
    if not isinstance(disputes, bool):
        errors.append("pending_disputes must be boolean")
    else:
        facts["pending_disputes"] = disputes
        if disputes:
            blockers.append({"code": "pending_dispute", "message": "Active or pending disputes must be resolved before closure."})

    # All replacement orders must be final. An omitted or malformed check is not a pass.
    orders = payload.get("replacement_orders")
    if not isinstance(orders, list):
        errors.append("replacement_orders must be an array, including an empty array when none exist")
    else:
        nonfinal = []
        malformed = False
        for index, order in enumerate(orders):
            if not isinstance(order, dict) or not isinstance(order.get("status"), str):
                malformed = True
                nonfinal.append({"index": index, "status": None})
                continue
            status = order["status"].strip().lower()
            if status not in FINAL_REPLACEMENT_STATUSES:
                nonfinal.append({"index": index, "status": status})
        facts["replacement_order_count"] = len(orders)
        facts["nonfinal_replacement_orders"] = nonfinal
        if malformed:
            errors.append("each replacement order must have a string status")
        if nonfinal:
            blockers.append({"code": "replacement_card_pending", "message": "All replacement-card orders must be delivered or cancelled.", "orders": nonfinal})

    rewards_value = None
    if "reward_points" in payload:
        try:
            points = parse_points(payload["reward_points"])
            if points is not None:
                rewards_value = format((points * Decimal("0.01")).quantize(Decimal("0.01")), ".2f")
                facts["reward_points"] = str(points)
        except ValueError as exc:
            errors.append(str(exc))

    card_type = payload.get("card_type")
    if card_type is not None and not isinstance(card_type, str):
        errors.append("card_type must be a string when supplied")
    elif isinstance(card_type, str):
        facts["card_type"] = card_type
        facts["rewards_representation"] = (
            "cash_back" if card_type in CASHBACK_CARD_TYPES else
            "sustainability_points" if card_type == "EcoCard" else "unclassified"
        )

    eligible = not errors and not blockers
    return {
        "eligible": eligible,
        "next_step": "continue_closure_protocol" if eligible else "resolve_eligibility",
        "blockers": blockers,
        "input_errors": errors,
        "facts": facts,
        "rewards_value_at_0_01_per_point": rewards_value,
        "note": "Eligibility does not replace identity verification, fresh authoritative checks, prior-retention history, or customer decision steps."
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        result = main(raw)
    except json.JSONDecodeError:
        result = {"eligible": False, "blockers": [], "input_errors": ["stdin must contain valid JSON"], "facts": {}}
    except Exception as exc:  # Keep the script interface JSON-only for executor handling.
        result = {"eligible": False, "blockers": [], "input_errors": ["unexpected assessment error: " + str(exc)], "facts": {}}
    print(json.dumps(result, sort_keys=True))
