#!/usr/bin/env python3
"""Classify a claimed promotion against caller-supplied documented offers.

Reads one JSON object from stdin and emits one JSON object to stdout. No files,
network access, or banking actions are used.
"""
import datetime as dt
import json
import sys


def as_date(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("date must be an ISO YYYY-MM-DD string or null")
    return dt.date.fromisoformat(value)


def amount(value, field):
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(field + " must be a nonnegative number or null")
    return value


def normalized(value):
    return value.strip().casefold() if isinstance(value, str) and value.strip() else None


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    flyer = payload.get("flyer")
    offers = payload.get("documented_offers")
    if not isinstance(flyer, dict) or not isinstance(offers, list):
        raise ValueError("flyer object and documented_offers array are required")

    current = as_date(payload.get("current_date"))
    required = ("bonus_amount", "spend_requirement", "period_months")
    for key in required:
        amount(flyer.get(key), "flyer." + key)

    identifiers = ("product", "promo_code", "expiration_date", "campaign_id")
    missing = [key for key in identifiers if flyer.get(key) in (None, "")]
    field_matches = []
    candidates = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        for key in required:
            amount(offer.get(key), "documented_offers." + key)
        matches = {
            "product": normalized(flyer.get("product")) == normalized(offer.get("product"))
            if normalized(flyer.get("product")) else False,
            "bonus_amount": flyer.get("bonus_amount") == offer.get("bonus_amount"),
            "spend_requirement": flyer.get("spend_requirement") == offer.get("spend_requirement"),
            "period_months": flyer.get("period_months") == offer.get("period_months"),
        }
        start, end = as_date(offer.get("start_date")), as_date(offer.get("end_date"))
        window_current = None if current is None or start is None or end is None else start <= current <= end
        field_matches.append({"product": offer.get("product"), "matches": matches, "window_current": window_current})
        if all(matches.values()) and (window_current is not False):
            candidates.append(offer.get("product"))

    demand = payload.get("customer_demands_unverified_offer") is True
    if candidates:
        disposition = "verified_match"
        next_step = "Verify required banking prerequisites before taking any application or account action."
    elif demand:
        disposition = "human_escalation"
        next_step = "Transfer for review; do not promise, apply, or credit the unverified offer."
    elif all(flyer.get(key) in (None, "") for key in identifiers):
        disposition = "needs_identifiers"
        next_step = "Request product or objective offer-identifying details before proceeding."
    else:
        disposition = "unverified_or_mismatch"
        next_step = "Explain the documented mismatch and do not attach the claim to an application."

    return {
        "disposition": disposition,
        "candidate_products": candidates,
        "missing_identifiers": missing,
        "documented_comparisons": field_matches,
        "safe_next_step": next_step,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
