#!/usr/bin/env python3
"""Extract, rank, and describe standard flat everyday cash-back card offers.

Reads a JSON object from stdin. Accepts either normalized card records or public
product documents. Emits JSON only, so it can be composed by an execution agent.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation

CONSUMER_SEGMENTS = {"consumer", "personal", "retail"}
FLAT_SCOPES = {"all eligible purchases", "eligible purchases", "all purchases", "all categories"}


def norm(value):
    return str(value or "").strip().lower()


def decimal(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result >= 0 else None


def display_number(value):
    value = Decimal(value)
    return format(value.quantize(Decimal("0.1")), "f")


def fail(errors):
    print(json.dumps({"status": "error", "errors": errors}, separators=(",", ":")))


def segment_for_document(document):
    marker = " ".join([
        str(document.get("document_id", "")),
        str(document.get("title", "")),
    ]).lower()
    return "business" if "business" in marker else "consumer"


def card_name_from_title(title):
    name = str(title or "").split(":", 1)[0].strip()
    return name or None


def first_decimal(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return decimal(match.group(1)) if match else None


def extract_document_cards(documents):
    """Build candidate records only from explicit published-language matches."""
    grouped = {}
    flat_patterns = [
        r"(?:you\s+)?earn\s+(\d+(?:\.\d+)?)%\s+cash\s*back\s+on\s+(all\s+eligible\s+purchases|eligible\s+purchases|all\s+purchases|all\s+categories)",
        r"cash\s*back\s+on\s+(all\s+eligible\s+purchases|eligible\s+purchases|all\s+purchases|all\s+categories)\s*:\s*(\d+(?:\.\d+)?)%",
    ]

    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            continue
        title = str(document.get("title", ""))
        content = str(document.get("content", ""))
        name = card_name_from_title(title)
        if not name:
            continue
        segment = segment_for_document(document)
        key = (name.lower(), segment)
        record = grouped.setdefault(key, {
            "name": name,
            "market_segment": segment,
            "status": "active",
            "base_flat_cashback_rate": None,
            "base_rate_scope": None,
            "annual_fee": None,
            "minimum_credit_score": None,
            "source_ids": [],
        })
        source_id = document.get("document_id", "document-" + str(index))
        record["source_ids"].append(str(source_id))

        for pattern_index, pattern in enumerate(flat_patterns):
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            if pattern_index == 0:
                rate, scope = decimal(match.group(1)), norm(match.group(2))
            else:
                scope, rate = norm(match.group(1)), decimal(match.group(2))
            if rate is not None and scope in FLAT_SCOPES:
                prior = record["base_flat_cashback_rate"]
                if prior is None or rate > prior:
                    record["base_flat_cashback_rate"] = rate
                    record["base_rate_scope"] = scope

        fee = first_decimal(r"annual\s+fee\s*:\s*\$?\s*(\d+(?:\.\d+)?)", content)
        if fee is not None and record["annual_fee"] is None:
            record["annual_fee"] = fee
        score = first_decimal(r"minimum(?:\s+personal)?\s+credit\s+score(?:\s+required)?[^\d$]{0,40}\$?\s*(\d{3,4})", content)
        if score is not None and record["minimum_credit_score"] is None:
            record["minimum_credit_score"] = score

    return list(grouped.values())


def normalize_cards(cards, errors):
    normalized = []
    for index, card in enumerate(cards):
        prefix = "cards[%d]" % index
        if not isinstance(card, dict):
            errors.append(prefix + " must be an object")
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(prefix + ".name must be a nonempty string")
            continue
        rate = decimal(card.get("base_flat_cashback_rate"))
        fee = decimal(card.get("annual_fee")) if card.get("annual_fee") is not None else None
        score = decimal(card.get("minimum_credit_score")) if card.get("minimum_credit_score") is not None else None
        if card.get("base_flat_cashback_rate") is not None and rate is None:
            errors.append(prefix + ".base_flat_cashback_rate must be a nonnegative number")
            continue
        normalized.append({
            "name": name.strip(),
            "market_segment": norm(card.get("market_segment", "consumer")),
            "status": norm(card.get("status", "active")),
            "base_flat_cashback_rate": rate,
            "base_rate_scope": norm(card.get("base_rate_scope")),
            "annual_fee": fee,
            "minimum_credit_score": score,
            "source_ids": [str(x) for x in card.get("source_ids", [])] if isinstance(card.get("source_ids", []), list) else [],
        })
    return normalized


def serial(card):
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


def compose_response(winner):
    rate = display_number(winner["base_flat_cashback_rate"])
    response = (
        "Recommendation: %s. It earns %s%% cash back on all eligible purchases, "
        "the highest published standard flat rate for everyday consumer spending among the cards reviewed. "
        "Category-specific, business-card, and temporary promotional offers are not equivalent to an across-purchase everyday rate."
    ) % (winner["name"], rate)
    terms = []
    if winner["annual_fee"] is not None:
        terms.append("a $%s annual fee" % display_number(winner["annual_fee"]))
    if winner["minimum_credit_score"] is not None:
        terms.append("a minimum credit-score requirement of %d" % int(winner["minimum_credit_score"]))
    if terms:
        response += " Published terms list " + " and ".join(terms) + "; eligibility and approval are determined separately."
    return response


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(["invalid JSON: " + exc.msg])
        return
    if not isinstance(payload, dict):
        fail(["input must be a JSON object"])
        return

    segment = norm(payload.get("market_segment", "consumer"))
    if segment not in CONSUMER_SEGMENTS | {"business"}:
        fail(["market_segment must be consumer, personal, retail, or business"])
        return

    errors = []
    if isinstance(payload.get("cards"), list):
        cards = normalize_cards(payload["cards"], errors)
    elif isinstance(payload.get("documents"), list):
        cards = extract_document_cards(payload["documents"])
    else:
        fail(["provide cards or documents as an array"])
        return
    if errors:
        fail(errors)
        return

    requested_consumer = segment in CONSUMER_SEGMENTS
    qualifying, excluded = [], []
    for card in cards:
        card_consumer = card["market_segment"] in CONSUMER_SEGMENTS
        if card_consumer != requested_consumer:
            excluded.append({"name": card["name"], "reason": "outside requested market segment"})
        elif card["status"] != "active":
            excluded.append({"name": card["name"], "reason": "product is not active"})
        elif card["base_flat_cashback_rate"] is None or card["base_rate_scope"] not in FLAT_SCOPES:
            excluded.append({"name": card["name"], "reason": "no explicit standard flat rate across eligible purchases"})
        else:
            qualifying.append(card)

    if not qualifying:
        fail(["no qualifying active standard flat everyday cash-back card was established by the supplied material"])
        return

    qualifying.sort(key=lambda card: (-card["base_flat_cashback_rate"], card["name"].lower()))
    winner = qualifying[0]
    print(json.dumps({
        "status": "ok",
        "selection": serial(winner),
        "ranked_qualifying_cards": [serial(card) for card in qualifying],
        "excluded_cards": excluded,
        "response": compose_response(winner),
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
