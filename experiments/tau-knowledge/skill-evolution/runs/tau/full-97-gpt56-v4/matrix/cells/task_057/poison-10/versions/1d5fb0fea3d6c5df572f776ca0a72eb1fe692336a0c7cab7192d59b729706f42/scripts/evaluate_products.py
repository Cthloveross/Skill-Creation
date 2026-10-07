#!/usr/bin/env python3
"""Evaluate supplied checking-product facts against explicit customer constraints.

Input (stdin JSON):
{
  "products": [{
    "name": "string",
    "overdraft_fee": "decimal or number",
    "overdraft_protection": {"available": true, "transfer_fee": "decimal or number"},
    "early_direct_deposit_days": 1,
    "monthly_maintenance_fee": "optional decimal or number"
  }],
  "requirements": {
    "require_zero_overdraft_fee": true,
    "require_overdraft_protection": true,
    "min_early_direct_deposit_days": 1
  }
}

Output (stdout JSON):
{
  "ok": true,
  "candidates": [{"name": "...", "meets_requirements": true, "unmet": []}],
  "best_candidate": "name or null"
}

The program never performs bank actions. Missing facts make a product fail the
corresponding requested constraint rather than being treated as favorable.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def decimal_value(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def nonnegative_int(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
        return parsed if parsed >= 0 and str(parsed) == str(value) or isinstance(value, int) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def evaluate(product, requirements):
    unmet = []
    if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not product["name"].strip():
        return {"name": None, "meets_requirements": False, "unmet": ["missing product name"]}

    if requirements.get("require_zero_overdraft_fee") is True:
        fee = decimal_value(product.get("overdraft_fee"))
        if fee is None or fee != Decimal("0"):
            unmet.append("does not have a verified $0 account overdraft fee")

    if requirements.get("require_overdraft_protection") is True:
        protection = product.get("overdraft_protection")
        if not isinstance(protection, dict) or protection.get("available") is not True:
            unmet.append("does not have verified linked-account overdraft protection")

    if "min_early_direct_deposit_days" in requirements:
        required_days = nonnegative_int(requirements.get("min_early_direct_deposit_days"))
        actual_days = nonnegative_int(product.get("early_direct_deposit_days"))
        if required_days is None:
            unmet.append("invalid requested early-direct-deposit timing")
        elif actual_days is None or actual_days < required_days:
            unmet.append("does not meet the requested early-direct-deposit timing")

    return {"name": product["name"], "meets_requirements": not unmet, "unmet": unmet}


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"ok": False, "error": "stdin must contain one JSON object"}))
        return

    if not isinstance(payload, dict) or not isinstance(payload.get("products"), list) or not isinstance(payload.get("requirements"), dict):
        print(json.dumps({"ok": False, "error": "products must be a list and requirements must be an object"}))
        return

    candidates = [evaluate(product, payload["requirements"]) for product in payload["products"]]
    matches = [item["name"] for item in candidates if item["meets_requirements"]]
    # A recommendation is deterministic only when constraints identify exactly one product.
    best = matches[0] if len(matches) == 1 else None
    print(json.dumps({"ok": True, "candidates": candidates, "best_candidate": best}, ensure_ascii=False))


if __name__ == "__main__":
    main()
