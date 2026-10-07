#!/usr/bin/env python3
"""Validate and rank evidence-extracted credit-card promotions.

Read one JSON object from stdin and write one JSON object to stdout. This helper
never infers dates, eligibility, point values, or fee terms from missing data.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_date(value, label, errors):
    if not isinstance(value, str):
        errors.append(f"{label} must be YYYY-MM-DD")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} must be YYYY-MM-DD")
        return None


def parse_decimal(value, label, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be decimal-compatible")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{label} must be a non-negative finite number")
        return None
    return result


def money(value):
    return None if value is None else format(value.quantize(Decimal("0.01")), ".2f")


def date_status(offer, today, index, errors):
    start = parse_date(offer.get("open_start"), f"offers[{index}].open_start", errors)
    end = parse_date(offer.get("open_end"), f"offers[{index}].open_end", errors)
    if start is None or end is None:
        return "unknown"
    if start > end:
        errors.append(f"offers[{index}] has an invalid offer window")
        return "unknown"
    return "active" if start <= today <= end else "inactive"


def eligibility(offer, customer):
    requirements = offer.get("requirements", [])
    if not isinstance(requirements, list):
        return "failed", ["invalid requirements record"]
    failed, unknown = [], []
    for requirement in requirements:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("field"), str):
            failed.append("invalid requirement record")
            continue
        field = requirement["field"]
        label = requirement.get("label")
        label = label if isinstance(label, str) and label.strip() else field
        actual = customer.get(field)
        if actual is None:
            unknown.append(label)
        elif actual != requirement.get("equals"):
            failed.append(label)
    if failed:
        return "failed", failed
    return ("conditional", unknown) if unknown else ("eligible", [])


def cash_value(benefit, index, errors):
    if not isinstance(benefit, dict):
        errors.append(f"offers[{index}].benefit must be an object")
        return None
    explicit = benefit.get("cash_value_usd")
    if explicit is not None:
        return parse_decimal(explicit, f"offers[{index}].benefit.cash_value_usd", errors)
    amount_raw = benefit.get("amount")
    if amount_raw is None:
        return None
    amount = parse_decimal(amount_raw, f"offers[{index}].benefit.amount", errors)
    if amount is None:
        return None
    if benefit.get("unit") == "USD":
        return amount
    rate_raw = benefit.get("point_value_usd")
    if rate_raw is None:
        return None
    rate = parse_decimal(rate_raw, f"offers[{index}].benefit.point_value_usd", errors)
    return None if rate is None else amount * rate


def make_record(offer, window_status, eligibility_status, reasons, value):
    return {
        "id": offer.get("id"),
        "product": offer.get("product"),
        "audience": offer.get("audience"),
        "offer_window": {"start": offer.get("open_start"), "end": offer.get("open_end")},
        "benefit": offer.get("benefit"),
        "cash_value_usd": money(value),
        "annual_fee_usd": offer.get("annual_fee_usd"),
        "date_status": window_status,
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
    customer = payload.get("customer")
    offers = payload.get("offers")
    targets = payload.get("target_benefit_kinds")
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
    if not isinstance(offers, list):
        errors.append("offers must be a list")
    if not isinstance(targets, list) or not all(isinstance(x, str) for x in targets):
        errors.append("target_benefit_kinds must be a list of strings")
    if errors:
        return {"ok": False, "errors": errors}

    ranked, nontargeted, excluded = [], [], []
    audience = customer.get("audience")
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            errors.append(f"offers[{index}] must be an object")
            continue
        status = date_status(offer, today, index, errors)
        eligibility_status, reasons = eligibility(offer, customer)
        benefit = offer.get("benefit")
        kind = benefit.get("kind") if isinstance(benefit, dict) else None
        value = cash_value(benefit, index, errors)
        item = make_record(offer, status, eligibility_status, reasons, value)
        if audience is not None and offer.get("audience") != audience:
            item["exclusion_reason"] = "offer audience does not match customer audience"
            excluded.append(item)
        elif status == "inactive":
            item["exclusion_reason"] = "offer window is not current"
            excluded.append(item)
        elif status == "unknown":
            item["exclusion_reason"] = "offer window is unknown"
            excluded.append(item)
        elif eligibility_status == "failed":
            item["exclusion_reason"] = "a known eligibility condition is not met"
            excluded.append(item)
        elif kind not in targets:
            nontargeted.append(item)
        else:
            ranked.append(item)

    if errors:
        return {"ok": False, "errors": errors}
    eligibility_order = {"eligible": 0, "conditional": 1}
    ranked.sort(key=lambda item: (
        eligibility_order.get(item["eligibility_status"], 2),
        item["cash_value_usd"] is None,
        -(Decimal(item["cash_value_usd"]) if item["cash_value_usd"] is not None else Decimal("0")),
        str(item.get("product") or ""),
    ))
    return {
        "ok": True,
        "ranked_candidates": ranked,
        "active_nontargeted": nontargeted,
        "excluded": excluded,
    }


if __name__ == "__main__":
    try:
        output = main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        output = {"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}
    print(json.dumps(output, ensure_ascii=False))
