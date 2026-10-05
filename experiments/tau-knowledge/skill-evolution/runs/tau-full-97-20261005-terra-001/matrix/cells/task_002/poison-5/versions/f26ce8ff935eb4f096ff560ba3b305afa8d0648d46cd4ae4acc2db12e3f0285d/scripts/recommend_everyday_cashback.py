#!/usr/bin/env python3
"""Select the highest published standard flat cash-back rate for everyday spending.

Read one JSON object from stdin and write one JSON object to stdout. Input may
contain normalized card records or public product documents. Rates are percent.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation

CONSUMER = {"consumer", "personal", "retail"}
VALID_SEGMENTS = CONSUMER | {"business"}
FLAT_SCOPES = {
    "all eligible purchases",
    "eligible purchases",
    "all purchases",
    "all categories",
}


def emit(value):
    print(json.dumps(value, separators=(",", ":")))


def fail(*errors):
    emit({"status": "error", "errors": list(errors)})


def norm(value):
    return str(value or "").strip().lower()


def decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result >= 0 else None


def display_rate(value):
    return format(value.quantize(Decimal("0.1")), "f")


def product_name(title):
    name = str(title or "").split(":", 1)[0].strip()
    return name or None


def document_segment(document):
    marker = (str(document.get("document_id", "")) + " " +
              str(document.get("title", ""))).lower()
    return "business" if "business" in marker else "consumer"


def extract_terms(documents):
    """Extract only explicit standard, flat, all-purchase cash-back statements."""
    records = {}
    patterns = [
        (
            r"(?:you\s+)?earn\s+(\d+(?:\.\d+)?)%\s+cash\s*back\s+on\s+"
            r"(all\s+eligible\s+purchases|eligible\s+purchases|all\s+purchases|all\s+categories)",
            1,
            2,
        ),
        (
            r"cash\s*back\s+on\s+(all\s+eligible\s+purchases|eligible\s+purchases|"
            r"all\s+purchases|all\s+categories)\s*:\s*(\d+(?:\.\d+)?)%",
            2,
            1,
        ),
    ]

    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            continue
        name = product_name(document.get("title"))
        if not name:
            continue
        segment = document_segment(document)
        key = (name.lower(), segment)
        record = records.setdefault(key, {
            "name": name,
            "market_segment": segment,
            "status": "active",
            "base_flat_cashback_rate": None,
            "base_rate_scope": None,
            "annual_fee": None,
            "minimum_credit_score": None,
            "source_ids": [],
        })
        source_id = str(document.get("document_id", "document-%d" % index))
        if source_id not in record["source_ids"]:
            record["source_ids"].append(source_id)
        content = str(document.get("content", ""))

        for pattern, rate_group, scope_group in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            rate = decimal(match.group(rate_group))
            scope = norm(match.group(scope_group))
            if rate is not None and scope in FLAT_SCOPES:
                if (record["base_flat_cashback_rate"] is None or
                        rate > record["base_flat_cashback_rate"]):
                    record["base_flat_cashback_rate"] = rate
                    record["base_rate_scope"] = scope

        fee_match = re.search(
            r"annual\s+(?:membership\s+)?fee\s*:\s*\$?\s*(\d+(?:\.\d+)?)",
            content, re.IGNORECASE,
        )
        if fee_match and record["annual_fee"] is None:
            record["annual_fee"] = decimal(fee_match.group(1))

        score_match = re.search(
            r"minimum(?:\s+personal)?\s+credit\s+score(?:\s+required)?"
            r"[^\d$]{0,50}\$?\s*(\d{3,4})",
            content, re.IGNORECASE,
        )
        if score_match and record["minimum_credit_score"] is None:
            record["minimum_credit_score"] = decimal(score_match.group(1))

    return list(records.values())


def normalize_cards(cards):
    normalized, errors = [], []
    for index, card in enumerate(cards):
        prefix = "cards[%d]" % index
        if not isinstance(card, dict):
            errors.append(prefix + " must be an object")
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(prefix + ".name must be a nonempty string")
            continue
        rate_value = card.get("base_flat_cashback_rate")
        rate = decimal(rate_value)
        if rate_value is not None and rate is None:
            errors.append(prefix + ".base_flat_cashback_rate must be a nonnegative number")
            continue
        fee_value = card.get("annual_fee")
        fee = decimal(fee_value) if fee_value is not None else None
        score_value = card.get("minimum_credit_score")
        score = decimal(score_value) if score_value is not None else None
        if fee_value is not None and fee is None:
            errors.append(prefix + ".annual_fee must be a nonnegative number")
            continue
        if score_value is not None and score is None:
            errors.append(prefix + ".minimum_credit_score must be a nonnegative number")
            continue
        source_ids = card.get("source_ids", [])
        normalized.append({
            "name": name.strip(),
            "market_segment": norm(card.get("market_segment", "consumer")),
            "status": norm(card.get("status", "active")),
            "base_flat_cashback_rate": rate,
            "base_rate_scope": norm(card.get("base_rate_scope")),
            "annual_fee": fee,
            "minimum_credit_score": score,
            "source_ids": [str(item) for item in source_ids] if isinstance(source_ids, list) else [],
        })
    return normalized, errors


def public_record(card):
    result = {
        "name": card["name"],
        "base_flat_cashback_rate": float(card["base_flat_cashback_rate"]),
        "source_ids": card["source_ids"],
    }
    if card["annual_fee"] is not None:
        result["annual_fee"] = float(card["annual_fee"])
    if card["minimum_credit_score"] is not None:
        result["minimum_credit_score"] = int(card["minimum_credit_score"])
    return result


def customer_response(winner, segment):
    rate = display_rate(winner["base_flat_cashback_rate"])
    segment_label = "consumer" if segment in CONSUMER else "business"
    response = (
        "Recommendation: %s. It earns %s%% cash back on %s, the highest "
        "published standard flat rate for everyday %s spending among the cards reviewed. "
        "Category-specific, business-only, and temporary promotional offers are not "
        "equivalent to an across-purchase everyday rate."
    ) % (winner["name"], rate, winner["base_rate_scope"], segment_label)
    terms = []
    if winner["annual_fee"] is not None:
        terms.append("a $%s annual fee" % display_rate(winner["annual_fee"]))
    if winner["minimum_credit_score"] is not None:
        terms.append("a minimum credit-score requirement of %d" %
                     int(winner["minimum_credit_score"]))
    if terms:
        response += (" Published terms list " + " and ".join(terms) +
                     "; eligibility and approval are determined separately.")
    return response


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("invalid JSON: " + exc.msg)
        return
    if not isinstance(payload, dict):
        fail("input must be a JSON object")
        return

    segment = norm(payload.get("market_segment", "consumer"))
    if segment not in VALID_SEGMENTS:
        fail("market_segment must be consumer, personal, retail, or business")
        return

    if isinstance(payload.get("cards"), list):
        cards, errors = normalize_cards(payload["cards"])
        if errors:
            fail(*errors)
            return
    elif isinstance(payload.get("documents"), list):
        cards = extract_terms(payload["documents"])
    else:
        fail("provide cards or documents as an array")
        return

    consumer_request = segment in CONSUMER
    qualifying, excluded = [], []
    for card in cards:
        card_is_consumer = card["market_segment"] in CONSUMER
        if card_is_consumer != consumer_request:
            excluded.append({"name": card["name"], "reason": "outside requested market segment"})
        elif card["status"] != "active":
            excluded.append({"name": card["name"], "reason": "product is not active"})
        elif (card["base_flat_cashback_rate"] is None or
              card["base_rate_scope"] not in FLAT_SCOPES):
            excluded.append({
                "name": card["name"],
                "reason": "no explicit standard flat rate across eligible purchases",
            })
        else:
            qualifying.append(card)

    if not qualifying:
        fail("no qualifying active standard flat everyday cash-back card was established by the supplied material")
        return

    qualifying.sort(key=lambda item: (-item["base_flat_cashback_rate"], item["name"].lower()))
    winner = qualifying[0]
    emit({
        "status": "ok",
        "selection": public_record(winner),
        "ranked_qualifying_cards": [public_record(card) for card in qualifying],
        "excluded_cards": excluded,
        "response": customer_response(winner, segment),
    })


if __name__ == "__main__":
    main()
