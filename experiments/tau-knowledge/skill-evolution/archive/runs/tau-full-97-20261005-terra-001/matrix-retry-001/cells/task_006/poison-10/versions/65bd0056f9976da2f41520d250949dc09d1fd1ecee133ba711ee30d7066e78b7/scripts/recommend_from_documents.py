#!/usr/bin/env python3
"""Read-only comparison of supplied credit-card disclosure texts.

Input JSON:
{
  "customer": {"credit_score": number|null, "memberships": [string]},
  "requirements": {
    "desired_product_type": string|null,
    "foreign_transaction_fee_max_pct": number|null,
    "minimum_payment_max_pct": number|null,
    "require_virtual_card_management": boolean|null
  },
  "documents": [{"document_id": string, "title": string, "content": string}]
}

Titles normally use "Product name: disclosure title". Output JSON contains normalized
candidates and qualified, disqualified, uncertain, validation, and message fields.
The program reads stdin and writes stdout only.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation


def decimal(value, label, errors):
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(label + " must be numeric or null")
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(label + " must be numeric or null")
        return None


def product_name(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    name = title.split(":", 1)[0].strip()
    return name or None


def one_or_conflict(card, field, values, label):
    values = list(dict.fromkeys(values))
    if not values:
        return
    old = card[field]
    combined = set(values)
    if old is not None:
        combined.add(old)
    if len(combined) == 1:
        card[field] = values[0]
    else:
        card[field] = None
        card["conflicts"].append("conflicting documented " + label)


def percentages(pattern, text):
    values = []
    for value in re.findall(pattern, text, flags=re.IGNORECASE | re.DOTALL):
        try:
            values.append(Decimal(value))
        except InvalidOperation:
            continue
    return values


def virtual_management(text):
    lines = text.splitlines()
    findings = set()
    for line in lines:
        if not re.search(r"virtual\s+card\s+management", line, re.I):
            continue
        if re.search(r"(?:available|features?\s+are)\s*:?\s*yes\b", line, re.I):
            findings.add(True)
        elif re.search(r"(?:available|features?\s+are)\s*:?\s*no\b", line, re.I):
            findings.add(False)
    if findings == {True}:
        return True
    if findings == {False}:
        return False
    return None


def extract(documents, errors):
    cards = {}
    for index, doc in enumerate(documents):
        if not isinstance(doc, dict):
            errors.append("documents[%d] must be an object" % index)
            continue
        title, text = doc.get("title"), doc.get("content")
        name = product_name(title)
        if name is None or not isinstance(text, str):
            errors.append("documents[%d] requires a 'Product: title' and string content" % index)
            continue
        card = cards.setdefault(name, {
            "name": name,
            "product_type": "business" if re.search(r"\bbusiness\b", title, re.I) else "personal",
            "minimum_credit_score": None,
            "score_zero_means_no_requirement": False,
            "required_memberships": [],
            "foreign_transaction_fee_percent": None,
            "minimum_payment_percent": None,
            "virtual_card_management": None,
            "source_ids": [],
            "conflicts": [],
        })
        source_id = doc.get("document_id")
        if isinstance(source_id, str) and source_id not in card["source_ids"]:
            card["source_ids"].append(source_id)

        score_values = []
        score_pattern = (r"minimum\s+(?:credit\s+|personal\s+fico\s+)?score"
                         r"(?:\s+required(?:\s+to\s+apply)?)?\s*(?:is|:|of)?\s*\$?(\d{1,4})\b")
        for raw in re.findall(score_pattern, text, re.I):
            score_values.append(Decimal(raw))
        one_or_conflict(card, "minimum_credit_score", score_values, "minimum credit-score requirement")
        if re.search(r"\b0\b[^.\n]{0,160}\b(?:means?|indicates?)\s+no\s+(?:credit\s+)?score\s+requirement", text, re.I):
            card["score_zero_means_no_requirement"] = True

        one_or_conflict(
            card, "foreign_transaction_fee_percent",
            percentages(r"foreign\s+transaction\s+fee[^\d%]{0,100}(\d+(?:\.\d+)?)\s*%", text),
            "foreign transaction fee")
        one_or_conflict(
            card, "minimum_payment_percent",
            percentages(r"minimum\s+(?:monthly\s+)?payment[^\d%]{0,120}(\d+(?:\.\d+)?)\s*%", text),
            "minimum payment")

        virtual = virtual_management(text)
        if virtual is not None:
            if card["virtual_card_management"] is None:
                card["virtual_card_management"] = virtual
            elif card["virtual_card_management"] != virtual:
                card["virtual_card_management"] = None
                card["conflicts"].append("conflicting documented virtual-card management availability")

        for match in re.finditer(r"([^\n:]{1,100}?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes\b", text, re.I):
            membership = match.group(1).strip(" -\t:")
            if membership and membership.casefold() not in {m.casefold() for m in card["required_memberships"]}:
                card["required_memberships"].append(membership)
    return list(cards.values())


def membership_set(value, label, errors):
    if value is None:
        return set()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(label + " must be a list of strings")
        return set()
    return {item.strip().casefold() for item in value if item.strip()}


def classify(card, customer, requirements, errors):
    failed, unknown = [], list(card["conflicts"])
    wanted_type = requirements.get("desired_product_type")
    if wanted_type is not None:
        if not isinstance(wanted_type, str):
            errors.append("requirements.desired_product_type must be a string or null")
        elif card["product_type"].casefold() != wanted_type.strip().casefold():
            failed.append("product type is %s, not %s" % (card["product_type"], wanted_type))

    customer_score = decimal(customer.get("credit_score"), "customer.credit_score", errors)
    minimum = card["minimum_credit_score"]
    if customer_score is not None:
        if minimum is None:
            unknown.append("minimum credit-score requirement is not documented")
        elif minimum == 0 and not card["score_zero_means_no_requirement"]:
            unknown.append("a score of zero is not documented as no score requirement")
        elif minimum > 0 and customer_score < minimum:
            failed.append("reported credit score %s is below published minimum %s" % (customer_score, minimum))

    held = membership_set(customer.get("memberships", []), "customer.memberships", errors)
    required = {item.casefold() for item in card["required_memberships"]}
    missing = sorted(required - held)
    if missing:
        failed.append("missing required membership(s): " + ", ".join(missing))

    for requirement_key, card_key, label in (
        ("foreign_transaction_fee_max_pct", "foreign_transaction_fee_percent", "foreign transaction fee"),
        ("minimum_payment_max_pct", "minimum_payment_percent", "minimum payment"),
    ):
        cap = decimal(requirements.get(requirement_key), "requirements." + requirement_key, errors)
        if cap is None:
            continue
        actual = card[card_key]
        if actual is None:
            unknown.append(label + " is not documented")
        elif actual > cap:
            failed.append("%s %s%% exceeds %s%%" % (label, actual, cap))

    virtual_needed = requirements.get("require_virtual_card_management")
    if virtual_needed not in (None, True, False):
        errors.append("requirements.require_virtual_card_management must be boolean or null")
    elif virtual_needed is True:
        if card["virtual_card_management"] is False:
            failed.append("virtual card management is not available")
        elif card["virtual_card_management"] is not True:
            unknown.append("virtual-card management availability is not documented")

    decision = {"name": card["name"], "source_ids": card["source_ids"], "reasons": failed, "unknown": unknown}
    return ("disqualified" if failed else "uncertain" if unknown else "qualified"), decision


def shown(value):
    return str(value)


def render(cards, qualified, customer, requirements):
    card_by_name = {card["name"]: card for card in cards}
    paragraphs = []
    for decision in qualified:
        card = card_by_name[decision["name"]]
        text = ["I recommend %s." % card["name"]]
        if card["minimum_credit_score"] == 0 and card["score_zero_means_no_requirement"]:
            score_text = "Its published minimum credit-score requirement is 0, meaning no credit-score requirement"
            if customer.get("credit_score") is not None:
                score_text += ", so your reported %s score does not exclude you from applying" % shown(customer["credit_score"])
            text.append(score_text + ".")
        elif card["minimum_credit_score"] is not None:
            text.append("Its published minimum credit-score requirement is %s." % shown(card["minimum_credit_score"]))
        if requirements.get("foreign_transaction_fee_max_pct") is not None:
            text.append("Its foreign transaction fee is %s%%, within your %s%% maximum." % (shown(card["foreign_transaction_fee_percent"]), shown(requirements["foreign_transaction_fee_max_pct"])))
        if requirements.get("minimum_payment_max_pct") is not None:
            text.append("Its minimum monthly payment is %s%%, within your %s%% maximum." % (shown(card["minimum_payment_percent"]), shown(requirements["minimum_payment_max_pct"])))
        if requirements.get("require_virtual_card_management") is True:
            text.append("Virtual card management is available.")
        paragraphs.append(" ".join(text))
    if not paragraphs:
        return ""
    return " ".join(paragraphs) + " Meeting published terms does not guarantee approval, and final approval, credit limit, and pricing remain subject to the issuer's application and underwriting process."


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": "invalid JSON: " + exc.msg}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"status": "error", "error": "top-level JSON must be an object"}))
        return
    errors = []
    customer = data.get("customer", {})
    requirements = data.get("requirements", {})
    documents = data.get("documents", [])
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
        customer = {}
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
        requirements = {}
    if not isinstance(documents, list):
        errors.append("documents must be a list")
        documents = []

    cards = extract(documents, errors)
    output = {"status": "ok", "candidates": cards, "qualified": [], "disqualified": [], "uncertain": [], "validation": errors, "message": ""}
    for card in cards:
        bucket, decision = classify(card, customer, requirements, errors)
        output[bucket].append(decision)
    output["message"] = render(cards, output["qualified"], customer, requirements)
    print(json.dumps(output, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
