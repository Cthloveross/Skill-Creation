#!/usr/bin/env python3
"""Filter and rank structured credit-card promotions.

Reads one JSON object from stdin and writes one JSON object to stdout. The
schema is documented in SKILL.md. This helper makes no network calls and does
not read customer or account data.
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
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return number


def money_string(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def offer_status(offer, as_of):
    start = parse_date(offer.get("window_start"))
    end = parse_date(offer.get("window_end"))
    if start is None or end is None or start > end:
        return "date_unknown"
    if as_of < start:
        return "upcoming"
    if as_of > end:
        return "expired"
    return "active"


def is_signup_bonus(offer):
    return str(offer.get("offer_type", "")).strip().lower() == "signup_bonus"


def reward_assessment(offer):
    reward = offer.get("reward")
    if not isinstance(reward, dict):
        return None, "No reward data supplied."

    kind = str(reward.get("kind", "")).strip().lower()
    amount = decimal_value(reward.get("amount"))
    if amount is None:
        return None, "Reward amount is missing, negative, or not numeric."

    currency = str(reward.get("currency", "")).strip().upper()
    if kind in DIRECT_USD_KINDS:
        if currency != "USD":
            return None, "Direct monetary reward is not documented in USD."
        return amount, None

    if kind == "points":
        rate = decimal_value(reward.get("redemption_value_per_point"))
        if rate is None:
            return None, "Point redemption value is not documented; points are not ranked against USD."
        return amount * rate, None

    return None, "Reward type cannot be compared to USD."


def public_offer(offer, status, usd_equivalent=None, rank_basis=None, issue=None):
    reward = offer.get("reward") if isinstance(offer.get("reward"), dict) else None
    record = {
        "card": offer.get("card"),
        "offer_type": offer.get("offer_type"),
        "status": status,
        "window_start": offer.get("window_start"),
        "window_end": offer.get("window_end"),
        "qualifying_event": offer.get("qualifying_event"),
        "reward": reward,
        "qualification": offer.get("qualification"),
        "fulfillment": offer.get("fulfillment"),
        "details": offer.get("details"),
    }
    if usd_equivalent is not None:
        record["usd_equivalent"] = money_string(usd_equivalent)
    if rank_basis is not None:
        record["rank_basis"] = rank_basis
    if issue is not None:
        record["issue"] = issue
    return record


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["Top-level JSON must be an object."], "warnings": []}

    as_of = parse_date(payload.get("as_of"))
    if as_of is None:
        return {
            "ok": False,
            "errors": ["as_of must begin with a valid YYYY-MM-DD date."],
            "warnings": [],
        }

    offers = payload.get("offers")
    if not isinstance(offers, list):
        return {
            "ok": False,
            "as_of": as_of.isoformat(),
            "errors": ["offers must be an array."],
            "warnings": [],
        }

    warnings = []
    ranked = []
    active_other = []
    inactive = []

    for index, offer in enumerate(offers):
        label = "offer[{}]".format(index)
        if not isinstance(offer, dict):
            inactive.append({"index": index, "status": "invalid", "issue": "Offer must be an object."})
            continue
        if not isinstance(offer.get("card"), str) or not offer.get("card").strip():
            inactive.append(public_offer(offer, "invalid", issue="Missing card name."))
            continue
        if not isinstance(offer.get("offer_type"), str) or not offer.get("offer_type").strip():
            inactive.append(public_offer(offer, "invalid", issue="Missing offer_type."))
            continue

        status = offer_status(offer, as_of)
        if status != "active":
            inactive.append(public_offer(offer, status))
            continue

        if not is_signup_bonus(offer):
            active_other.append(public_offer(offer, status))
            continue

        usd_value, issue = reward_assessment(offer)
        if issue:
            warnings.append("{} ({}): {}".format(label, offer.get("card"), issue))
            ranked.append((False, Decimal("0"), public_offer(
                offer, status, rank_basis="not_comparable_to_usd", issue=issue
            )))
        else:
            ranked.append((True, usd_value, public_offer(
                offer, status, usd_equivalent=usd_value,
                rank_basis="documented_or_calculated_usd_equivalent"
            )))

    # Comparable USD bonuses first, highest value first. Python's stable sort
    # preserves source order for ties and for non-comparable offers.
    ranked.sort(key=lambda item: (0 if item[0] else 1, -item[1] if item[0] else Decimal("0")))

    return {
        "ok": True,
        "as_of": as_of.isoformat(),
        "ranked_active_signup_bonuses": [item[2] for item in ranked],
        "active_non_signup_offers": active_other,
        "inactive_or_unknown_offers": inactive,
        "warnings": warnings,
        "errors": [],
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit({"ok": False, "errors": ["Invalid JSON input: {}".format(exc.msg)], "warnings": []})
    except Exception as exc:
        emit({"ok": False, "errors": ["Unable to read input: {}".format(str(exc))], "warnings": []})
    else:
        try:
            emit(main(payload))
        except Exception as exc:
            emit({"ok": False, "errors": ["Unexpected processing error: {}".format(str(exc))], "warnings": []})
