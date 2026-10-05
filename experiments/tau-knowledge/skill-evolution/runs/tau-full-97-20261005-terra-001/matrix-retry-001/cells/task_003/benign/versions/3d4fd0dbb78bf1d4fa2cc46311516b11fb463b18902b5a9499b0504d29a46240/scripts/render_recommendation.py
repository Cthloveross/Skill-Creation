#!/usr/bin/env python3
"""Render a recommendation from evidence-backed records supplied by the caller.

Reads one JSON object from stdin and writes one JSON object to stdout. Product
facts must be extracted from current task documents; this script does not
retrieve facts or make approval decisions.
"""
import json
import sys


def is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def cash(value):
    return "${:,.0f}".format(float(value))


def percent(value):
    return "{:g}%".format(float(value))


def protection_phrase(product):
    detail = product.get("purchase_protection")
    if not isinstance(detail, dict) or detail.get("available") is not True:
        return None
    pieces = ["purchase protection"]
    if is_num(detail.get("days")):
        pieces.append("for up to {:g} days".format(detail["days"]))
    if detail.get("unlimited") is True:
        pieces.append("with documented unlimited coverage")
    elif is_num(detail.get("max_per_claim")):
        pieces.append("up to {} per eligible claim".format(cash(detail["max_per_claim"])))
    return ", ".join(pieces)


def qualification_errors(product, requested_limit):
    errors = []
    if product.get("foreign_transaction_fee_pct") != 0:
        errors.append("does not document a 0% foreign transaction fee")
    if protection_phrase(product) is None:
        errors.append("does not document purchase protection")
    ceiling = product.get("credit_limit_max")
    if not is_num(ceiling):
        errors.append("does not document a credit-limit ceiling")
    elif is_num(requested_limit) and float(ceiling) < float(requested_limit):
        errors.append("documented limit ceiling is below requested limit")
    return errors


def rewards_sentence(product, priorities):
    flat = product.get("flat_cashback_pct")
    travel = product.get("travel_cashback_pct")
    fragments = []
    if is_num(flat):
        fragments.append(percent(flat) + " cash back on all eligible purchases")
    if str(priorities.get("primary_category", "")).strip().lower() == "travel" and is_num(travel):
        fragments.append(percent(travel) + " back on eligible travel purchases")
    if not fragments:
        return "The supplied record has no documented rewards rate to describe."
    earning = " and ".join(fragments)
    if priorities.get("everyday_spend") is True and is_num(flat):
        return "It earns " + earning + ", which fits everyday purchases while also rewarding travel-heavy spending."
    if str(priorities.get("primary_category", "")).strip().lower() == "travel":
        return "It earns " + earning + ", which fits travel-led spending."
    return "It earns " + earning + "."


def limit_sentence(product, requested_limit):
    lower, upper = product.get("credit_limit_min"), product.get("credit_limit_max")
    if is_num(lower) and is_num(upper):
        range_text = "a documented credit-limit range of {}–{}".format(cash(lower), cash(upper))
    else:
        range_text = "a documented credit-limit ceiling of " + cash(upper)
    requested = cash(requested_limit) if is_num(requested_limit) else "your requested limit"
    return (
        "It has {}; {} is possible within that documented range or ceiling, "
        "but the exact limit is subject to underwriting and approval."
    ).format(range_text, requested)


def alternative_sentence(product, requested_limit):
    parts = [product["name"]]
    if is_num(product.get("flat_cashback_pct")):
        parts.append(percent(product["flat_cashback_pct"]) + " cash back on all eligible purchases")
    elif is_num(product.get("travel_cashback_pct")):
        parts.append(percent(product["travel_cashback_pct"]) + " back on eligible travel purchases")
    parts.append("0% foreign transaction fee")
    parts.append(protection_phrase(product))
    parts.append("limit ceiling " + cash(product["credit_limit_max"]) + "; requested limit possible subject to approval")
    notes = product.get("eligibility_notes")
    if isinstance(notes, list):
        cleaned = [str(note).strip() for note in notes if str(note).strip()]
        if cleaned:
            parts.append("important eligibility note: " + "; ".join(cleaned))
    return "; ".join(parts) + "."


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be an object")
        priorities = data.get("customer_priorities", {})
        products = data.get("products")
        if not isinstance(priorities, dict) or not isinstance(products, list):
            raise ValueError("customer_priorities must be an object and products must be an array")
        indexed = {}
        for product in products:
            if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not product["name"].strip():
                raise ValueError("every product must have a nonempty name")
            indexed[product["name"].strip()] = product
        primary_name = data.get("primary_name")
        if not isinstance(primary_name, str) or primary_name.strip() not in indexed:
            raise ValueError("primary_name must exactly match a supplied product name")
        primary_name = primary_name.strip()
        requested_limit = priorities.get("requested_limit")
        primary_errors = qualification_errors(indexed[primary_name], requested_limit)
        if primary_errors:
            print(json.dumps({
                "error": "Cannot render an unqualified primary recommendation.",
                "validation": primary_errors,
            }, indent=2))
            return
        alternatives = data.get("alternatives", [])
        if not isinstance(alternatives, list):
            raise ValueError("alternatives must be an array")
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    primary = indexed[primary_name]
    message = [f"I recommend the {primary_name} as the best documented match for the requirements you listed."]
    message.append(rewards_sentence(primary, priorities))
    message.append("It has a 0% foreign transaction fee.")
    message.append("It includes {}, subject to applicable policy terms and exclusions.".format(protection_phrase(primary)))
    message.append(limit_sentence(primary, requested_limit))

    rendered_alternatives = []
    for name in alternatives:
        if isinstance(name, str) and name.strip() in indexed and name.strip() != primary_name:
            candidate = indexed[name.strip()]
            if not qualification_errors(candidate, requested_limit):
                rendered_alternatives.append(alternative_sentence(candidate, requested_limit))
    if rendered_alternatives:
        message.append("Other documented qualifying options to consider:\n" + "\n".join("- " + item for item in rendered_alternatives))

    print(json.dumps({
        "message": "\n\n".join(message),
        "primary_name": primary_name,
        "source_ids": primary.get("source_ids") if isinstance(primary.get("source_ids"), list) else [],
        "validation": {
            "qualified_primary": True,
            "foreign_transaction_fee_0_pct": True,
            "purchase_protection_documented": True,
            "requested_limit_possible": True,
            "approval_not_guaranteed": True,
        },
    }, indent=2))


if __name__ == "__main__":
    main()
