#!/usr/bin/env python3
"""Deterministically reconcile structured ATM withdrawal events.

Reads one JSON object from stdin and emits one JSON object on stdout.  It never
calls banking tools.  See SKILL.md for the input schema.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")
CENT = Decimal("0.01")


def money(value, field):
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal amount or null")
    if result < ZERO:
        raise ValueError(f"{field} cannot be negative")
    return result


def display(value):
    return format(value.quantize(CENT), ".2f")


def exact_cent(value):
    """Do not invent a rounding convention absent from the policy."""
    return value == value.quantize(CENT)


def parse_date(value):
    for form in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, form).date()
        except (TypeError, ValueError):
            pass
    raise ValueError("withdrawal_date must be MM/DD/YYYY or YYYY-MM-DD")


def product_name(value):
    name = str(value).strip().lower().replace(" account", "")
    aliases = {
        "purple": "Purple",
        "light blue": "Light Blue",
        "dark green": "Dark Green",
        "evergreen": "Evergreen",
    }
    if name not in aliases:
        raise ValueError("account_product must be Purple, Light Blue, Dark Green, or Evergreen")
    return aliases[name]


def expected_fee(product, amount, region, network, domestic_index, foreign_index):
    if region not in {"domestic", "foreign"}:
        return None, "unknown region"
    if network not in {"in_network", "out_of_network"}:
        return None, "unknown network classification"

    if product == "Purple":
        if region == "foreign" or network == "in_network":
            return ZERO, None
        return Decimal("2.50"), None

    if product == "Light Blue":
        if region == "foreign":
            return (ZERO if foreign_index <= 2 else Decimal("4.00")), None
        if network == "in_network":
            return ZERO, None
        return (ZERO if domestic_index <= 2 else Decimal("2.50")), None

    if product == "Dark Green":
        if region == "foreign":
            fee = min(amount * Decimal("0.025"), Decimal("6.00"))
        elif network == "in_network":
            fee = ZERO
        else:
            fee = max(amount * Decimal("0.01"), Decimal("1.50"))
    else:  # Evergreen
        if region == "foreign":
            fee = max(amount * Decimal("0.02"), Decimal("3.00"))
        elif network == "in_network":
            fee = ZERO
        else:
            fee = min(amount * Decimal("0.01"), Decimal("2.50"))

    if not exact_cent(fee):
        return None, "policy percentage yields a fractional cent; exact rounding rule is not supplied"
    return fee, None


def main(data):
    product = product_name(data.get("account_product"))
    month = data.get("month")
    try:
        month_start = datetime.strptime(month, "%Y-%m")
    except (TypeError, ValueError):
        raise ValueError("month must be YYYY-MM")

    events = data.get("events")
    if not isinstance(events, list):
        raise ValueError("events must be a list")

    parsed = []
    for index, raw in enumerate(events):
        if not isinstance(raw, dict):
            raise ValueError(f"events[{index}] must be an object")
        date = parse_date(raw.get("withdrawal_date"))
        if date.year != month_start.year or date.month != month_start.month:
            raise ValueError(f"events[{index}] withdrawal_date is outside month")
        parsed.append({
            "index": index,
            "date": date,
            "amount": money(raw.get("amount"), f"events[{index}].amount"),
            "region": raw.get("region"),
            "network": raw.get("network"),
            "bank_fee": money(raw.get("bank_fee_charged"), f"events[{index}].bank_fee_charged"),
            "operator": money(raw.get("operator_surcharge"), f"events[{index}].operator_surcharge"),
            "operator_eligible": raw.get("operator_fee_eligible"),
            "rebate": money(raw.get("rebate_received"), f"events[{index}].rebate_received"),
        })
    parsed.sort(key=lambda event: (event["date"], event["index"]))

    unresolved = []
    event_results = []
    domestic_count = 0
    foreign_count = 0
    fee_refund_amount = ZERO
    fee_refund_items = 0

    for event in parsed:
        if event["amount"] is None:
            unresolved.append(f"event {event['index']}: withdrawal amount is unresolved")
            continue
        if event["region"] == "domestic" and event["network"] == "out_of_network":
            domestic_count += 1
        if event["region"] == "foreign":
            foreign_count += 1
        expected, issue = expected_fee(
            product, event["amount"], event["region"], event["network"],
            domestic_count, foreign_count,
        )
        if issue:
            unresolved.append(f"event {event['index']}: {issue}")
        if event["bank_fee"] is None:
            unresolved.append(f"event {event['index']}: matched posted Rho-Bank fee is unresolved")
        difference = None
        if expected is not None and event["bank_fee"] is not None:
            difference = event["bank_fee"] - expected
            if difference > ZERO:
                fee_refund_amount += difference
                fee_refund_items += 1
        event_results.append({
            "event_index": event["index"],
            "withdrawal_date": event["date"].isoformat(),
            "expected_bank_fee": display(expected) if expected is not None else None,
            "observed_bank_fee": display(event["bank_fee"]) if event["bank_fee"] is not None else None,
            "overcharge": display(difference) if difference is not None and difference > ZERO else "0.00",
        })

    missing_rebate = ZERO
    rebate_items = 0
    if product == "Purple":
        eligible_operator_total = ZERO
        received_rebates = ZERO
        purple_rebate_unknown = False
        for event in parsed:
            if event["operator"] is None or event["rebate"] is None:
                purple_rebate_unknown = True
                continue
            if event["operator_eligible"] not in {True, False}:
                purple_rebate_unknown = True
                continue
            if event["operator_eligible"]:
                eligible_operator_total += event["operator"]
            received_rebates += event["rebate"]
        if purple_rebate_unknown:
            unresolved.append("Purple operator-surcharge eligibility or matched posted rebate is unresolved")
        else:
            expected_rebate = min(eligible_operator_total, Decimal("30.00"))
            if expected_rebate > received_rebates:
                missing_rebate = expected_rebate - received_rebates
                rebate_items = 1
    else:
        expected_rebate = None
        received_rebates = None

    prerequisites = {
        "identity_verified": data.get("identity_verified") is True,
        "open_checking_account": data.get("is_checking") is True and str(data.get("account_status", "")).upper() == "OPEN",
        "review_complete": data.get("review_complete") is True,
        "one_credit_call_available": data.get("one_credit_call_available") is True,
        "no_unresolved_items": not unresolved,
    }
    total_credit = fee_refund_amount + missing_rebate
    correction_items = fee_refund_items + rebate_items
    credit_type = None
    tie = False
    if fee_refund_items > rebate_items:
        credit_type = "fee_refund"
    elif rebate_items > fee_refund_items:
        credit_type = "rebate_credit"
    elif correction_items:
        tie = True

    eligible = total_credit > ZERO and all(prerequisites.values()) and not tie
    return {
        "status": "ok",
        "account_product": product,
        "month": month,
        "events_reviewed": len(parsed),
        "event_results": event_results,
        "purple_rebate": ({
            "expected_eligible_rebate": display(expected_rebate),
            "posted_rebate_received": display(received_rebates),
            "missing_rebate": display(missing_rebate),
        } if product == "Purple" and expected_rebate is not None else None),
        "unresolved": unresolved,
        "prerequisites": prerequisites,
        "credit": {
            "eligible": eligible,
            "amount": display(total_credit),
            "fee_refund_component": display(fee_refund_amount),
            "rebate_credit_component": display(missing_rebate),
            "fee_refund_correction_items": fee_refund_items,
            "rebate_correction_items": rebate_items,
            "credit_type": credit_type,
            "type_tie_requires_authorized_determination": tie,
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        sys.exit(2)
