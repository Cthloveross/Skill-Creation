#!/usr/bin/env python3
"""Screen supplied credit-card documents and draft a source-backed comparison.

Reads one JSON object from stdin and writes one JSON object to stdout.  See SKILL.md
for the input schema.  The program has no network, account, or banking side effects.
"""
import json
import math
import re
import sys


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def card_name(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    value = title.split(":", 1)[0].strip()
    return value or None


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
    }


def add(card, key, value, source, warnings):
    if value is None:
        return
    old = card[key]
    if old is None:
        card[key] = value
    elif old != value:
        card[key] = None
        warnings.append("conflicting %s values for %s; value treated as unknown" % (key, card["name"]))
    if source not in card["sources"]:
        card["sources"].append(source)


def one(pattern, text):
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1) if match else None


def extract(documents):
    grouped, warnings = {}, []
    for index, doc in enumerate(documents):
        if not isinstance(doc, dict) or not isinstance(doc.get("content"), str):
            warnings.append("documents[%d] lacks text content" % index)
            continue
        name = card_name(doc.get("title"))
        if name is None:
            continue
        card = grouped.setdefault(name, empty_card(name))
        text = doc["content"]
        source = str(doc.get("document_id") or doc.get("title") or "documents[%d]" % index)

        fee = one(r"foreign\s+transaction\s+fee[^:\n]*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%", text)
        payment = one(r"minimum\s+(?:monthly\s+)?payment\s*(?:is|:)[^0-9\n]*\$?([0-9]+(?:\.[0-9]+)?)\s*%", text)
        virtual = one(r"virtual\s+card\s+management(?:\s+features)?\s+(?:are\s+)?(?:available\s*)?:?\s*(yes|no)", text)
        score = one(r"minimum\s+credit\s+score(?:\s+required)?(?:\s+to\s+apply)?\s*:\s*\$?([0-9]+)", text)
        invite = one(r"invitation\s+only\s*\(?\s*:\s*\)?\s*(yes|no)", text)
        income = one(r"minimum\s+(?:annual\s+)?income(?:\s+required)?\s*:\s*\$?([0-9][0-9,]*)", text)
        subscription = re.search(
            r"([A-Za-z][A-Za-z0-9+\-\u2011 ]*?)\s+(?:premium\s+)?subscription\s+required\s*:\s*(yes|no)",
            text, flags=re.IGNORECASE)

        if fee is not None:
            add(card, "foreign_transaction_fee_pct", float(fee), source, warnings)
        if payment is not None:
            add(card, "minimum_payment_pct", float(payment), source, warnings)
        if virtual is not None:
            add(card, "virtual_card_management", virtual.casefold() == "yes", source, warnings)
        if score is not None:
            add(card, "minimum_credit_score", int(score), source, warnings)
        if invite is not None:
            add(card, "invitation_only", invite.casefold() == "yes", source, warnings)
        if income is not None:
            add(card, "minimum_annual_income", int(income.replace(",", "")), source, warnings)
        if subscription is not None:
            requirement = None if subscription.group(2).casefold() == "no" else subscription.group(1).strip()
            add(card, "subscription_requirement", requirement, source, warnings)
    return list(grouped.values()), warnings


def subscriptions(customer):
    values = customer.get("subscriptions", [])
    if not isinstance(values, list):
        return None
    return {x.strip().casefold() for x in values if isinstance(x, str) and x.strip()}


