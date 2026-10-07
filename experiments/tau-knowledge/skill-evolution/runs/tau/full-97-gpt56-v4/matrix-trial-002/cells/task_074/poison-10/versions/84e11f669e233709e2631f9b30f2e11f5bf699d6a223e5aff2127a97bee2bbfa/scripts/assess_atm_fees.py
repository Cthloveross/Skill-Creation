#!/usr/bin/env python3
"""Assess normalized ATM fee evidence; reads JSON stdin and emits JSON stdout.

This helper is intentionally non-authoritative: it calculates documented rules only
when the caller has already established withdrawal/fee associations and classifications.
It does not access banking systems or recommend an automatic account action.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value):
    try:
        result = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("must be a valid monetary amount")
    if result < 0:
        raise ValueError("must not be negative")
    return result


def date_value(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for form in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, form).date()
        except ValueError:
            pass
    raise ValueError("date must use YYYY-MM-DD or MM/DD/YYYY")


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def normalized_class(value):
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "purple": "purple", "purple_account": "purple",
        "light_blue": "light_blue", "light_blue_account": "light_blue",
        "evergreen": "evergreen", "evergreen_account": "evergreen",
        "dark_green": "dark_green", "dark_green_account": "dark_green",
    }
    if text not in aliases:
        raise ValueError("account_class must be purple, light_blue, evergreen, or dark_green")
    return aliases[text]


def expected_fee(product, route, amount, allowance_number):
    if route == "in_network":
        return ZERO, "in-network withdrawal: no documented out-of-network bank fee"
    if product == "purple":
        if route == "foreign":
            return ZERO, "Purple foreign ATM withdrawal fee is $0.00"
        return Decimal("2.50"), "Purple domestic out-of-network fee is $2.50 per withdrawal"
    if product == "light_blue":
        if route == "domestic_out_of_network":
            return (ZERO if allowance_number <= 2 else Decimal("2.50"),
                    "Light Blue domestic out-of-network allowance number %d" % allowance_number)
        return (ZERO if allowance_number <= 2 else Decimal("4.00"),
                "Light Blue foreign withdrawal allowance number %d" % allowance_number)
    if product == "evergreen":
        if route == "domestic_out_of_network":
            return min(amount * Decimal("0.01"), Decimal("2.50")).quantize(CENT, rounding=ROUND_HALF_UP), \
                   "Evergreen domestic out-of-network fee: 1% capped at $2.50"
        return max(amount * Decimal("0.02"), Decimal("3.00")).quantize(CENT, rounding=ROUND_HALF_UP), \
               "Evergreen foreign fee: 2% with $3.00 minimum"
    if route == "foreign":
        return min(amount * Decimal("0.025"), Decimal("6.00")).quantize(CENT, rounding=ROUND_HALF_UP), \
               "Dark Green foreign fee: 2.5% capped at $6.00"
    return max(amount * Decimal("0.01"), Decimal("1.50")).quantize(CENT, rounding=ROUND_HALF_UP), \
           "Dark Green domestic out-of-network fee: 1% with $1.50 minimum"


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level input must be an object")
    product = normalized_class(payload.get("account_class"))
    month = payload.get("month")
    try:
        requested_month = datetime.strptime(month, "%Y-%m").strftime("%Y-%m")
    except (TypeError, ValueError):
        raise ValueError("month must use YYYY-MM")
    transitioned = payload.get("transitioned", False)
    if not isinstance(transitioned, bool):
        raise ValueError("transitioned must be boolean")
    withdrawals = payload.get("withdrawals")
    if not isinstance(withdrawals, list):
        raise ValueError("withdrawals must be an array")

    errors = []
    if product == "dark_green" and transitioned:
        errors.append("Dark Green account is transitioned; replacement product fee terms are required.")

    parsed = []
    for index, record in enumerate(withdrawals):
        try:
            if not isinstance(record, dict):
                raise ValueError("record must be an object")
            identifier = record.get("id")
            if identifier is None or str(identifier) == "":
                raise ValueError("id is required")
            dt = date_value(record.get("date"))
            if dt.strftime("%Y-%m") != requested_month:
                raise ValueError("date is outside requested month")
            route = record.get("route")
            if route not in ("in_network", "domestic_out_of_network", "foreign"):
                raise ValueError("route is invalid")
            status = record.get("status")
            if status not in ("posted", "pending"):
                raise ValueError("status must be posted or pending")
            observed = None if "observed_bank_fee" not in record or record.get("observed_bank_fee") is None else money(record.get("observed_bank_fee"))
            parsed.append({"id": str(identifier), "date": dt, "amount": money(record.get("amount")),
                           "route": route, "status": status, "observed": observed})
        except ValueError as exc:
            errors.append("withdrawals[%d]: %s" % (index, exc))

    parsed.sort(key=lambda item: (item["date"], item["id"]))
    domestic_count = 0
    foreign_count = 0
    assessments = []
    refund_total = ZERO
    incomplete = bool(errors)
    for item in parsed:
        output = {"id": item["id"], "date": item["date"].isoformat(), "route": item["route"],
                  "withdrawal_amount": fmt(item["amount"]), "status": item["status"]}
        if item["status"] != "posted":
            output["assessment"] = "not_assessed_pending"
            incomplete = True
            assessments.append(output)
            continue
        allowance = 0
        if item["route"] == "domestic_out_of_network":
            domestic_count += 1
            allowance = domestic_count
        elif item["route"] == "foreign":
            foreign_count += 1
            allowance = foreign_count
        try:
            expected, rule = expected_fee(product, item["route"], item["amount"], allowance)
        except ValueError as exc:
            output["assessment"] = "manual_review_required"
            output["reason"] = str(exc)
            incomplete = True
            assessments.append(output)
            continue
        output["expected_bank_fee"] = fmt(expected)
        output["rule"] = rule
        if item["observed"] is None:
            output["assessment"] = "expected_fee_only"
            incomplete = True
        else:
            output["observed_bank_fee"] = fmt(item["observed"])
            difference = (item["observed"] - expected).quantize(CENT, rounding=ROUND_HALF_UP)
            output["difference_observed_minus_expected"] = fmt(difference.copy_abs())
            if difference > ZERO:
                output["assessment"] = "possible_overcharge"
                output["possible_fee_refund"] = fmt(difference)
                refund_total += difference
            elif difference == ZERO:
                output["assessment"] = "matches_documented_fee"
            else:
                output["assessment"] = "observed_fee_below_documented_fee"
        assessments.append(output)

    rebate_output = None
    if product == "purple" and ("operator_fee_events" in payload or "posted_rebates" in payload):
        events = payload.get("operator_fee_events", [])
        rebates = payload.get("posted_rebates", [])
        if not isinstance(events, list) or not isinstance(rebates, list):
            errors.append("operator_fee_events and posted_rebates must be arrays")
            incomplete = True
        else:
            eligible_total = ZERO
            for index, event in enumerate(events):
                try:
                    if not isinstance(event, dict) or event.get("eligible") is not True:
                        raise ValueError("must be a confirmed eligible event")
                    if event.get("status") != "posted":
                        raise ValueError("must be posted")
                    if date_value(event.get("date")).strftime("%Y-%m") != requested_month:
                        raise ValueError("date is outside requested month")
                    eligible_total += money(event.get("amount"))
                except ValueError as exc:
                    errors.append("operator_fee_events[%d]: %s" % (index, exc))
                    incomplete = True
            posted_total = ZERO
            for index, value in enumerate(rebates):
                try:
                    posted_total += money(value)
                except ValueError as exc:
                    errors.append("posted_rebates[%d]: %s" % (index, exc))
                    incomplete = True
            expected_rebate = min(eligible_total, Decimal("30.00"))
            missing = max(ZERO, expected_rebate - posted_total)
            rebate_output = {"confirmed_eligible_operator_fees": fmt(eligible_total),
                             "monthly_rebate_cap": "30.00", "expected_rebate": fmt(expected_rebate),
                             "confirmed_posted_rebates": fmt(posted_total),
                             "possible_missing_rebate": fmt(missing)}

    return {
        "ok": not errors,
        "errors": errors,
        "account_class": product,
        "month": requested_month,
        "withdrawal_assessments": assessments,
        "possible_fee_refund_total": fmt(refund_total),
        "purple_operator_rebate_assessment": rebate_output,
        "ready_for_manual_review": incomplete or bool(errors),
        "notice": "Amounts are calculations from normalized evidence, not authorization to apply a credit. Confirm complete transaction coverage, associations, eligibility, ownership, and already-posted credits before any banking action."
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)], "ready_for_manual_review": True}))
        sys.exit(2)
