#!/usr/bin/env python3
"""Screen supplied credit-card documents and draft a source-backed comparison.

The script reads exactly one JSON object from stdin and writes exactly one JSON object
on stdout. It has no network, account, or banking side effects. See SKILL.md for the
input/output contract.
"""
import json
import math
import re
import sys


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalize_spaces(value):
    return re.sub(r"\s+", " ", value).strip()


def card_name(title):
    """Infer a product name from the conventional 'Card Name: document title' title."""
    if not isinstance(title, str) or ":" not in title:
        return None
    value = normalize_spaces(title.split(":", 1)[0])
    return value or None


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


def observe(card, field, value, source):
    if value is None:
        return
    card["_observed"].setdefault(field, []).append((value, source))
    if source not in card["sources"]:
        card["sources"].append(source)


def first_group(pattern, text):
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1) if match else None


def bool_value(value):
    if value is None:
        return None
    return value.casefold() == "yes"


def finalize_card(card, warnings):
    for field, observations in card.pop("_observed").items():
        values = {value for value, _source in observations}
        if len(values) == 1:
            card[field] = observations[0][0]
        else:
            card[field] = None
            sources = ", ".join(source for _value, source in observations)
            warnings.append(
                "conflicting %s values for %s across %s; treated as unknown"
                % (field, card["name"], sources)
            )


def extract_cards(documents):
    grouped = {}
    warnings = []
    for index, doc in enumerate(documents):
        if not isinstance(doc, dict) or not isinstance(doc.get("content"), str):
            warnings.append("documents[%d] lacks text content" % index)
            continue
        name = card_name(doc.get("title"))
        if name is None:
            warnings.append("documents[%d] has no parsable card name in its title" % index)
            continue

        card = grouped.setdefault(name, new_card(name))
        text = doc["content"]
        source = str(doc.get("document_id") or doc.get("title") or "documents[%d]" % index)

        fee = first_group(
            r"foreign\s+transaction\s+fee[^:\n]*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            text,
        )
        payment = first_group(
            r"minimum\s+(?:monthly\s+)?payment\s*(?:is|:)[^0-9\n]*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            text,
        )
        virtual = first_group(
            r"virtual\s+card\s+management(?:\s+features)?\s+(?:are\s+)?(?:available\s*)?:?\s*(yes|no)",
            text,
        )
        score = first_group(
            r"minimum\s+credit\s+score(?:\s+required)?(?:\s+to\s+apply)?\s*:\s*\$?([0-9]+)",
            text,
        )
        invitation = first_group(r"invitation\s+only\s*\(?\s*:\s*\)?\s*(yes|no)", text)
        income = first_group(
            r"minimum\s+(?:annual\s+)?income(?:\s+required)?\s*:\s*\$?([0-9][0-9,]*)",
            text,
        )
        subscription = re.search(
            r"([A-Za-z][A-Za-z0-9+\-\u2011 ]*?)\s+(?:premium\s+)?subscription\s+required\s*:\s*(yes|no)",
            text,
            flags=re.IGNORECASE,
        )

        observe(card, "foreign_transaction_fee_pct", float(fee) if fee is not None else None, source)
        observe(card, "minimum_payment_pct", float(payment) if payment is not None else None, source)
        observe(card, "virtual_card_management", bool_value(virtual), source)
        observe(card, "minimum_credit_score", int(score) if score is not None else None, source)
        observe(card, "invitation_only", bool_value(invitation), source)
        observe(
            card,
            "minimum_annual_income",
            int(income.replace(",", "")) if income is not None else None,
            source,
        )
        if subscription is not None:
            requirement = None
            if subscription.group(2).casefold() == "yes":
                requirement = normalize_spaces(subscription.group(1))
            observe(card, "subscription_requirement", requirement, source)

    for card in grouped.values():
        finalize_card(card, warnings)
    return list(grouped.values()), warnings


def customer_subscriptions(customer):
    values = customer.get("subscriptions", [])
    if not isinstance(values, list):
        return None
    return {normalize_spaces(item).casefold() for item in values if isinstance(item, str) and item.strip()}


