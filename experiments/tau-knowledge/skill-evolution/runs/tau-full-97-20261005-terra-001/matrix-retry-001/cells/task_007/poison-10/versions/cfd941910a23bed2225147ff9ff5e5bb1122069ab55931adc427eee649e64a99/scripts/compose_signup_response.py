#!/usr/bin/env python3
"""Compose a complete customer-facing description of one current bonus offer.

All facts are supplied by the caller after extraction from current task evidence.
The helper formats and validates them; it does not discover or invent offers.
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
        errors.append(f"{label} must be decimal-compatible")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{label} must be a non-negative finite number")
        return None
    return result


def as_money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def as_number(value):
    if value == 0:
        return "0"
    return format(value.normalize(), "f").rstrip("0").rstrip(".")


def text_list(value, label, errors):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
        errors.append(f"{label} must be a list of nonempty text")
        return []
    return [x.strip() for x in value]


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["top-level input must be an object"]}
    errors = []
    as_of = parse_date(payload.get("as_of_date"), "as_of_date", errors)
    customer = payload.get("customer")
    offer = payload.get("offer")
    fee_requested = payload.get("include_annual_fee", False)
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
    if not isinstance(offer, dict):
        errors.append("offer must be an object")
    if not isinstance(fee_requested, bool):
        errors.append("include_annual_fee must be boolean")
    if errors:
        return {"ok": False, "errors": errors}

    product = offer.get("product")
    benefit = offer.get("benefit")
    spend = offer.get("spend_requirement")
    start = parse_date(offer.get("open_start"), "offer.open_start", errors)
    end = parse_date(offer.get("open_end"), "offer.open_end", errors)
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
    elif not (start <= as_of <= end):
        errors.append("offer must be current on as_of_date")

    kind = benefit.get("kind")
    unit = benefit.get("unit")
    if not isinstance(kind, str) or not kind.strip():
        errors.append("offer.benefit.kind must be nonempty text")
    if not isinstance(unit, str) or not unit.strip():
        errors.append("offer.benefit.unit must be nonempty text")
    amount = parse_decimal(benefit.get("amount"), "offer.benefit.amount", errors)
    spend_amount = parse_decimal(spend.get("amount_usd"), "offer.spend_requirement.amount_usd", errors)
    period = spend.get("period_text")
    if not isinstance(period, str) or not period.strip():
        errors.append("offer.spend_requirement.period_text must be nonempty text")
    requirements = text_list(offer.get("requirements", []), "offer.requirements", errors)
    exclusions = text_list(offer.get("exclusions", []), "offer.exclusions", errors)
    if errors:
        return {"ok": False, "errors": errors}

    fee = None
    if fee_requested:
        if offer.get("annual_fee_usd") is None:
            errors.append("a documented annual_fee_usd is required when include_annual_fee is true")
        else:
            fee = parse_decimal(offer.get("annual_fee_usd"), "offer.annual_fee_usd", errors)
    if errors:
        return {"ok": False, "errors": errors}

    display_kind = kind.strip().replace("_", " ")
    lines = [
        f"As of {as_of.isoformat()}, **{product.strip()}** is a current documented {display_kind} sign-up-bonus option matching your priority.",
        f"The offer applies to accounts opened from {start.isoformat()} through {end.isoformat()}. It offers **{as_number(amount)} {unit.strip()}** after **${as_money(spend_amount)}** in eligible purchases within **{period.strip()}**.",
    ]
    if customer.get("new_customer") is True:
        lines.append("You indicated that you are a new customer; the documented new-customer condition is therefore consistent with the information provided.")
    if requirements:
        lines.append("Documented conditions: " + "; ".join(requirements) + ".")
    if fee_requested:
        lines.append(f"The documented annual fee is **${as_money(fee)}**.")

    if kind.strip().lower() == "points":
        rate = parse_decimal(benefit.get("point_value_usd"), "offer.benefit.point_value_usd", errors)
        channels = text_list(benefit.get("redemption_methods"), "offer.benefit.redemption_methods", errors)
        if benefit.get("point_value_usd") is None:
            errors.append("points offers require an explicit point_value_usd")
        if not channels:
            errors.append("points offers require documented redemption_methods")
        if errors:
            return {"ok": False, "errors": errors}
        value = amount * rate
        channel_text = " or ".join(channels)
        lines.append(
            f"The documented redemption rate is **${as_number(rate)} per point**: "
            f"{as_number(amount)} points × ${as_number(rate)} = approximately **${as_money(value)}** "
            f"as a {channel_text}. This is not a ${as_number(amount)} cash bonus."
        )
    else:
        cash_raw = benefit.get("cash_value_usd")
        if cash_raw is not None:
            cash = parse_decimal(cash_raw, "offer.benefit.cash_value_usd", errors)
        elif unit.strip().upper() == "USD":
            cash = amount
        else:
            cash = None
        if errors:
            return {"ok": False, "errors": errors}
        if cash is not None:
            lines.append(f"The documented cash-equivalent bonus value is **${as_money(cash)}**.")

    if exclusions:
        lines.append("Spend-threshold exclusions or adjustments: " + "; ".join(exclusions) + ".")
    posting = offer.get("posting_timing")
    if isinstance(posting, str) and posting.strip():
        lines.append("Bonus timing: " + posting.strip())
    if customer.get("expected_eligible_spend_known") is False:
        lines.append(
            f"The key decision point is whether you expect to reach **${as_money(spend_amount)}** "
            f"of eligible spend in {period.strip()}. Estimate that eligible spend before applying."
        )
    return {"ok": True, "message": "\n\n".join(lines)}


if __name__ == "__main__":
    try:
        output = main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        output = {"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}
    print(json.dumps(output, ensure_ascii=False))
