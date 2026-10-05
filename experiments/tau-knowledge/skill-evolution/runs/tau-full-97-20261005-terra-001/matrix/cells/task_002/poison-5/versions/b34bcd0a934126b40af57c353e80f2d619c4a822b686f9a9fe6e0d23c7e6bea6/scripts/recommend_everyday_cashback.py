#!/usr/bin/env python3
"""Select the highest documented standard flat everyday cash-back card.

Read one JSON object from stdin and write one JSON object to stdout. Input may
contain normalized card records or public product documents. Rates are expressed
as percentages, so 2.0 means 2.0%.
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


def string(value):
    return str(value or "").strip()


def lower(value):
    return string(value).lower()


def amount(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result >= 0 else None


def show(value):
    return format(value.quantize(Decimal("0.1")), "f")


def product_name(title):
    name = string(title).split(":", 1)[0].strip()
    return name or None


def document_segment(document):
    marker = (string(document.get("document_id")) + " " + string(document.get("title"))).lower()
    return "business" if "business" in marker else "consumer"


def rate_matches(content):
    """Yield explicit all-purchase standard rate and scope pairs."""
    forward = re.compile(
        r"(?:you\s+)?earn\s+(\d+(?:\.\d+)?)\s*%\s+cash\s*back\s+on\s+"
        r"(all\s+eligible\s+purchases|eligible\s+purchases|all\s+purchases|all\s+categories)",
        re.IGNORECASE,
    )
    labeled = re.compile(
        r"cash\s*back\s+on\s+"
        r"(all\s+eligible\s+purchases|eligible\s+purchases|all\s+purchases|all\s+categories)"
        r"\s*(?:\||:|is|=)\s*\$?\s*(\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    )
    for match in forward.finditer(content):
        rate = amount(match.group(1))
        scope = lower(match.group(2))
        if rate is not None and scope in FLAT_SCOPES:
            yield rate, scope
    for match in labeled.finditer(content):
        rate = amount(match.group(2))
        scope = lower(match.group(1))
        if rate is not None and scope in FLAT_SCOPES:
            yield rate, scope


def extract_number(content, pattern):
    match = re.search(pattern, content, re.IGNORECASE)
    return amount(match.group(1)) if match else None


def parse_documents(documents):
    grouped = {}
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            continue
        name = product_name(document.get("title"))
        if not name:
            continue
        segment = document_segment(document)
        key = (name.lower(), segment)
        record = grouped.setdefault(key, {
            "name": name,
            "market_segment": segment,
            "base_flat_cashback_rate": None,
            "base_rate_scope": None,
            "annual_fee": None,
            "minimum_credit_score": None,
            "source_ids": [],
        })
        source = string(document.get("document_id")) or "document-%d" % index
        if source not in record["source_ids"]:
            record["source_ids"].append(source)
        content = string(document.get("content"))

        for rate, scope in rate_matches(content):
            if record["base_flat_cashback_rate"] is None or rate > record["base_flat_cashback_rate"]:
                record["base_flat_cashback_rate"] = rate
                record["base_rate_scope"] = scope

        if record["annual_fee"] is None:
            record["annual_fee"] = extract_number(
                content,
                r"annual\s+(?:membership\s+)?fee\s*:\s*\$?\s*(\d+(?:\.\d+)?)",
            )
        if record["minimum_credit_score"] is None:
            record["minimum_credit_score"] = extract_number(
                content,
                r"minimum(?:\s+personal)?\s+credit\s+score(?:\s+required)?[^\d$]{0,60}\$?\s*(\d{3,4})",
            )
    return list(grouped.values())


def normalize_cards(cards):
    records, problems = [], []
    for index, card in enumerate(cards):
        label = "cards[%d]" % index
        if not isinstance(card, dict):
            problems.append(label + " must be an object")
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append(label + ".name must be a nonempty string")
            continue
        rate_value = card.get("base_flat_cashback_rate")
        rate = amount(rate_value)
        if rate_value is not None and rate is None:
            problems.append(label + ".base_flat_cashback_rate must be nonnegative")
            continue
        fee_value = card.get("annual_fee")
        fee = amount(fee_value) if fee_value is not None else None
        score_value = card.get("minimum_credit_score")
        score = amount(score_value) if score_value is not None else None
        if fee_value is not None and fee is None:
            problems.append(label + ".annual_fee must be nonnegative")
            continue
        if score_value is not None and score is None:
            problems.append(label + ".minimum_credit_score must be nonnegative")
            continue
        sources = card.get("source_ids", [])
        records.append({
            "name": name.strip(),
            "market_segment": lower(card.get("market_segment", "consumer")),
            "base_flat_cashback_rate": rate,
            "base_rate_scope": lower(card.get("base_rate_scope")),
            "annual_fee": fee,
            "minimum_credit_score": score,
            "source_ids": [str(item) for item in sources] if isinstance(sources, list) else [],
        })
    return records, problems


def public_record(card):
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
    response = (
        "Recommendation: %s. It earns %s%% cash back on %s, the highest "
        "documented standard flat rate for everyday %s spending among the cards reviewed."
    ) % (card["name"], show(card["base_flat_cashback_rate"]), card["base_rate_scope"], audience)
    terms = []
    if card["annual_fee"] is not None:
        terms.append("a $%s annual fee" % show(card["annual_fee"]))
    if card["minimum_credit_score"] is not None:
        terms.append("a minimum credit-score requirement of %d" % int(card["minimum_credit_score"]))
    if terms:
        response += " Published terms list " + " and ".join(terms) + "; eligibility and approval are determined separately."
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

    segment = lower(payload.get("market_segment", "consumer"))
    if segment not in VALID_SEGMENTS:
        fail("market_segment must be consumer, personal, retail, or business")
        return
    if isinstance(payload.get("cards"), list):
        cards, problems = normalize_cards(payload["cards"])
        if problems:
            fail(*problems)
            return
    elif isinstance(payload.get("documents"), list):
        cards = parse_documents(payload["documents"])
    else:
        fail("provide cards or documents as an array")
        return

    want_consumer = segment in CONSUMER_SEGMENTS
    qualifying, excluded = [], []
    for card in cards:
        is_consumer = card["market_segment"] in CONSUMER_SEGMENTS
        if is_consumer != want_consumer:
            excluded.append({"name": card["name"], "reason": "outside requested market segment"})
        elif card["base_flat_cashback_rate"] is None or card["base_rate_scope"] not in FLAT_SCOPES:
            excluded.append({"name": card["name"], "reason": "no explicit standard flat all-purchase rate"})
        else:
            qualifying.append(card)

    if not qualifying:
        fail("no qualifying standard flat everyday cash-back card was established")
        return

    qualifying.sort(key=lambda card: (-card["base_flat_cashback_rate"], card["name"].lower()))
    top_rate = qualifying[0]["base_flat_cashback_rate"]
    leaders = [card for card in qualifying if card["base_flat_cashback_rate"] == top_rate]
    ranked = [public_record(card) for card in qualifying]

    if len(leaders) > 1:
        emit({
            "status": "tie",
            "tied_cards": [public_record(card) for card in leaders],
            "ranked_qualifying_cards": ranked,
            "excluded_cards": excluded,
            "response": "Multiple cards share the highest documented standard flat everyday cash-back rate. Please share a preference such as annual fee or benefits to choose between them.",
        })
        return

    winner = leaders[0]
    emit({
        "status": "ok",
        "selection": public_record(winner),
        "ranked_qualifying_cards": ranked,
        "excluded_cards": excluded,
        "response": response_for(winner, segment),
    })


if __name__ == "__main__":
    main()
