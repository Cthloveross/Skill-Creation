#!/usr/bin/env python3
"""Render verified customer-facing welcome-offer prose from JSON on stdin."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def text(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required text")
    return value.strip()


def number(data, key, optional=False, positive=False):
    value = data.get(key)
    if value is None and optional:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be numeric")
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{key} must be numeric") from exc
    if not value.is_finite() or value < 0 or (positive and value == 0):
        raise ValueError(f"{key} has an invalid value")
    return value


def iso_date(data, key):
    value = text(data, key)[:10]
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO date") from exc
    return value


def display_number(value, dollars=False):
    value = value.quantize(Decimal("0.01"))
    whole, fraction = format(value, "f").split(".")
    result = f"{int(whole):,}" + ("" if fraction == "00" else f".{fraction}")
    return "$" + result if dollars else result


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    as_of = iso_date(data, "as_of")
    start = iso_date(data, "start")
    end = iso_date(data, "end")
    if not start <= as_of <= end:
        raise ValueError("offer is not current on as_of")

    card = text(data, "card_name")
    reward = number(data, "reward_amount", positive=True)
    unit = text(data, "reward_unit")
    spend = number(data, "spend_requirement_usd", positive=True)
    period = text(data, "qualification_period")

    paragraphs = [
        f"**Recommendation: {card}.** Based on the documented offers, it is the best currently available eligible sign-up award for you as of {as_of}.",
        f"The promotion is active from {start} through {end}. Earn **{display_number(reward)} {unit}** after at least **{display_number(spend, True)} in eligible purchases** within {period} after account opening.",
    ]

    conditions = []
    if data.get("new_customer_required") is True:
        conditions.append("you must be a new customer")
    if data.get("good_standing_required") is True:
        conditions.append("the account must be open and in good standing when the bonus is awarded")
    if conditions:
        paragraphs.append("Qualification conditions: " + "; ".join(conditions) + ".")

    redemption_rate = number(data, "usd_per_reward_unit", optional=True, positive=True)
    if redemption_rate is not None:
        channel = text(data, "redemption_channel")
        singular_unit = unit[:-1] if unit.lower().endswith("s") else unit
        dollar_value = reward * redemption_rate
        paragraphs.append(
            f"At the documented redemption rate of {display_number(redemption_rate, True)} per {singular_unit}, "
            f"the bonus equals {display_number(dollar_value, True)} when redeemed as {channel}."
        )

    annual_fee = number(data, "annual_fee_usd", optional=True)
    if annual_fee is not None:
        paragraphs.append(f"The documented annual fee is {display_number(annual_fee, True)}.")

    exclusions = data.get("exclusions", [])
    if not isinstance(exclusions, list):
        raise ValueError("exclusions must be an array")
    for exclusion in exclusions:
        if not isinstance(exclusion, dict):
            raise ValueError("each exclusion must be an object")
        paragraphs.append(
            f"{text(exclusion, 'card_name')} is not an available recommendation for you because {text(exclusion, 'reason')}."
        )

    return {"ok": True, "message": "\n\n".join(paragraphs)}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
