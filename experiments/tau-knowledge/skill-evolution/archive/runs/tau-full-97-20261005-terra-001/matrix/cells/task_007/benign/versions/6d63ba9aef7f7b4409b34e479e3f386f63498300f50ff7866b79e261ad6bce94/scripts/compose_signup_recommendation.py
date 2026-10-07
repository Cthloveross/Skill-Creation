#!/usr/bin/env python3
"""Render verified customer-facing welcome-offer prose from JSON on stdin."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def required(data, key):
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


def iso(data, key):
    value = required(data, key)[:10]
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO date") from exc
    return value


def show(value, dollars=False):
    value = value.quantize(Decimal("0.01"))
    whole, fraction = format(value, "f").split(".")
    result = f"{int(whole):,}" + ("" if fraction == "00" else f".{fraction}")
    return "$" + result if dollars else result


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    as_of, start, end = iso(data, "as_of"), iso(data, "start"), iso(data, "end")
    if not start <= as_of <= end:
        raise ValueError("offer is not current on as_of")
    card = required(data, "card_name")
    unit = required(data, "reward_unit")
    reward = number(data, "reward_amount", positive=True)
    spend = number(data, "spend_requirement_usd", positive=True)
    period = required(data, "qualification_period")
    paragraphs = [
        f"**Recommendation: {card}.** Based on the documented offers supplied, it is the best currently available eligible sign-up award for you as of {as_of}.",
        f"Its promotion runs from {start} through {end}. Earn **{show(reward)} {unit}** after at least **{show(spend, True)} in eligible purchases** within {period} after account opening."
    ]
    conditions = []
    if data.get("new_customer_required") is True:
        conditions.append("You must be a new customer")
    if data.get("good_standing_required") is True:
        conditions.append("the account must be open and in good standing when the bonus is awarded")
    if conditions:
        paragraphs.append("Qualification conditions: " + "; ".join(conditions) + ".")
    rate = number(data, "usd_per_reward_unit", optional=True, positive=True)
    if rate is not None:
        channel = required(data, "redemption_channel")
        singular = unit[:-1] if unit.lower().endswith("s") else unit
        paragraphs.append(f"At the documented redemption rate of {show(rate, True)} per {singular}, the bonus equals {show(reward * rate, True)} when redeemed as {channel}.")
    fee = number(data, "annual_fee_usd", optional=True)
    if fee is not None:
        paragraphs.append(f"The documented annual fee is {show(fee, True)}.")
    exclusions = data.get("exclusions", [])
    if not isinstance(exclusions, list):
        raise ValueError("exclusions must be an array")
    for item in exclusions:
        if not isinstance(item, dict):
            raise ValueError("each exclusion must be an object")
        paragraphs.append(f"{required(item, 'card_name')} is not an available recommendation for you because {required(item, 'reason')}.")
    return {"ok": True, "message": "\n\n".join(paragraphs)}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
