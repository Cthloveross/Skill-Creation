#!/usr/bin/env python3
"""Rank structured, documented credit-card promotions.

Reads one JSON object from stdin and writes one JSON object to stdout. This tool
filters by dates and known eligibility and calculates a cash equivalent only when
its input explicitly provides a direct USD value or a points conversion rate.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_date(value, field, errors):
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{field} must be an ISO date string")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} must use YYYY-MM-DD")
        return None


def parse_decimal(value, field, errors):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be decimal-compatible")
        return None


def money_text(value):
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def offer_date_status(offer, today, index, errors):
    start = parse_date(offer.get("open_start"), f"offers[{index}].open_start", errors)
    end = parse_date(offer.get("open_end"), f"offers[{index}].open_end", errors)
    if start is None or end is None:
        return "unknown"
    if start > end:
        errors.append(f"offers[{index}] has open_start after open_end")
        return "unknown"
    return "active" if start <= today <= end else "inactive"


def eligibility(offer, customer):
    requirements = offer.get("requirements", [])
    if not isinstance(requirements, list):
        return "failed", ["requirements must be a list"]
    failed = []
    unknown = []
    for requirement in requirements:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("field"), str):
            failed.append("invalid requirement record")
            continue
        field = requirement["field"]
        label = requirement.get("label") if isinstance(requirement.get("label"), str) else field
        actual = customer.get(field)
        if actual is None:
            unknown.append(label)
        elif actual != requirement.get("equals"):
            failed.append(label)
    if failed:
        return "failed", failed
    if unknown:
        return "conditional", unknown
    return "eligible", []


def documented_cash_value(benefit, index, errors):
    if not isinstance(benefit, dict):
        errors.append(f"offers[{index}].benefit must be an object")
        return None
    if benefit.get("cash_value_usd") is not None:
        return parse_decimal(
            benefit.get("cash_value_usd"),
            f"offers[{index}].benefit.cash_value_usd",
            errors,
        )
    amount = benefit.get("amount")
    unit = benefit.get("unit")
    if amount is None:
        return None
    parsed_amount = parse_decimal(amount, f"offers[{index}].benefit.amount", errors)
    if parsed_amount is None:
        return None
    if unit == "USD":
        return parsed_amount
    if benefit.get("point_value_usd") is None:
        return None
    conversion = parse_decimal(
        benefit.get("point_value_usd"),
        f"offers[{index}].benefit.point_value_usd",
        errors,
    )
    return None if conversion is None else parsed_amount * conversion


def result_record(offer, status, eligibility_status, reasons, cash_value):
    return {
        "id": offer.get("id"),
        "product": offer.get("product"),
        "audience": offer.get("audience"),
        "benefit": offer.get("benefit"),
        "cash_value_usd": money_text(cash_value),
        "date_status": status,
        "eligibility_status": eligibility_status,
        "eligibility_reasons": reasons,
        "spend_requirement": offer.get("spend_requirement"),
        "notes": offer.get("notes", []),
    }


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["top-level input must be an object"]}

    errors = []
    today = parse_date(payload.get("current_date"), "current_date", errors)
    customer = payload.get("customer", {})
    offers = payload.get("offers")
    target_kinds = payload.get("target_benefit_kinds", [])
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
    if not isinstance(offers, list):
        errors.append("offers must be a list")
    if not isinstance(target_kinds, list) or not all(isinstance(item, str) for item in target_kinds):
        errors.append("target_benefit_kinds must be a list of strings")
    if errors:
        return {"ok": False, "errors": errors}

    ranked = []
    active_nontargeted = []
    excluded = []
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            errors.append(f"offers[{index}] must be an object")
            continue
        status = offer_date_status(offer, today, index, errors)
        eligibility_status, reasons = eligibility(offer, customer)
        benefit = offer.get("benefit")
        kind = benefit.get("kind") if isinstance(benefit, dict) else None
        cash_value = documented_cash_value(benefit, index, errors)
        record = result_record(offer, status, eligibility_status, reasons, cash_value)

        if status == "inactive":
            record["exclusion_reason"] = "offer dates are inactive"
            excluded.append(record)
        elif status == "unknown":
            record["exclusion_reason"] = "offer dates are unknown"
            excluded.append(record)
        elif eligibility_status == "failed":
            record["exclusion_reason"] = "one or more eligibility requirements are not met"
            excluded.append(record)
        elif kind not in target_kinds:
            active_nontargeted.append(record)
        else:
            ranked.append(record)

    if errors:
        return {"ok": False, "errors": errors}

    eligibility_order = {"eligible": 0, "conditional": 1}
    ranked.sort(
        key=lambda item: (
            eligibility_order.get(item["eligibility_status"], 2),
            item["cash_value_usd"] is None,
            -(Decimal(item["cash_value_usd"]) if item["cash_value_usd"] is not None else Decimal("0")),
            item.get("product") or "",
        )
    )
    return {
        "ok": True,
        "ranked_candidates": ranked,
        "active_nontargeted": active_nontargeted,
        "excluded": excluded,
    }


if __name__ == "__main__":
    try:
        input_payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}))
    else:
        print(json.dumps(main(input_payload), ensure_ascii=False))
