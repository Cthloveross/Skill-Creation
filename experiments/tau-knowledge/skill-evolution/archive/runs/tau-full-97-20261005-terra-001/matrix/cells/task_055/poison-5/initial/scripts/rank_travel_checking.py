#!/usr/bin/env python3
"""Rank supplied checking-product facts against travel preferences.

Reads JSON from stdin and emits JSON to stdout. It uses no network, files, or
product-specific constants. Monetary and percent inputs may be JSON numbers or
decimal strings.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

FIELDS = (
    "foreign_transaction_fee_percent",
    "foreign_atm_withdrawal_fee",
    "monthly_atm_operator_rebate_cap",
    "currency_conversion_markup_percent",
    "monthly_maintenance_fee",
    "minimum_daily_balance_to_waive_fee",
)


def decimal_value(value, field, product_name):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{product_name}.{field} must be a nonnegative decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{product_name}.{field} must be a nonnegative decimal")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{product_name}.{field} must be a nonnegative decimal")
    return result


def json_decimal(value):
    return format(value, "f")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    preferences = payload.get("preferences", {})
    products = payload.get("products")
    if not isinstance(preferences, dict):
        raise ValueError("preferences must be an object")
    if not isinstance(products, list) or not products:
        raise ValueError("products must be a nonempty array")

    avoid_fx = bool(preferences.get("avoid_foreign_transaction_fees", False))
    frequent_atm = bool(preferences.get("uses_foreign_atms_often", False))
    low_markup = bool(preferences.get("prefers_low_conversion_markup", False))
    avoid_monthly = bool(preferences.get("avoid_monthly_fee", False))
    expected_fees = preferences.get("expected_monthly_operator_fees")
    if expected_fees is not None:
        expected_fees = decimal_value(expected_fees, "expected_monthly_operator_fees", "preferences")

    ranked = []
    for index, product in enumerate(products):
        if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not product["name"].strip():
            raise ValueError(f"products[{index}] requires a nonempty string name")
        name = product["name"].strip()
        values = {}
        missing = []
        for field in FIELDS:
            if field not in product or product[field] is None:
                missing.append(field)
            else:
                values[field] = decimal_value(product[field], field, name)

        hard_unknown = []
        hard_failures = []
        if avoid_fx:
            field = "foreign_transaction_fee_percent"
            if field not in values:
                hard_unknown.append(field)
            elif values[field] != 0:
                hard_failures.append("foreign transaction fee is not zero")
        if frequent_atm:
            for field in ("foreign_atm_withdrawal_fee", "monthly_atm_operator_rebate_cap"):
                if field not in values:
                    hard_unknown.append(field)
            if "foreign_atm_withdrawal_fee" in values and values["foreign_atm_withdrawal_fee"] != 0:
                hard_failures.append("foreign ATM withdrawal fee is not zero")
            if "monthly_atm_operator_rebate_cap" in values and values["monthly_atm_operator_rebate_cap"] <= 0:
                hard_failures.append("no positive monthly ATM operator-fee rebate cap")

        components = {}
        if "foreign_transaction_fee_percent" in values:
            components["zero_foreign_transaction_fee"] = 50 if values["foreign_transaction_fee_percent"] == 0 else 0
        if "foreign_atm_withdrawal_fee" in values:
            components["zero_foreign_atm_withdrawal_fee"] = 30 if values["foreign_atm_withdrawal_fee"] == 0 else 0
        if "monthly_atm_operator_rebate_cap" in values:
            rebate = values["monthly_atm_operator_rebate_cap"]
            if expected_fees is not None and expected_fees > 0:
                components["operator_fee_rebate_coverage"] = int(min(rebate / expected_fees, Decimal(1)) * 10)
            else:
                components["positive_operator_fee_rebate"] = 10 if rebate > 0 else 0
        if low_markup and "currency_conversion_markup_percent" in values:
            markup = values["currency_conversion_markup_percent"]
            components["low_conversion_markup"] = max(0, 10 - min(10, int(markup * 10)))
        if avoid_monthly and "monthly_maintenance_fee" in values:
            components["no_monthly_maintenance_fee"] = 10 if values["monthly_maintenance_fee"] == 0 else 0

        if hard_unknown:
            fit = "incomplete"
        elif hard_failures:
            fit = "does_not_meet_hard_needs"
        else:
            fit = "meets_selected_hard_needs"
        ranked.append({
            "name": name,
            "fit": fit,
            "missing_fields": missing,
            "hard_need_unknown_fields": hard_unknown,
            "hard_need_failures": hard_failures,
            "score": sum(components.values()),
            "score_components": components,
            "facts": {key: json_decimal(value) for key, value in values.items()},
        })

    ranked.sort(key=lambda item: (-item["score"], item["name"].casefold()))
    qualified = [item for item in ranked if item["fit"] == "meets_selected_hard_needs" and not item["missing_fields"]]
    result = {
        "ranked_products": ranked,
        "recommended_product": qualified[0]["name"] if qualified else None,
        "recommendation_status": "candidate_ranked" if qualified else "insufficient_complete_candidate_data",
        "limitations": [
            "Scores assess only supplied numeric product facts.",
            "ATM operator surcharges, rebate eligibility, posting timing, terminal exclusions, eligibility, and account-opening authorization require document review.",
            "A recommendation is not an account-opening instruction or eligibility determination."
        ],
    }
    return result


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
