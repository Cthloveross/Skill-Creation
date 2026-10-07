#!/usr/bin/env python3
"""Rank structured, documented card promotions. Reads one JSON object from stdin."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def as_decimal(value, field, errors):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a decimal-compatible value")
        return None


def parse_date(value, field, errors):
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{field} must be an ISO date string")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} must be YYYY-MM-DD")
        return None


def decimal_text(value):
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def date_status(offer, today, errors, index):
    start = parse_date(offer.get("open_start"), f"offers[{index}].open_start", errors)
    end = parse_date(offer.get("open_end"), f"offers[{index}].open_end", errors)
    if start is None or end is None:
        return "unknown"
    if start > end:
        errors.append(f"offers[{index}] has open_start after open_end")
        return "unknown"
    return "active" if start <= today <= end else "inactive"


def eligibility_status(offer, customer):
    failed, unknown = [], []
    requirements = offer.get("requirements", [])
    if not isinstance(requirements, list):
        return "failed", ["requirements must be a list"]
    for requirement in requirements:
        if not isinstance(requirement, dict) or not requirement.get("field"):
            failed.append("invalid requirement record")
            continue
        field = requirement["field"]
        label = requirement.get("label") or field
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


def cash_value(benefit, errors, index):
    if not isinstance(benefit, dict):
        errors.append(f"offers[{index}].benefit must be an object")
        return None
    direct = as_decimal(benefit.get("cash_value_usd"), f"offers[{index}].benefit.cash_value_usd", errors)
    if direct is not None:
        return direct
    amount = as_decimal(benefit.get("amount"), f"offers[{index}].benefit.amount", errors)
    if amount is None:
        return None
    if benefit.get("unit") == "USD":
        return amount
    conversion = as_decimal(benefit.get("point_value_usd"), f"offers[{index}].benefit.point_value_usd", errors)
    return amount * conversion if conversion is not None else None


def main(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["top-level input must be an object"]}
    today = parse_date(payload.get("current_date"), "current_date", errors)
    offers = payload.get("offers")
    customer = payload.get("customer", {})
    target_kinds = payload.get("target_benefit_kinds", [])
    if not isinstance(offers, list):
        errors.append("offers must be a list")
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
    if not isinstance(target_kinds, list) or not all(isinstance(x, str) for x in target_kinds):
        errors.append("target_benefit_kinds must be a list of strings")
    if errors:
        return {"ok": False, "errors": errors}

    ranked, non_targeted, excluded = [], [], []
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            errors.append(f"offers[{index}] must be an object")
            continue
        status = date_status(offer, today, errors, index)
        benefit = offer.get("benefit", {})
        kind = benefit.get("kind") if isinstance(benefit, dict) else None
        eligibility, reasons = eligibility_status(offer, customer)
        value = cash_value(benefit, errors, index)
        result = {
            "id": offer.get("id"),
            "product": offer.get("product"),
            "audience": offer.get("audience"),
            "benefit": benefit,
            "cash_value_usd": decimal_text(value),
            "date_status": status,
            "eligibility_status": eligibility,
            "eligibility_reasons": reasons,
            "spend_requirement": offer.get("spend_requirement"),
            "notes": offer.get("notes", []),
        }
        if status != "active":
            result["exclusion_reason"] = "offer dates are inactive" if status == "inactive" else "offer dates are unknown"
            excluded.append(result)
        elif eligibility == "failed":
            result["exclusion_reason"] = "one or more eligibility requirements are not met"
            excluded.append(result)
        elif kind not in target_kinds:
            non_targeted.append(result)
        else:
            ranked.append(result)

    if errors:
        return {"ok": False, "errors": errors}
    eligibility_order = {"eligible": 0, "conditional": 1}
    ranked.sort(key=lambda item: (
        eligibility_order.get(item["eligibility_status"], 2),
        item["cash_value_usd"] is None,
        -(Decimal(item["cash_value_usd"]) if item["cash_value_usd"] is not None else Decimal("0")),
        item.get("product") or "",
    ))
    return {
        "ok": True,
        "ranked_candidates": ranked,
        "active_nontargeted": non_targeted,
        "excluded": excluded,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}))
        sys.exit(0)
    print(json.dumps(main(payload), ensure_ascii=False))
