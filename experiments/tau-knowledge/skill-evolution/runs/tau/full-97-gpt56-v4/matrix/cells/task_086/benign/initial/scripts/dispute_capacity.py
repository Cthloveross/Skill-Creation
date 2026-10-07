#!/usr/bin/env python3
"""Calculate debit-dispute capacity and most severe required card action.

Reads one JSON object from stdin and writes one JSON object to stdout.
Input: tier (entry|mid|premium|elite), open_disputes (nonnegative integer),
requested_disputes (nonnegative integer), and optional categories (list of valid
filing categories). Output is an object with either ok:true and calculations or
ok:false and a machine-readable error. This script makes no banking changes.
"""
import json
import sys

LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active",
    "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active",
    "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active",
    "recurring_charge_after_cancellation": "keep_active",
}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def fail(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(0)


def is_nonnegative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        fail("input must be one JSON object")
    if not isinstance(data, dict):
        fail("input must be one JSON object")

    tier = data.get("tier")
    if tier not in LIMITS:
        fail("tier must be one of: entry, mid, premium, elite")
    open_disputes = data.get("open_disputes")
    requested = data.get("requested_disputes")
    if not is_nonnegative_int(open_disputes):
        fail("open_disputes must be a nonnegative integer")
    if not is_nonnegative_int(requested):
        fail("requested_disputes must be a nonnegative integer")

    categories = data.get("categories", [])
    if not isinstance(categories, list) or any(c not in ACTIONS for c in categories):
        fail("categories must contain only supported dispute categories")

    limit = LIMITS[tier]
    available = max(0, limit - open_disputes)
    actions = [ACTIONS[c] for c in categories]
    highest = max(actions, key=lambda a: SEVERITY[a]) if actions else "keep_active"
    output = {
        "ok": True,
        "tier": tier,
        "open_dispute_limit": limit,
        "current_open_disputes": open_disputes,
        "available_slots": available,
        "requested_disputes": requested,
        "can_file_now": min(available, requested),
        "requires_prioritization": requested > available,
        "per_category_actions": [ACTIONS[c] for c in categories],
        "highest_actual_card_action": highest,
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
