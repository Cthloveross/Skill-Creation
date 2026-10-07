#!/usr/bin/env python3
"""Screen supplied credit-card documents without side effects.

The script reads one JSON object from stdin and writes one JSON object to stdout.
It uses only the supplied payload and does not access accounts, networks, or tools.
"""
import json
import math
import re
import sys


def clean(value):
    return re.sub(r"\s+", " ", value).strip()


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def product_name(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    name = clean(title.split(":", 1)[0])
    return name or None


def source_id(document, index):
    return str(document.get("document_id") or document.get("title") or "documents[%d]" % index)


def percent_on_matching_line(text, required_words):
    for line in text.splitlines():
        lowered = line.casefold()
        if all(word in lowered for word in required_words):
            match = re.search(r"\$?([0-9]+(?:\.[0-9]+)?)\s*%", line)
            if match:
                return float(match.group(1))
    return None


def yes_no_on_matching_line(text, required_words):
    for line in text.splitlines():
        lowered = line.casefold()
        if all(word in lowered for word in required_words):
            match = re.search(r"\b(yes|no)\b", line, re.IGNORECASE)
            if match:
                return match.group(1).casefold() == "yes"
    return None


def integer_on_matching_line(text, required_words):
    for line in text.splitlines():
        lowered = line.casefold()
        if all(word in lowered for word in required_words):
            match = re.search(r"\$?([0-9][0-9,]*)", line)
            if match:
                return int(match.group(1).replace(",", ""))
    return None


def empty_card(name):
    return {
        "name": name,
        "foreign_transaction_fee_pct": None,
        "minimum_payment_pct": None,
        "virtual_card_management": None,
        "minimum_credit_score": None,
        "subscription_requirement": None,
        "invitation_only": None,
        "minimum_annual_income": None,
        "sources": [],
        "_observed": {},
    }


def observe(card, field, value, source):
    if value is None:
        return
    card["_observed"].setdefault(field, []).append((value, source))
    if source not in card["sources"]:
        card["sources"].append(source)


def finalize(card, warnings):
    for field, records in card.pop("_observed").items():
        values = {value for value, _source in records}
        if len(values) == 1:
            card[field] = records[0][0]
        else:
            warnings.append(
                "conflicting %s values for %s; treated as unknown (%s)" %
                (field, card["name"], ", ".join(source for _value, source in records))
            )


def extract_cards(documents):
    cards = {}
    warnings = []
    for index, document in enumerate(documents):
        if not isinstance(document, dict) or not isinstance(document.get("content"), str):
            warnings.append("documents[%d] lacks text content" % index)
            continue
        name = product_name(document.get("title"))
        if name is None:
            warnings.append("documents[%d] has no parsable product name" % index)
            continue

        card = cards.setdefault(name, empty_card(name))
        text = document["content"]
        source = source_id(document, index)

        fee = percent_on_matching_line(text, ("foreign", "transaction", "fee"))
        payment = percent_on_matching_line(text, ("minimum", "payment"))
        virtual = yes_no_on_matching_line(text, ("virtual", "card", "management"))
        score = integer_on_matching_line(text, ("minimum", "credit", "score"))
        invitation = yes_no_on_matching_line(text, ("invitation", "only"))
        income = integer_on_matching_line(text, ("minimum", "income"))

        subscription_match = re.search(
            r"([A-Za-z][A-Za-z0-9+\-\u2011 ]*?)\s+(?:premium\s+)?subscription\s+required\s*:\s*(yes|no)\b",
            text,
            re.IGNORECASE,
        )

        observe(card, "foreign_transaction_fee_pct", fee, source)
        observe(card, "minimum_payment_pct", payment, source)
        observe(card, "virtual_card_management", virtual, source)
        observe(card, "minimum_credit_score", score, source)
        observe(card, "invitation_only", invitation, source)
        observe(card, "minimum_annual_income", income, source)
        if subscription_match and subscription_match.group(2).casefold() == "yes":
            observe(card, "subscription_requirement", clean(subscription_match.group(1)), source)

    for card in cards.values():
        finalize(card, warnings)
    return list(cards.values()), warnings


def customer_subscriptions(customer):
    values = customer.get("subscriptions", [])
    if not isinstance(values, list):
        return None
    return {clean(item).casefold() for item in values if isinstance(item, str) and item.strip()}


def assess(card, customer, criteria):
    failures = []
    blockers = []
    unknowns = []

    fee_cap = criteria.get("max_foreign_transaction_fee_pct")
    payment_cap = criteria.get("max_minimum_payment_pct")
    if is_number(fee_cap):
        fee = card["foreign_transaction_fee_pct"]
        if not is_number(fee):
            unknowns.append("foreign transaction fee is not documented")
        elif fee > fee_cap:
            failures.append("foreign transaction fee %.1f%% exceeds %.1f%% cap" % (fee, fee_cap))
    if is_number(payment_cap):
        payment = card["minimum_payment_pct"]
        if not is_number(payment):
            unknowns.append("minimum payment is not documented")
        elif payment > payment_cap:
            failures.append("minimum payment %.1f%% exceeds %.1f%% cap" % (payment, payment_cap))
    if criteria.get("requires_virtual_card_management") is True:
        virtual = card["virtual_card_management"]
        if virtual is None:
            unknowns.append("virtual card management is not documented")
        elif not virtual:
            failures.append("virtual card management is unavailable")

    stated_score = customer.get("credit_score")
    minimum_score = card["minimum_credit_score"]
    if not is_number(minimum_score):
        unknowns.append("minimum credit-score condition is not documented")
    elif not is_number(stated_score):
        unknowns.append("customer credit score was not supplied")
    elif stated_score < minimum_score:
        blockers.append("stated credit score %s is below its %s minimum" % (stated_score, minimum_score))

    requirement = card["subscription_requirement"]
    held = customer_subscriptions(customer)
    if requirement:
        if held is None:
            unknowns.append("customer subscription status was not supplied")
        elif requirement.casefold() not in held:
            blockers.append("requires %s subscription" % requirement)
    if card["invitation_only"] is True:
        blockers.append("is invitation-only")

    income_floor = card["minimum_annual_income"]
    stated_income = customer.get("annual_income")
    if is_number(income_floor):
        if not is_number(stated_income):
            unknowns.append("customer annual income was not supplied")
        elif stated_income < income_floor:
            blockers.append("stated annual income is below its documented minimum")

    return {
        "name": card["name"],
        "terms": card,
        "feature_failures": failures,
        "eligibility_blockers": blockers,
        "unknowns": unknowns,
        "documented_fit": not failures and not blockers and not unknowns,
    }


def response_facts(item, customer, criteria):
    terms = item["terms"]
    return {
        "product": item["name"],
        "foreign_transaction_fee_pct": terms["foreign_transaction_fee_pct"],
        "foreign_transaction_fee_cap_pct": criteria.get("max_foreign_transaction_fee_pct"),
        "minimum_payment_pct": terms["minimum_payment_pct"],
        "minimum_payment_cap_pct": criteria.get("max_minimum_payment_pct"),
        "virtual_card_management": terms["virtual_card_management"],
        "minimum_credit_score": terms["minimum_credit_score"],
        "customer_credit_score": customer.get("credit_score"),
        "sources": terms["sources"],
    }


def emit_error(message):
    print(json.dumps({"ok": False, "errors": [message]}, sort_keys=True))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        emit_error("stdin must contain one JSON object: %s" % exc)
        return
    if not isinstance(payload, dict):
        emit_error("input must be a JSON object")
        return
    if not isinstance(payload.get("documents"), list):
        emit_error("input must contain a documents list")
        return
    if not isinstance(payload.get("customer"), dict):
        emit_error("customer must be an object")
        return
    if not isinstance(payload.get("criteria"), dict):
        emit_error("criteria must be an object")
        return

    cards, warnings = extract_cards(payload["documents"])
    assessed = [assess(card, payload["customer"], payload["criteria"]) for card in cards]
    assessed.sort(key=lambda item: (not item["documented_fit"], item["name"].casefold()))
    recommendations = [item for item in assessed if item["documented_fit"]]
    alternatives = [item for item in assessed if not item["documented_fit"]]

    output = {
        "ok": True,
        "cards": cards,
        "recommendations": recommendations,
        "alternatives": alternatives,
        "warnings": warnings,
        "required_response_facts": [
            response_facts(item, payload["customer"], payload["criteria"])
            for item in recommendations
        ],
        "disclaimer": (
            "This compares supplied product terms with stated facts; it is not an approval, "
            "underwriting decision, or application submission."
        ),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
