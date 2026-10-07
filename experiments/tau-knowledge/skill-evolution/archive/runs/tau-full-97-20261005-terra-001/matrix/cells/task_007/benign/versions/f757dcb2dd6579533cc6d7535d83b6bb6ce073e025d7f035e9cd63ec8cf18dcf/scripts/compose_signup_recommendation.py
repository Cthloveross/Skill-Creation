#!/usr/bin/env python3
"""Compose a complete documented sign-up-offer recommendation from extracted facts.

The program has no retrieval or banking capability. It never selects an offer;
the caller must first establish that the supplied selected offer is current and
eligible from the source documents.
"""
import json
import sys
from decimal import Decimal, InvalidOperation
from datetime import date


def text(data, key, required=True):
    value = data.get(key)
    if required and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{key} is required text")
    if not required and value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
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
    whole = f"{int(whole):,}"
    rendered = whole if fraction == "00" else f"{whole}.{fraction}"
    return "$" + rendered if currency else rendered


def check_date(value, field):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{field} must be an ISO date")
    try:
        date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc
    return value[:10]


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    as_of = check_date(data.get("as_of"), "as_of")
    start, end = check_date(data.get("start"), "start"), check_date(data.get("end"), "end")
    if not (start <= as_of <= end):
        raise ValueError("selected offer is not current on as_of")
    card = text(data, "card_name")
    unit = text(data, "reward_unit")
    period = text(data, "qualification_period")
    reward = number(data, "reward_amount", positive=True)
    spend = number(data, "spend_requirement_usd", positive=True)
    new_customer = data.get("new_customer_required", False)
    good_standing = data.get("good_standing_required", False)
    if not isinstance(new_customer, bool) or not isinstance(good_standing, bool):
        raise ValueError("new_customer_required and good_standing_required must be booleans")

    message = [
        f"**Recommendation: {card}.** Based on the documented offers supplied, it is the highest currently available eligible sign-up award for you as of {as_of}.",
        f"The promotion runs from {start} through {end}. You can earn **{display(reward)} {unit}** after at least **{display(spend, currency=True)} in eligible purchases** within {period} after account opening.",
    ]
    qualifications = []
    if new_customer:
        qualifications.append("You must be a new customer")
    if good_standing:
        qualifications.append("the account must be open and in good standing when the bonus is awarded")
    if qualifications:
        message.append("Qualification conditions: " + "; ".join(qualifications) + ".")

    rate = number(data, "usd_per_reward_unit", required=False, positive=True)
    if rate is not None:
        value = reward * rate
        channel = text(data, "redemption_channel")
        message.append(
            f"At the documented redemption rate of {display(rate, currency=True)} per {unit.rstrip('s') or unit}, "
            f"the bonus is worth {display(value, currency=True)} when redeemed as {channel}."
        )
    fee = number(data, "annual_fee_usd", required=False)
    if fee is not None:
        message.append(f"The documented annual fee is {display(fee, currency=True)}.")

    exclusions = data.get("exclusions", [])
    if not isinstance(exclusions, list):
        raise ValueError("exclusions must be an array")
    for item in exclusions:
        if not isinstance(item, dict):
            raise ValueError("each exclusion must be an object")
        excluded_card = text(item, "card_name")
        reason = text(item, "reason")
        message.append(f"{excluded_card} is not an available recommendation for you because {reason}.")
    source = text(data, "source", required=False)
    if source:
        message.append(f"This comparison is limited to the documented offers supplied for this request ({source}).")

    return {
        "ok": True,
        "message": "\n\n".join(message),
        "validation": {
            "current_window": True,
            "contains_reward": True,
            "contains_spend_requirement": True,
            "contains_qualification_period": True,
        },
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
