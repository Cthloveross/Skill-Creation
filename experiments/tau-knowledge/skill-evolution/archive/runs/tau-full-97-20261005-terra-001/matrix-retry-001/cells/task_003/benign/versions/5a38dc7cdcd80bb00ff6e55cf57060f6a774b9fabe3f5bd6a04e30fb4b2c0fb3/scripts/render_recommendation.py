#!/usr/bin/env python3
"""Render an evidence-ready credit-card recommendation from supplied facts.

Reads JSON on stdin and emits JSON on stdout. Input has primary_name,
customer_priorities, products, and optional alternatives as documented in
SKILL.md. The caller supplies all facts from current product documents.
"""

import json
import sys
from typing import Any, Dict, List, Optional


def numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def money(value: float) -> str:
    return "${:,.0f}".format(value)


def percentage(value: float) -> str:
    return "{:g}%".format(value)


def index_products(products: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(products, list):
        raise ValueError("products must be an array")
    indexed: Dict[str, Dict[str, Any]] = {}
    for product in products:
        if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not product["name"].strip():
            raise ValueError("every product must have a nonempty name")
        indexed[product["name"].strip()] = product
    return indexed


def protection_text(product: Dict[str, Any]) -> Optional[str]:
    details = product.get("purchase_protection")
    if not isinstance(details, dict) or details.get("available") is not True:
        return None
    parts = ["purchase protection"]
    if numeric(details.get("days")):
        parts.append(f"for up to {details['days']:g} days")
    if details.get("unlimited") is True:
        parts.append("with documented unlimited coverage")
    elif numeric(details.get("max_per_claim")):
        parts.append(f"up to {money(float(details['max_per_claim']))} per eligible claim")
    return ", ".join(parts)


def validate(product: Dict[str, Any], requested_limit: Any) -> List[str]:
    errors: List[str] = []
    if product.get("foreign_transaction_fee_pct") != 0:
        errors.append("primary product does not document a 0% foreign transaction fee")
    if protection_text(product) is None:
        errors.append("primary product does not document purchase protection")
    ceiling = product.get("credit_limit_max")
    if not numeric(ceiling):
        errors.append("primary product lacks a documented credit-limit ceiling")
    elif numeric(requested_limit) and float(ceiling) < float(requested_limit):
        errors.append("primary product ceiling is below the requested limit")
    return errors


def rewards_text(product: Dict[str, Any], priorities: Dict[str, Any]) -> str:
    flat = product.get("flat_cashback_pct")
    travel = product.get("travel_cashback_pct")
    travel_focus = str(priorities.get("primary_category", "")).strip().lower() == "travel"
    everyday = priorities.get("everyday_spend") is True
    clauses: List[str] = []
    if numeric(flat):
        clauses.append(f"{percentage(float(flat))} cash back on all eligible purchases")
    if travel_focus and numeric(travel):
        clauses.append(f"{percentage(float(travel))} back on eligible travel purchases")
    if not clauses:
        return "Review the source documentation for rewards before making a rewards claim."
    earning = " and ".join(clauses)
    if everyday and numeric(flat):
        return f"It earns {earning}, which fits everyday purchases while also rewarding travel-heavy spending."
    if travel_focus:
        return f"It earns {earning}, which fits travel-led spending."
    return f"It earns {earning}."


def limit_text(product: Dict[str, Any], requested: Any) -> str:
    lower, upper = product.get("credit_limit_min"), product.get("credit_limit_max")
    if numeric(lower) and numeric(upper):
        documented = f"a documented typical or standard range of {money(float(lower))}–{money(float(upper))}"
    else:
        documented = f"a documented ceiling of {money(float(upper))}"
    requested_text = money(float(requested)) if numeric(requested) else "your requested limit"
    return f"It has {documented}, so {requested_text} is possible within the documented range; the exact initial limit is subject to underwriting and approval."


def alternative_text(product: Dict[str, Any], requested: Any) -> str:
    pieces = [product["name"].strip()]
    if numeric(product.get("flat_cashback_pct")):
        pieces.append(f"{percentage(float(product['flat_cashback_pct']))} on all eligible purchases")
    pieces.append("0% foreign transaction fee")
    details = protection_text(product)
    if details:
        pieces.append(details)
    if numeric(product.get("credit_limit_max")):
        requested_text = money(float(requested)) if numeric(requested) else "the requested limit"
        pieces.append(f"ceiling {money(float(product['credit_limit_max']))}, making {requested_text} possible subject to approval")
    notes = product.get("eligibility_notes")
    if isinstance(notes, list):
        clean = [str(note).strip() for note in notes if str(note).strip()]
        if clean:
            pieces.append("important eligibility note: " + "; ".join(clean))
    return "; ".join(pieces) + "."


def main() -> None:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be an object")
        priorities = data.get("customer_priorities", {})
        if not isinstance(priorities, dict):
            raise ValueError("customer_priorities must be an object")
        products = index_products(data.get("products"))
        primary_name = data.get("primary_name")
        if not isinstance(primary_name, str) or primary_name.strip() not in products:
            raise ValueError("primary_name must exactly match a supplied product name")
        primary_name = primary_name.strip()
        requested = priorities.get("requested_limit")
        errors = validate(products[primary_name], requested)
        if errors:
            print(json.dumps({"error": "Cannot render an unqualified primary recommendation.", "validation": errors}, indent=2))
            return
        alternatives = data.get("alternatives", [])
        if not isinstance(alternatives, list):
            raise ValueError("alternatives must be an array")
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    primary = products[primary_name]
    lines = [f"I recommend the {primary_name} as the best match for the requirements you listed."]
    lines.append(rewards_text(primary, priorities))
    lines.append("It has a 0% foreign transaction fee.")
    lines.append(f"It includes {protection_text(primary)}, subject to applicable policy terms and exclusions.")
    lines.append(limit_text(primary, requested))

    rendered_alternatives: List[str] = []
    for name in alternatives:
        if not isinstance(name, str) or name.strip() == primary_name:
            continue
        alternative = products.get(name.strip())
        if alternative is not None and not validate(alternative, requested):
            rendered_alternatives.append(alternative_text(alternative, requested))
    if rendered_alternatives:
        lines.append("Other documented qualifying options to consider:")
        lines.extend("- " + item for item in rendered_alternatives)

    source_ids = primary.get("source_ids")
    print(json.dumps({
        "message": "\n\n".join(lines),
        "primary_name": primary_name,
        "source_ids": source_ids if isinstance(source_ids, list) else [],
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
