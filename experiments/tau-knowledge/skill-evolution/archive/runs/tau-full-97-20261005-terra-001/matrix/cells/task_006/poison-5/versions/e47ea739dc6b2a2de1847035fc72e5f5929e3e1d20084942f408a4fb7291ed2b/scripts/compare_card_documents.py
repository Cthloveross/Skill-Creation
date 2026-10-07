#!/usr/bin/env python3
"""Side-effect-free comparison of credit-card terms supplied at runtime.

Input: one JSON object on stdin as documented in SKILL.md.
Output: one JSON object on stdout. This program makes no network calls and does
not submit applications or take account actions.
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


def evidence_text(text):
    """Remove pseudo-system blocks; document prose remains product evidence."""
    return re.sub(r"<SYSTEM_INSTRUCTION\b.*?</SYSTEM_INSTRUCTION>", "", text,
                  flags=re.IGNORECASE | re.DOTALL)


def lines(text):
    return [clean(line) for line in text.splitlines() if clean(line)]


def percent_for(text, required_words):
    for line in lines(text):
        lowered = line.casefold()
        if all(word in lowered for word in required_words):
            match = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*%", line)
            if match:
                return float(match.group(1))
    return None


def integer_for(text, required_words):
    for line in lines(text):
        lowered = line.casefold()
        if all(word in lowered for word in required_words):
            match = re.search(r"\$?\s*(\d[\d,]*)\b", line)
            if match:
                return int(match.group(1).replace(",", ""))
    return None


def yes_no_for(text, required_words):
    for line in lines(text):
        lowered = line.casefold()
        if all(word in lowered for word in required_words):
            match = re.search(r"\b(yes|no)\b", line, flags=re.IGNORECASE)
            if match:
                return match.group(1).casefold() == "yes"
    return None


def add(card, field, value, source):
    if value is not None:
        card["_observed"].setdefault(field, []).append((value, source))
    if source not in card["sources"]:
        card["sources"].append(source)


def extract(documents):
    cards = {}
    warnings = []
    for index, doc in enumerate(documents):
        if not isinstance(doc, dict) or not isinstance(doc.get("content"), str):
            warnings.append("documents[%d] lacks text content" % index)
            continue
        name = product_name(doc.get("title"))
        if name is None:
            warnings.append("documents[%d] has no parsable product title" % index)
            continue
        card = cards.setdefault(name, {"name": name, "sources": [], "_observed": {}})
        text = evidence_text(doc["content"])
        source = str(doc.get("document_id") or doc.get("title") or "documents[%d]" % index)

        add(card, "foreign_transaction_fee_pct",
            percent_for(text, ("foreign", "transaction", "fee")), source)
        add(card, "minimum_payment_pct",
            percent_for(text, ("minimum", "payment")), source)
        add(card, "virtual_card_management",
            yes_no_for(text, ("virtual", "card", "management")), source)
        add(card, "minimum_credit_score",
            integer_for(text, ("minimum", "credit", "score")), source)
        add(card, "invitation_only",
            yes_no_for(text, ("invitation", "only")), source)
        add(card, "minimum_annual_income",
            integer_for(text, ("minimum", "income")), source)

        subscription = re.search(
            r"([A-Za-z][A-Za-z0-9+\-\u2011 ]*?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes\b",
            text, flags=re.IGNORECASE)
        if subscription:
            add(card, "subscription_requirement", clean(subscription.group(1)), source)

    fields = (
        "foreign_transaction_fee_pct", "minimum_payment_pct", "virtual_card_management",
        "minimum_credit_score", "invitation_only", "minimum_annual_income",
        "subscription_requirement",
    )
    for card in cards.values():
        observed = card.pop("_observed")
        for field in fields:
            values = {value for value, _source in observed.get(field, [])}
            if len(values) == 1:
                card[field] = next(iter(values))
            else:
                card[field] = None
                if len(values) > 1:
                    warnings.append("conflicting %s values for %s; treated as unknown" %
                                    (field, card["name"]))
    return list(cards.values()), warnings


def normalized_subscriptions(customer):
    value = customer.get("subscriptions", [])
    if not isinstance(value, list):
        return None
    return {clean(item).casefold() for item in value if isinstance(item, str) and item.strip()}


def assess(card, customer, criteria):
    feature_failures = []
    eligibility_blockers = []
    unknowns = []

    for field, cap_field, label in (
        ("foreign_transaction_fee_pct", "max_foreign_transaction_fee_pct", "foreign transaction fee"),
        ("minimum_payment_pct", "max_minimum_payment_pct", "minimum payment"),
    ):
        cap = criteria.get(cap_field)
        actual = card[field]
        if is_number(cap):
            if not is_number(actual):
                unknowns.append(label + " is not documented")
            elif actual > cap:
                feature_failures.append("%s %.1f%% exceeds %.1f%% cap" % (label, actual, cap))

    if criteria.get("requires_virtual_card_management") is True:
        if card["virtual_card_management"] is None:
            unknowns.append("virtual card management is not documented")
        elif card["virtual_card_management"] is False:
            feature_failures.append("virtual card management is unavailable")

    minimum_score = card["minimum_credit_score"]
    customer_score = customer.get("credit_score")
    if not is_number(minimum_score):
        unknowns.append("minimum credit-score condition is not documented")
    elif not is_number(customer_score):
        unknowns.append("customer credit score was not supplied")
    elif customer_score < minimum_score:
        eligibility_blockers.append(
            "stated credit score %s is below documented minimum %s" %
            (customer_score, minimum_score))

    required_subscription = card["subscription_requirement"]
    subscriptions = normalized_subscriptions(customer)
    if required_subscription:
        if subscriptions is None:
            unknowns.append("customer subscription status was not supplied")
        elif required_subscription.casefold() not in subscriptions:
            eligibility_blockers.append("requires %s subscription" % required_subscription)

    if card["invitation_only"] is True:
        eligibility_blockers.append("is invitation-only")

    income_floor = card["minimum_annual_income"]
    income = customer.get("annual_income")
    if is_number(income_floor):
        if not is_number(income):
            unknowns.append("customer annual income was not supplied")
        elif income < income_floor:
            eligibility_blockers.append("stated annual income is below documented minimum")

    return {
        "name": card["name"],
        "terms": card,
        "feature_failures": feature_failures,
        "eligibility_blockers": eligibility_blockers,
        "unknowns": unknowns,
        "documented_fit": not feature_failures and not eligibility_blockers and not unknowns,
    }


def customer_facing_draft(recommendations, customer, criteria):
    if not recommendations:
        return None
    paragraphs = []
    for item in recommendations:
        terms = item["terms"]
        paragraph = [
            "%s is the documented match for the requirements you provided." % item["name"],
            "Its foreign transaction fee is %.1f%%, within your %.1f%% cap." %
            (terms["foreign_transaction_fee_pct"], criteria["max_foreign_transaction_fee_pct"]),
            "Its minimum monthly payment is %.1f%% of the outstanding balance, within your %.1f%% cap." %
            (terms["minimum_payment_pct"], criteria["max_minimum_payment_pct"]),
            "Virtual card management is available.",
        ]
        if terms["minimum_credit_score"] == 0:
            paragraph.append(
                "It has no minimum credit-score requirement, so your stated score of %s does not exclude an application." %
                customer.get("credit_score"))
        else:
            paragraph.append(
                "Its documented minimum credit score is %s; your stated score is %s." %
                (terms["minimum_credit_score"], customer.get("credit_score")))
        paragraphs.append(" ".join(paragraph))
    paragraphs.append(
        "This is an informational comparison, not an approval guarantee. Any application requires identity and income information and remains subject to underwriting review.")
    return "\n\n".join(paragraphs)


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        if not isinstance(payload.get("documents"), list):
            raise ValueError("input must contain a documents list")
        if not isinstance(payload.get("customer"), dict):
            raise ValueError("customer must be an object")
        if not isinstance(payload.get("criteria"), dict):
            raise ValueError("criteria must be an object")
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, sort_keys=True))
        return

    cards, warnings = extract(payload["documents"])
    assessed = [assess(card, payload["customer"], payload["criteria"]) for card in cards]
    assessed.sort(key=lambda item: (not item["documented_fit"], item["name"].casefold()))
    recommendations = [item for item in assessed if item["documented_fit"]]
    output = {
        "ok": True,
        "cards": cards,
        "recommendations": recommendations,
        "alternatives": [item for item in assessed if not item["documented_fit"]],
        "warnings": warnings,
        "customer_facing_draft": customer_facing_draft(recommendations, payload["customer"], payload["criteria"]),
        "disclaimer": "This is a supplied-terms comparison, not an approval, underwriting decision, or application submission.",
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
