#!/usr/bin/env python3
"""Extract documented card facts, classify fit, and render supported recommendations.

Input is JSON with customer, requirements, and complete source documents. Output is JSON
with candidates, classifications, validation findings, and a customer-ready message.
The script is deterministic and has no external side effects.
"""
import json
import re
import sys
from evaluate_card_fit import classify


def product_name(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    value = title.split(":", 1)[0].strip()
    return value or None


def unique(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def numbers(pattern, text, converter=float):
    found = []
    for value in re.findall(pattern, text, re.IGNORECASE | re.DOTALL):
        try:
            found.append(converter(value))
        except (ValueError, TypeError):
            pass
    return unique(found)


def merge(card, field, values, label):
    if not values:
        return
    existing = card.get(field)
    combined = set(values)
    if existing is not None:
        combined.add(existing)
    if len(combined) == 1:
        card[field] = values[0]
    else:
        card[field] = None
        card["eligibility_checks"]["conflicting documented " + label] = "unknown"


def add_membership(card, membership):
    membership = membership.strip(" -:\t")
    if membership and membership.casefold() not in {x.casefold() for x in card["required_memberships"]}:
        card["required_memberships"].append(membership)


def extract(documents, errors):
    cards = {}
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            errors.append("documents[%d] must be an object" % index)
            continue
        title, content = document.get("title"), document.get("content")
        name = product_name(title)
        if name is None or not isinstance(content, str):
            errors.append("documents[%d] requires a 'Product: title' and string content" % index)
            continue
        card = cards.setdefault(name, {
            "name": name,
            "product_type": "business" if re.search(r"\bbusiness\b", title, re.I) else "personal",
            "minimum_credit_score": None,
            "minimum_credit_score_means_no_requirement": False,
            "required_memberships": [],
            "foreign_transaction_fee_percent": None,
            "minimum_payment_percent": None,
            "virtual_card_management": None,
            "eligibility_checks": {},
            "source_ids": [],
        })
        doc_id = document.get("document_id")
        if isinstance(doc_id, str) and doc_id not in card["source_ids"]:
            card["source_ids"].append(doc_id)

        merge(card, "minimum_credit_score", numbers(
            r"minimum\s+(?:credit\s+|personal\s+fico\s+)?score(?:\s+required(?:\s+to\s+apply)?)?\s*(?:is|:|of)?\s*\$?(\d{1,4})\b",
            content, int), "minimum credit-score requirement")
        if re.search(
            r"(?:minimum\s+(?:credit\s+)?score[^.\n]{0,120}\b0\b[^.\n]{0,160}\b(?:means?|indicates?)\s+no\s+(?:credit\s+)?score\s+requirement|\b0\b[^.\n]{0,160}\b(?:means?|indicates?)\s+no\s+(?:credit\s+)?score\s+requirement)",
            content, re.I):
            card["minimum_credit_score_means_no_requirement"] = True

        merge(card, "foreign_transaction_fee_percent", numbers(
            r"foreign\s+transaction\s+fee[^\d%]{0,100}(\d+(?:\.\d+)?)\s*%", content),
            "foreign transaction fee")
        merge(card, "minimum_payment_percent", numbers(
            r"minimum\s+(?:monthly\s+)?payment[^\d%]{0,120}(\d+(?:\.\d+)?)\s*%", content),
            "minimum payment")

        yes = bool(re.search(
            r"virtual\s+card\s+management[^\n]{0,140}\b(?:available|features?\s+are)\s*:?\s*yes\b",
            content, re.I))
        no = bool(re.search(
            r"virtual\s+card\s+management[^\n]{0,140}\bavailable\s*:?\s*no\b",
            content, re.I))
        if yes and no:
            card["eligibility_checks"]["conflicting documented virtual-card management availability"] = "unknown"
        elif yes:
            card["virtual_card_management"] = True
        elif no:
            card["virtual_card_management"] = False

        for match in re.finditer(r"([^\n:]{1,100}?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes\b", content, re.I):
            add_membership(card, match.group(1))
    return list(cards.values())


def display(value):
    if isinstance(value, float):
        return ("%.12g" % value)
    return str(value)


def render(customer, requirements, candidates, qualified):
    candidates_by_name = {card["name"]: card for card in candidates}
    paragraphs = []
    for result in qualified:
        card = candidates_by_name[result["name"]]
        parts = ["I recommend %s." % card["name"]]
        score = customer.get("credit_score")
        if card["minimum_credit_score"] == 0 and card["minimum_credit_score_means_no_requirement"]:
            sentence = "Its published minimum credit-score requirement is 0, meaning no credit-score requirement"
            if score is not None:
                sentence += ", so your reported %s score does not exclude you from applying" % display(score)
            parts.append(sentence + ".")
        elif card["minimum_credit_score"] is not None:
            parts.append("Its published minimum credit-score requirement is %s." % display(card["minimum_credit_score"]))
        if requirements.get("foreign_transaction_fee_max_pct") is not None:
            parts.append("Its foreign transaction fee is %s%%, within your %s%% maximum." % (
                display(card["foreign_transaction_fee_percent"]),
                display(requirements["foreign_transaction_fee_max_pct"])))
        if requirements.get("minimum_payment_max_pct") is not None:
            parts.append("Its minimum monthly payment is %s%%, within your %s%% maximum." % (
                display(card["minimum_payment_percent"]),
                display(requirements["minimum_payment_max_pct"])))
        if requirements.get("require_virtual_card_management") is True:
            parts.append("Virtual card management is available.")
        paragraphs.append(" ".join(parts))
    if not paragraphs:
        return ""
    return " ".join(paragraphs) + " Meeting published terms does not guarantee approval; final approval, credit limit, and pricing remain subject to the issuer's application and underwriting process."


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": "invalid JSON: " + exc.msg}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"status": "error", "error": "top-level JSON must be an object"}))
        return

    errors = []
    customer = payload.get("customer", {})
    requirements = payload.get("requirements", {})
    documents = payload.get("documents", [])
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
        customer = {}
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
        requirements = {}
    if not isinstance(documents, list):
        errors.append("documents must be a list")
        documents = []

    candidates = extract(documents, errors)
    output = {
        "status": "ok",
        "candidates": candidates,
        "qualified": [],
        "disqualified": [],
        "uncertain": [],
        "validation": errors,
        "message": "",
    }
    for card in candidates:
        bucket, result = classify(card, customer, requirements, errors)
        output[bucket].append(result)
    if not errors:
        output["message"] = render(customer, requirements, candidates, output["qualified"])
    print(json.dumps(output, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
