#!/usr/bin/env python3
"""Categorize and rank structured credit-card promotion records.

Reads one JSON object from stdin and writes one JSON object to stdout. No
network, customer, account, or filesystem data is accessed.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
DIRECT_USD_KINDS = {"statement_credit", "cash_back", "cash"}


def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def parse_date(value):
    if not isinstance(value, str):
        return None
    match = DATE_RE.match(value.strip())
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def decimal_value(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        converted = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return converted if converted.is_finite() and converted >= 0 else None


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def status_for(offer, as_of):
    start = parse_date(offer.get("window_start"))
    end = parse_date(offer.get("window_end"))
    if start is None or end is None or start > end:
        return "date_unknown"
    if as_of < start:
        return "upcoming"
    if as_of > end:
        return "expired"
    return "active"


def assessed_usd(offer):
    reward = offer.get("reward")
    if not isinstance(reward, dict):
        return None, "No reward data supplied."
    amount = decimal_value(reward.get("amount"))
    kind = str(reward.get("kind", "")).strip().lower()
    if amount is None:
        return None, "Reward amount is missing, negative, or not numeric."
    if kind in DIRECT_USD_KINDS:
        if str(reward.get("currency", "")).strip().upper() != "USD":
            return None, "Direct monetary reward is not documented in USD."
        return amount, None
    if kind == "points":
        rate = decimal_value(reward.get("redemption_value_per_point"))
        if rate is None:
            return None, "Point redemption value is not documented; points are not ranked against USD."
        return amount * rate, None
    return None, "Reward type cannot be compared to USD."


def public_record(offer, status, issue=None, usd=None):
    record = {
        "card": offer.get("card"),
        "offer_type": offer.get("offer_type"),
        "status": status,
        "window_start": offer.get("window_start"),
        "window_end": offer.get("window_end"),
        "qualifying_event": offer.get("qualifying_event"),
        "reward": offer.get("reward"),
        "qualification": offer.get("qualification"),
        "annual_fee": offer.get("annual_fee"),
        "supplemental_benefits": offer.get("supplemental_benefits"),
        "fulfillment": offer.get("fulfillment"),
        "details": offer.get("details"),
        "product_scope": offer.get("product_scope"),
    }
    if issue:
        record["issue"] = issue
    if usd is not None:
        record["usd_equivalent"] = money(usd)
        record["rank_basis"] = "documented_or_calculated_usd_equivalent"
    return record


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["Top-level JSON must be an object."], "warnings": []}
    as_of = parse_date(payload.get("as_of"))
    if as_of is None:
        return {"ok": False, "errors": ["as_of must begin with a valid YYYY-MM-DD date."], "warnings": []}
    offers = payload.get("offers")
    if not isinstance(offers, list):
        return {"ok": False, "as_of": as_of.isoformat(), "errors": ["offers must be an array."], "warnings": []}

    ranked = []
    non_signup = []
    inactive = []
    warnings = []
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            inactive.append({"index": index, "status": "invalid", "issue": "Offer must be an object."})
            continue
        if not isinstance(offer.get("card"), str) or not offer["card"].strip():
            inactive.append(public_record(offer, "invalid", "Missing card name."))
            continue
        if not isinstance(offer.get("offer_type"), str) or not offer["offer_type"].strip():
            inactive.append(public_record(offer, "invalid", "Missing offer_type."))
            continue
        status = status_for(offer, as_of)
        if status != "active":
            inactive.append(public_record(offer, status))
            continue
        if offer["offer_type"].strip().lower() != "signup_bonus":
            non_signup.append(public_record(offer, status))
            continue
        usd, issue = assessed_usd(offer)
        if issue:
            warnings.append("offer[{}] ({}): {}".format(index, offer["card"], issue))
            ranked.append((False, Decimal("0"), public_record(offer, status, issue=issue)))
        else:
            ranked.append((True, usd, public_record(offer, status, usd=usd)))

    ranked.sort(key=lambda row: (0 if row[0] else 1, -row[1] if row[0] else Decimal("0")))
    return {
        "ok": True,
        "as_of": as_of.isoformat(),
        "ranked_active_signup_bonuses": [row[2] for row in ranked],
        "active_non_signup_offers": non_signup,
        "inactive_or_unknown_offers": inactive,
        "warnings": warnings,
        "errors": [],
    }


if __name__ == "__main__":
    try:
        emit(main(json.load(sys.stdin)))
    except json.JSONDecodeError as exc:
        emit({"ok": False, "errors": ["Invalid JSON input: {}".format(exc.msg)], "warnings": []})
    except Exception as exc:
        emit({"ok": False, "errors": ["Unexpected processing error: {}".format(exc)], "warnings": []})
