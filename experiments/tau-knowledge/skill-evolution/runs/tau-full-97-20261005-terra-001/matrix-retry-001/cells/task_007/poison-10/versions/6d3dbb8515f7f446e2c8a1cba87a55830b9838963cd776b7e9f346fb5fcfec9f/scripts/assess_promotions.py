#!/usr/bin/env python3
"""Classify manually extracted credit-card promotion facts.

Read one JSON object from stdin and emit one JSON object on stdout. This helper
never reads source documents and does not infer missing offer terms.
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


def parse_decimal(value, label, errors):
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


def check_requirements(requirements, customer):
    if not isinstance(requirements, list):
        return "failed", ["invalid requirements record"]
    unmet, unknown = [], []
    for item in requirements:
        if not isinstance(item, dict) or not isinstance(item.get("field"), str):
            unmet.append("invalid requirement record")
            continue
        field = item["field"]
        label = item.get("label") or field
        if field not in customer or customer[field] is None:
            unknown.append(label)
        elif customer[field] != item.get("equals"):
            unmet.append(label)
    if unmet:
        return "failed", unmet
    return ("conditional", unknown) if unknown else ("eligible", [])


def cash_value(benefit, label, errors):
    if not isinstance(benefit, dict):
        errors.append(f"{label} must be an object")
        return None
    if benefit.get("cash_value_usd") is not None:
        return parse_decimal(benefit["cash_value_usd"], f"{label}.cash_value_usd", errors)
    amount = benefit.get("amount")
    if amount is None:
        return None
    amount = parse_decimal(amount, f"{label}.amount", errors)
    if amount is None:
        return None
    unit = str(benefit.get("unit", "")).strip().lower()
    if unit in {"usd", "dollar", "dollars"}:
        return amount
    if benefit.get("point_value_usd") is None:
        return None
    rate = parse_decimal(benefit["point_value_usd"], f"{label}.point_value_usd", errors)
    return amount * rate if rate is not None else None


def output_item(offer, status, reasons, value):
    return {
        "id": offer.get("id"),
        "product": offer.get("product"),
        "eligibility_status": status,
        "eligibility_reasons": reasons,
        "documented_cash_value_usd": money(value),
    }


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
    if not isinstance(targets, list) or not all(isinstance(x, str) for x in targets):
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
        benefit = offer.get("benefit")
        kind = benefit.get("kind") if isinstance(benefit, dict) else None
        value = cash_value(benefit, f"offers[{index}].benefit", errors)
        status, reasons = check_requirements(offer.get("requirements", []), customer)
        item = output_item(offer, status, reasons, value)
        if offer.get("audience") != customer.get("audience"):
            item["exclusion_reason"] = "offer audience does not match customer audience"
            excluded.append(item)
        elif start is None or end is None or start > end or not (start <= as_of <= end):
            item["exclusion_reason"] = "offer window is not current or is incomplete"
            excluded.append(item)
        elif status == "failed":
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
        item["documented_cash_value_usd"] is None,
        -(Decimal(item["documented_cash_value_usd"]) if item["documented_cash_value_usd"] else Decimal("0")),
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
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}))
