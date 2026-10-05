#!/usr/bin/env python3
"""Filter and rank evidence-extracted card promotions.

Read one JSON object from stdin and emit one JSON object to stdout. Facts must be
extracted from supplied evidence by the caller; this program never discovers,
infers, or executes an offer.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def parse_date(value, label, errors):
    if not isinstance(value, str):
        errors.append(f"{label} must be YYYY-MM-DD")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} must be YYYY-MM-DD")
        return None


def decimal(value, label, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{label} must be a non-negative finite number")
        return None
    return result


def money(value):
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def window_status(offer, today, index, errors):
    start = parse_date(offer.get("open_start"), f"offers[{index}].open_start", errors)
    end = parse_date(offer.get("open_end"), f"offers[{index}].open_end", errors)
    if start is None or end is None:
        return "unknown"
    if start > end:
        errors.append(f"offers[{index}] has a reversed offer window")
        return "unknown"
    return "active" if start <= today <= end else "inactive"


def eligibility(offer, customer):
    requirements = offer.get("requirements", [])
    if not isinstance(requirements, list):
        return "failed", ["invalid requirements record"]
    unmet, unknown = [], []
    for requirement in requirements:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("field"), str):
            unmet.append("invalid requirement record")
            continue
        label = requirement.get("label")
        label = label.strip() if isinstance(label, str) and label.strip() else requirement["field"]
        actual = customer.get(requirement["field"])
        if actual is None:
            unknown.append(label)
        elif actual != requirement.get("equals"):
            unmet.append(label)
    if unmet:
        return "failed", unmet
    return ("conditional", unknown) if unknown else ("eligible", [])


def value_of(benefit, index, errors):
    if not isinstance(benefit, dict):
        errors.append(f"offers[{index}].benefit must be an object")
        return None
    if benefit.get("cash_value_usd") is not None:
        return decimal(benefit["cash_value_usd"], f"offers[{index}].benefit.cash_value_usd", errors)
    amount = benefit.get("amount")
    if amount is None:
        return None
    amount = decimal(amount, f"offers[{index}].benefit.amount", errors)
    if amount is None:
        return None
    if str(benefit.get("unit", "")).upper() == "USD":
        return amount
    if benefit.get("point_value_usd") is None:
        return None
    rate = decimal(benefit["point_value_usd"], f"offers[{index}].benefit.point_value_usd", errors)
    return None if rate is None else amount * rate


def record(offer, status, eligibility_status, reasons, value):
    return {
        "id": offer.get("id"),
        "product": offer.get("product"),
        "offer": offer,
        "date_status": status,
        "eligibility_status": eligibility_status,
        "eligibility_reasons": reasons,
        "cash_value_usd": money(value),
    }


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["top-level input must be an object"]}
    errors = []
    today = parse_date(payload.get("as_of_date"), "as_of_date", errors)
    customer = payload.get("customer")
    targets = payload.get("target_benefit_kinds")
    offers = payload.get("offers")
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
    if not isinstance(targets, list) or not all(isinstance(x, str) for x in targets):
        errors.append("target_benefit_kinds must be a list of strings")
    if not isinstance(offers, list):
        errors.append("offers must be a list")
    if errors:
        return {"ok": False, "errors": errors}

    ranked, nontargeted, excluded = [], [], []
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            errors.append(f"offers[{index}] must be an object")
            continue
        status = window_status(offer, today, index, errors)
        eligibility_status, reasons = eligibility(offer, customer)
        benefit = offer.get("benefit")
        kind = benefit.get("kind") if isinstance(benefit, dict) else None
        value = value_of(benefit, index, errors)
        item = record(offer, status, eligibility_status, reasons, value)
        if customer.get("audience") is not None and offer.get("audience") != customer["audience"]:
            item["exclusion_reason"] = "offer audience does not match customer audience"
            excluded.append(item)
        elif status != "active":
            item["exclusion_reason"] = "offer window is not current" if status == "inactive" else "offer window is unknown"
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
    status_order = {"eligible": 0, "conditional": 1}
    ranked.sort(key=lambda item: (
        status_order.get(item["eligibility_status"], 2),
        item["cash_value_usd"] is None,
        -(Decimal(item["cash_value_usd"]) if item["cash_value_usd"] is not None else Decimal("0")),
        str(item.get("product") or ""),
    ))
    return {"ok": True, "ranked_candidates": ranked, "active_nontargeted": nontargeted, "excluded": excluded}


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        result = {"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}
    print(json.dumps(result, ensure_ascii=False))
