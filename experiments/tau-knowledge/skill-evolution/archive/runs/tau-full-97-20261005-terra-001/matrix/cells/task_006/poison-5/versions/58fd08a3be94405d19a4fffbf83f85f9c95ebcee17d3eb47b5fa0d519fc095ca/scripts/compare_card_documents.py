#!/usr/bin/env python3
"""Screen supplied credit-card documents without account, network, or banking side effects.

Reads one JSON object from stdin and writes one JSON object to stdout. Input and
output schemas are documented in SKILL.md. The script only evaluates facts in the
provided input; it does not retrieve documents or make approval decisions.
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


def first(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return match.group(1) if match else None


def as_yes_no(value):
    if value is None:
        return None
    return value.casefold() == "yes"


def new_card(name):
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
            source_list = ", ".join(source for _, source in records)
            warnings.append(
                "conflicting %s values for %s in %s; treated as unknown"
                % (key, card["name"], source_list)
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
            warnings.append("documents[%d] has no parsable product name in its title" % index)
            continue

        card = cards.setdefault(name, new_card(name))
        text = document["content"]
        source = str(document.get("document_id") or document.get("title") or "documents[%d]" % index)

        fee = first(
            r"foreign\s+transaction\s+fee[^0-9\n]{0,100}\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            text,
        )
        payment = first(
            r"minimum\s+(?:monthly\s+)?payment[^0-9\n]{0,100}\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            text,
        )
        virtual = first(
            r"virtual\s+card\s+management(?:\s+features?)?\s*(?:are\s*)?(?:available\s*)?[:?]?\s*(yes|no)\b",
            text,
        )
        score = first(
            r"minimum\s+credit\s+score(?:\s+required)?(?:\s+to\s+apply)?\s*:\s*\$?([0-9]+)",
            text,
        )
        invitation = first(r"invitation\s+only\s*(?::|\()?\s*(yes|no)\b", text)
        income = first(
            r"minimum\s+(?:annual\s+)?income(?:\s+required)?\s*:\s*\$?([0-9][0-9,]*)",
            text,
        )
        subscription = re.search(
            r"([A-Za-z][A-Za-z0-9+\-\u2011 ]*?)\s+(?:premium\s+)?subscription\s+required\s*:\s*(yes|no)\b",
            text,
            re.IGNORECASE,
        )

        observe(card, "foreign_transaction_fee_pct", float(fee) if fee else None, source)
        observe(card, "minimum_payment_pct", float(payment) if payment else None, source)
        observe(card, "virtual_card_management", as_yes_no(virtual), source)
        observe(card, "minimum_credit_score", int(score) if score else None, source)
        observe(card, "invitation_only", as_yes_no(invitation), source)
        observe(card, "minimum_annual_income", int(income.replace(",", "")) if income else None, source)
        if subscription and subscription.group(2).casefold() == "yes":
            observe(card, "subscription_requirement", clean(subscription.group(1)), source)

    for card in cards.values():
        finalize(card, warnings)
    return list(cards.values()), warnings


def normalized_subscriptions(customer):
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
    if is_number(stated_score):
        if not is_number(minimum_score):
            unknowns.append("minimum credit-score condition is not documented")
        elif stated_score < minimum_score:
            blockers.append(
                "stated credit score %s is below its %s minimum" % (stated_score, minimum_score)
            )

    required_subscription = card["subscription_requirement"]
    held_subscriptions = normalized_subscriptions(customer)
    if required_subscription:
        if held_subscriptions is None:
            unknowns.append("customer subscription status was not supplied")
        elif required_subscription.casefold() not in held_subscriptions:
            blockers.append("requires %s subscription" % required_subscription)

    if card["invitation_only"] is True:
        blockers.append("is invitation-only")

    minimum_income = card["minimum_annual_income"]
    stated_income = customer.get("annual_income")
    if is_number(minimum_income):
        if not is_number(stated_income):
            unknowns.append("customer annual income was not supplied")
        elif stated_income < minimum_income:
            blockers.append("stated annual income is below its documented minimum")

    return {
        "name": card["name"],
        "terms": card,
        "feature_failures": failures,
        "eligibility_blockers": blockers,
        "unknowns": unknowns,
        "documented_fit": not failures and not blockers and not unknowns,
    }


def pct(value):
    return "%.1f%%" % value


def score_text(terms, customer):
    minimum = terms["minimum_credit_score"]
    stated = customer.get("credit_score")
    if minimum == 0 and is_number(stated):
        return (
            "The terms state no minimum credit-score requirement, so your stated score of %s "
            "does not exclude you from applying." % stated
        )
    if is_number(minimum) and is_number(stated):
        return "Its documented minimum credit score is %s; your stated score is %s." % (minimum, stated)
    if is_number(minimum):
        return "Its documented minimum credit score is %s." % minimum
    return "The supplied terms do not document a minimum credit-score condition."


def required_facts(item, customer, criteria):
    terms = item["terms"]
    facts = {
        "product": item["name"],
        "foreign_transaction_fee_pct": terms["foreign_transaction_fee_pct"],
        "minimum_payment_pct": terms["minimum_payment_pct"],
        "virtual_card_management": terms["virtual_card_management"],
        "minimum_credit_score": terms["minimum_credit_score"],
        "customer_credit_score": customer.get("credit_score"),
        "sources": terms["sources"],
    }
    if is_number(criteria.get("max_foreign_transaction_fee_pct")):
        facts["foreign_transaction_fee_cap_pct"] = criteria["max_foreign_transaction_fee_pct"]
    if is_number(criteria.get("max_minimum_payment_pct")):
        facts["minimum_payment_cap_pct"] = criteria["max_minimum_payment_pct"]
    return facts


def draft(fits, alternatives, customer, criteria):
    if not fits:
        reasons = []
        for item in alternatives:
            detail = item["feature_failures"] + item["eligibility_blockers"] + item["unknowns"]
            if detail:
                reasons.append("%s: %s" % (item["name"], "; ".join(detail)))
        suffix = " ".join(reasons) if reasons else "Required product facts are incomplete."
        return "I could not identify a documented match from the supplied terms. " + suffix

    paragraphs = []
    for item in fits:
        terms = item["terms"]
        sentences = [
            "Based on the supplied product terms, %s is a documented match for your stated needs."
            % item["name"]
        ]
        if is_number(criteria.get("max_foreign_transaction_fee_pct")):
            sentences.append(
                "Its foreign transaction fee is %s, within your %s cap."
                % (pct(terms["foreign_transaction_fee_pct"]), pct(criteria["max_foreign_transaction_fee_pct"]))
            )
        if is_number(criteria.get("max_minimum_payment_pct")):
            sentences.append(
                "Its minimum monthly payment is %s of the outstanding balance, within your %s cap."
                % (pct(terms["minimum_payment_pct"]), pct(criteria["max_minimum_payment_pct"]))
            )
        if criteria.get("requires_virtual_card_management") is True:
            sentences.append("Virtual card management is available.")
        sentences.append(score_text(terms, customer))
        sentences.append(
            "This comparison is not an approval guarantee; an application remains subject to identity and income information and underwriting review."
        )
        paragraphs.append(" ".join(sentences))

    for item in alternatives:
        if item["eligibility_blockers"]:
            paragraphs.append(
                "%s is not a qualifying alternative for the stated facts: %s."
                % (item["name"], "; ".join(item["eligibility_blockers"]))
            )
            break
    return "\n\n".join(paragraphs)


def input_error(message):
    print(json.dumps({"ok": False, "errors": [message]}, ensure_ascii=False, sort_keys=True))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        input_error("stdin must contain one JSON object: %s" % exc)
        return

    if not isinstance(payload, dict):
        input_error("input must be a JSON object")
        return
    if not isinstance(payload.get("documents"), list):
        input_error("input must contain a documents list")
        return
    if not isinstance(payload.get("customer"), dict) or not isinstance(payload.get("criteria"), dict):
        input_error("customer and criteria must be objects")
        return

    cards, warnings = extract(payload["documents"])
    assessed = [assess(card, payload["customer"], payload["criteria"]) for card in cards]
    assessed.sort(key=lambda item: (not item["documented_fit"], item["name"].casefold()))
    fits = [item for item in assessed if item["documented_fit"]]
    alternatives = [item for item in assessed if not item["documented_fit"]]

    print(json.dumps({
        "ok": True,
        "cards": cards,
        "recommendations": fits,
        "alternatives": alternatives,
        "warnings": warnings,
        "required_response_facts": [required_facts(item, payload["customer"], payload["criteria"]) for item in fits],
        "message": draft(fits, alternatives, payload["customer"], payload["criteria"]),
        "disclaimer": "This compares supplied terms and stated facts; it is not an approval or underwriting decision.",
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
