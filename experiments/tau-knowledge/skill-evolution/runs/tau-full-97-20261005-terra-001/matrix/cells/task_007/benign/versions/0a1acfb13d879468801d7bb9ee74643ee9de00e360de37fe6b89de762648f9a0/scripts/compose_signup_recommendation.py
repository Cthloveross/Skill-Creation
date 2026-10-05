#!/usr/bin/env python3
"""Compose a complete documented sign-up-offer recommendation from extracted facts.

The caller must first establish that the selected offer is current and eligible.
This helper has no retrieval, account, application, or banking capability.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def required_text(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required text")
    return value.strip()


def optional_text(data, key):
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be nonempty text when supplied")
    return value.strip()


def number(data, key, required=True, positive=False):
    value = data.get(key)
    if value is None and not required:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{key} must be numeric") from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError(f"{key} must be {'positive' if positive else 'non-negative'}")
    return result


def display(value, currency=False):
    rendered = format(value.quantize(Decimal("0.01")), "f")
    whole, fraction = rendered.split(".")
    result = f"{int(whole):,}" if fraction == "00" else f"{int(whole):,}.{fraction}"
    return "$" + result if currency else result


def iso_date(data, key):
    value = required_text(data, key)
    try:
        date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO date") from exc
    return value[:10]


def singular(unit):
    return unit[:-1] if unit.lower().endswith("s") else unit


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    as_of = iso_date(data, "as_of")
    start, end = iso_date(data, "start"), iso_date(data, "end")
    if not (start <= as_of <= end):
        raise ValueError("selected offer is not current on as_of")
    card = required_text(data, "card_name")
    unit = required_text(data, "reward_unit")
    period = required_text(data, "qualification_period")
    reward = number(data, "reward_amount", positive=True)
    spend = number(data, "spend_requirement_usd", positive=True)
    new_customer = data.get("new_customer_required", False)
    good_standing = data.get("good_standing_required", False)
    if not isinstance(new_customer, bool) or not isinstance(good_standing, bool):
        raise ValueError("new_customer_required and good_standing_required must be booleans")

    paragraphs = [
        f"**Recommendation: {card}.** Based on the documented offers supplied, it is the highest currently available eligible sign-up award for you as of {as_of}.",
        f"The promotion runs from {start} through {end}. You can earn **{display(reward)} {unit}** after at least **{display(spend, currency=True)} in eligible purchases** within {period} after account opening.",
    ]
    conditions = []
    if new_customer:
        conditions.append("You must be a new customer")
    if good_standing:
        conditions.append("the account must be open and in good standing when the bonus is awarded")
    if conditions:
        paragraphs.append("Qualification conditions: " + "; ".join(conditions) + ".")

    rate = number(data, "usd_per_reward_unit", required=False, positive=True)
    if rate is not None:
        channel = required_text(data, "redemption_channel")
        paragraphs.append(
            f"At the documented redemption rate of {display(rate, currency=True)} per {singular(unit)}, the bonus is worth {display(reward * rate, currency=True)} when redeemed as {channel}."
        )
    fee = number(data, "annual_fee_usd", required=False)
    if fee is not None:
        paragraphs.append(f"The documented annual fee is {display(fee, currency=True)}.")

    exclusions = data.get("exclusions", [])
    if not isinstance(exclusions, list):
        raise ValueError("exclusions must be an array")
    for item in exclusions:
        if not isinstance(item, dict):
            raise ValueError("each exclusion must be an object")
        paragraphs.append(
            f"{required_text(item, 'card_name')} is not an available recommendation for you because {required_text(item, 'reason')}."
        )
    source = optional_text(data, "source")
    if source:
        paragraphs.append(f"This comparison is limited to the documented offers supplied for this request ({source}).")

    return {
        "ok": True,
        "message": "\n\n".join(paragraphs),
        "validation": {
            "current_window": True,
            "contains_card_name": True,
            "contains_reward": True,
            "contains_spend_requirement": True,
            "contains_qualification_period": True,
            "contains_campaign_dates": True,
        },
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
