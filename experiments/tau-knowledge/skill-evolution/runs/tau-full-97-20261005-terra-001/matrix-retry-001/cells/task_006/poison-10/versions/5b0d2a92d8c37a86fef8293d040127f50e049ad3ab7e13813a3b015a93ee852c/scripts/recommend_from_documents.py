#!/usr/bin/env python3
"""Extract common credit-card facts from supplied documents and classify their fit.

Input JSON contains customer, requirements, and documents. Documents use titles in the
form "Product: document title". Output JSON contains candidates, fit classifications,
validation findings, and a customer-ready message. No external actions are performed.
"""
import json
import re
import sys
from evaluate_card_fit import classify


def product_name(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    result = title.split(":", 1)[0].strip()
    return result or None


def extracted_numbers(pattern, text, convert=float):
    values = []
    for match in re.findall(pattern, text, re.IGNORECASE | re.DOTALL):
        try:
            value = convert(match)
        except (TypeError, ValueError):
            continue
        if value not in values:
            values.append(value)
    return values


def merge(card, field, values, label):
    if not values:
        return
    existing = card.get(field)
    all_values = set(values)
    if existing is not None:
        all_values.add(existing)
    if len(all_values) == 1:
        card[field] = values[0]
    else:
        card[field] = None
        card["eligibility_checks"]["conflicting documented " + label] = "unknown"


def add_membership(card, value):
    value = value.strip(" -:\t")
    if value and value.casefold() not in {x.casefold() for x in card["required_memberships"]}:
        card["required_memberships"].append(value)


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
        identifier = document.get("document_id")
        if isinstance(identifier, str) and identifier not in card["source_ids"]:
            card["source_ids"].append(identifier)

        scores = extracted_numbers(
            r"minimum\s+(?:credit\s+|personal\s+fico\s+)?score(?:\s+required(?:\s+to\s+apply)?)?[^\d]{0,90}\$?(\d{1,4})\b",
            content, int)
        merge(card, "minimum_credit_score", scores, "minimum credit-score requirement")
        if re.search(
            r"(?:minimum\s+(?:credit\s+)?score[^.\n]{0,100}\$?0\b[^.\n]{0,180}\b(?:means?|indicates?)\s+no\s+(?:credit\s+)?score\s+requirement|\b0\b[^.\n]{0,180}\b(?:means?|indicates?)\s+no\s+(?:credit\s+)?score\s+requirement)",
            content, re.I):
            card["minimum_credit_score_means_no_requirement"] = True

        merge(card, "foreign_transaction_fee_percent",
              extracted_numbers(r"foreign\s+transaction\s+fee[^\d%]{0,100}(\d+(?:\.\d+)?)\s*%", content),
              "foreign transaction fee")
        merge(card, "minimum_payment_percent",
              extracted_numbers(r"minimum\s+(?:monthly\s+)?payment[^\d%]{0,120}(\d+(?:\.\d+)?)\s*%", content),
              "minimum payment")

        yes = bool(re.search(r"virtual\s+card\s+management[^\n]{0,140}(?:available[^\n]{0,40}:?\s*yes|:\s*yes)", content, re.I))
        no = bool(re.search(r"virtual\s+card\s+management[^\n]{0,140}(?:available[^\n]{0,40}:?\s*no|:\s*no)", content, re.I))
        if yes and no:
            card["eligibility_checks"]["conflicting documented virtual-card management availability"] = "unknown"
        elif yes:
            card["virtual_card_management"] = True
        elif no:
            card["virtual_card_management"] = False

        for match in re.finditer(r"([^\n:]{1,80}?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes", content, re.I):
            add_membership(card, match.group(1))
    return list(cards.values())


def show(value):
    if isinstance(value, float):
        return "%.12g" % value
    return str(value)


def render(customer, requirements, candidates, qualified):
    lookup = {candidate["name"]: candidate for candidate in candidates}
    messages = []
    for result in qualified:
        card = lookup[result["name"]]
        score = customer.get("credit_score")
        if card["minimum_credit_score"] == 0 and card["minimum_credit_score_means_no_requirement"]:
            score_text = "Its published minimum credit-score requirement is 0, meaning no credit-score requirement"
            if score is not None:
                score_text += ", so your reported %s score does not exclude you from applying" % show(score)
            score_text += "."
        else:
            score_text = "Its published minimum credit-score requirement is %s." % show(card["minimum_credit_score"])
        parts = ["I recommend %s." % card["name"], score_text]
        if requirements.get("foreign_transaction_fee_max_pct") is not None:
            parts.append("Its foreign transaction fee is %s%%, at or below your %s%% maximum." %
                         (show(card["foreign_transaction_fee_percent"]), show(requirements["foreign_transaction_fee_max_pct"])))
        if requirements.get("minimum_payment_max_pct") is not None:
            parts.append("Its minimum monthly payment is %s%%, at or below your %s%% maximum." %
                         (show(card["minimum_payment_percent"]), show(requirements["minimum_payment_max_pct"])))
        if requirements.get("require_virtual_card_management") is True:
            parts.append("Virtual card management is available.")
        messages.append(" ".join(parts))
    if not messages:
        return ""
    return " ".join(messages) + " Meeting published terms does not guarantee approval; final approval, credit limit, and pricing remain subject to the issuer's application and underwriting process."


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
    output = {"status": "ok", "candidates": candidates, "qualified": [],
              "disqualified": [], "uncertain": [], "validation": errors, "message": ""}
    for card in candidates:
        bucket, result = classify(card, customer, requirements, errors)
        output[bucket].append(result)
    if not errors:
        output["message"] = render(customer, requirements, candidates, output["qualified"])
    print(json.dumps(output, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
