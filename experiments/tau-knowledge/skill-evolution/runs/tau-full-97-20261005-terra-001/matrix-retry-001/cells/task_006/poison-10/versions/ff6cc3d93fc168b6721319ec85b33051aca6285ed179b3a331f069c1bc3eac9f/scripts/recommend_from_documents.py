#!/usr/bin/env python3
"""Extract common card facts from current-task documents and classify card fit.

Reads JSON on stdin with customer, requirements, and documents. A document has a
product-prefixed title, document_id, and content. Emits JSON on stdout with extracted
candidates, classifications, validation findings, and a customer-facing recommendation.
No external actions are performed.
"""
import json
import re
import sys
from evaluate_card_fit import classify


def product_from_title(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    product = title.split(":", 1)[0].strip()
    return product or None


def values(pattern, text, converter=float):
    found = []
    for item in re.findall(pattern, text, re.IGNORECASE | re.DOTALL):
        try:
            item = converter(item)
        except (TypeError, ValueError):
            continue
        if item not in found:
            found.append(item)
    return found


def merge(card, field, new_values, label):
    if not new_values:
        return
    existing = card.get(field)
    all_values = set(new_values)
    if existing is not None:
        all_values.add(existing)
    if len(all_values) == 1:
        card[field] = new_values[0]
    else:
        card[field] = None
        card["eligibility_checks"]["conflicting documented " + label] = "unknown"


def add_membership(card, membership):
    normalized = membership.strip(" -:\t")
    if not normalized:
        return
    if normalized.casefold() not in {item.casefold() for item in card["required_memberships"]}:
        card["required_memberships"].append(normalized)


def extract(documents, errors):
    cards = {}
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            errors.append("documents[%d] must be an object" % index)
            continue
        title, text = document.get("title"), document.get("content")
        name = product_from_title(title)
        if name is None or not isinstance(text, str):
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

        scores = values(
            r"minimum\s+(?:credit\s+|personal\s+fico\s+)?score(?:\s+required(?:\s+to\s+apply)?)?[^\d]{0,90}\$?(\d{1,4})\b",
            text,
            int,
        )
        merge(card, "minimum_credit_score", scores, "minimum credit-score requirement")
        if re.search(
            r"(?:minimum\s+(?:credit\s+)?score[^.\n]{0,90}:?\s*\$?0\b[^.\n]{0,160}\b(?:indicates?|means?)\s+no\s+(?:credit\s+)?score\s+requirement|\b0\b[^.\n]{0,160}\b(?:indicates?|means?)\s+no\s+(?:credit\s+)?score\s+requirement)",
            text,
            re.I,
        ):
            card["minimum_credit_score_means_no_requirement"] = True

        fees = values(r"foreign\s+transaction\s+fee[^\d%]{0,100}(\d+(?:\.\d+)?)\s*%", text)
        merge(card, "foreign_transaction_fee_percent", fees, "foreign transaction fee")

        payments = values(r"minimum\s+(?:monthly\s+)?payment[^\d%]{0,120}(\d+(?:\.\d+)?)\s*%", text)
        merge(card, "minimum_payment_percent", payments, "minimum payment")

        yes = bool(re.search(
            r"virtual\s+card\s+management[^\n]{0,140}(?:available[^\n]{0,40}:?\s*yes|:\s*yes)", text, re.I
        ))
        no = bool(re.search(
            r"virtual\s+card\s+management[^\n]{0,140}(?:available[^\n]{0,40}:?\s*no|:\s*no)", text, re.I
        ))
        if yes and no:
            card["eligibility_checks"]["conflicting documented virtual-card management availability"] = "unknown"
        elif yes:
            card["virtual_card_management"] = True
        elif no:
            card["virtual_card_management"] = False

        for match in re.finditer(r"([^\n:]{1,80}?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes", text, re.I):
            add_membership(card, match.group(1))
    return list(cards.values())


def display(value):
    if isinstance(value, float):
        return ("%.12g" % value)
    return str(value)


def render(customer, requirements, candidates, qualified):
    cards = {card["name"]: card for card in candidates}
    messages = []
    for item in qualified:
        card = cards[item["name"]]
        score = customer.get("credit_score")
        if card["minimum_credit_score"] == 0 and card["minimum_credit_score_means_no_requirement"]:
            if score is None:
                score_text = "Its published minimum credit-score requirement is 0, meaning no credit-score requirement."
            else:
                score_text = "Its published minimum credit-score requirement is 0, meaning no credit-score requirement, so your reported %s score does not exclude you from applying." % display(score)
        else:
            score_text = "Its published minimum credit-score requirement is %s." % display(card["minimum_credit_score"])
        messages.append(
            "I recommend %s. %s Its foreign transaction fee is %s%%, at or below your %s%% maximum. Its minimum monthly payment is %s%%, at or below your %s%% maximum. Virtual card management is available." % (
                card["name"],
                score_text,
                display(card["foreign_transaction_fee_percent"]),
                display(requirements.get("foreign_transaction_fee_max_pct")),
                display(card["minimum_payment_percent"]),
                display(requirements.get("minimum_payment_max_pct")),
            )
        )
    if not messages:
        return ""
    return " ".join(messages) + " Meeting published terms does not guarantee approval; final approval, credit limit, and pricing remain subject to the issuer's application and underwriting process."


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
    print(json.dumps(output, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
