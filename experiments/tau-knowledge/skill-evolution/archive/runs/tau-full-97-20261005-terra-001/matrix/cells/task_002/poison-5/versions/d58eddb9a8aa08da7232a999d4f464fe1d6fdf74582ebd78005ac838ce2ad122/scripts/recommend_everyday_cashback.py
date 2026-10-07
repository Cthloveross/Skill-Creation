#!/usr/bin/env python3
"""Select the highest published standard flat everyday cash-back card.

Reads one JSON object from stdin and writes one JSON object to stdout. Input may
contain normalized card records or public product documents. Rates are expressed
as percentages, so 2.0 represents 2.0%.
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


def fail(*messages):
    emit({"status": "error", "errors": list(messages)})


def clean(value):
    return str(value or "").strip().lower()


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result >= 0 else None


def shown(value):
    return format(value.quantize(Decimal("0.1")), "f")


def product_name(title):
    name = str(title or "").split(":", 1)[0].strip()
    return name or None


def document_segment(document):
    marker = (str(document.get("document_id", "")) + " " +
              str(document.get("title", ""))).lower()
    return "business" if "business" in marker else "consumer"


def scope_rate_matches(content):
    """Yield explicit statements establishing a standard all-purchase rate."""
    patterns = (
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
    )
    for position, pattern in enumerate(patterns):
        for match in pattern.finditer(content):
            if position == 0:
                rate, scope = number(match.group(1)), clean(match.group(2))
            else:
                rate, scope = number(match.group(2)), clean(match.group(1))
            if rate is not None and scope in FLAT_SCOPES:
                yield rate, scope


def parse_documents(documents):
    records = {}
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

        for rate, scope in scope_rate_matches(content):
            current = record["base_flat_cashback_rate"]
            if current is None or rate > current:
                record["base_flat_cashback_rate"] = rate
                record["base_rate_scope"] = scope

        fee = re.search(
            r"annual\s+(?:membership\s+)?fee\s*:\s*\$?\s*(\d+(?:\.\d+)?)",
            content, re.I,
        )
        if fee and record["annual_fee"] is None:
            record["annual_fee"] = number(fee.group(1))
        score = re.search(
            r"minimum(?:\s+personal)?\s+credit\s+score(?:\s+required)?[^\d$]{0,50}\$?\s*(\d{3,4})",
            content, re.I,
        )
        if score and record["minimum_credit_score"] is None:
            record["minimum_credit_score"] = number(score.group(1))
    return list(records.values())


def normalize_cards(cards):
    records, errors = [], []
    for index, card in enumerate(cards):
        label = "cards[%d]" % index
        if not isinstance(card, dict):
            errors.append(label + " must be an object")
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(label + ".name must be a nonempty string")
            continue
        rate_value = card.get("base_flat_cashback_rate")
        rate = number(rate_value)
        if rate_value is not None and rate is None:
            errors.append(label + ".base_flat_cashback_rate must be nonnegative")
            continue
        fee_value = card.get("annual_fee")
        fee = number(fee_value) if fee_value is not None else None
        score_value = card.get("minimum_credit_score")
        score = number(score_value) if score_value is not None else None
        if fee_value is not None and fee is None:
            errors.append(label + ".annual_fee must be nonnegative")
            continue
        if score_value is not None and score is None:
            errors.append(label + ".minimum_credit_score must be nonnegative")
            continue
        source_ids = card.get("source_ids", [])
        records.append({
            "name": name.strip(),
            "market_segment": clean(card.get("market_segment", "consumer")),
            "base_flat_cashback_rate": rate,
            "base_rate_scope": clean(card.get("base_rate_scope")),
            "annual_fee": fee,
            "minimum_credit_score": score,
            "source_ids": [str(item) for item in source_ids] if isinstance(source_ids, list) else [],
        })
    return records, errors


def public_record(card):
    output = {
        "name": card["name"],
        "base_flat_cashback_rate": float(card["base_flat_cashback_rate"]),
        "base_rate_scope": card["base_rate_scope"],
        "source_ids": card["source_ids"],
    }
    if card["annual_fee"] is not None:
        output["annual_fee"] = float(card["annual_fee"])
    if card["minimum_credit_score"] is not None:
        output["minimum_credit_score"] = int(card["minimum_credit_score"])
    return output


def customer_response(card, segment):
    audience = "consumer" if segment in CONSUMER_SEGMENTS else "business"
    text = (
        "Recommendation: %s. It earns %s%% cash back on %s, the highest "
        "documented standard flat rate for everyday %s spending among the cards reviewed."
    ) % (card["name"], shown(card["base_flat_cashback_rate"]),
         card["base_rate_scope"], audience)
    terms = []
    if card["annual_fee"] is not None:
        terms.append("a $%s annual fee" % shown(card["annual_fee"]))
    if card["minimum_credit_score"] is not None:
        terms.append("a minimum credit-score requirement of %d" % int(card["minimum_credit_score"]))
    if terms:
        text += " Published terms list " + " and ".join(terms) + "; eligibility and approval are determined separately."
    return text


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("invalid JSON: " + exc.msg)
        return
    if not isinstance(payload, dict):
        fail("input must be a JSON object")
        return

    segment = clean(payload.get("market_segment", "consumer"))
    if segment not in VALID_SEGMENTS:
        fail("market_segment must be consumer, personal, retail, or business")
        return

    if isinstance(payload.get("cards"), list):
        cards, errors = normalize_cards(payload["cards"])
        if errors:
            fail(*errors)
            return
    elif isinstance(payload.get("documents"), list):
        cards = parse_documents(payload["documents"])
    else:
        fail("provide cards or documents as an array")
        return

    wants_consumer = segment in CONSUMER_SEGMENTS
    qualifying, excluded = [], []
    for card in cards:
        is_consumer = card["market_segment"] in CONSUMER_SEGMENTS
        if is_consumer != wants_consumer:
            excluded.append({"name": card["name"], "reason": "outside requested market segment"})
        elif (card["base_flat_cashback_rate"] is None or
              card["base_rate_scope"] not in FLAT_SCOPES):
            excluded.append({"name": card["name"], "reason": "no explicit standard flat all-purchase rate"})
        else:
            qualifying.append(card)

    if not qualifying:
        fail("no qualifying standard flat everyday cash-back card was established")
        return

    qualifying.sort(key=lambda card: (-card["base_flat_cashback_rate"], card["name"].lower()))
    best_rate = qualifying[0]["base_flat_cashback_rate"]
    leaders = [card for card in qualifying if card["base_flat_cashback_rate"] == best_rate]
    ranking = [public_record(card) for card in qualifying]

    if len(leaders) != 1:
        emit({
            "status": "tie",
            "tied_cards": [public_record(card) for card in leaders],
            "ranked_qualifying_cards": ranking,
            "excluded_cards": excluded,
            "response": "Multiple cards share the highest documented standard flat everyday cash-back rate. Please share a preference such as annual fee or benefits to choose between them.",
        })
        return

    winner = leaders[0]
    emit({
        "status": "ok",
        "selection": public_record(winner),
        "ranked_qualifying_cards": ranking,
        "excluded_cards": excluded,
        "response": customer_response(winner, segment),
    })


if __name__ == "__main__":
    main()