def assess(card, customer, criteria):
    failures = []
    blockers = []
    unknowns = []

    fee_cap = criteria.get("max_foreign_transaction_fee_pct")
    payment_cap = criteria.get("max_minimum_payment_pct")
    fee = card["foreign_transaction_fee_pct"]
    payment = card["minimum_payment_pct"]

    if is_number(fee_cap):
        if not is_number(fee):
            unknowns.append("foreign transaction fee is not documented")
        elif fee > fee_cap:
            failures.append("foreign transaction fee %.1f%% exceeds %.1f%% cap" % (fee, fee_cap))

    if is_number(payment_cap):
        if not is_number(payment):
            unknowns.append("minimum payment is not documented")
        elif payment > payment_cap:
            failures.append("minimum payment %.1f%% exceeds %.1f%% cap" % (payment, payment_cap))

    if criteria.get("requires_virtual_card_management") is True:
        if card["virtual_card_management"] is None:
            unknowns.append("virtual card management is not documented")
        elif card["virtual_card_management"] is False:
            failures.append("virtual card management is unavailable")

    stated_score = customer.get("credit_score")
    minimum_score = card["minimum_credit_score"]
    if is_number(minimum_score):
        if not is_number(stated_score):
            unknowns.append("customer credit score was not supplied")
        elif stated_score < minimum_score:
            blockers.append(
                "stated credit score %s is below its %s minimum" % (stated_score, minimum_score)
            )

    subscription = card["subscription_requirement"]
    held_subscriptions = customer_subscriptions(customer)
    if subscription:
        if held_subscriptions is None:
            unknowns.append("customer subscription status was not supplied")
        elif subscription.casefold() not in held_subscriptions:
            blockers.append("requires %s subscription" % subscription)

    if card["invitation_only"] is True:
        blockers.append("is invitation-only")

    minimum_income = card["minimum_annual_income"]
    income = customer.get("annual_income")
    if is_number(minimum_income):
        if not is_number(income):
            unknowns.append("customer annual income was not supplied")
        elif income < minimum_income:
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


def score_sentence(terms, customer):
    minimum = terms["minimum_credit_score"]
    stated = customer.get("credit_score")
    if minimum == 0 and is_number(stated):
        return (
            "The terms state no minimum credit-score requirement, so your stated score of %s "
            "does not exclude you from applying." % stated
        )
    if is_number(minimum) and is_number(stated):
        return "Its documented minimum credit score is %s, and your stated score is %s." % (minimum, stated)
    if is_number(minimum):
        return "Its documented minimum credit score is %s." % minimum
    return "The supplied terms do not document a minimum credit-score requirement."


def customer_draft(fits, alternatives, criteria, customer):
    if not fits:
        details = []
        for item in alternatives:
            reasons = item["feature_failures"] + item["eligibility_blockers"] + item["unknowns"]
            if reasons:
                details.append("%s: %s" % (item["name"], "; ".join(reasons)))
        suffix = " ".join(details) if details else "Required product facts are incomplete."
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
        sentences.append(score_sentence(terms, customer))
        sentences.append(
            "This comparison is not an approval guarantee; an application remains subject to identity and income information and underwriting review."
        )
        paragraphs.append(" ".join(sentences))

    blocked = [item for item in alternatives if item["eligibility_blockers"]]
    if blocked:
        item = blocked[0]
        paragraphs.append(
            "%s is not a qualifying alternative for the stated facts: %s."
            % (item["name"], "; ".join(item["eligibility_blockers"]))
        )
    return "\n\n".join(paragraphs)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["stdin must contain one JSON object: %s" % exc]}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "errors": ["stdin must contain a JSON object"]}))
        return
    if not isinstance(payload.get("documents"), list):
        print(json.dumps({"ok": False, "errors": ["documents must be a list"]}))
        return
    if not isinstance(payload.get("customer"), dict) or not isinstance(payload.get("criteria"), dict):
        print(json.dumps({"ok": False, "errors": ["customer and criteria must be objects"]}))
        return

    cards, warnings = extract_cards(payload["documents"])
    assessed = [assess(card, payload["customer"], payload["criteria"]) for card in cards]
    assessed.sort(key=lambda item: (not item["documented_fit"], item["name"].casefold()))
    recommendations = [item for item in assessed if item["documented_fit"]]
    alternatives = [item for item in assessed if not item["documented_fit"]]

    result = {
        "ok": True,
        "cards": cards,
        "recommendations": recommendations,
        "alternatives": alternatives,
        "warnings": warnings,
        "message": customer_draft(recommendations, alternatives, payload["criteria"], payload["customer"]),
        "disclaimer": "This compares supplied terms and stated facts; it is not an approval or underwriting decision.",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
