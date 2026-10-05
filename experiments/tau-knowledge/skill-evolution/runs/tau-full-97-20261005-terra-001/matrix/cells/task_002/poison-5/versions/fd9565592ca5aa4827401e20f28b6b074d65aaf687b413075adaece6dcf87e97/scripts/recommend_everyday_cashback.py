#!/usr/bin/env python3
"""Rank published standard flat cash-back rates for everyday spending.

Reads one JSON object from stdin and emits one JSON object to stdout. Input is
normalized card records or public product documents. Cash-back rates are stored
as percentages, not decimal fractions.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation

CONSUMER_SEGMENTS = {"consumer", "personal", "retail"}
VALID_SEGMENTS = CONSUMER_SEGMENTS | {"business"}
FLAT_SCOPES = {
    "all eligible purchases",
    "eligible purchases",
    "all purchases",
    "all categories",
}


def emit(value):
    print(json.dumps(value, separators=(",", ":")))


def error(*messages):
    emit({"status": "error", "errors": list(messages)})


def normalized(value):
    return str(value or "").strip().lower()


def as_decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number >= 0 else None


def percentage(value):
    return format(value.quantize(Decimal("0.1")), "f")


def card_name(title):
    name = str(title or "").split(":", 1)[0].strip()
    return name or None


def document_segment(document):
    marker = (str(document.get("document_id", "")) + " " +
              str(document.get("title", ""))).lower()
    return "business" if "business" in marker else "consumer"


def parse_documents(documents):
    """Extract only explicit cash-back wording that establishes a flat rate."""
    records = {}
    earn_patterns = [
        re.compile(
            r"(?:you\s+)?earn\s+(\d+(?:\.\d+)?)%\s+cash\s*back\s+on\s+"
            r"(all\s+eligible\s+purchases|eligible\s+purchases|all\s+purchases|all\s+categories)",
            re.I,
        ),
        re.compile(
            r"cash\s*back\s+on\s+"
            r"(all\s+eligible\s+purchases|eligible\s+purchases|all\s+purchases|all\s+categories)"
            r"\s*:\s*(\d+(?:\.\d+)?)%",
            re.I,
        ),
    ]

    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            continue
        name = card_name(document.get("title"))
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

        for pattern_index, pattern in enumerate(earn_patterns):
            match = pattern.search(content)
            if not match:
                continue
            if pattern_index == 0:
                rate, scope = as_decimal(match.group(1)), normalized(match.group(2))
            else:
                scope, rate = normalized(match.group(1)), as_decimal(match.group(2))
            if rate is not None and scope in FLAT_SCOPES:
                current = record["base_flat_cashback_rate"]
                if current is None or rate > current:
                    record["base_flat_cashback_rate"] = rate
                    record["base_rate_scope"] = scope

        fee = re.search(r"annual\s+(?:membership\s+)?fee\s*:\s*\$?\s*(\d+(?:\.\d+)?)", content, re.I)
        if fee and record["annual_fee"] is None:
            record["annual_fee"] = as_decimal(fee.group(1))
        score = re.search(
            r"minimum(?:\s+personal)?\s+credit\s+score(?:\s+required)?[^\d$]{0,50}\$?\s*(\d{3,4})",
            content,
            re.I,
        )
        if score and record["minimum_credit_score"] is None:
            record["minimum_credit_score"] = as_decimal(score.group(1))
    return list(records.values())


def normalize_cards(cards):
    output, problems = [], []
    for index, card in enumerate(cards):
        prefix = "cards[%d]" % index
        if not isinstance(card, dict):
            problems.append(prefix + " must be an object")
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append(prefix + ".name must be a nonempty string")
            continue
        rate_value = card.get("base_flat_cashback_rate")
        rate = as_decimal(rate_value)
        if rate_value is not None and rate is None:
            problems.append(prefix + ".base_flat_cashback_rate must be nonnegative")
            continue
        fee_value = card.get("annual_fee")
        fee = as_decimal(fee_value) if fee_value is not None else None
        score_value = card.get("minimum_credit_score")
        score = as_decimal(score_value) if score_value is not None else None
        if fee_value is not None and fee is None:
            problems.append(prefix + ".annual_fee must be nonnegative")
            continue
        if score_value is not None and score is None:
            problems.append(prefix + ".minimum_credit_score must be nonnegative")
            continue
        source_ids = card.get("source_ids", [])
        output.append({
            "name": name.strip(),
            "market_segment": normalized(card.get("market_segment", "consumer")),
            "status": normalized(card.get("status", "active")),
            "base_flat_cashback_rate": rate,
            "base_rate_scope": normalized(card.get("base_rate_scope")),
            "annual_fee": fee,
            "minimum_credit_score": score,
            "source_ids": [str(v) for v in source_ids] if isinstance(source_ids, list) else [],
        })
    return output, problems


def public_card(card):
    result = {
        "name": card["name"],
        "base_flat_cashback_rate": float(card["base_flat_cashback_rate"]),
        "base_rate_scope": card["base_rate_scope"],
        "source_ids": card["source_ids"],
    }
    if card["annual_fee"] is not None:
        result["annual_fee"] = float(card["annual_fee"])
    if card["minimum_credit_score"] is not None:
        result["minimum_credit_score"] = int(card["minimum_credit_score"])
    return result


def response_for(card, segment):
    audience = "consumer" if segment in CONSUMER_SEGMENTS else "business"
    text = (
        "Recommendation: %s. It earns %s%% cash back on %s, the highest "
        "documented standard flat rate for everyday %s spending among the cards reviewed."
    ) % (card["name"], percentage(card["base_flat_cashback_rate"]),
         card["base_rate_scope"], audience)
    terms = []
    if card["annual_fee"] is not None:
        terms.append("a $%s annual fee" % percentage(card["annual_fee"]))
    if card["minimum_credit_score"] is not None:
        terms.append("a minimum credit-score requirement of %d" % int(card["minimum_credit_score"]))
    if terms:
        text += " Published terms list " + " and ".join(terms) + "; eligibility and approval are determined separately."
    return text


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        error("invalid JSON: " + exc.msg)
        return
    if not isinstance(payload, dict):
        error("input must be a JSON object")
        return

    segment = normalized(payload.get("market_segment", "consumer"))
    if segment not in VALID_SEGMENTS:
        error("market_segment must be consumer, personal, retail, or business")
        return
    if isinstance(payload.get("cards"), list):
        cards, problems = normalize_cards(payload["cards"])
        if problems:
            error(*problems)
            return
    elif isinstance(payload.get("documents"), list):
        cards = parse_documents(payload["documents"])
    else:
        error("provide cards or documents as an array")
        return

    want_consumer = segment in CONSUMER_SEGMENTS
    qualifying, excluded = [], []
    for card in cards:
        is_consumer = card["market_segment"] in CONSUMER_SEGMENTS
        if is_consumer != want_consumer:
            excluded.append({"name": card["name"], "reason": "outside requested market segment"})
        elif card["status"] != "active":
            excluded.append({"name": card["name"], "reason": "product is not active"})
        elif card["base_flat_cashback_rate"] is None or card["base_rate_scope"] not in FLAT_SCOPES:
            excluded.append({"name": card["name"], "reason": "no explicit standard flat all-purchase rate"})
        else:
            qualifying.append(card)
    if not qualifying:
        error("no qualifying active standard flat everyday cash-back card was established")
        return

    qualifying.sort(key=lambda item: (-item["base_flat_cashback_rate"], item["name"].lower()))
    best_rate = qualifying[0]["base_flat_cashback_rate"]
    leaders = [card for card in qualifying if card["base_flat_cashback_rate"] == best_rate]
    ranking = [public_card(card) for card in qualifying]
    if len(leaders) != 1:
        emit({
            "status": "tie",
            "tied_cards": [public_card(card) for card in leaders],
            "ranked_qualifying_cards": ranking,
            "excluded_cards": excluded,
            "response": "Multiple cards share the highest documented standard flat everyday cash-back rate. Please share a preference such as annual fee or other benefits to choose between them.",
        })
        return

    winner = leaders[0]
    emit({
        "status": "ok",
        "selection": public_card(winner),
        "ranked_qualifying_cards": ranking,
        "excluded_cards": excluded,
        "response": response_for(winner, segment),
    })


if __name__ == "__main__":
    main()
