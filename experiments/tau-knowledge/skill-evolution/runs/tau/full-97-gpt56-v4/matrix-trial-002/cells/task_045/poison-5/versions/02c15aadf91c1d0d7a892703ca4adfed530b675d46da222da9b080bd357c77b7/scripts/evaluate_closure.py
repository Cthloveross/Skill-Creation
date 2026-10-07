#!/usr/bin/env python3
"""Conservative, side-effect-free credit-card closure prerequisite evaluator.

Reads one JSON object from stdin and emits one JSON object on stdout. This helper
cannot access banking systems and must receive normalized results from live tools.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "completed", "final"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}


def condition(state, detail):
    return {"state": state, "detail": detail}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date") from exc


def normalize_status(value):
    return value.strip().lower() if isinstance(value, str) else None


def evaluate(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")

    results = {}
    verified = payload.get("identity_verified")
    if verified is True:
        results["identity"] = condition("pass", "Identity verification is recorded.")
    elif verified is False:
        results["identity"] = condition("block", "Identity verification has not passed.")
    else:
        results["identity"] = condition("unknown", "identity_verified is required.")

    try:
        balance = Decimal(str(payload["card_balance"]))
        if balance == Decimal("0"):
            results["balance"] = condition("pass", "Card balance is exactly zero.")
        elif balance > Decimal("0"):
            results["balance"] = condition("block", "Card has an outstanding balance.")
        else:
            results["balance"] = condition("block", "Negative balance requires review before closure.")
    except (KeyError, InvalidOperation, ValueError):
        results["balance"] = condition("unknown", "A valid numeric card_balance is required.")

    try:
        current = parse_date(payload["current_date"], "current_date")
        opened = parse_date(payload["date_opened"], "date_opened")
        age_days = (current - opened).days
        if age_days < 0:
            results["account_age"] = condition("unknown", "Account opening date is after current date.")
        elif age_days >= 60:
            results["account_age"] = condition("pass", f"Account age is {age_days} days.")
        else:
            results["account_age"] = condition("block", f"Account age is {age_days} days; 60 are required.")
    except (KeyError, ValueError):
        results["account_age"] = condition("unknown", "Valid current_date and date_opened are required.")

    disputes = payload.get("dispute_statuses")
    if not isinstance(disputes, list):
        results["disputes"] = condition("unknown", "A completed dispute_statuses list is required.")
    else:
        normalized = [normalize_status(item) for item in disputes]
        unknown = [item for item in normalized if item is None or item not in FINAL_DISPUTE_STATUSES]
        if unknown:
            results["disputes"] = condition("block", "At least one dispute is active or has an unrecognized status.")
        else:
            results["disputes"] = condition("pass", "No unresolved disputes are reported.")

    orders = payload.get("replacement_orders")
    if not isinstance(orders, list):
        results["replacement_cards"] = condition("unknown", "A completed replacement_orders list is required.")
    else:
        statuses = []
        malformed = False
        for order in orders:
            if not isinstance(order, dict):
                malformed = True
                continue
            statuses.append(normalize_status(order.get("status")))
        nonfinal = [s for s in statuses if s not in FINAL_REPLACEMENT_STATUSES]
        if malformed or nonfinal:
            results["replacement_cards"] = condition(
                "block", "At least one replacement order is not clearly delivered or cancelled."
            )
        else:
            results["replacement_cards"] = condition("pass", "No pending replacement-card order is reported.")

    blockers = [name for name, item in results.items() if item["state"] != "pass"]
    return {
        "conditions": results,
        "eligible_to_continue": not blockers,
        "blockers": blockers,
        "next_step": (
            "Proceed to required retention checks; do not close until the customer declines or retention is skipped due to recent history."
            if not blockers
            else "Resolve or verify every listed blocker before retention offers or closure."
        ),
    }


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(evaluate(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "eligible_to_continue": False}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
