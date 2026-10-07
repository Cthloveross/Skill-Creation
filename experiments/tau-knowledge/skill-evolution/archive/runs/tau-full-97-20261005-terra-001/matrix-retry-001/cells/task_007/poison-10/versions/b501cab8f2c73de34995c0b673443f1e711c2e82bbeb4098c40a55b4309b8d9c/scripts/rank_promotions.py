#!/usr/bin/env python3
"""Validate and rank structured, documented credit-card promotions.

Reads one JSON object from stdin and writes one JSON object to stdout. It never
infers missing offer dates, eligibility, or point values.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be an ISO date string")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} must use YYYY-MM-DD")
        return None


def parse_decimal(value, field, errors):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be decimal-compatible")
        return None
    if not parsed.is_finite():
        errors.append(f"{field} must be finite")
        return None
    return parsed


def money(value):
    return None if value is None else format(value.quantize(Decimal("0.01")), "f")


def date_status(offer, today, index, errors):
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
    failed, unknown = [], []
    for requirement in requirements:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("field"), str):
            failed.append("invalid requirement record")
            continue
        field = requirement["field"]
        expected = requirement.get("equals")
        label = requirement.get("label") if isinstance(requirement.get("label"), str) else field
        actual = customer.get(field)
        if actual is None:
            unknown.append(label)
        elif actual != expected:
            failed.append(label)
    if failed:
        return "failed", failed
    return ("conditional", unknown) if unknown else ("eligible", [])


def cash_value(benefit, index, errors):
    if not isinstance(benefit, dict):
        errors.append(f"offers[{index}].benefit must be an object")
        return None
    if benefit.get("cash_value_usd") is not None:
        return parse_decimal(benefit["cash_value_usd"], f"offers[{index}].benefit.cash_value_usd", errors)
    if benefit.get("amount") is None:
        return None
    amount = parse_decimal(benefit["amount"], f"offers[{index}].benefit.amount", errors)
    if amount is None:
        return None
    if benefit.get("unit") == "USD":
        return amount
    if benefit.get("point_value_usd") is None:
        return None
    rate = parse_decimal(benefit["point_value_usd"], f"offers[{index}].benefit.point_value_usd", errors)
    return None if rate is None else amount * rate


def record(offer, status, eligibility_status, reasons, value):
    return {
        "id": offer.get("id"),
        "product": offer.get("product"),
        "audience": offer.get("audience"),
        "offer_window": {"start": offer.get("open_start"), "end": offer.get("open_end")},
        "benefit": offer.get("benefit"),
        "cash_value_usd": money(value),
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
    if not isinstance(target_kinds, list) or not all(isinstance(kind, str) for kind in target_kinds):
        errors.append("target_benefit_kinds must be a list of strings")
    if errors:
        return {"ok": False, "errors": errors}

    ranked, nontargeted, excluded = [], [], []
    desired_audience = customer.get("audience")
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            errors.append(f"offers[{index}] must be an object")
            continue
        status = date_status(offer, today, index, errors)
        elig, reasons = eligibility(offer, customer)
        benefit = offer.get("benefit")
        kind = benefit.get("kind") if isinstance(benefit, dict) else None
        value = cash_value(benefit, index, errors)
        item = record(offer, status, elig, reasons, value)
        audience = offer.get("audience")

        if desired_audience is not None and audience != desired_audience:
            item["exclusion_reason"] = "offer audience does not match customer audience"
            excluded.append(item)
        elif status == "inactive":
            item["exclusion_reason"] = "offer dates are inactive"
            excluded.append(item)
        elif status == "unknown":
            item["exclusion_reason"] = "offer dates are unknown"
            excluded.append(item)
        elif elig == "failed":
            item["exclusion_reason"] = "one or more eligibility requirements are not met"
            excluded.append(item)
        elif kind not in target_kinds:
            nontargeted.append(item)
        else:
            ranked.append(item)

    if errors:
        return {"ok": False, "errors": errors}

    order = {"eligible": 0, "conditional": 1}
    ranked.sort(key=lambda item: (
        order.get(item["eligibility_status"], 2),
        item["cash_value_usd"] is None,
        -(Decimal(item["cash_value_usd"]) if item["cash_value_usd"] is not None else Decimal("0")),
        item.get("product") or "",
    ))
    return {"ok": True, "ranked_candidates": ranked, "active_nontargeted": nontargeted, "excluded": excluded}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}))
    else:
        print(json.dumps(main(payload), ensure_ascii=False))
