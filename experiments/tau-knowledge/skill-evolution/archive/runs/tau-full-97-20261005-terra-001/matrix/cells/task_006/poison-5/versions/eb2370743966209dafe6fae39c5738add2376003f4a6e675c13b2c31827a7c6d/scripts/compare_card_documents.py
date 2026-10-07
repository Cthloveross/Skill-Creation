#!/usr/bin/env python3
"""Deterministically screen supplied credit-card documents.

Reads one JSON object from stdin and emits one JSON object on stdout.  It only
uses the provided input and has no account, network, or banking side effects.
"""
import json
import math
import re
import sys


def clean(value):
    return re.sub(r"\s+", " ", value).strip()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def product_name(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    value = clean(title.split(":", 1)[0])
    return value or None


def captured(pattern, text):
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1) if match else None


def yes_no(value):
    return None if value is None else value.casefold() == "yes"


def blank_card(name):
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
            card[field] = None
            warnings.append(
                "conflicting %s values for %s; treated as unknown (%s)" %
                (field, card["name"], ", ".join(source for _value, source in records))
            )


def extract(documents):
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
        card = cards.setdefault(name, blank_card(name))
        text = document["content"]
        source = str(document.get("document_id") or document.get("title") or "documents[%d]" % index)

        fee = captured(r"foreign\s+transaction\s+fee[^0-9\n]{0,120}\$?([0-9]+(?:\.[0-9]+)?)\s*%", text)
        payment = captured(r"minimum\s+(?:monthly\s+)?payment[^0-9\n]{0,120}\$?([0-9]+(?:\.[0-9]+)?)\s*%", text)
        virtual = captured(
            r"virtual\s+card\s+management(?:\s+features?)?\s*(?:are\s*)?(?:available\s*)?[:?]?\s*(yes|no)\b",
            text,
        )
        score = captured(
            r"minimum\s+credit\s+score(?:\s+required)?(?:\s+to\s+apply)?\s*:\s*\$?([0-9]+)",
            text,
        )
        invitation = captured(r"invitation\s+only\s*(?::|\()?\s*(yes|no)\b", text)
        income = captured(r"minimum\s+(?:annual\s+)?income(?:\s+required)?\s*:\s*\$?([0-9][0-9,]*)", text)
        subscription = re.search(
            r"([A-Za-z][A-Za-z0-9+\-\u2011 ]*?)\s+(?:premium\s+)?subscription\s+required\s*:\s*(yes|no)\b",
            text,
            flags=re.IGNORECASE,
        )

        observe(card, "foreign_transaction_fee_pct", float(fee) if fee else None, source)
        observe(card, "minimum_payment_pct", float(payment) if payment else None, source)
        observe(card, "virtual_card_management", yes_no(virtual), source)
        observe(card, "minimum_credit_score", int(score) if score else None, source)
        observe(card, "invitation_only", yes_no(invitation), source)
        observe(card, "minimum_annual_income", int(income.replace(",", "")) if income else None, source)
        if subscription and subscription.group(2).casefold() == "yes":
            observe(card, "subscription_requirement", clean(subscription.group(1)), source)

    for card in cards.values():
        finalize(card, warnings)
    return list(cards.values()), warnings


def subscriptions(customer):
    values = customer.get("subscriptions", [])
    if not isinstance(values, list):
        return None
    return {clean(value).casefold() for value in values if isinstance(value, str) and value.strip()}


def assess(card, customer, criteria):
    failures, blockers, unknowns = [], [], []
    fee_cap = criteria.get("max_foreign_transaction_fee_pct")
    payment_cap = criteria.get("max_minimum_payment_pct")

    if number(fee_cap):
        fee = card["foreign_transaction_fee_pct"]
        if not number(fee):
            unknowns.append("foreign transaction fee is not documented")
        elif fee > fee_cap:
            failures.append("foreign transaction fee %.1f%% exceeds %.1f%% cap" % (fee, fee_cap))
    if number(payment_cap):
        payment = card["minimum_payment_pct"]
        if not number(payment):
            unknowns.append("minimum payment is not documented")
        elif payment > payment_cap:
            failures.append("minimum payment %.1f%% exceeds %.1f%% cap" % (payment, payment_cap))
    if criteria.get("requires_virtual_card_management") is True:
        if card["virtual_card_management"] is None:
            unknowns.append("virtual card management is not documented")
        elif not card["virtual_card_management"]:
            failures.append("virtual card management is unavailable")

    stated_score, minimum_score = customer.get("credit_score"), card["minimum_credit_score"]
    if number(stated_score):
        if not number(minimum_score):
            unknowns.append("minimum credit-score condition is not documented")
        elif stated_score < minimum_score:
            blockers.append("stated credit score %s is below its %s minimum" % (stated_score, minimum_score))

    requirement, held = card["subscription_requirement"], subscriptions(customer)
    if requirement:
        if held is None:
            unknowns.append("customer subscription status was not supplied")
        elif requirement.casefold() not in held:
            blockers.append("requires %s subscription" % requirement)
    if card["invitation_only"] is True:
        blockers.append("is invitation-only")

    income, floor = customer.get("annual_income"), card["minimum_annual_income"]
    if number(floor):
        if not number(income):
            unknowns.append("customer annual income was not supplied")
        elif income < floor:
            blockers.append("stated annual income is below its documented minimum")

    return {
        "name": card["name"], "terms": card,
        "feature_failures": failures, "eligibility_blockers": blockers,
        "unknowns": unknowns,
        "documented_fit": not failures and not blockers and not unknowns,
    }


