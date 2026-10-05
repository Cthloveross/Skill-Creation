#!/usr/bin/env python3
"""Render a complete, evidence-ready recommendation from supplied card facts.

Input JSON:
{
  "primary_name": "name matching one product",
  "customer_priorities": {
    "primary_category": "optional category",
    "everyday_spend": true,
    "requested_limit": 100000
  },
  "products": [product objects as documented in SKILL.md],
  "alternatives": ["optional matching product names"]
}

Output JSON contains a customer-facing `message`, `validation`, and `source_ids`.
The caller is responsible for extracting each product fact from current public
product documents; this utility makes no product assumptions of its own.
"""

import json
import sys
from typing import Any, Dict, List, Optional


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def money(value: float) -> str:
    return "${:,.0f}".format(value)


def pct(value: float) -> str:
    return "{:g}%".format(value)


def product_index(products: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(products, list):
        raise ValueError("products must be an array")
    result: Dict[str, Dict[str, Any]] = {}
    for item in products:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError("every product must have a nonempty name")
        result[item["name"].strip()] = item
    return result


def protection_description(product: Dict[str, Any]) -> Optional[str]:
    protection = product.get("purchase_protection")
    if not isinstance(protection, dict) or protection.get("available") is not True:
        return None
    parts = ["purchase protection"]
    days = protection.get("days")
    if is_number(days):
        parts.append(f"for up to {days:g} days")
    if protection.get("unlimited") is True:
        parts.append("with documented unlimited coverage")
    else:
        cap = protection.get("max_per_claim")
        if is_number(cap):
            parts.append(f"up to {money(float(cap))} per eligible claim")
    return ", ".join(parts)


def reward_description(product: Dict[str, Any], priorities: Dict[str, Any]) -> str:
    flat = product.get("flat_cashback_pct")
    travel = product.get("travel_cashback_pct")
    category = str(priorities.get("primary_category", "")).strip().lower()
    everyday = priorities.get("everyday_spend") is True
    fragments: List[str] = []
    if is_number(flat):
        fragments.append(f"{pct(float(flat))} cash back on all eligible purchases")
    if category == "travel" and is_number(travel):
        fragments.append(f"{pct(float(travel))} back on eligible travel purchases")
    if not fragments:
        return "The supplied record does not establish a rewards rate, so review the source before adding a rewards claim."
    explanation = " and ".join(fragments)
    if everyday and is_number(flat):
        return f"It earns {explanation}, which supports both everyday spending and travel-heavy spend."
    if category == "travel":
        return f"It earns {explanation}, which is relevant to travel-led spending."
    return f"It earns {explanation}."


def validate_primary(product: Dict[str, Any], requested_limit: Any) -> List[str]:
    errors: List[str] = []
    if product.get("foreign_transaction_fee_pct") != 0:
        errors.append("primary product does not document a 0% foreign transaction fee")
    if protection_description(product) is None:
        errors.append("primary product does not document purchase protection")
    maximum = product.get("credit_limit_max")
    if not is_number(maximum):
        errors.append("primary product lacks a documented maximum credit limit")
    elif is_number(requested_limit) and float(maximum) < float(requested_limit):
        errors.append("primary product maximum credit limit is below the requested limit")
    return errors


def limit_sentence(product: Dict[str, Any], requested: Any) -> str:
    lower = product.get("credit_limit_min")
    upper = product.get("credit_limit_max")
    if is_number(lower) and is_number(upper):
        range_text = f"a documented typical/standard limit range of {money(float(lower))}–{money(float(upper))}"
    elif is_number(upper):
        range_text = f"a documented limit ceiling of {money(float(upper))}"
    else:
        range_text = "a limit range that requires source review"
    requested_text = money(float(requested)) if is_number(requested) else "your requested limit"
    return f"It has {range_text}, so {requested_text} is possible within the documented range; the exact limit is subject to underwriting and approval."


def alternative_sentence(product: Dict[str, Any], requested: Any) -> str:
    name = product["name"].strip()
    components = [name]
    flat = product.get("flat_cashback_pct")
    if is_number(flat):
        components.append(f"{pct(float(flat))} on all eligible purchases")
    components.append("0% foreign transaction fee" if product.get("foreign_transaction_fee_pct") == 0 else "foreign-fee term requires review")
    protection = protection_description(product)
    if protection:
        components.append(protection)
    maximum = product.get("credit_limit_max")
    if is_number(maximum):
        requested_text = money(float(requested)) if is_number(requested) else "the requested limit"
        components.append(f"ceiling {money(float(maximum))}, making {requested_text} possible subject to approval")
    notes = product.get("eligibility_notes")
    if isinstance(notes, list) and notes:
        clean_notes = [str(note).strip() for note in notes if str(note).strip()]
        if clean_notes:
            components.append("important eligibility note: " + "; ".join(clean_notes))
    return "; ".join(components) + "."


def main() -> None:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be an object")
        priorities = data.get("customer_priorities", {})
        if not isinstance(priorities, dict):
            raise ValueError("customer_priorities must be an object")
        products = product_index(data.get("products"))
        primary_name = data.get("primary_name")
        if not isinstance(primary_name, str) or primary_name.strip() not in products:
            raise ValueError("primary_name must exactly match a supplied product name")
        primary = products[primary_name.strip()]
        requested_limit = priorities.get("requested_limit")
        errors = validate_primary(primary, requested_limit)
        if errors:
            print(json.dumps({"error": "Cannot render an unqualified primary recommendation.", "validation": errors}, indent=2))
            return

        lines = [f"I recommend the {primary_name.strip()} as the best match for the requirements you listed."]
        lines.append(reward_description(primary, priorities))
        lines.append("It has a 0% foreign transaction fee.")
        protection = protection_description(primary)
        lines.append(f"It includes {protection}, subject to applicable policy terms and exclusions.")
        lines.append(limit_sentence(primary, requested_limit))

        raw_alternatives = data.get("alternatives", [])
        if not isinstance(raw_alternatives, list):
            raise ValueError("alternatives must be an array")
        alt_lines: List[str] = []
        for alternative_name in raw_alternatives:
            if not isinstance(alternative_name, str) or alternative_name.strip() == primary_name.strip():
                continue
            alternative = products.get(alternative_name.strip())
            if alternative is None:
                continue
            if not validate_primary(alternative, requested_limit):
                alt_lines.append(alternative_sentence(alternative, requested_limit))
        if alt_lines:
            lines.append("Other documented qualifying options to consider:")
            lines.extend("- " + line for line in alt_lines)

        source_ids = primary.get("source_ids", [])
        print(json.dumps({
            "message": "\n\n".join(lines),
            "primary_name": primary_name.strip(),
            "source_ids": source_ids if isinstance(source_ids, list) else [],
            "validation": {
                "qualified_primary": True,
                "foreign_transaction_fee_0_pct": True,
                "purchase_protection_documented": True,
                "requested_limit_possible": True,
                "approval_not_guaranteed": True,
            },
        }, indent=2))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))


if __name__ == "__main__":
    main()
