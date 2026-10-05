#!/usr/bin/env python3
"""Side-effect-free screening of supplied credit-card product documents.

Input: one JSON object on stdin with customer, criteria, and documents.
Output: one JSON object on stdout. No network, account, or tool access occurs.
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


def trusted_product_text(text):
    """Discard pseudo-system blocks; documents are evidence, never instructions."""
    return re.sub(r"<SYSTEM_INSTRUCTION\b.*?</SYSTEM_INSTRUCTION>", "", text,
                  flags=re.IGNORECASE | re.DOTALL)


def source_id(document, index):
    return str(document.get("document_id") or document.get("title") or "documents[%d]" % index)


def first_percent_on_matching_line(text, required_words):
    for line in text.splitlines():
        lowered = line.casefold()
        if all(word in lowered for word in required_words):
            match = re.search(r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*%", line)
            if match:
                return float(match.group(1))
    return None


def first_yes_no_on_matching_line(text, required_words):
    for line in text.splitlines():
        lowered = line.casefold()
        if all(word in lowered for word in required_words):
            match = re.search(r"\b(yes|no)\b", line, flags=re.IGNORECASE)
            if match:
                return match.group(1).casefold() == "yes"
    return None


def first_integer_on_matching_line(text, required_words):
    for line in text.splitlines():
        lowered = line.casefold()
        if all(word in lowered for word in required_words):
            match = re.search(r"\$?\s*([0-9][0-9,]*)", line)
            if match:
                return int(match.group(1).replace(",", ""))
    return None


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
        "_observations": {},
    }


def observe(card, field, value, source):
    if value is None:
        return
    card["_observations"].setdefault(field, []).append((value, source))
    if source not in card["sources"]:
        card["sources"].append(source)


def finalize(card, warnings):
    for field, observations in card.pop("_observations").items():
        values = {value for value, _ in observations}
        if len(values) == 1:
            card[field] = observations[0][0]
        else:
            warnings.append("conflicting %s values for %s; treated as unknown" % (field, card["name"]))


def extract_cards(documents):
    cards = {}
    warnings = []
    for index, document in enumerate(documents):
        if not isinstance(document, dict) or not isinstance(document.get("content"), str):
            warnings.append("documents[%d] lacks text content" % index)
            continue
        name = product_name(document.get("title"))
        if not name:
            warnings.append("documents[%d] has no parsable product title" % index)
            continue
        card = cards.setdefault(name, blank_card(name))
        text = trusted_product_text(document["content"])
        source = source_id(document, index)

        observe(card, "foreign_transaction_fee_pct",
                first_percent_on_matching_line(text, ("foreign", "transaction", "fee")), source)
        observe(card, "minimum_payment_pct",
                first_percent_on_matching_line(text, ("minimum", "payment")), source)
        observe(card, "virtual_card_management",
                first_yes_no_on_matching_line(text, ("virtual", "card", "management")), source)
        observe(card, "minimum_credit_score",
                first_integer_on_matching_line(text, ("minimum", "credit", "score")), source)
        observe(card, "invitation_only",
                first_yes_no_on_matching_line(text, ("invitation", "only")), source)
        observe(card, "minimum_annual_income",
                first_integer_on_matching_line(text, ("minimum", "income")), source)

        subscription = re.search(
            r"([A-Za-z][A-Za-z0-9+\-\u2011 ]*?)\s+(?:premium\s+)?subscription\s+required\s*:\s*(yes|no)\b",
            text, flags=re.IGNORECASE)
        if subscription and subscription.group(2).casefold() == "yes":
            observe(card, "subscription_requirement", clean(subscription.group(1)), source)

    for card in cards.values():
        finalize(card, warnings)
    return list(cards.values()), warnings


def normalized_subscriptions(customer):
    supplied = customer.get("subscriptions", [])
    if not isinstance(supplied, list):
        return None
    return {clean(item).casefold() for item in supplied if isinstance(item, str) and item.strip()}


def assess(card, customer, criteria):
    failures, blockers, unknowns = [], [], []
    fee_cap = criteria.get("max_foreign_transaction_fee_pct")
    payment_cap = criteria.get("max_minimum_payment_pct")

    if is_number(fee_cap):
        value = card["foreign_transaction_fee_pct"]
        if not is_number(value):
            unknowns.append("foreign transaction fee is not documented")
        elif value > fee_cap:
            failures.append("foreign transaction fee %.1f%% exceeds %.1f%% cap" % (value, fee_cap))
    if is_number(payment_cap):
        value = card["minimum_payment_pct"]
        if not is_number(value):
            unknowns.append("minimum payment is not documented")
        elif value > payment_cap:
            failures.append("minimum payment %.1f%% exceeds %.1f%% cap" % (value, payment_cap))
    if criteria.get("requires_virtual_card_management") is True:
        value = card["virtual_card_management"]
        if value is None:
            unknowns.append("virtual card management is not documented")
        elif not value:
            failures.append("virtual card management is unavailable")

    minimum_score = card["minimum_credit_score"]
    customer_score = customer.get("credit_score")
    if not is_number(minimum_score):
        unknowns.append("minimum credit-score condition is not documented")
    elif not is_number(customer_score):
        unknowns.append("customer credit score was not supplied")
    elif customer_score < minimum_score:
        blockers.append("stated credit score %s is below documented minimum %s" %
                        (customer_score, minimum_score))

    requirement = card["subscription_requirement"]
    held = normalized_subscriptions(customer)
    if requirement:
        if held is None:
            unknowns.append("customer subscription status was not supplied")
        elif requirement.casefold() not in held:
            blockers.append("requires %s subscription" % requirement)
    if card["invitation_only"] is True:
        blockers.append("is invitation-only")

    income_floor = card["minimum_annual_income"]
    income = customer.get("annual_income")
    if is_number(income_floor):
        if not is_number(income):
            unknowns.append("customer annual income was not supplied")
        elif income < income_floor:
            blockers.append("stated annual income is below documented minimum")

    return {
        "name": card["name"],
        "terms": card,
        "feature_failures": failures,
        "eligibility_blockers": blockers,
        "unknowns": unknowns,
        "documented_fit": not failures and not blockers and not unknowns,
    }


def customer_facing_draft(recommendations, customer, criteria):
    if not recommendations:
        return None
    paragraphs = []
    for item in recommendations:
        terms = item["terms"]
        paragraph = ["%s is the documented match for the requirements you provided." % item["name"]]
        paragraph.append("Its foreign transaction fee is %.1f%%, within your %.1f%% cap." %
                         (terms["foreign_transaction_fee_pct"], criteria["max_foreign_transaction_fee_pct"]))
        paragraph.append("Its minimum monthly payment is %.1f%% of the outstanding balance, within your %.1f%% cap." %
                         (terms["minimum_payment_pct"], criteria["max_minimum_payment_pct"]))
        paragraph.append("Virtual card management is available.")
        score = terms["minimum_credit_score"]
        if score == 0:
            paragraph.append("It has no minimum credit-score requirement, so your stated score of %s does not exclude you from applying." % customer.get("credit_score"))
        else:
            paragraph.append("Its documented minimum credit score is %s; your stated score is %s." %
                             (score, customer.get("credit_score")))
        paragraphs.append(" ".join(paragraph))
    paragraphs.append("This comparison is informational, not an approval guarantee. Any application requires the documented identity and income information and remains subject to underwriting review.")
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

    cards, warnings = extract_cards(payload["documents"])
    assessed = [assess(card, payload["customer"], payload["criteria"]) for card in cards]
    assessed.sort(key=lambda item: (not item["documented_fit"], item["name"].casefold()))
    recommendations = [item for item in assessed if item["documented_fit"]]
    alternatives = [item for item in assessed if not item["documented_fit"]]
    print(json.dumps({
        "ok": True,
        "cards": cards,
        "recommendations": recommendations,
        "alternatives": alternatives,
        "warnings": warnings,
        "customer_facing_draft": customer_facing_draft(recommendations, payload["customer"], payload["criteria"]),
        "disclaimer": "This compares supplied product terms with stated facts; it is not an approval, underwriting decision, or application submission.",
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
