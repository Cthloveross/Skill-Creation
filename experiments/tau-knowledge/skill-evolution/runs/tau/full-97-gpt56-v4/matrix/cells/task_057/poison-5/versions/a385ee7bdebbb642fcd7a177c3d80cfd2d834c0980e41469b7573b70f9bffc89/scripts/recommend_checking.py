#!/usr/bin/env python3
"""Filter structured checking products against stated hard requirements.

Reads JSON from stdin and emits JSON to stdout.  No network or bank actions occur.
"""
import json
import sys

REQUIRED_PRODUCT_FIELDS = {
    "account_class",
    "ordinary_overdraft_fee",
    "overdraft_protection_available",
    "overdraft_protection_transfer_fee",
    "early_direct_deposit_days",
}


def fail(message):
    print(json.dumps({"ok": False, "error": message}))
    raise SystemExit(2)


def as_nonnegative_number(value, field, account_class):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{account_class}: {field} must be a non-negative number")
    return value


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc.msg}")
    if not isinstance(payload, dict):
        fail("input must be a JSON object")
    requirements = payload.get("requirements")
    products = payload.get("products")
    if not isinstance(requirements, dict) or not isinstance(products, list):
        fail("requirements must be an object and products must be an array")

    no_overdraft_fee = requirements.get("no_overdraft_fee", False)
    needs_protection = requirements.get("needs_overdraft_protection", False)
    early_days = requirements.get("min_early_direct_deposit_days", 0)
    if not isinstance(no_overdraft_fee, bool) or not isinstance(needs_protection, bool):
        fail("no_overdraft_fee and needs_overdraft_protection must be booleans")
    if isinstance(early_days, bool) or not isinstance(early_days, (int, float)) or early_days < 0:
        fail("min_early_direct_deposit_days must be a non-negative number")

    matches, rejections = [], []
    for product in products:
        if not isinstance(product, dict):
            fail("each product must be an object")
        missing = REQUIRED_PRODUCT_FIELDS - product.keys()
        if missing:
            fail("product missing fields: " + ", ".join(sorted(missing)))
        account_class = product["account_class"]
        if not isinstance(account_class, str) or not account_class.strip():
            fail("account_class must be a nonempty string")
        try:
            ordinary_fee = as_nonnegative_number(product["ordinary_overdraft_fee"], "ordinary_overdraft_fee", account_class)
            transfer_fee = as_nonnegative_number(product["overdraft_protection_transfer_fee"], "overdraft_protection_transfer_fee", account_class)
            offered_days = as_nonnegative_number(product["early_direct_deposit_days"], "early_direct_deposit_days", account_class)
        except ValueError as exc:
            fail(str(exc))
        if not isinstance(product["overdraft_protection_available"], bool):
            fail(f"{account_class}: overdraft_protection_available must be boolean")

        reasons = []
        if no_overdraft_fee and ordinary_fee != 0:
            reasons.append("ordinary overdraft fee is not zero")
        if needs_protection and not product["overdraft_protection_available"]:
            reasons.append("no overdraft-protection option")
        if offered_days < early_days:
            reasons.append(f"early direct deposit is {offered_days} day(s), below required {early_days}")
        normalized = {
            "account_class": account_class,
            "ordinary_overdraft_fee": ordinary_fee,
            "overdraft_protection_available": product["overdraft_protection_available"],
            "overdraft_protection_transfer_fee": transfer_fee,
            "early_direct_deposit_days": offered_days,
        }
        if reasons:
            rejections.append({"product": normalized, "reasons": reasons})
        else:
            matches.append(normalized)

    print(json.dumps({"ok": True, "matches": matches, "rejections": rejections}, sort_keys=True))


if __name__ == "__main__":
    main()
