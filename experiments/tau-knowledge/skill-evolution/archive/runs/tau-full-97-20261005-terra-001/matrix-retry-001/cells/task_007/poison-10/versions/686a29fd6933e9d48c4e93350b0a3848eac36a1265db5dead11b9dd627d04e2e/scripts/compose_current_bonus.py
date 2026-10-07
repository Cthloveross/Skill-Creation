#!/usr/bin/env python3
"""Validate and compose a complete description of one current direct bonus offer."""
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


def number(value, label, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{label} must be a non-negative finite number")
        return None
    return result


def amount_text(value):
    result = format(value.normalize(), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def dollars(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def text_list(value, label, errors):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        errors.append(f"{label} must be a list of nonempty strings")
        return []
    return [item.strip() for item in value]


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["top-level input must be an object"]}
    errors = []
    as_of = parse_date(payload.get("as_of_date"), "as_of_date", errors)
    fee_requested = payload.get("include_annual_fee", False)
    spend_known = payload.get("expected_eligible_spend_known")
    offer = payload.get("offer")
    if not isinstance(fee_requested, bool):
        errors.append("include_annual_fee must be boolean")
    if not isinstance(spend_known, bool):
        errors.append("expected_eligible_spend_known must be boolean")
    if not isinstance(offer, dict):
        errors.append("offer must be an object")
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
    elif not start <= as_of <= end:
        errors.append("offer must be current on as_of_date")

    kind = benefit.get("kind")
    unit = benefit.get("unit")
    if not isinstance(kind, str) or not kind.strip():
        errors.append("offer.benefit.kind must be nonempty text")
    if not isinstance(unit, str) or not unit.strip():
        errors.append("offer.benefit.unit must be nonempty text")
    bonus = number(benefit.get("amount"), "offer.benefit.amount", errors)
    threshold = number(spend.get("amount_usd"), "offer.spend_requirement.amount_usd", errors)
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
            return {"ok": False, "errors": ["documented annual_fee_usd is required for a fee comparison"]}
        fee = number(offer.get("annual_fee_usd"), "offer.annual_fee_usd", errors)
    if errors:
        return {"ok": False, "errors": errors}

    lines = [
        f"As of {as_of.isoformat()}, **{product.strip()}** is a current documented {kind.strip().replace('_', ' ')} sign-up-bonus option.",
        f"Accounts must be opened from {start.isoformat()} through {end.isoformat()}. The bonus is **{amount_text(bonus)} {unit.strip()}** after **${dollars(threshold)}** in eligible purchases within **{period.strip()}**.",
    ]
    if requirements:
        lines.append("Documented eligibility conditions: " + "; ".join(requirements) + ".")
    if fee_requested:
        lines.append(f"The documented annual fee is **${dollars(fee)}**.")

    if kind.strip().lower() == "points":
        if benefit.get("point_value_usd") is None:
            return {"ok": False, "errors": ["points offer requires documented point_value_usd"]}
        rate = number(benefit.get("point_value_usd"), "offer.benefit.point_value_usd", errors)
        channels = text_list(benefit.get("redemption_methods"), "offer.benefit.redemption_methods", errors)
        if not channels:
            errors.append("points offer requires documented redemption_methods")
        if errors:
            return {"ok": False, "errors": errors}
        value = bonus * rate
        lines.append(
            f"The documented redemption rate is **${amount_text(rate)} per point**: "
            f"{amount_text(bonus)} points × ${amount_text(rate)} = approximately **${dollars(value)}** "
            f"when redeemed as " + " or ".join(channels) + ". This is not a cash bonus equal to the point count."
        )
    else:
        cash = benefit.get("cash_value_usd")
        if cash is not None:
            cash = number(cash, "offer.benefit.cash_value_usd", errors)
        elif unit.strip().upper() == "USD":
            cash = bonus
        else:
            cash = None
        if errors:
            return {"ok": False, "errors": errors}
        if cash is not None:
            lines.append(f"The documented cash-equivalent bonus value is **${dollars(cash)}**.")

    if exclusions:
        lines.append("Eligible-spend exclusions/adjustments: " + "; ".join(exclusions) + ".")
    posting = offer.get("posting_timing")
    if isinstance(posting, str) and posting.strip():
        lines.append("Bonus timing: " + posting.strip())
    if not spend_known:
        lines.append(
            f"The key decision point is whether you can reach **${dollars(threshold)}** of eligible spend in {period.strip()}; estimate that spend before applying."
        )
    return {"ok": True, "message": "\n\n".join(lines)}


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        result = {"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}
    print(json.dumps(result, ensure_ascii=False))
