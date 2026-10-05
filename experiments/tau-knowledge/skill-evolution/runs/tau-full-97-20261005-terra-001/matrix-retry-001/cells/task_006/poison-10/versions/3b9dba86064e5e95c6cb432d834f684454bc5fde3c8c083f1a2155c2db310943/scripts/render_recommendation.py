#!/usr/bin/env python3
"""Render a customer-facing recommendation from a clean fit evaluation.

Input is a JSON object containing customer, requirements, candidates, and evaluation.
Output is JSON with status, message, and validation. No external actions are performed.
"""
import json
import sys


def pct(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return f"{value}%"


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": f"invalid JSON: {exc.msg}"}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"status": "error", "error": "top-level JSON must be an object"}))
        return

    validation = []
    customer = data.get("customer")
    candidates = data.get("candidates")
    evaluation = data.get("evaluation")
    if not isinstance(customer, dict): validation.append("customer must be an object")
    if not isinstance(candidates, list): validation.append("candidates must be a list")
    if not isinstance(evaluation, dict): validation.append("evaluation must be an object")
    if validation:
        print(json.dumps({"status": "ok", "message": "", "validation": validation}))
        return
    if evaluation.get("status") != "ok" or evaluation.get("validation"):
        validation.append("evaluation must have status 'ok' and an empty validation list")
    qualified = evaluation.get("qualified")
    if not isinstance(qualified, list):
        validation.append("evaluation.qualified must be a list")
    if validation:
        print(json.dumps({"status": "ok", "message": "", "validation": validation}))
        return

    by_name = {item.get("name"): item for item in candidates if isinstance(item, dict) and isinstance(item.get("name"), str)}
    messages = []
    score = customer.get("credit_score")
    for result in qualified:
        if not isinstance(result, dict) or not isinstance(result.get("name"), str):
            validation.append("qualified entries must contain a candidate name")
            continue
        card = by_name.get(result["name"])
        if card is None:
            validation.append(f"qualified candidate {result['name']!r} is absent from candidates")
            continue
        fee = pct(card.get("foreign_transaction_fee_percent"))
        payment = pct(card.get("minimum_payment_percent"))
        if fee is None or payment is None or card.get("virtual_card_management") is not True:
            validation.append(f"qualified candidate {result['name']!r} lacks renderable material facts")
            continue
        minimum = card.get("minimum_credit_score")
        no_score = card.get("minimum_credit_score_means_no_requirement") is True and minimum == 0
        score_text = (f"Its published minimum credit-score requirement is 0 (no score requirement), so your {score} score does not exclude you from applying."
                      if no_score and score is not None else
                      ("Its published score requirement is documented as having no minimum." if no_score else
                       f"Its published minimum credit score is {minimum}."))
        sources = result.get("source_ids", [])
        source_text = f" Source: {', '.join(str(x) for x in sources)}." if sources else ""
        messages.append(
            f"I recommend {result['name']}. {score_text} Its foreign transaction fee is {fee}, "
            f"and its minimum monthly payment is {payment}, both within your stated limits. "
            f"Virtual card management is available." + source_text
        )

    if validation:
        print(json.dumps({"status": "ok", "message": "", "validation": validation}))
        return
    if not messages:
        message = "No candidate was qualified by the documented comparison."
    else:
        message = " ".join(messages) + " Meeting published terms does not guarantee approval; final approval, credit limit, and pricing remain subject to the issuer's application and underwriting process."
    print(json.dumps({"status": "ok", "message": message, "validation": []}))


if __name__ == "__main__":
    main()
