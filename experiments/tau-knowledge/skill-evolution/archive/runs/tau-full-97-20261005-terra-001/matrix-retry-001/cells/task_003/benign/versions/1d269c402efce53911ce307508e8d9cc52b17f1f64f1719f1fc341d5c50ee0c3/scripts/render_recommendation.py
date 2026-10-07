#!/usr/bin/env python3
"""Render a documented card recommendation from caller-supplied facts.

Reads JSON from stdin and writes JSON to stdout. Required keys are
primary_name, customer_priorities, and products. Product facts must originate
in current task documents; this program does not retrieve or invent them.
"""
import json
import sys


def is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def cash(value):
    return "${:,.0f}".format(float(value))


def pct(value):
    return "{:g}%".format(float(value))


def protection_phrase(product):
    info = product.get("purchase_protection")
    if not isinstance(info, dict) or info.get("available") is not True:
        return None
    parts = ["purchase protection"]
    if is_num(info.get("days")):
        parts.append("for up to {:g} days".format(info["days"]))
    if info.get("unlimited") is True:
        parts.append("with documented unlimited coverage")
    elif is_num(info.get("max_per_claim")):
        parts.append("up to {} per eligible claim".format(cash(info["max_per_claim"])))
    return ", ".join(parts)


def qualified(product, requested_limit):
    errors = []
    if product.get("foreign_transaction_fee_pct") != 0:
        errors.append("does not document a 0% foreign transaction fee")
    if protection_phrase(product) is None:
        errors.append("does not document purchase protection")
    maximum = product.get("credit_limit_max")
    if not is_num(maximum):
        errors.append("does not document a credit-limit ceiling")
    elif is_num(requested_limit) and float(maximum) < float(requested_limit):
        errors.append("documented limit ceiling is below requested limit")
    return errors


def rewards_phrase(product, priorities):
    pieces = []
    flat = product.get("flat_cashback_pct")
    travel = product.get("travel_cashback_pct")
    if is_num(flat):
        pieces.append(pct(flat) + " cash back on all eligible purchases")
    if str(priorities.get("primary_category", "")).lower() == "travel" and is_num(travel):
        pieces.append(pct(travel) + " back on eligible travel purchases")
    if not pieces:
        return "No documented rewards statement is available for this record."
    text = " and ".join(pieces)
    if priorities.get("everyday_spend") is True and is_num(flat):
        return "It earns " + text + ", which fits everyday purchases while also rewarding travel-heavy spending."
    if str(priorities.get("primary_category", "")).lower() == "travel":
        return "It earns " + text + ", which fits travel-led spending."
    return "It earns " + text + "."


def limit_phrase(product, requested):
    lower, upper = product.get("credit_limit_min"), product.get("credit_limit_max")
    if is_num(lower) and is_num(upper):
        range_text = "a documented credit-limit range of {}–{}".format(cash(lower), cash(upper))
    else:
        range_text = "a documented credit-limit ceiling of " + cash(upper)
    desired = cash(requested) if is_num(requested) else "your requested limit"
    return "It has {}; {} is possible within that documented range or ceiling, but the exact limit is subject to underwriting and approval.".format(range_text, desired)


def alternative_phrase(product, requested):
    parts = [product["name"]]
    if is_num(product.get("flat_cashback_pct")):
        parts.append(pct(product["flat_cashback_pct"]) + " on all eligible purchases")
    parts.append("0% foreign transaction fee")
    parts.append(protection_phrase(product))
    parts.append("limit ceiling " + cash(product["credit_limit_max"]) + "; " + (cash(requested) if is_num(requested) else "requested limit") + " is possible subject to approval")
    notes = product.get("eligibility_notes")
    if isinstance(notes, list):
        notes = [str(note).strip() for note in notes if str(note).strip()]
        if notes:
            parts.append("important eligibility note: " + "; ".join(notes))
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
        requested = priorities.get("requested_limit")
        errors = qualified(indexed[primary_name], requested)
        if errors:
            print(json.dumps({"error": "Cannot render an unqualified primary recommendation.", "validation": errors}, indent=2))
            return
        alternatives = data.get("alternatives", [])
        if not isinstance(alternatives, list):
            raise ValueError("alternatives must be an array")
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    primary = indexed[primary_name]
    message = ["I recommend the {} as the best match for the requirements you listed.".format(primary_name)]
    message.append(rewards_phrase(primary, priorities))
    message.append("It has a 0% foreign transaction fee.")
    message.append("It includes {}, subject to applicable policy terms and exclusions.".format(protection_phrase(primary)))
    message.append(limit_phrase(primary, requested))
    rendered = []
    for name in alternatives:
        if isinstance(name, str) and name.strip() in indexed and name.strip() != primary_name:
            candidate = indexed[name.strip()]
            if not qualified(candidate, requested):
                rendered.append(alternative_phrase(candidate, requested))
    if rendered:
        message.append("Other documented qualifying options to consider:\n" + "\n".join("- " + item for item in rendered))
    print(json.dumps({
        "message": "\n\n".join(message),
        "primary_name": primary_name,
        "source_ids": primary.get("source_ids") if isinstance(primary.get("source_ids"), list) else [],
        "validation": {"qualified_primary": True, "foreign_transaction_fee_0_pct": True,
                       "purchase_protection_documented": True, "requested_limit_possible": True,
                       "approval_not_guaranteed": True}
    }, indent=2))


if __name__ == "__main__":
    main()
