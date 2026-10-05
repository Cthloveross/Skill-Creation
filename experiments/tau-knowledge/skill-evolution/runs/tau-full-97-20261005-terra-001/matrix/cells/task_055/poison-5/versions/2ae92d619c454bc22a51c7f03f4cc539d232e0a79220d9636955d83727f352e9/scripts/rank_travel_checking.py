#!/usr/bin/env python3
"""Rank supplied checking-product facts against travel preferences.

Reads one JSON object from stdin and writes one JSON object to stdout. The script
uses no network, external files, or product-specific constants. It ranks only
runtime-supplied facts and does not establish eligibility or named-currency support.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

NUMERIC_FIELDS = (
    "foreign_transaction_fee_percent",
    "foreign_atm_withdrawal_fee",
    "monthly_atm_operator_rebate_cap",
    "currency_conversion_markup_percent",
    "monthly_maintenance_fee",
    "minimum_daily_balance_to_waive_fee",
    "daily_atm_withdrawal_limit",
)


def decimal_value(value, field, owner):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{owner}.{field} must be a nonnegative decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{owner}.{field} must be a nonnegative decimal")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{owner}.{field} must be a nonnegative decimal")
    return result


def integer_value(value, field, owner):
    if isinstance(value, bool):
        raise ValueError(f"{owner}.{field} must be a nonnegative integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{owner}.{field} must be a nonnegative integer")
    if result < 0 or str(result) != str(value).strip():
        raise ValueError(f"{owner}.{field} must be a nonnegative integer")
    return result


def json_decimal(value):
    return format(value, "f")


def optional_decimal(mapping, field, owner):
    if field not in mapping or mapping[field] is None:
        return None
    return decimal_value(mapping[field], field, owner)


def balance_assessment(values, low, high):
    fee = values.get("monthly_maintenance_fee")
    threshold = values.get("minimum_daily_balance_to_waive_fee")
    if low is None and high is None:
        return None
    if fee is None or threshold is None:
        return {"status": "unknown_missing_product_terms"}
    if low is None:
        low = high
    if high is None:
        high = low
    if low > high:
        raise ValueError("preferences.expected_balance_min cannot exceed expected_balance_max")
    if high < threshold:
        status = "below_waiver_threshold"
    elif low >= threshold:
        status = "at_or_above_waiver_threshold"
    else:
        status = "range_spans_waiver_threshold"
    return {
        "status": status,
        "expected_balance_min": json_decimal(low),
        "expected_balance_max": json_decimal(high),
        "monthly_maintenance_fee": json_decimal(fee),
        "minimum_daily_balance_to_waive_fee": json_decimal(threshold),
    }


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
    needs_wallet = bool(preferences.get("needs_multi_currency_wallet", False))
    expected_fees = optional_decimal(preferences, "expected_monthly_operator_fees", "preferences")
    balance_low = optional_decimal(preferences, "expected_balance_min", "preferences")
    balance_high = optional_decimal(preferences, "expected_balance_max", "preferences")

    ranked = []
    for index, product in enumerate(products):
        if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not product["name"].strip():
            raise ValueError(f"products[{index}] requires a nonempty string name")
        name = product["name"].strip()
        values = {}
        missing = []
        for field in NUMERIC_FIELDS:
            if field not in product or product[field] is None:
                missing.append(field)
            else:
                values[field] = decimal_value(product[field], field, name)

        wallet = product.get("multi_currency_wallet")
        if wallet is None:
            missing.append("multi_currency_wallet")
        elif not isinstance(wallet, bool):
            raise ValueError(f"{name}.multi_currency_wallet must be boolean")
        currencies = product.get("supported_wallet_currencies")
        if currencies is None:
            missing.append("supported_wallet_currencies")
        else:
            currencies = integer_value(currencies, "supported_wallet_currencies", name)

        unknown = []
        failures = []
        if avoid_fx:
            if "foreign_transaction_fee_percent" not in values:
                unknown.append("foreign_transaction_fee_percent")
            elif values["foreign_transaction_fee_percent"] != 0:
                failures.append("foreign transaction fee is not zero")
        if frequent_atm:
            for field in ("foreign_atm_withdrawal_fee", "monthly_atm_operator_rebate_cap"):
                if field not in values:
                    unknown.append(field)
            if values.get("foreign_atm_withdrawal_fee", Decimal(0)) != 0:
                failures.append("foreign ATM withdrawal fee is not zero")
            if "monthly_atm_operator_rebate_cap" in values and values["monthly_atm_operator_rebate_cap"] <= 0:
                failures.append("no positive monthly ATM operator-fee rebate cap")
        if needs_wallet:
            if wallet is None:
                unknown.append("multi_currency_wallet")
            elif not wallet:
                failures.append("no multi-currency wallet")

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
        if needs_wallet and wallet is True:
            components["multi_currency_wallet"] = 10

        if unknown:
            fit = "incomplete"
        elif failures:
            fit = "does_not_meet_hard_needs"
        else:
            fit = "meets_selected_hard_needs"
        facts = {key: json_decimal(value) for key, value in values.items()}
        facts["multi_currency_wallet"] = wallet
        facts["supported_wallet_currencies"] = currencies
        ranked.append({
            "name": name,
            "fit": fit,
            "missing_fields": sorted(set(missing)),
            "hard_need_unknown_fields": sorted(set(unknown)),
            "hard_need_failures": failures,
            "score": sum(components.values()),
            "score_components": components,
            "facts": facts,
            "balance_waiver_assessment": balance_assessment(values, balance_low, balance_high),
        })

    ranked.sort(key=lambda item: (-item["score"], item["name"].casefold()))
    qualified = [item for item in ranked if item["fit"] == "meets_selected_hard_needs" and not item["missing_fields"]]
    return {
        "ranked_products": ranked,
        "recommended_product": qualified[0]["name"] if qualified else None,
        "recommendation_status": "candidate_ranked" if qualified else "insufficient_complete_candidate_data",
        "limitations": [
            "Scores assess only runtime-supplied product facts.",
            "The wallet currency count does not establish that any particular named currency is supported.",
            "ATM operator surcharges, rebate eligibility, posting timing, terminal exclusions, eligibility, and account-opening authorization require source-record review.",
            "A recommendation is not an account-opening instruction or eligibility determination.",
        ],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