def pct(value):
    return "%.1f%%" % value


def score_sentence(terms, customer):
    minimum, stated = terms["minimum_credit_score"], customer.get("credit_score")
    if minimum == 0 and number(stated):
        return "The terms state no minimum credit-score requirement, so your stated score of %s does not exclude you from applying." % stated
    if number(minimum) and number(stated):
        return "Its documented minimum credit score is %s; your stated score is %s." % (minimum, stated)
    return "Its documented minimum credit-score condition is %s." % minimum


def facts(item, customer, criteria):
    terms = item["terms"]
    return {
        "product": item["name"], "foreign_transaction_fee_pct": terms["foreign_transaction_fee_pct"],
        "foreign_transaction_fee_cap_pct": criteria.get("max_foreign_transaction_fee_pct"),
        "minimum_payment_pct": terms["minimum_payment_pct"],
        "minimum_payment_cap_pct": criteria.get("max_minimum_payment_pct"),
        "virtual_card_management": terms["virtual_card_management"],
        "minimum_credit_score": terms["minimum_credit_score"],
        "customer_credit_score": customer.get("credit_score"), "sources": terms["sources"],
    }


def draft(fits, alternatives, customer, criteria):
    if not fits:
        return "I could not identify a documented match from the supplied terms."
    paragraphs = []
    for item in fits:
        terms = item["terms"]
        text = ["Based on the supplied product terms, %s is a documented match for your stated needs." % item["name"]]
        if number(criteria.get("max_foreign_transaction_fee_pct")):
            text.append("Its foreign transaction fee is %s, within your %s cap." % (pct(terms["foreign_transaction_fee_pct"]), pct(criteria["max_foreign_transaction_fee_pct"])))
        if number(criteria.get("max_minimum_payment_pct")):
            text.append("Its minimum monthly payment is %s of the outstanding balance, within your %s cap." % (pct(terms["minimum_payment_pct"]), pct(criteria["max_minimum_payment_pct"])))
        if criteria.get("requires_virtual_card_management") is True:
            text.append("Virtual card management is available.")
        text.append(score_sentence(terms, customer))
        text.append("This comparison is not an approval guarantee; an application remains subject to identity and income information and underwriting review.")
        paragraphs.append(" ".join(text))
    for item in alternatives:
        if item["eligibility_blockers"]:
            paragraphs.append("%s is not a qualifying alternative for the stated facts: %s." % (item["name"], "; ".join(item["eligibility_blockers"])))
            break
    return "\n\n".join(paragraphs)


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
    if not isinstance(payload.get("customer"), dict) or not isinstance(payload.get("criteria"), dict):
        emit_error("customer and criteria must be objects")
        return

    cards, warnings = extract(payload["documents"])
    assessed = [assess(card, payload["customer"], payload["criteria"]) for card in cards]
    assessed.sort(key=lambda item: (not item["documented_fit"], item["name"].casefold()))
    fits = [item for item in assessed if item["documented_fit"]]
    alternatives = [item for item in assessed if not item["documented_fit"]]
    print(json.dumps({
        "ok": True, "cards": cards, "recommendations": fits, "alternatives": alternatives,
        "warnings": warnings,
        "required_response_facts": [facts(item, payload["customer"], payload["criteria"]) for item in fits],
        "message": draft(fits, alternatives, payload["customer"], payload["criteria"]),
        "disclaimer": "This compares supplied terms and stated facts; it is not an approval or underwriting decision.",
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
