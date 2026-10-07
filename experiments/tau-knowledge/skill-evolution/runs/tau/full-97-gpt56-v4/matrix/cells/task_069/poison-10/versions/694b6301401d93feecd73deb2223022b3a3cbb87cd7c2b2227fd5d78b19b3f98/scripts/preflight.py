#!/usr/bin/env python3
"""Report generic banking-action blockers from verified facts supplied as JSON."""
import json
import sys
from decimal import Decimal, InvalidOperation


def truth(value):
    return value is True


def money(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be numeric")n

def blockers_for_global(data):
    blockers = []
    for name in ("identity_verified", "authority_confirmed", "ownership_confirmed"):
        if not truth(data.get(name)):
            blockers.append(name)
    return blockers


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    global_blockers = blockers_for_global(data)
    result = {"global_blockers": global_blockers, "actions": {}}

    for action_name, field in (("open_checking", "checking_open"), ("open_savings", "savings_open")):
        supplied = data.get(field, {})
        if not isinstance(supplied, dict):
            raise ValueError(f"{field} must be an object")
        blockers = list(global_blockers)
        if not truth(supplied.get("eligible")):
            blockers.append(f"{field}.eligible")
        result["actions"][action_name] = {"ready": not blockers, "blockers": blockers}

    transfer = data.get("transfer", {})
    if not isinstance(transfer, dict):
        raise ValueError("transfer must be an object")
    transfer_blockers = list(global_blockers)
    if truth(transfer.get("requested")):
        for name in ("source_open", "destination_open", "distinct_accounts", "sufficient_available_funds", "amount_positive_usd", "authorized"):
            if not truth(transfer.get(name)):
                transfer_blockers.append(f"transfer.{name}")
    result["actions"]["transfer"] = {"ready": not transfer_blockers, "blockers": transfer_blockers}

    closure = data.get("closure", {})
    if not isinstance(closure, dict):
        raise ValueError("closure must be an object")
    closure_blockers = list(global_blockers)
    if truth(closure.get("requested")):
        for name in ("status_open", "no_pending_transactions", "final_confirmation"):
            if not truth(closure.get(name)):
                closure_blockers.append(f"closure.{name}")
        holdings = money(closure.get("current_holdings", 0), "closure.current_holdings")
        fee = money(closure.get("applicable_early_closure_fee", 0), "closure.applicable_early_closure_fee")
        if fee < 0 or holdings < 0:
            closure_blockers.append("closure.balance values must not be negative")
        elif fee > 0 and holdings < fee:
            closure_blockers.append("closure.current_holdings must cover applicable early closure fee")
        elif fee == 0 and holdings != 0:
            closure_blockers.append("closure.current_holdings must be zero when no early closure fee applies")
    result["actions"]["close_account"] = {"ready": not closure_blockers, "blockers": closure_blockers}
    result["ready"] = all(x["ready"] for x in result["actions"].values())
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
