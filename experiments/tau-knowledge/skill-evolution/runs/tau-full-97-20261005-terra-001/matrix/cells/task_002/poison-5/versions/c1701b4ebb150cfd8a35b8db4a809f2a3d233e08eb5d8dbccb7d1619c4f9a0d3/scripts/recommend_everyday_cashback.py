#!/usr/bin/env python3
"""Rank published standard flat cash-back offers for everyday spending.

The program reads a JSON object from stdin and writes a JSON object to stdout.
It accepts either normalized card records or public product documents.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation

CONSUMER_SEGMENTS = {"consumer", "personal", "retail"}
FLAT_SCOPES = {
    "all eligible purchases",
    "eligible purchases",
    "all purchases",
    "all categories",
}


def norm(value):
    return str(value or "").strip().lower()


def to_decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number >= 0 else None


def number_text(value):
    return format(Decimal(value).quantize(Decimal("0.1")), "f")


def emit(value):
    print(json.dumps(value, separators=(",", ":")))


def fail(*errors):
    emit({"status": "error", "errors": list(errors)})


def source_segment(document):
    marker = " ".join(
        (str(document.get("document_id", "")), str(document.get("title", "")))
    ).lower()
    return "business" if "business" in marker else "consumer"


def title_name(title):
    name = str(title or "").split(":", 1)[0].strip()
    return name or None


def first_match_decimal(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return to_decimal(match.group(1)) if match else None


def extract_documents(documents):
    """Extract only explicitly stated standard flat all-purchase earn rates."""
    groups = {}
    rate_patterns = (
        # "Earn 2.0% cash back on all eligible purchases."
        (r"(?:you\s+)?earn\s+(\d+(?:\.\d+)?)%\s+cash\s*back\s+on\s+"
         r"(all\s+eligible\s+purchases|eligible\s+purchases|all\s+purchases|all\s+categories)",
         1, 2),
        # "Cash back on all purchases: 2.0%."
        (r"cash\s*back\s+on\s+(all\s+eligible\s+purchases|eligible\s+purchases|"
         r"all\s+purchases|all\s+categories)\s*:\s*(\d+(?:\.\d+)?)%",
         2, 1),
        # "Earn a flat rate ... 2.0% on all other eligible purchases" is deliberately
        # not accepted: "other" does not establish an across-purchase rate.
    )

    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            continue
        name = title_name(document.get("title"))
        if not name:
            continue
        segment = source_segment(document)
        key = (name.lower(), segment)
        record = groups.setdefault(key, {
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

        for pattern, rate_group, scope_group in rate_patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            rate = to_decimal(match.group(rate_group))
            scope = norm(match.group(scope_group))
            if rate is not None and scope in FLAT_SCOPES:
                old_rate = record["base_flat_cashback_rate"]
                if old_rate is None or rate > old_rate:
                    record["base_flat_cashback_rate"] = rate
                    record["base_rate_scope"] = scope

        fee = first_match_decimal(
            r"annual\s+(?:membership\s+)?fee\s*:\s*\$?\s*(\d+(?:\.\d+)?)",
            content,
        )
        if fee is not None and record["annual_fee"] is None:
            record["annual_fee"] = fee

        score = first_match_decimal(
            r"minimum(?:\s+personal)?\s+credit\s+score(?:\s+required)?"
            r"[^\d$]{0,50}\$?\s*(\d{3,4})",
            content,
        )
        if score is not None and record["minimum_credit_score"] is None:
            record["minimum_credit_score"] = score

    return list(groups.values())


def normalize_cards(cards):
    result, errors = [], []
    for index, card in enumerate(cards):
        label = "cards[%d]" % index
        if not isinstance(card, dict):
            errors.append(label + " must be an object")
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(label + ".name must be a nonempty string")
            continue
        raw_rate = card.get("base_flat_cashback_rate")
        rate = to_decimal(raw_rate)
        if raw_rate is not None and rate is None:
            errors.append(label + ".base_flat_cashback_rate must be a nonnegative number")
            continue
        fee = to_decimal(card.get("annual_fee")) if card.get("annual_fee") is not None else None
        score = (to_decimal(card.get("minimum_credit_score"))
                 if card.get("minimum_credit_score") is not None else None)
        if card.get("annual_fee") is not None and fee is None:
            errors.append(label + ".annual_fee must be a nonnegative number")
            continue
        if card.get("minimum_credit_score") is not None and score is None:
            errors.append(label + ".minimum_credit_score must be a nonnegative number")
            continue
        source_ids = card.get("source_ids", [])
        result.append({
            "name": name.strip(),
            "market_segment": norm(card.get("market_segment", "consumer")),
            "status": norm(card.get("status", "active")),
            "base_flat_cashback_rate": rate,
            "base_rate_scope": norm(card.get("base_rate_scope")),
            "annual_fee": fee,
            "minimum_credit_score": score,
            "source_ids": [str(item) for item in source_ids] if isinstance(source_ids, list) else [],
        })
    return result, errors


def public_card(card):
    value = {
        "name": card["name"],
        "base_flat_cashback_rate": float(card["base_flat_cashback_rate"]),
        "source_ids": card["source_ids"],
    }
    if card["annual_fee"] is not None:
        value["annual_fee"] = float(card["annual_fee"])
    if card["minimum_credit_score"] is not None:
        value["minimum_credit_score"] = int(card["minimum_credit_score"])
    return value


def compose(winner, segment):
    rate = number_text(winner["base_flat_cashback_rate"])
    scope = winner["base_rate_scope"]
    segment_word = "consumer" if segment in CONSUMER_SEGMENTS else "business"
    message = (
        "Recommendation: %s. It earns %s%% cash back on %s, the highest "
        "published standard flat rate for everyday %s spending among the cards reviewed. "
        "Category-specific, business-only, and temporary promotional offers are not "
        "equivalent to an across-purchase everyday rate."
    ) % (winner["name"], rate, scope, segment_word)
    terms = []
    if winner["annual_fee"] is not None:
        terms.append("a $%s annual fee" % number_text(winner["annual_fee"]))
    if winner["minimum_credit_score"] is not None:
        terms.append("a minimum credit-score requirement of %d" % int(winner["minimum_credit_score"]))
    if terms:
        message += " Published terms list " + " and ".join(terms) + "; eligibility and approval are determined separately."
    return message


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
    valid_segments = CONSUMER_SEGMENTS | {"business"}
    if segment not in valid_segments:
        fail("market_segment must be consumer, personal, retail, or business")
        return

    if isinstance(payload.get("cards"), list):
        cards, errors = normalize_cards(payload["cards"])
        if errors:
            fail(*errors)
            return
    elif isinstance(payload.get("documents"), list):
        cards = extract_documents(payload["documents"])
    else:
        fail("provide cards or documents as an array")
        return

    requested_consumer = segment in CONSUMER_SEGMENTS
    qualifying, excluded = [], []
    for card in cards:
        card_consumer = card["market_segment"] in CONSUMER_SEGMENTS
        if card_consumer != requested_consumer:
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
        "selection": public_card(winner),
        "ranked_qualifying_cards": [public_card(card) for card in qualifying],
        "excluded_cards": excluded,
        "response": compose(winner, segment),
    })


if __name__ == "__main__":
    main()
