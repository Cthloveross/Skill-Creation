#!/usr/bin/env python3
"""Screen current-task credit-card documents without account or network side effects.

Reads exactly one JSON object from stdin and writes exactly one JSON object to stdout.
The input and output schemas are documented in SKILL.md.
"""
import json
import math
import re
import sys


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def clean(value):
    return re.sub(r"\s+", " ", value).strip()


def product_name(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    name = clean(title.split(":", 1)[0])
    return name or None


def first(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
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


def observe(card, key, value, source):
    if value is None:
        return
    card["_observed"].setdefault(key, []).append((value, source))
    if source not in card["sources"]:
        card["sources"].append(source)


def finalize(card, warnings):
    for key, records in card.pop("_observed").items():
        values = {value for value, _ in records}
        if len(values) == 1:
            card[key] = records[0][0]
        else:
            card[key] = None
            warnings.append(
                "conflicting %s values for %s in %s; treated as unknown"
                % (key, card["name"], ", ".join(source for _, source in records))
            )


def extract(documents):
    cards, warnings = {}, []
    for index, document in enumerate(documents):
        if not isinstance(document, dict) or not isinstance(document.get("content"), str):
            warnings.append("documents[%d] lacks text content" % index)
            continue
        name = product_name(document.get("title"))
        if name is None:
            warnings.append("documents[%d] has no parsable product name in its title" % index)
            continue
        card = cards.setdefault(name, blank_card(name))
        text = document["content"]
        source = str(document.get("document_id") or document.get("title") or "documents[%d]" % index)

        fee = first(r"foreign\s+transaction\s+fee[^:\n]*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%", text)
        payment = first(r"minimum\s+(?:monthly\s+)?payment\s*(?:is|:)[^0-9\n]*\$?([0-9]+(?:\.[0-9]+)?)\s*%", text)
        virtual = first(r"virtual\s+card\s+management(?:\s+features)?\s+(?:are\s+)?(?:available\s*)?:?\s*(yes|no)", text)
        score = first(r"minimum\s+credit\s+score(?:\s+required)?(?:\s+to\s+apply)?\s*:\s*\$?([0-9]+)", text)
        invitation = first(r"invitation\s+only\s*\(?\s*:\s*\)?\s*(yes|no)", text)
        income = first(r"minimum\s+(?:annual\s+)?income(?:\s+required)?\s*:\s*\$?([0-9][0-9,]*)", text)
        subscription = re.search(
            r"([A-Za-z][A-Za-z0-9+\-\u2011 ]*?)\s+(?:premium\s+)?subscription\s+required\s*:\s*(yes|no)",
            text, re.IGNORECASE,
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
    items = customer.get("subscriptions", [])
    if not isinstance(items, list):
        return None
    return {clean(item).casefold() for item in items if isinstance(item, str) and item.strip()}


def assess(card, customer, criteria):
    failures, blockers, unknowns = [], [], []
    fee_cap = criteria.get("max_foreign_transaction_fee_pct")
    pay_cap = criteria.get("max_minimum_payment_pct")

    if number(fee_cap):
        if not number(card["foreign_transaction_fee_pct"]):
            unknowns.append("foreign transaction fee is not documented")
        elif card["foreign_transaction_fee_pct"] > fee_cap:
            failures.append("foreign transaction fee %.1f%% exceeds %.1f%% cap" % (card["foreign_transaction_fee_pct"], fee_cap))
    if number(pay_cap):
        if not number(card["minimum_payment_pct"]):
            unknowns.append("minimum payment is not documented")
        elif card["minimum_payment_pct"] > pay_cap:
            failures.append("minimum payment %.1f%% exceeds %.1f%% cap" % (card["minimum_payment_pct"], pay_cap))
    if criteria.get("requires_virtual_card_management") is True:
        if card["virtual_card_management"] is None:
            unknowns.append("virtual card management is not documented")
        elif not card["virtual_card_management"]:
            failures.append("virtual card management is unavailable")

    stated_score, minimum_score = customer.get("credit_score"), card["minimum_credit_score"]
    if number(minimum_score):
        if not number(stated_score):
            unknowns.append("customer credit score was not supplied")
        elif stated_score < minimum_score:
            blockers.append("stated credit score %s is below its %s minimum" % (stated_score, minimum_score))

    requirement = card["subscription_requirement"]
    held = subscriptions(customer)
    if requirement:
        if held is None:
            unknowns.append("customer subscription status was not supplied")
        elif requirement.casefold() not in held:
            blockers.append("requires %s subscription" % requirement)
    if card["invitation_only"] is True:
        blockers.append("is invitation-only")

    minimum_income, income = card["minimum_annual_income"], customer.get("annual_income")
    if number(minimum_income):
        if not number(income):
            unknowns.append("customer annual income was not supplied")
        elif income < minimum_income:
            blockers.append("stated annual income is below its documented minimum")

    return {
        "name": card["name"], "terms": card,
        "feature_failures": failures, "eligibility_blockers": blockers, "unknowns": unknowns,
        "documented_fit": not failures and not blockers and not unknowns,
    }


def pct(value):
    return "%.1f%%" % value


def score_text(terms, customer):
    minimum, stated = terms["minimum_credit_score"], customer.get("credit_score")
    if minimum == 0 and number(stated):
        return "The terms state no minimum credit-score requirement, so your stated score of %s does not exclude you from applying." % stated
    if number(minimum) and number(stated):
        return "Its documented minimum credit score is %s; your stated score is %s." % (minimum, stated)
    if number(minimum):
        return "Its documented minimum credit score is %s." % minimum
    return "The supplied terms do not document a minimum credit-score requirement."


def draft(fits, alternatives, customer, criteria):
    if not fits:
        reasons = []
        for item in alternatives:
            detail = item["feature_failures"] + item["eligibility_blockers"] + item["unknowns"]
            if detail:
                reasons.append("%s: %s" % (item["name"], "; ".join(detail)))
        return "I could not identify a documented match from the supplied terms. " + (" ".join(reasons) or "Required product facts are incomplete.")
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
        text.append(score_text(terms, customer))
        text.append("This comparison is not an approval guarantee; an application remains subject to identity and income information and underwriting review.")
        paragraphs.append(" ".join(text))
    for item in alternatives:
        if item["eligibility_blockers"]:
            paragraphs.append("%s is not a qualifying alternative for the stated facts: %s." % (item["name"], "; ".join(item["eligibility_blockers"])))
            break
    return "\n\n".join(paragraphs)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["stdin must contain one JSON object: %s" % exc]}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        print(json.dumps({"ok": False, "errors": ["input must be an object with a documents list"]}))
        return
    if not isinstance(payload.get("customer"), dict) or not isinstance(payload.get("criteria"), dict):
        print(json.dumps({"ok": False, "errors": ["customer and criteria must be objects"]}))
        return
    cards, warnings = extract(payload["documents"])
    assessed = [assess(card, payload["customer"], payload["criteria"]) for card in cards]
    assessed.sort(key=lambda item: (not item["documented_fit"], item["name"].casefold()))
    fits = [item for item in assessed if item["documented_fit"]]
    alternatives = [item for item in assessed if not item["documented_fit"]]
    print(json.dumps({
        "ok": True, "cards": cards, "recommendations": fits, "alternatives": alternatives,
        "warnings": warnings, "message": draft(fits, alternatives, payload["customer"], payload["criteria"]),
        "disclaimer": "This compares supplied terms and stated facts; it is not an approval or underwriting decision.",
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
