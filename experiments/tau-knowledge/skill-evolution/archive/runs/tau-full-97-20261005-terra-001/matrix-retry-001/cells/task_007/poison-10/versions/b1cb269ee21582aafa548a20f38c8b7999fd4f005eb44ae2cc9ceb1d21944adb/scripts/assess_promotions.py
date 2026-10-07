#!/usr/bin/env python3
"""Filter and rank evidence-extracted credit-card promotion records.

Input: one JSON object on stdin following the schema in SKILL.md.
Output: one JSON object on stdout. This utility deliberately does not discover
facts, parse source documents, infer eligibility, or perform account actions.
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


def parse_nonnegative_decimal(value, label, errors):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not number.is_finite() or number < 0:
        errors.append(f"{label} must be a non-negative finite number")
        return None
    return number


def money(value):
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def evaluate_requirements(offer, customer):
    requirements = offer.get("requirements", [])
    if not isinstance(requirements, list):
        return "failed", ["invalid requirements record"]

    failed = []
    unknown = []
    for requirement in requirements:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("field"), str):
            failed.append("invalid requirement record")
            continue
        field = requirement["field"]
        label = requirement.get("label")
        if not isinstance(label, str) or not label.strip():
            label = field
        if field not in customer or customer[field] is None:
            unknown.append(label)
        elif customer[field] != requirement.get("equals"):
            failed.append(label)

    if failed:
        return "failed", failed
    if unknown:
        return "conditional", unknown
    return "eligible", []


def benefit_value(benefit, label, errors):
    """Return documented cash value, or None when no supported conversion exists."""
    if not isinstance(benefit, dict):
        errors.append(f"{label} must be an object")
        return None

    if benefit.get("cash_value_usd") is not None:
        return parse_nonnegative_decimal(
            benefit["cash_value_usd"], f"{label}.cash_value_usd", errors
        )

    amount = benefit.get("amount")
    if amount is None:
        return None
    amount = parse_nonnegative_decimal(amount, f"{label}.amount", errors)
    if amount is None:
        return None

    unit = str(benefit.get("unit", "")).strip().lower()
    if unit in {"usd", "dollar", "dollars"}:
        return amount

    if benefit.get("point_value_usd") is None:
        return None
    rate = parse_nonnegative_decimal(
        benefit["point_value_usd"], f"{label}.point_value_usd", errors
    )
    return None if rate is None else amount * rate


def record(offer, value, status, reasons):
    return {
        "id": offer.get("id"),
        "product": offer.get("product"),
        "offer": offer,
        "cash_value_usd": money(value),
        "eligibility_status": status,
        "eligibility_reasons": reasons,
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
    if not isinstance(targets, list) or not all(isinstance(item, str) for item in targets):
        errors.append("target_benefit_kinds must be a list of strings")
    if not isinstance(offers, list):
        errors.append("offers must be a list")
    if errors:
        return {"ok": False, "errors": errors}

    candidates = []
    nontargeted = []
    excluded = []

    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            errors.append(f"offers[{index}] must be an object")
            continue

        start = parse_date(offer.get("open_start"), f"offers[{index}].open_start", errors)
        end = parse_date(offer.get("open_end"), f"offers[{index}].open_end", errors)
        if start is not None and end is not None and start > end:
            errors.append(f"offers[{index}] has a reversed offer window")

        benefit = offer.get("benefit")
        kind = benefit.get("kind") if isinstance(benefit, dict) else None
        value = benefit_value(benefit, f"offers[{index}].benefit", errors)
        status, reasons = evaluate_requirements(offer, customer)
        item = record(offer, value, status, reasons)

        offer_audience = offer.get("audience")
        customer_audience = customer.get("audience")
        if customer_audience is not None and offer_audience != customer_audience:
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

    eligibility_order = {"eligible": 0, "conditional": 1}

    def rank_key(item):
        value = item["cash_value_usd"]
        decimal_value = Decimal(value) if value is not None else Decimal("0")
        return (
            eligibility_order.get(item["eligibility_status"], 2),
            value is None,
            -decimal_value,
            str(item.get("product") or ""),
        )

    candidates.sort(key=rank_key)
    return {
        "ok": True,
        "ranked_candidates": candidates,
        "active_nontargeted": nontargeted,
        "excluded": excluded,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        output = main(payload)
    except json.JSONDecodeError as exc:
        output = {"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}
    print(json.dumps(output, ensure_ascii=False))
