#!/usr/bin/env python3
"""Extract standard card-fit facts from supplied product documents and classify them.

Input JSON: customer, requirements, and documents (document_id, title, content).
Output JSON: normalized candidates, classifications, validation, and a recommendation
message when qualified candidates exist. This script has no external side effects.
"""
import json
import re
import sys
from evaluate_card_fit import classify


def values(pattern, text, cast=float, flags=re.I | re.S):
    found = []
    for item in re.findall(pattern, text, flags):
        try:
            value = cast(item)
            if value not in found:
                found.append(value)
        except (TypeError, ValueError):
            pass
    return found


def product_name(title):
    if not isinstance(title, str) or not title.strip():
        return None
    return title.split(":", 1)[0].strip()


def set_fact(card, key, found, conflict_label):
    if not found:
        return
    current = card.get(key)
    all_values = set(found)
    if current is not None:
        all_values.add(current)
    if len(all_values) == 1:
        card[key] = found[0]
    else:
        card[key] = None
        card["eligibility_checks"][f"conflicting documented {conflict_label}"] = "unknown"


def extract(documents, errors):
    cards = {}
    for index, doc in enumerate(documents):
        if not isinstance(doc, dict):
            errors.append(f"documents[{index}] must be an object")
            continue
        name = product_name(doc.get("title"))
        text = doc.get("content")
        if name is None or not isinstance(text, str):
            errors.append(f"documents[{index}] requires string title and content")
            continue
        card = cards.setdefault(name, {
            "name": name, "product_type": "business" if re.search(r"\bbusiness\b", doc.get("title", ""), re.I) else "personal",
            "minimum_credit_score": None, "minimum_credit_score_means_no_requirement": False,
            "required_memberships": [], "foreign_transaction_fee_percent": None,
            "minimum_payment_percent": None, "minimum_payment_basis": None,
            "virtual_card_management": None, "available_from": None, "available_through": None,
            "eligibility_checks": {}, "source_ids": []
        })
        doc_id = doc.get("document_id")
        if isinstance(doc_id, str) and doc_id not in card["source_ids"]:
            card["source_ids"].append(doc_id)
        score_values = values(r"minimum\s+(?:credit|personal\s+fico)\s+score.{0,70}?\$?\b(\d{1,4})\b", text, int)
        set_fact(card, "minimum_credit_score", score_values, "minimum credit-score requirement")
        if card.get("minimum_credit_score") == 0 and re.search(r"0\s*(?:\([^)]*)?no credit score requirement", text, re.I):
            card["minimum_credit_score_means_no_requirement"] = True
        fee_values = values(r"foreign\s+transaction\s+fee[^\d%]{0,80}(\d+(?:\.\d+)?)\s*%", text)
        set_fact(card, "foreign_transaction_fee_percent", fee_values, "foreign transaction fee")
        payment_values = values(r"minimum\s+(?:monthly\s+)?payment[^\d%]{0,100}(\d+(?:\.\d+)?)\s*%", text)
        set_fact(card, "minimum_payment_percent", payment_values, "minimum payment")
        if payment_values:
            card["minimum_payment_basis"] = "outstanding_balance" if re.search(r"minimum\s+(?:monthly\s+)?payment.{0,120}outstanding balance", text, re.I | re.S) else "statement_balance"
        virtual_yes = bool(re.search(r"virtual\s+card\s+management[^\n]{0,100}(?:available[^\n]{0,30}:?\s*yes|:\s*yes)", text, re.I))
        virtual_no = bool(re.search(r"virtual\s+card\s+management[^\n]{0,100}(?:available[^\n]{0,30}:?\s*no|:\s*no)", text, re.I))
        if virtual_yes and virtual_no:
            card["virtual_card_management"] = None
            card["eligibility_checks"]["conflicting documented virtual-card management availability"] = "unknown"
        elif virtual_yes:
            card["virtual_card_management"] = True
        elif virtual_no:
            card["virtual_card_management"] = False
        for membership in re.findall(r"([A-Za-z0-9+\- ]+?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes", text, re.I):
            cleaned = membership.strip()
            if cleaned and cleaned.casefold() not in {m.casefold() for m in card["required_memberships"]}:
                card["required_memberships"].append(cleaned)
    return list(cards.values())


def render(customer, candidates, qualified):
    by_name = {c["name"]: c for c in candidates}
    pieces = []
    for item in qualified:
        card = by_name[item["name"]]
        score = customer.get("credit_score")
        if card["minimum_credit_score"] == 0 and card["minimum_credit_score_means_no_requirement"]:
            score_text = f"Its published minimum credit-score requirement is 0 (no score requirement), so your {score} score does not exclude you from applying."
        else:
            score_text = f"Its published minimum credit score is {card['minimum_credit_score']}."
        sources = ", ".join(card["source_ids"])
        pieces.append(f"I recommend {card['name']}. {score_text} Its foreign transaction fee is {card['foreign_transaction_fee_percent']}%, and its minimum monthly payment is {card['minimum_payment_percent']}%, both within your stated limits. Virtual card management is available. Source: {sources}.")
    if not pieces:
        return ""
    return " ".join(pieces) + " Meeting published terms does not guarantee approval; final approval, credit limit, and pricing remain subject to the issuer's application and underwriting process."


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
    customer, requirements, documents = data.get("customer"), data.get("requirements"), data.get("documents")
    if not isinstance(customer, dict): errors.append("customer must be an object"); customer = {}
    if not isinstance(requirements, dict): errors.append("requirements must be an object"); requirements = {}
    if not isinstance(documents, list): errors.append("documents must be a list"); documents = []
    candidates = extract(documents, errors)
    output = {"status": "ok", "candidates": candidates, "qualified": [], "disqualified": [], "uncertain": [], "validation": errors, "message": ""}
    for candidate in candidates:
        bucket, result = classify(candidate, customer, requirements, errors)
        output[bucket].append(result)
    if not errors:
        output["message"] = render(customer, candidates, output["qualified"])
    print(json.dumps(output, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
