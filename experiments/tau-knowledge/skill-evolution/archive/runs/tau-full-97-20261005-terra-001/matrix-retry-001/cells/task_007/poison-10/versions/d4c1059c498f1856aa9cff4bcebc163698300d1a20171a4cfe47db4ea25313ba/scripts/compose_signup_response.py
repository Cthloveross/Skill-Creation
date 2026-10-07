#!/usr/bin/env python3
"""Compose a complete, evidence-bound sign-up-bonus explanation.

Reads one JSON object from stdin and emits one JSON object. All offer facts must
be extracted from current supplied evidence by the caller; this program only
formats and calculates explicitly supplied values.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def decimal(value, label, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be decimal-compatible")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{label} must be a non-negative finite number")
        return None
    return result


def iso(value, label, errors):
    if not isinstance(value, str):
        errors.append(f"{label} must be YYYY-MM-DD")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} must be YYYY-MM-DD")
        return None


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def number(value):
    return format(value.normalize(), "f").rstrip("0").rstrip(".") if value != 0 else "0"


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["top-level input must be an object"]}
    errors = []
    as_of = iso(payload.get("as_of_date"), "as_of_date", errors)
    customer = payload.get("customer", {})
    offer = payload.get("offer")
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
    if not isinstance(offer, dict):
        errors.append("offer must be an object")
    if errors:
        return {"ok": False, "errors": errors}

    product = offer.get("product")
    benefit = offer.get("benefit")
    spend = offer.get("spend_requirement")
    start = iso(offer.get("open_start"), "offer.open_start", errors)
    end = iso(offer.get("open_end"), "offer.open_end", errors)
    if not isinstance(product, str) or not product.strip():
        errors.append("offer.product must be nonempty text")
    if not isinstance(benefit, dict):
        errors.append("offer.benefit must be an object")
    if not isinstance(spend, dict):
        errors.append("offer.spend_requirement must be an object")
    if errors:
        return {"ok": False, "errors": errors}
    if start > end:
        errors.append("offer window start must not be after end")
    if not (start <= as_of <= end):
        errors.append("composer accepts only an offer current on as_of_date")

    kind, unit = benefit.get("kind"), benefit.get("unit")
    amount = decimal(benefit.get("amount"), "offer.benefit.amount", errors)
    spend_amount = decimal(spend.get("amount_usd"), "offer.spend_requirement.amount_usd", errors)
    period = spend.get("period_text")
    if not isinstance(kind, str) or not kind:
        errors.append("offer.benefit.kind must be nonempty text")
    if not isinstance(unit, str) or not unit:
        errors.append("offer.benefit.unit must be nonempty text")
    if not isinstance(period, str) or not period.strip():
        errors.append("offer.spend_requirement.period_text must be nonempty text")
    requirements = offer.get("requirements", [])
    if not isinstance(requirements, list) or not all(isinstance(x, str) and x.strip() for x in requirements):
        errors.append("offer.requirements must be a list of nonempty text")
    exclusions = offer.get("exclusions", [])
    if not isinstance(exclusions, list) or not all(isinstance(x, str) and x.strip() for x in exclusions):
        errors.append("offer.exclusions must be a list of nonempty text")
    if errors:
        return {"ok": False, "errors": errors}

    lines = [
        f"Based on the supplied promotion terms and the observed date ({as_of.isoformat()}), **{product.strip()}** is the current documented {kind.replace('_', ' ')} sign-up option that matches your priority.",
        f"Its offer window is {start.isoformat()} through {end.isoformat()}. You can earn **{number(amount)} {unit}** after **${money(spend_amount)}** in eligible purchases within **{period.strip()}**.",
    ]
    if requirements:
        lines.append("Documented conditions: " + "; ".join(requirements) + ".")

    rate = benefit.get("point_value_usd")
    if rate is not None:
        point_rate = decimal(rate, "offer.benefit.point_value_usd", errors)
        if point_rate is not None:
            value = amount * point_rate
            channels = benefit.get("redemption_methods", [])
            if not isinstance(channels, list) or not all(isinstance(x, str) and x.strip() for x in channels):
                errors.append("offer.benefit.redemption_methods must be a list of nonempty text")
            else:
                channel_text = " or ".join(channels)
                suffix = f" as a {channel_text}" if channel_text else ""
                lines.append(f"At **${number(point_rate)} per point**, {number(amount)} {unit} × ${number(point_rate)} = approximately **${money(value)}** in redemption value{suffix}. This is not a ${number(amount)} cash bonus.")
    elif unit.upper() == "USD" or benefit.get("cash_value_usd") is not None:
        value = decimal(benefit.get("cash_value_usd", amount), "offer.benefit.cash_value_usd", errors)
        if value is not None:
            lines.append(f"The documented cash-equivalent bonus value is **${money(value)}**.")

    if exclusions:
        lines.append("For the spend threshold, note: " + "; ".join(exclusions) + ".")
    posting = offer.get("posting_timing")
    if isinstance(posting, str) and posting.strip():
        lines.append("Bonus timing: " + posting.strip())
    if customer.get("expected_eligible_spend_known") is False:
        lines.append(f"The key decision point is whether you expect to reach **${money(spend_amount)}** of eligible spend in {period.strip()}. If you are unsure, estimate that eligible spend before applying.")
    alternatives = payload.get("alternatives", [])
    if not isinstance(alternatives, list):
        errors.append("alternatives must be a list")
    else:
        notes = []
        for item in alternatives:
            if not isinstance(item, dict):
                errors.append("each alternative must be an object")
                continue
            name, status, description = item.get("product"), item.get("status"), item.get("description")
            if all(isinstance(x, str) and x.strip() for x in (name, status, description)):
                notes.append(f"{name.strip()} is {status.strip()}: {description.strip()}")
        if notes:
            lines.append("For comparison, " + " ".join(notes))
    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True, "message": "\n\n".join(lines)}


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        result = {"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}
    print(json.dumps(result, ensure_ascii=False))
