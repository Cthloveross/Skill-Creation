#!/usr/bin/env python3
"""Classify manually extracted credit-card promotion facts.

Reads one JSON object from stdin and writes one JSON object to stdout. It does
not read source documents or infer facts that were omitted from its input.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def date_value(value, label, errors):
    if not isinstance(value, str):
        errors.append(f"{label} must be YYYY-MM-DD")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} must be YYYY-MM-DD")
        return None


def decimal_value(value, label, errors):
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
    if unknown:
        return "conditional", unknown
    return "eligible", []


def cash_value(benefit, label, errors):
    if not isinstance(benefit, dict):
        errors.append(f"{label} must be an object")
        return None
    if benefit.get("cash_value_usd") is not None:
        return decimal_value(benefit["cash_value_usd"], f"{label}.cash_value_usd", errors)
    if benefit.get("amount") is None:
        return None
    amount = decimal_value(benefit["amount"], f"{label}.amount", errors)
    if amount is None:
        return None
    kind = str(benefit.get("kind", "")).lower()
    unit = str(benefit.get("unit", "")).lower()
    if kind in {"cash_back", "statement_credit"} or unit in {"usd", "dollar", "dollars"}:
        return amount
    if benefit.get("point_value_usd") is None:
        return None
    rate = decimal_value(benefit["point_value_usd"], f"{label}.point_value_usd", errors)
    return amount * rate if rate is not None else None


def output_item(offer, state, reasons, value):
    benefit = offer.get("benefit") if isinstance(offer.get("benefit"), dict) else {}
    return {
        "id": offer.get("id"),
        "product": offer.get("product"),
        "benefit_kind": benefit.get("kind"),
        "eligibility_status": state,
        "eligibility_reasons": reasons,
        "documented_cash_value_usd": money(value),
        "annual_fee_usd": money(decimal_value(offer["annual_fee_usd"], "annual_fee_usd", []) if offer.get("annual_fee_usd") is not None else None),
        "redemption_channel": benefit.get("redemption_channel"),
    }


def assess(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["top-level input must be an object"]}
    errors = []
    as_of = date_value(payload.get("as_of_date"), "as_of_date", errors)
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

    candidates, active_other, excluded = [], [], []
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            errors.append(f"offers[{index}] must be an object")
            continue
        start = date_value(offer.get("open_start"), f"offers[{index}].open_start", errors)
        end = date_value(offer.get("open_end"), f"offers[{index}].open_end", errors)
        benefit = offer.get("benefit")
        kind = benefit.get("kind") if isinstance(benefit, dict) else None
        value = cash_value(benefit, f"offers[{index}].benefit", errors)
        state, reasons = check_requirements(offer.get("requirements", []), customer)
        item = output_item(offer, state, reasons, value)
        if offer.get("audience") != customer.get("audience"):
            item["exclusion_reason"] = "offer audience does not match customer audience"
            excluded.append(item)
        elif start is None or end is None or start > end or not (start <= as_of <= end):
            item["exclusion_reason"] = "offer window is not current or is incomplete"
            excluded.append(item)
        elif state == "failed":
            item["exclusion_reason"] = "a known eligibility condition is not met"
            excluded.append(item)
        elif kind not in targets:
            active_other.append(item)
        else:
            candidates.append(item)
    if errors:
        return {"ok": False, "errors": errors}

    rank = {"eligible": 0, "conditional": 1}
    candidates.sort(key=lambda x: (
        rank.get(x["eligibility_status"], 2),
        x["documented_cash_value_usd"] is None,
        -(Decimal(x["documented_cash_value_usd"]) if x["documented_cash_value_usd"] else Decimal("0")),
        str(x.get("product") or ""),
    ))
    return {"ok": True, "ranked_candidates": candidates,
            "active_nontargeted": active_other, "excluded": excluded}


if __name__ == "__main__":
    try:
        print(json.dumps(assess(json.load(sys.stdin)), ensure_ascii=False))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}))
