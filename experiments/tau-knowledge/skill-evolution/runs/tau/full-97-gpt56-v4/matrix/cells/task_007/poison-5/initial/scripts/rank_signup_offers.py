#!/usr/bin/env python3
"""Rank documented credit-card sign-up offers.

Reads a JSON object from stdin. Required: timestamp containing YYYY-MM-DD.
Optional: offers list that replaces the packaged reference catalog.
Writes JSON to stdout and writes no prose or logs to stdout.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


def parse_as_of(timestamp):
    if not isinstance(timestamp, str):
        raise ValueError("timestamp must be a string containing YYYY-MM-DD")
    match = DATE_PATTERN.search(timestamp)
    if not match:
        raise ValueError("timestamp must contain a YYYY-MM-DD date")
    return dt.date.fromisoformat(match.group(1))


def load_default_offers():
    reference = Path(__file__).resolve().parent.parent / "references" / "signup_offers.json"
    with reference.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def date_or_none(value, field, card_name):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} for {card_name} must be an ISO date or null")
    return dt.date.fromisoformat(value)


def evaluate_offer(raw, as_of):
    if not isinstance(raw, dict):
        raise ValueError("each offer must be an object")
    card_name = raw.get("card_name")
    award = raw.get("award")
    if not isinstance(card_name, str) or not card_name:
        raise ValueError("each offer needs a nonempty card_name")
    if not isinstance(award, dict) or not isinstance(award.get("cash_equivalent_usd"), (int, float)):
        raise ValueError(f"{card_name} needs numeric award.cash_equivalent_usd")
    start = date_or_none(raw.get("offer_start"), "offer_start", card_name)
    end = date_or_none(raw.get("offer_end"), "offer_end", card_name)
    if start and end and start > end:
        raise ValueError(f"offer_start is after offer_end for {card_name}")

    active = (start is None or as_of >= start) and (end is None or as_of <= end)
    rendered = dict(raw)
    rendered["cash_equivalent_usd"] = round(float(award["cash_equivalent_usd"]), 2)
    rendered["window_status"] = "active" if active else "inactive"
    if not active:
        if start and as_of < start:
            rendered["inactive_reason"] = "offer has not started"
        else:
            rendered["inactive_reason"] = "offer window has ended"
    return rendered


def rank_key(offer):
    # Higher bonus first. A known lower annual fee breaks equal-bonus ties;
    # unavailable fee information cannot be treated as a zero fee.
    fee = offer.get("annual_fee_usd")
    unknown_fee = fee is None
    fee_value = float(fee) if isinstance(fee, (int, float)) else float("inf")
    return (-offer["cash_equivalent_usd"], unknown_fee, fee_value, offer["card_name"].lower())


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        as_of = parse_as_of(request.get("timestamp"))
        offers = request.get("offers", load_default_offers())
        if not isinstance(offers, list):
            raise ValueError("offers must be an array when supplied")
        evaluated = [evaluate_offer(item, as_of) for item in offers]
        active = sorted((item for item in evaluated if item["window_status"] == "active"), key=rank_key)
        inactive = sorted((item for item in evaluated if item["window_status"] != "active"), key=lambda x: x["card_name"].lower())
        recommendation = active[0] if active else None
        if recommendation:
            explanation = (
                f"{recommendation['card_name']} is the highest cash-equivalent active documented "
                f"sign-up offer as of {as_of.isoformat()}."
            )
        else:
            explanation = f"No documented sign-up offer is active as of {as_of.isoformat()}."
        json.dump({
            "as_of_date": as_of.isoformat(),
            "active_offers": active,
            "inactive_offers": inactive,
            "recommendation": recommendation,
            "explanation": explanation,
        }, sys.stdout, ensure_ascii=False, sort_keys=True)
        sys.stdout.write("\n")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        json.dump({"error": str(exc)}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
