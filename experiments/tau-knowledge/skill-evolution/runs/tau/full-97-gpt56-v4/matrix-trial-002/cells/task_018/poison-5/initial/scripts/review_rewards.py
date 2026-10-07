#!/usr/bin/env python3
"""Deterministically assess documented credit-card reward rules.

Read a JSON object from stdin and write one JSON result to stdout.  See SKILL.md
for the input and output schema.  This program does not call bank tools or alter
any account.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

# Categories established as reward categories. "Other" is intentionally excluded:
# it denotes card-specific exclusions/exceptions and cannot be assumed eligible.
RECOGNIZED_ELIGIBLE = {
    "travel", "software", "media", "green", "sustainable", "operations",
    "transportation", "groceries", "dining", "entertainment", "utilities",
    "shopping",
}

DOCUMENTED_RULES = {
    "Crypto-Cash Back": {
        "default_points_per_dollar": "2",
        "eligible_categories": sorted(RECOGNIZED_ELIGIBLE),
    },
    "EcoCard": {
        "default_points_per_dollar": "1",
        "category_points_per_dollar": {"Green": "5", "Sustainable": "5"},
        "eligible_categories": sorted(RECOGNIZED_ELIGIBLE),
    },
}


def as_decimal(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} must be a decimal number")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} must be a finite non-negative decimal")
    return result


def as_points(value, label):
    try:
        points = int(str(value))
    except (ValueError, TypeError):
        raise ValueError(f"{label} must be a whole-number point value")
    if points < 0:
        raise ValueError(f"{label} must be non-negative")
    return points


def normalized(value):
    return str(value).strip().casefold()


def lookup_rate(rule, category):
    """Return (Decimal rate, reason) or (None, explanatory reason)."""
    category_key = normalized(category)
    allowed = rule.get("eligible_categories")
    if allowed is not None:
        allowed_keys = {normalized(item) for item in allowed}
        if category_key not in allowed_keys:
            return None, "category is not documented as eligible for this rule"

    category_rates = rule.get("category_points_per_dollar", {})
    if not isinstance(category_rates, dict):
        return None, "category_points_per_dollar must be an object"
    for rule_category, rate in category_rates.items():
        if normalized(rule_category) == category_key:
            try:
                return as_decimal(rate, "category points-per-dollar rate"), None
            except ValueError as exc:
                return None, str(exc)

    if "default_points_per_dollar" not in rule:
        return None, "no documented default or category-specific rate"
    try:
        return as_decimal(rule["default_points_per_dollar"], "default points-per-dollar rate"), None
    except ValueError as exc:
        return None, str(exc)


def dollars_for_points(points):
    return format((Decimal(points) / Decimal("100")).quantize(Decimal("0.01")), "f")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be an array")
    custom_rules = payload.get("rules", {})
    if custom_rules is None:
        custom_rules = {}
    if not isinstance(custom_rules, dict):
        raise ValueError("rules must be an object when supplied")

    # Custom current-task terms override packaged documented defaults.
    rules = dict(DOCUMENTED_RULES)
    rules.update(custom_rules)
    result = {
        "findings": [], "discrepancies": [], "matches": [],
        "unassessable": [], "skipped": [], "errors": [],
    }

    for index, txn in enumerate(transactions):
        prefix = f"transactions[{index}]"
        if not isinstance(txn, dict):
            result["errors"].append({"index": index, "reason": f"{prefix} must be an object"})
            continue
        transaction_id = str(txn.get("transaction_id", "")).strip()
        status = normalized(txn.get("status", ""))
        if status != "completed":
            result["skipped"].append({"transaction_id": transaction_id, "reason": "transaction is not COMPLETED"})
            continue
        card = str(txn.get("credit_card_type", "")).strip()
        category = str(txn.get("category", "")).strip()
        if not transaction_id or not card or not category:
            result["errors"].append({"index": index, "transaction_id": transaction_id,
                                     "reason": "completed transaction requires transaction_id, credit_card_type, and category"})
            continue
        rule = rules.get(card)
        if not isinstance(rule, dict):
            result["unassessable"].append({"transaction_id": transaction_id, "card_type": card,
                                            "reason": "no documented reward rule for this card"})
            continue
        rate, reason = lookup_rate(rule, category)
        if rate is None:
            result["unassessable"].append({"transaction_id": transaction_id, "card_type": card,
                                            "category": category, "reason": reason})
            continue
        try:
            amount = as_decimal(txn.get("transaction_amount"), "transaction_amount")
            recorded = as_points(txn.get("rewards_earned"), "rewards_earned")
        except ValueError as exc:
            result["errors"].append({"index": index, "transaction_id": transaction_id, "reason": str(exc)})
            continue
        expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
        finding = {
            "transaction_id": transaction_id,
            "card_type": card,
            "category": category,
            "amount_dollars": format(amount, "f"),
            "points_per_dollar": format(rate, "f"),
            "expected_points": expected,
            "recorded_points": recorded,
            "expected_cash_value_dollars": dollars_for_points(expected),
            "recorded_cash_value_dollars": dollars_for_points(recorded),
            "difference_points": expected - recorded,
            "difference_cash_value_dollars": dollars_for_points(abs(expected - recorded)),
            "matches": expected == recorded,
        }
        result["findings"].append(finding)
        result["matches" if finding["matches"] else "discrepancies"].append(finding)

    result["summary"] = {
        "assessable_completed": len(result["findings"]),
        "discrepancy_count": len(result["discrepancies"]),
        "match_count": len(result["matches"]),
        "unassessable_count": len(result["unassessable"]),
        "skipped_count": len(result["skipped"]),
        "error_count": len(result["errors"]),
    }
    return result


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        print(json.dumps(main(incoming), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
