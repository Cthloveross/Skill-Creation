#!/usr/bin/env python3
"""Extract common card terms from supplied documents and evaluate card fit.

Input JSON: customer, requirements, and documents. Each document requires a
product-prefixed title, document_id, and content. Output JSON includes normalized
candidates, classifications, validation messages, and a customer-facing message.
No external actions are performed.
"""
import json
import re
import sys
from evaluate_card_fit import classify


def product_name(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    name = title.split(":", 1)[0].strip()
    return name or None


def extract_numbers(pattern, text, cast=float):
    values = []
    for raw in re.findall(pattern, text, re.IGNORECASE | re.DOTALL):
        try:
            value = cast(raw)
        except (TypeError, ValueError):
            continue
        if value not in values:
            values.append(value)
    return values


def merge_fact(card, key, values, label):
    """Merge a fact while marking disagreement as a documented uncertainty."""
    if not values:
        return
    existing = card.get(key)
    all_values = set(values)
    if existing is not None:
        all_values.add(existing)
    if len(all_values) == 1:
        card[key] = values[0]
    else:
        card[key] = None
        card["eligibility_checks"][f"conflicting documented {label}"] = "unknown"


def add_membership(card, value):
    if not value:
        return
    existing = {item.casefold() for item in card["required_memberships"]}
    if value.casefold() not in existing:
        card["required_memberships"].append(value)


def extract(documents, errors):
    cards = {}
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            errors.append(f"documents[{index}] must be an object")
            continue
        title = document.get("title")
        text = document.get("content")
        name = product_name(title)
        if name is None or not isinstance(text, str):
            errors.append(
                f"documents[{index}] requires a 'Product: title' string and string content"
            )
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
            "source_ids": [],
        })
        document_id = document.get("document_id")
        if isinstance(document_id, str) and document_id not in card["source_ids"]:
            card["source_ids"].append(document_id)

        scores = extract_numbers(
            r"minimum\s+(?:credit\s+|personal\s+fico\s+)?score[^\d]{0,90}\$?(\d{1,4})\b",
            text,
            int,
        )
        merge_fact(card, "minimum_credit_score", scores, "minimum credit-score requirement")
        if re.search(
            r"minimum\s+credit\s+score[^\n]{0,80}\b0\b[^\n]{0,100}\bno\s+(?:credit\s+)?score\s+requirement",
            text,
            re.I,
        ):
            card["minimum_credit_score_means_no_requirement"] = True

        fees = extract_numbers(
            r"foreign\s+transaction\s+fee[^\d%]{0,100}(\d+(?:\.\d+)?)\s*%",
            text,
        )
        merge_fact(card, "foreign_transaction_fee_percent", fees, "foreign transaction fee")

        payments = extract_numbers(
            r"minimum\s+(?:monthly\s+)?payment[^\d%]{0,120}(\d+(?:\.\d+)?)\s*%",
            text,
        )
        merge_fact(card, "minimum_payment_percent", payments, "minimum payment")
        if payments:
            basis_match = re.search(
                r"minimum\s+(?:monthly\s+)?payment[^\n]{0,150}(outstanding|statement)\s+balance",
                text,
                re.I,
            )
            if basis_match:
                card["minimum_payment_basis"] = basis_match.group(1).casefold() + "_balance"

        yes = bool(re.search(
            r"virtual\s+card\s+management[^\n]{0,120}(?:available[^\n]{0,40}:?\s*yes|:\s*yes)",
            text,
            re.I,
        ))
        no = bool(re.search(
            r"virtual\s+card\s+management[^\n]{0,120}(?:available[^\n]{0,40}:?\s*no|:\s*no)",
            text,
            re.I,
        ))
        if yes and no:
            card["virtual_card_management"] = None
            card["eligibility_checks"]["conflicting documented virtual-card management availability"] = "unknown"
        elif yes:
            card["virtual_card_management"] = True
        elif no:
            card["virtual_card_management"] = False

        for match in re.finditer(
            r"([^\n:]{1,80}?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes",
            text,
            re.I,
        ):
            add_membership(card, match.group(1).strip(" -"))
    return list(cards.values())


def render(customer, requirements, candidates, qualified):
    by_name = {candidate["name"]: candidate for candidate in candidates}
    statements = []
    for result in qualified:
        card = by_name[result["name"]]
        score = customer.get("credit_score")
        if card["minimum_credit_score"] == 0 and card["minimum_credit_score_means_no_requirement"]:
            score_text = (
                f"Its published minimum credit-score requirement is 0 (no score requirement), "
                f"so your {score} score does not exclude you from applying."
            )
        else:
            score_text = f"Its published minimum credit score is {card['minimum_credit_score']}."
        statements.append(
            f"I recommend {card['name']}. {score_text} "
            f"Its foreign transaction fee is {card['foreign_transaction_fee_percent']}%, "
            f"at or below your {requirements.get('foreign_transaction_fee_max_pct')}% maximum. "
            f"Its minimum monthly payment is {card['minimum_payment_percent']}%, "
            f"at or below your {requirements.get('minimum_payment_max_pct')}% maximum. "
            "Virtual card management is available."
        )
    if not statements:
        return ""
    return " ".join(statements) + (
        " Meeting published terms does not guarantee approval; final approval, credit limit, "
        "and pricing remain subject to the issuer's application and underwriting process."
    )


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
    for candidate in candidates:
        bucket, result = classify(candidate, customer, requirements, errors)
        output[bucket].append(result)
    if not errors:
        output["message"] = render(customer, requirements, candidates, output["qualified"])
    print(json.dumps(output, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
