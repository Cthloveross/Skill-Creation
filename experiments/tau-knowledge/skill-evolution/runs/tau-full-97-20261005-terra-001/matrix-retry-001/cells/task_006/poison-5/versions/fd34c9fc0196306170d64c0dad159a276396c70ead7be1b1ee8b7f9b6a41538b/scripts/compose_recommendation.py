#!/usr/bin/env python3
"""Produce a source-grounded customer-facing documented-card comparison.

Read the JSON input described in SKILL.md from stdin. Emit evaluation details and
a ready-to-send ``message`` on stdout. This script is informational and does not
apply for products or perform banking actions.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from evaluate_documented_cards import extract_cards
from match_cards import as_number, as_percent, evaluate_payload


def percent_text(value: Any) -> str:
    parsed = as_percent(value)
    if parsed is None:
        return "unknown"
    rendered = format(parsed.normalize(), "f")
    if "." not in rendered:
        rendered += ".0"
    return rendered + "%"


def score_text(value: Any) -> str:
    parsed = as_number(value)
    if parsed is None:
        return "unknown"
    return format(parsed.normalize(), "f").split(".")[0]


def confirmed_message(qualified: list[dict[str, Any]], customer: dict[str, Any], requirements: dict[str, Any]) -> str:
    names = ", ".join(str(card.get("name", "Documented card")) for card in qualified)
    lead = f"Based on the supplied product documents, {names} {'is' if len(qualified) == 1 else 'are'} a confirmed match for the published criteria you gave."
    paragraphs = [lead]
    supplied_score = as_number(customer.get("credit_score"))

    for card in qualified:
        name = str(card.get("name", "This card"))
        facts: list[str] = []
        threshold = as_number(card.get("minimum_credit_score"))
        if threshold == 0:
            if supplied_score is None:
                facts.append("the documentation states no credit-score requirement (published minimum 0)")
            else:
                facts.append(f"the documentation states no credit-score requirement (published minimum 0), so your stated {score_text(supplied_score)} score does not exclude you from applying")
        elif threshold is not None and supplied_score is not None:
            facts.append(f"the documented minimum credit score is {score_text(threshold)}, and your stated score meets that published minimum")

        if requirements.get("max_foreign_transaction_fee_percent") is not None:
            facts.append(f"the foreign transaction fee is {percent_text(card.get('foreign_transaction_fee_percent'))}, within your {percent_text(requirements.get('max_foreign_transaction_fee_percent'))} maximum")
        if requirements.get("max_minimum_payment_percent") is not None:
            facts.append(f"the minimum monthly payment is {percent_text(card.get('minimum_payment_percent'))} of the outstanding balance, within your {percent_text(requirements.get('max_minimum_payment_percent'))} maximum")
        if requirements.get("requires_virtual_card_management") is True:
            facts.append("virtual-card management is available, which can help organize spending")

        paragraphs.append(name + ": " + "; ".join(facts) + ".")

    if customer.get("income") is not None:
        paragraphs.append("No applicable documented income threshold was used in this comparison.")
    paragraphs.append("This meets the published criteria; it does not guarantee approval.")
    return "\n\n".join(paragraphs)


def nonmatch_message(comparison: dict[str, Any]) -> tuple[str, str]:
    review = comparison.get("needs_review", [])
    failed = comparison.get("not_qualified", [])
    if review:
        details = []
        for card in review:
            unknown = card.get("evaluation", {}).get("unknown", [])
            details.append(f"{card.get('name', 'A documented card')}: " + "; ".join(unknown))
        return "needs_review", "I could not confirm a match from the supplied documents because relevant terms remain unknown: " + " | ".join(details) + "."
    if failed:
        details = []
        for card in failed:
            reasons = card.get("evaluation", {}).get("failed", [])
            details.append(f"{card.get('name', 'A documented card')}: " + "; ".join(reasons))
        return "no_confirmed_match", "I found no confirmed match under the published criteria. Documented blockers: " + " | ".join(details) + ". This is not an approval decision."
    return "no_confirmed_match", "I found no usable product documents to confirm a match. This is not an approval decision."


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        documents = payload.get("documents")
        if not isinstance(documents, list):
            raise ValueError("documents must be an array of current-task product documents")
        customer = payload.get("customer", {})
        requirements = payload.get("requirements", {})
        if not isinstance(customer, dict) or not isinstance(requirements, dict):
            raise ValueError("customer and requirements must be objects")

        cards = extract_cards(documents)
        comparison = evaluate_payload({"customer": customer, "requirements": requirements, "cards": cards})
        qualified = comparison["qualified"]
        if qualified:
            status = "confirmed_match"
            message = confirmed_message(qualified, customer, requirements)
        else:
            status, message = nonmatch_message(comparison)
        output = {"status": status, "message": message, "extracted_cards": cards, **comparison}
    except (ValueError, json.JSONDecodeError) as exc:
        output = {"status": "invalid_input", "error": "invalid_input", "message": str(exc)}
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
