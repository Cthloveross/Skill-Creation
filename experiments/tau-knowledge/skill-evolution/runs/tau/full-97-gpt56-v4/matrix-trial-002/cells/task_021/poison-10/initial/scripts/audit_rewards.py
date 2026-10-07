#!/usr/bin/env python3
"""Audit supported card reward records. Reads JSON stdin and emits JSON stdout."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

BRONZE = "business bronze rewards card"
ECO = "ecocard"
ZERO_MERCHANTS = {
    "wework", "regus", "industrious", "gusto", "adp", "paychex", "rippling"
}
SAAS_MERCHANTS = {"slack", "zoom", "hubspot", "salesforce"}


def normalized(value):
    return str(value).strip().casefold()


def decimal_amount(value):
    if isinstance(value, str):
        value = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("transaction_amount must be a valid decimal amount")


def integer_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned must be an integer")
    try:
        converted = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("rewards_earned must be an integer")
    if converted != converted.to_integral_value():
        raise ValueError("rewards_earned must be an integer")
    return int(converted)


def truncate_points(value):
    """ROUND_DOWN is truncation toward zero for Decimal values."""
    return int(value.to_integral_value(rounding=ROUND_DOWN))


def base_result(txn):
    return {"transaction_id": txn.get("transaction_id"),
            "card_type": txn.get("credit_card_type"),
            "merchant_name": txn.get("merchant_name")}


def audit_transaction(txn):
    required = ("transaction_id", "credit_card_type", "merchant_name", "transaction_amount",
                "category", "status", "rewards_earned")
    missing = [key for key in required if key not in txn or txn[key] is None]
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))
    result = base_result(txn)
    if normalized(txn["status"]) != "completed":
        result.update(classification="skipped", rule="Only COMPLETED (posted) transactions are audited.")
        return result
    amount = decimal_amount(txn["transaction_amount"])
    recorded = integer_points(txn["rewards_earned"])
    card = normalized(txn["credit_card_type"])
    merchant = normalized(txn["merchant_name"])

    if card == BRONZE:
        if merchant in ZERO_MERCHANTS:
            expected, rule = 0, "Business Bronze listed merchant exclusion: 0 points."
        elif merchant in SAAS_MERCHANTS:
            age = txn.get("subscription_age_months")
            if age is None:
                result.update(classification="indeterminate", recorded_points=recorded,
                              rule="Subscription age is required to apply the Business Bronze SaaS exception.")
                return result
            try:
                age = Decimal(str(age))
                if age < 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                raise ValueError("subscription_age_months must be a nonnegative number")
            if age > 12:
                expected, rule = 0, "Business Bronze SaaS subscription after its first 12 months: 0 points."
            else:
                expected, rule = truncate_points(amount), "Business Bronze eligible purchase: 1 point per dollar (1.0% cash back)."
        else:
            expected, rule = truncate_points(amount), "Business Bronze eligible purchase: 1 point per dollar (1.0% cash back)."
    elif card == ECO:
        if normalized(txn["category"]) == "green":
            expected, rule = truncate_points(amount * Decimal("5")), "EcoCard Green purchase: 5 points per dollar."
        else:
            expected, rule = truncate_points(amount), "EcoCard non-Green purchase: 1 point per dollar."
    else:
        result.update(classification="unsupported", recorded_points=recorded,
                      rule="No rewards policy for this card type is included in this Skill.")
        return result

    difference = expected - recorded
    result.update(expected_points=expected, recorded_points=recorded,
                  difference_points=difference, rule=rule,
                  classification="match" if difference == 0 else "mismatch")
    return result


def audit_balance(account):
    if normalized(account.get("card_type", "")) != BRONZE:
        return None
    if "reward_points" not in account:
        raise ValueError("Business Bronze account missing reward_points")
    points = integer_points(account["reward_points"])
    cash_value = (Decimal(points) / Decimal("100")).quantize(Decimal("0.01"))
    threshold = Decimal("37.00")
    return {"card_type": account.get("card_type"), "reward_points": points,
            "cash_value_dollars": format(cash_value, ".2f"),
            "redemption_threshold_dollars": format(threshold, ".2f"),
            "redeemable": cash_value >= threshold}


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
            raise ValueError("input must be an object with a transactions array")
        accounts = payload.get("accounts", [])
        if not isinstance(accounts, list):
            raise ValueError("accounts must be an array when provided")
        audits, errors = [], []
        for index, txn in enumerate(payload["transactions"]):
            if not isinstance(txn, dict):
                errors.append("transactions[%d] must be an object" % index)
                continue
            try:
                audits.append(audit_transaction(txn))
            except ValueError as exc:
                errors.append("transactions[%d]: %s" % (index, exc))
        balances = []
        for index, account in enumerate(accounts):
            if not isinstance(account, dict):
                errors.append("accounts[%d] must be an object" % index)
                continue
            try:
                item = audit_balance(account)
                if item is not None:
                    balances.append(item)
            except ValueError as exc:
                errors.append("accounts[%d]: %s" % (index, exc))
        if errors:
            print(json.dumps({"ok": False, "errors": errors, "audits": audits}, indent=2))
            return
        summary = {key: 0 for key in ("match", "mismatch", "indeterminate", "skipped", "unsupported")}
        for item in audits:
            summary[item["classification"]] += 1
        print(json.dumps({"ok": True, "audits": audits, "balances": balances,
                          "summary": summary}, indent=2))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2))


if __name__ == "__main__":
    main()
