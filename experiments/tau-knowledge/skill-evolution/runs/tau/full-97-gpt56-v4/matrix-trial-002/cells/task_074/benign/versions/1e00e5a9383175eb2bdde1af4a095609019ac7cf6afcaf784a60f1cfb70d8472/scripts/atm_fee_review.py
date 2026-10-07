#!/usr/bin/env python3
"""Calculate review figures for explicitly classified, posted ATM events.

Input and output are JSON objects on stdin/stdout.  This is advisory only: it
never calls banking tools and rejects/returns exclusions for insufficient data.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
PRODUCTS = {
    "Purple Account": "purple",
    "Light Blue Account": "light_blue",
    "Dark Green Account": "dark_green",
    "Evergreen Account": "evergreen",
}
CATEGORIES = {"domestic_out_of_network", "foreign"}


def money(value, field):
    try:
        result = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("invalid %s" % field)
    if result < 0:
        raise ValueError("%s must be nonnegative" % field)
    return result


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(text):
    try:
        return datetime.strptime(str(text), "%m/%d/%Y").date()
    except (TypeError, ValueError):
        raise ValueError("date must use MM/DD/YYYY")


def expected_fee(product, category, cash, ordinal):
    if product == "purple":
        return Decimal("2.50") if category == "domestic_out_of_network" else Decimal("0")
    if product == "light_blue":
        if ordinal <= 2:
            return Decimal("0")
        return Decimal("2.50") if category == "domestic_out_of_network" else Decimal("4.00")
    if product == "dark_green":
        if category == "domestic_out_of_network":
            return max(cash * Decimal("0.01"), Decimal("1.50"))
        return min(cash * Decimal("0.025"), Decimal("6.00"))
    if product == "evergreen":
        if category == "domestic_out_of_network":
            return min(cash * Decimal("0.01"), Decimal("2.50"))
        return max(cash * Decimal("0.02"), Decimal("3.00"))
    raise ValueError("unsupported product")


def main(data):
    product_name = data.get("product")
    if product_name not in PRODUCTS:
        raise ValueError("product must be one of: " + ", ".join(PRODUCTS))
    if not isinstance(data.get("events"), list):
        raise ValueError("events must be an array")

    valid, exclusions = [], []
    for index, raw in enumerate(data["events"]):
        if not isinstance(raw, dict):
            exclusions.append({"index": index, "reason": "event is not an object"})
            continue
        ref = raw.get("reference", "event[%d]" % index)
        if raw.get("status") != "posted":
            exclusions.append({"reference": ref, "reason": "not posted"})
            continue
        if raw.get("confirmed") is not True:
            exclusions.append({"reference": ref, "reason": "not confirmed"})
            continue
        category = raw.get("category")
        if category not in CATEGORIES:
            exclusions.append({"reference": ref, "reason": "unsupported or unconfirmed category"})
            continue
        try:
            entry = {
                "raw": raw, "reference": ref, "date": parse_date(raw.get("date")),
                "category": category, "cash": money(raw.get("cash_amount"), "cash_amount"),
                "charged": money(raw.get("bank_fee_charged"), "bank_fee_charged"),
                "surcharge": money(raw.get("operator_surcharge", "0"), "operator_surcharge"),
                "credited": money(raw.get("rebate_credited", "0"), "rebate_credited"),
            }
        except ValueError as exc:
            exclusions.append({"reference": ref, "reason": str(exc)})
            continue
        valid.append(entry)

    # Chronological order is essential for monthly Light Blue allowances and the
    # Purple monthly rebate cap.  Sort ties deterministically by original text.
    valid.sort(key=lambda e: (e["date"], str(e["reference"])))
    allowance_count, purple_rebate_used = {}, {}
    items = []
    total_fee_refund = Decimal("0")
    total_missing_rebate = Decimal("0")

    for event in valid:
        month_key = (event["date"].year, event["date"].month, event["category"])
        ordinal = 1
        if PRODUCTS[product_name] == "light_blue":
            ordinal = allowance_count.get(month_key, 0) + 1
            allowance_count[month_key] = ordinal
        expected = expected_fee(PRODUCTS[product_name], event["category"], event["cash"], ordinal).quantize(CENT)
        fee_overcharge = max(event["charged"] - expected, Decimal("0"))

        missing_rebate = Decimal("0")
        raw = event["raw"]
        if PRODUCTS[product_name] == "purple" and raw.get("operator_fee_eligible") is True:
            rebate_month = (event["date"].year, event["date"].month)
            used = purple_rebate_used.get(rebate_month, Decimal("0"))
            eligible_rebate = min(event["surcharge"], max(Decimal("0"), Decimal("30.00") - used))
            # The cap is consumed by the eligible amount, not merely by an
            # analyst-entered credit field.  Input events must include all
            # confirmed eligible fees for the month in chronological order.
            purple_rebate_used[rebate_month] = used + eligible_rebate
            missing_rebate = max(eligible_rebate - event["credited"], Decimal("0"))

        total_fee_refund += fee_overcharge
        total_missing_rebate += missing_rebate
        items.append({
            "reference": event["reference"], "date": event["date"].strftime("%m/%d/%Y"),
            "category": event["category"], "allowance_ordinal": ordinal if PRODUCTS[product_name] == "light_blue" else None,
            "cash_amount": fmt(event["cash"]), "bank_fee_charged": fmt(event["charged"]),
            "expected_bank_fee": fmt(expected), "fee_overcharge": fmt(fee_overcharge),
            "eligible_operator_rebate": fmt((event["surcharge"] if raw.get("operator_fee_eligible") is True else Decimal("0"))),
            "missing_rebate": fmt(missing_rebate),
        })

    total = total_fee_refund + total_missing_rebate
    if total_fee_refund > total_missing_rebate:
        credit_type = "fee_refund"
    elif total_missing_rebate > total_fee_refund:
        credit_type = "rebate_credit"
    else:
        credit_type = None
    return {
        "product": product_name,
        "included_events": items,
        "excluded_events": exclusions,
        "fee_refund_total": fmt(total_fee_refund),
        "missing_rebate_total": fmt(total_missing_rebate),
        "provisional_total_correction": fmt(total),
        "recommended_credit_type": credit_type,
        "advisory": "Requires transaction-history reconciliation, verified customer/account ownership, checking-account confirmation, and one-credit-per-account review before any bank action.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