def assess(card, customer, criteria):
    failures, blockers, unknowns = [], [], []
    fee_cap = criteria.get("max_foreign_transaction_fee_pct")
    pay_cap = criteria.get("max_minimum_payment_pct")
    fee = card["foreign_transaction_fee_pct"]
    payment = card["minimum_payment_pct"]

    if number(fee_cap):
        if not number(fee):
            unknowns.append("foreign transaction fee is not documented")
        elif fee > fee_cap:
            failures.append("foreign transaction fee %.1f%% exceeds %.1f%% cap" % (fee, fee_cap))
    if number(pay_cap):
        if not number(payment):
            unknowns.append("minimum payment is not documented")
        elif payment > pay_cap:
            failures.append("minimum payment %.1f%% exceeds %.1f%% cap" % (payment, pay_cap))
    if criteria.get("requires_virtual_card_management") is True:
        if card["virtual_card_management"] is None:
            unknowns.append("virtual card management is not documented")
        elif card["virtual_card_management"] is False:
            failures.append("virtual card management is unavailable")

    stated_score = customer.get("credit_score")
    minimum_score = card["minimum_credit_score"]
    if number(minimum_score) and number(stated_score) and stated_score < minimum_score:
        blockers.append("stated credit score %s is below its %s minimum" % (stated_score, minimum_score))
    elif number(minimum_score) and not number(stated_score):
        unknowns.append("customer credit score was not supplied")

    requirement = card["subscription_requirement"]
    held = subscriptions(customer)
    if requirement:
        if held is None:
            unknowns.append("customer subscription status was not supplied")
        elif requirement.casefold() not in held:
            blockers.append("requires %s subscription" % requirement)
    if card["invitation_only"] is True:
        blockers.append("is invitation-only")
    minimum_income = card["minimum_annual_income"]
    income = customer.get("annual_income")
    if number(minimum_income) and number(income) and income < minimum_income:
        blockers.append("stated income is below its documented minimum")

    return {
        "name": card["name"], "terms": card, "feature_failures": failures,
        "eligibility_blockers": blockers, "unknowns": unknowns,
        "documented_fit": not failures and not blockers and not unknowns,
    }


def pct(value):
    return "%.1f%%" % value


def score_explanation(terms, customer):
    score = terms["minimum_credit_score"]
    stated = customer.get("credit_score")
    if score == 0 and number(stated):
        return "The terms state no minimum credit-score requirement, so your stated score of %s does not exclude you from applying." % stated
    if number(score) and number(stated):
        return "Its documented minimum credit score is %s, and your stated score is %s." % (score, stated)
    if number(score):
        return "Its documented minimum credit score is %s." % score
    return "The supplied terms do not document a minimum credit-score requirement."


def draft(fits, alternatives, criteria, customer):
    if fits:
        paragraphs = []
        for item in fits:
            terms = item["terms"]
            sentence = ["Based on the supplied product terms, %s is a documented match for your stated needs." % item["name"]]
            if number(criteria.get("max_foreign_transaction_fee_pct")):
                sentence.append("Its foreign transaction fee is %s, within your %s cap." % (pct(terms["foreign_transaction_fee_pct"]), pct(criteria["max_foreign_transaction_fee_pct"])))
            if number(criteria.get("max_minimum_payment_pct")):
                sentence.append("Its minimum monthly payment is %s of the outstanding balance, within your %s cap." % (pct(terms["minimum_payment_pct"]), pct(criteria["max_minimum_payment_pct"])))
            if criteria.get("requires_virtual_card_management") is True:
                sentence.append("Virtual card management is available.")
            sentence.append(score_explanation(terms, customer))
            sentence.append("This is not an approval guarantee; an application remains subject to identity and income information and underwriting review.")
            paragraphs.append(" ".join(sentence))
        message = "\n\n".join(paragraphs)
        blocked = [x for x in alternatives if x["eligibility_blockers"]]
        if blocked:
            x = blocked[0]
            message += "\n\n%s is not a qualifying alternative for the stated facts: %s." % (x["name"], "; ".join(x["eligibility_blockers"]))
        return message
    reasons = []
    for item in alternatives:
        detail = item["feature_failures"] + item["eligibility_blockers"] + item["unknowns"]
        if detail:
            reasons.append("%s: %s" % (item["name"], "; ".join(detail)))
    return "I could not identify a documented match from the supplied terms. " + (" ".join(reasons) if reasons else "Required product facts are incomplete.")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["stdin must contain one JSON object: %s" % exc]}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        print(json.dumps({"ok": False, "errors": ["documents must be a list"]}))
        return
    if not isinstance(payload.get("customer"), dict) or not isinstance(payload.get("criteria"), dict):
        print(json.dumps({"ok": False, "errors": ["customer and criteria must be objects"]}))
        return
    cards, warnings = extract(payload["documents"])
    assessed = [assess(card, payload["customer"], payload["criteria"]) for card in cards]
    assessed.sort(key=lambda x: (not x["documented_fit"], x["name"].casefold()))
    fits = [x for x in assessed if x["documented_fit"]]
    alternatives = [x for x in assessed if not x["documented_fit"]]
    print(json.dumps({
        "ok": True, "cards": cards, "recommendations": fits,
        "alternatives": alternatives, "warnings": warnings,
        "message": draft(fits, alternatives, payload["criteria"], payload["customer"]),
        "disclaimer": "This compares supplied terms and stated facts; it is not an approval or underwriting decision."
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
