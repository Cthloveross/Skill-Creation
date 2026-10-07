#!/usr/bin/env python3
"""Filter and rank evidence-extracted credit-card promotions.

Reads one JSON object from stdin and writes one JSON object to stdout. The caller
must extract all records from the current task evidence; this helper does not
search documents, infer missing facts, or perform actions.
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


def numeric(value, label, errors):
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


def eligibility(offer, customer):
    requirements = offer.get("requirements", [])
    if not isinstance(requirements, list):
        return "failed", ["invalid requirements record"]
    failed, unknown = [], []
    for requirement in requirements:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("field"), str):
            failed.append("invalid requirement record")
            continue
        label = requirement.get("label")
        if not isinstance(label, str) or not label.strip():
            label = requirement["field"]
        actual = customer.get(requirement["field"])
        if actual is None:
            unknown.append(label)
        elif actual != requirement.get("equals"):
            failed.append(label)
    if failed:
        return "failed", failed
    return ("conditional", unknown) if unknown else ("eligible", [])


def cash_value(benefit, label, errors):
    if not isinstance(benefit, dict):
        errors.append(f"{label} must be an object")
        return None
    if benefit.get("cash_value_usd") is not None:
        return numeric(benefit["cash_value_usd"], f"{label}.cash_value_usd", errors)
    amount = benefit.get("amount")
    if amount is None:
        return None
    amount = numeric(amount, f"{label}.amount", errors)
    if amount is None:
        return None
    if str(benefit.get("unit", "")).upper() == "USD":
        return amount
    rate = benefit.get("point_value_usd")
    if rate is None:
        return None
    rate = numeric(rate, f"{label}.point_value_usd", errors)
    return None if rate is None else amount * rate


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["top-level input must be an object"]}

    errors = []
    as_of = parse_date(payload.get("as_of_date"), "as_of_date", errors)
    customer = payload.get("customer")
    targets = payload.get("target_benefit_kinds")
    offers = payload.get("offers")
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
    if not isinstance(targets, list) or not all(isinstance(kind, str) for kind in targets):
        errors.append("target_benefit_kinds must be a list of strings")
    if not isinstance(offers, list):
        errors.append("offers must be a list")
    if errors:
        return {"ok": False, "errors": errors}

    candidates, nontargeted, excluded = [], [], []
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            errors.append(f"offers[{index}] must be an object")
            continue
        start = parse_date(offer.get("open_start"), f"offers[{index}].open_start", errors)
        end = parse_date(offer.get("open_end"), f"offers[{index}].open_end", errors)
        active = start is not None and end is not None and start <= end and start <= as_of <= end
        if start is not None and end is not None and start > end:
            errors.append(f"offers[{index}] has a reversed offer window")

        benefit = offer.get("benefit")
        kind = benefit.get("kind") if isinstance(benefit, dict) else None
        value = cash_value(benefit, f"offers[{index}].benefit", errors)
        eligibility_status, reasons = eligibility(offer, customer)
        item = {
            "id": offer.get("id"),
            "product": offer.get("product"),
            "offer": offer,
            "cash_value_usd": money(value),
            "eligibility_status": eligibility_status,
            "eligibility_reasons": reasons,
        }

        if customer.get("audience") is not None and offer.get("audience") != customer["audience"]:
            item["exclusion_reason"] = "offer audience does not match customer audience"
            excluded.append(item)
        elif not active:
            item["exclusion_reason"] = "offer window is not current or is incomplete"
            excluded.append(item)
        elif eligibility_status == "failed":
            item["exclusion_reason"] = "a known eligibility condition is not met"
            excluded.append(item)
        elif kind not in targets:
            nontargeted.append(item)
        else:
            candidates.append(item)

    if errors:
        return {"ok": False, "errors": errors}

    state_order = {"eligible": 0, "conditional": 1}
    candidates.sort(key=lambda item: (
        state_order.get(item["eligibility_status"], 2),
        item["cash_value_usd"] is None,
        -(Decimal(item["cash_value_usd"]) if item["cash_value_usd"] is not None else Decimal("0")),
        str(item.get("product") or ""),
    ))
    return {
        "ok": True,
        "ranked_candidates": candidates,
        "active_nontargeted": nontargeted,
        "excluded": excluded,
    }


if __name__ == "__main__":
    try:
        output = main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        output = {"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}
    print(json.dumps(output, ensure_ascii=False))
