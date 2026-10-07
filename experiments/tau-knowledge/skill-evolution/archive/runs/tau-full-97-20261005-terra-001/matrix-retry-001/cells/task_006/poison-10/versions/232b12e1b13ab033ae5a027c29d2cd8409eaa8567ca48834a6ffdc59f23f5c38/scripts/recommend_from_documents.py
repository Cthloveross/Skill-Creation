#!/usr/bin/env python3
"""Extract common card terms from supplied documents and evaluate card fit.

Input JSON has customer, requirements, and documents. Each document has document_id,
title, and content. Output JSON includes candidates, classifications, validation, and
a concise recommendation message. No external actions are performed.
"""
import json
import re
import sys
from evaluate_card_fit import classify


def product_name(title):
    return title.split(":", 1)[0].strip() if isinstance(title, str) and ":" in title else None


def numbers(pattern, text, cast=float):
    output = []
    for value in re.findall(pattern, text, re.I | re.S):
        try:
            item = cast(value)
            if item not in output:
                output.append(item)
        except (TypeError, ValueError):
            pass
    return output


def merge_fact(card, key, values, label):
    if not values:
        return
    known = card.get(key)
    all_values = set(values)
    if known is not None:
        all_values.add(known)
    if len(all_values) == 1:
        card[key] = values[0]
    else:
        card[key] = None
        card["eligibility_checks"][f"conflicting documented {label}"] = "unknown"


def extract(documents, errors):
    cards = {}
    for index, doc in enumerate(documents):
        if not isinstance(doc, dict):
            errors.append(f"documents[{index}] must be an object")
            continue
        title, text = doc.get("title"), doc.get("content")
        name = product_name(title)
        if name is None or not isinstance(text, str):
            errors.append(f"documents[{index}] requires a 'Product: title' string and string content")
            continue
        card = cards.setdefault(name, {
            "name": name,
            "product_type": "business" if re.search(r"\bbusiness\b", title, re.I) else "personal",
            "minimum_credit_score": None,
            "minimum_credit_score_means_no_requirement": False,
            "required_memberships": [],
            "foreign_transaction_fee_percent": None,
            "minimum_payment_percent": None,
            "minimum_payment_basis": None,
            "virtual_card_management": None,
            "available_from": None,
            "available_through": None,
            "eligibility_checks": {},
            "source_ids": []
        })
        doc_id = doc.get("document_id")
        if isinstance(doc_id, str) and doc_id not in card["source_ids"]:
            card["source_ids"].append(doc_id)

        scores = numbers(r"minimum\s+(?:credit\s+|personal\s+fico\s+)?score[^\d]{0,90}\$?(\d{1,4})\b", text, int)
        merge_fact(card, "minimum_credit_score", scores, "minimum credit-score requirement")
        if re.search(r"minimum\s+credit\s+score[^\n]{0,80}\b0\b[^\n]{0,100}\bno\s+(?:credit\s+)?score\s+requirement", text, re.I):
            card["minimum_credit_score_means_no_requirement"] = True

        fees = numbers(r"foreign\s+transaction\s+fee[^\d%]{0,100}(\d+(?:\.\d+)?)\s*%", text)
        merge_fact(card, "foreign_transaction_fee_percent", fees, "foreign transaction fee")
        payments = numbers(r"minimum\s+(?:monthly\s+)?payment[^\d%]{0,120}(\d+(?:\.\d+)?)\s*%", text)
        merge_fact(card, "minimum_payment_percent", payments, "minimum payment")
        if payments:
            card["minimum_payment_basis"] = (
                "outstanding_balance" if re.search(r"minimum\s+(?:monthly\s+)?payment[^\n]{0,150}outstanding\s+balance", text, re.I)
                else "statement_balance"
            )

        yes = bool(re.search(r"virtual\s+card\s+management[^\n]{0,120}(?:available[^\n]{0,30}:?\s*yes|:\s*yes)", text, re.I))
        no = bool(re.search(r"virtual\s+card\s+management[^\n]{0,120}(?:available[^\n]{0,30}:?\s*no|:\s*no)", text, re.I))
        if yes and no:
            card["virtual_card_management"] = None
            card["eligibility_checks"]["conflicting documented virtual-card management availability"] = "unknown"
        elif yes:
            card["virtual_card_management"] = True
        elif no:
            card["virtual_card_management"] = False

        for match in re.finditer(r"([^\n:]{1,80}?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes", text, re.I):
            membership = match.group(1).strip(" -")
            if membership and membership.casefold() not in {m.casefold() for m in card["required_memberships"]}:
                card["required_memberships"].append(membership)
    return list(cards.values())


def render(customer, requirements, candidates, qualified):
    by_name = {card["name"]: card for card in candidates}
    sentences = []
    for result in qualified:
        card = by_name[result["name"]]
        score = customer.get("credit_score")
        if card["minimum_credit_score"] == 0 and card["minimum_credit_score_means_no_requirement"]:
            score_text = f"Its published minimum credit-score requirement is 0 (no score requirement), so your {score} score does not exclude you from applying."
        else:
            score_text = f"Its published minimum credit score is {card['minimum_credit_score']}."
        fee_limit = requirements.get("foreign_transaction_fee_max_pct")
        payment_limit = requirements.get("minimum_payment_max_pct")
        sentences.append(
            f"I recommend {card['name']}. {score_text} Its foreign transaction fee is "
            f"{card['foreign_transaction_fee_percent']}%, at or below your {fee_limit}% maximum. "
            f"Its minimum monthly payment is {card['minimum_payment_percent']}%, at or below your "
            f"{payment_limit}% maximum. Virtual card management is available."
        )
    if not sentences:
        return ""
    return " ".join(sentences) + " Meeting published terms does not guarantee approval; final approval, credit limit, and pricing remain subject to the issuer's application and underwriting process."


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": f"invalid JSON: {exc.msg}"}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"status": "error", "error": "top-level JSON must be an object"}))
        return
    errors = []
    customer = data.get("customer")
    requirements = data.get("requirements")
    documents = data.get("documents")
    if not isinstance(customer, dict): errors.append("customer must be an object"); customer = {}
    if not isinstance(requirements, dict): errors.append("requirements must be an object"); requirements = {}
    if not isinstance(documents, list): errors.append("documents must be a list"); documents = []
    candidates = extract(documents, errors)
    output = {"status": "ok", "candidates": candidates, "qualified": [], "disqualified": [], "uncertain": [], "validation": errors, "message": ""}
    for candidate in candidates:
        bucket, result = classify(candidate, customer, requirements, errors)
        output[bucket].append(result)
    if not errors:
        output["message"] = render(customer, requirements, candidates, output["qualified"])
    print(json.dumps(output, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
