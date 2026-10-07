#!/usr/bin/env python3
"""Extract comparable card facts from supplied disclosures and classify their fit.

Input JSON contains customer, requirements, and documents. Each document has a document_id,
a title in the form "Product: disclosure title", and complete text content. Output JSON
contains normalized candidates, decision buckets, validation findings, and a customer-ready
message for qualified candidates. The script has no network, account, or filesystem effects.
"""
import json
import re
import sys

from evaluate_card_fit import classify


def unique(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def product_from_title(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    product = title.split(":", 1)[0].strip()
    return product or None


def extracted_numbers(pattern, text, converter=float):
    values = []
    for raw in re.findall(pattern, text, flags=re.IGNORECASE | re.DOTALL):
        try:
            values.append(converter(raw))
        except (TypeError, ValueError):
            continue
    return unique(values)


def merge_value(card, field, values, label):
    """Merge consistent facts, preserving conflicts as uncertainty."""
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


def add_membership(card, membership):
    membership = membership.strip(" -:\t")
    existing = {item.casefold() for item in card["required_memberships"]}
    if membership and membership.casefold() not in existing:
        card["required_memberships"].append(membership)


def extract_virtual_availability(content):
    """Return True/False/None; recognize an explicit management availability statement."""
    matches = re.findall(
        r"virtual\s+card\s+management[\s\S]{0,180}?(?:features?\s+are\s+)?available\s*:?\s*(yes|no)\b",
        content,
        flags=re.IGNORECASE,
    )
    states = {match.casefold() for match in matches}
    if states == {"yes"}:
        return True
    if states == {"no"}:
        return False
    return None


def extract(documents, errors):
    cards = {}
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            errors.append("documents[%d] must be an object" % index)
            continue
        title = document.get("title")
        content = document.get("content")
        name = product_from_title(title)
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
        source_id = document.get("document_id")
        if isinstance(source_id, str) and source_id not in card["source_ids"]:
            card["source_ids"].append(source_id)

        merge_value(card, "minimum_credit_score", extracted_numbers(
            r"minimum\s+(?:credit\s+|personal\s+fico\s+)?score(?:\s+required(?:\s+to\s+apply)?)?\s*(?:is|:|of)?\s*\$?(\d{1,4})\b",
            content,
            int,
        ), "minimum credit-score requirement")
        if re.search(
            r"\b0\b[^.\n]{0,180}\b(?:means?|indicates?)\s+no\s+(?:credit\s+)?score\s+requirement",
            content,
            re.I,
        ):
            card["minimum_credit_score_means_no_requirement"] = True

        merge_value(card, "foreign_transaction_fee_percent", extracted_numbers(
            r"foreign\s+transaction\s+fee[^\d%]{0,100}(\d+(?:\.\d+)?)\s*%",
            content,
        ), "foreign transaction fee")
        merge_value(card, "minimum_payment_percent", extracted_numbers(
            r"minimum\s+(?:monthly\s+)?payment[^\d%]{0,120}(\d+(?:\.\d+)?)\s*%",
            content,
        ), "minimum payment")

        virtual = extract_virtual_availability(content)
        if virtual is not None:
            previous = card["virtual_card_management"]
            if previous is None:
                card["virtual_card_management"] = virtual
            elif previous != virtual:
                card["virtual_card_management"] = None
                card["eligibility_checks"]["conflicting documented virtual-card management availability"] = "unknown"

        for match in re.finditer(
            r"([^\n:]{1,100}?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes\b",
            content,
            re.I,
        ):
            add_membership(card, match.group(1))
    return list(cards.values())


def show(value):
    """Keep useful disclosed precision, including a trailing .0 on parsed percentages."""
    if isinstance(value, float):
        return str(value)
    return str(value)


def render(customer, requirements, candidates, qualified):
    """Produce prose only from facts that were classified as qualified."""
    by_name = {card["name"]: card for card in candidates}
    paragraphs = []
    for result in qualified:
        card = by_name[result["name"]]
        lines = ["I recommend %s." % card["name"]]
        if card["minimum_credit_score"] == 0 and card["minimum_credit_score_means_no_requirement"]:
            score_line = "Its published minimum credit-score requirement is 0, meaning no credit-score requirement"
            if customer.get("credit_score") is not None:
                score_line += ", so your reported %s score does not exclude you from applying" % show(customer["credit_score"])
            lines.append(score_line + ".")
        elif card["minimum_credit_score"] is not None:
            lines.append("Its published minimum credit-score requirement is %s." % show(card["minimum_credit_score"]))
        if requirements.get("foreign_transaction_fee_max_pct") is not None:
            lines.append(
                "Its foreign transaction fee is %s%%, within your %s%% maximum."
                % (show(card["foreign_transaction_fee_percent"]), show(requirements["foreign_transaction_fee_max_pct"]))
            )
        if requirements.get("minimum_payment_max_pct") is not None:
            lines.append(
                "Its minimum monthly payment is %s%%, within your %s%% maximum."
                % (show(card["minimum_payment_percent"]), show(requirements["minimum_payment_max_pct"]))
            )
        if requirements.get("require_virtual_card_management") is True:
            lines.append("Virtual card management is available.")
        paragraphs.append(" ".join(lines))
    if not paragraphs:
        return ""
    return " ".join(paragraphs) + " Meeting published terms does not guarantee approval; final approval, credit limit, and pricing remain subject to the issuer's application and underwriting process."


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
    output["message"] = render(customer, requirements, candidates, output["qualified"])
    print(json.dumps(output, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
