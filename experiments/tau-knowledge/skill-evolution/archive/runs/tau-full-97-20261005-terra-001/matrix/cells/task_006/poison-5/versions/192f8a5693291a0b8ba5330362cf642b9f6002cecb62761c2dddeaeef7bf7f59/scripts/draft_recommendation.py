#!/usr/bin/env python3
"""Create a customer-facing draft from normalized, source-backed card facts."""
import json
import sys

from screen_cards import screen


def pct(value):
    return ("%.1f" % value) if isinstance(value, (int, float)) and not isinstance(value, bool) else "undocumented"


def score_sentence(terms, customer):
    required = terms.get("minimum_credit_score")
    stated = customer.get("credit_score")
    if required == 0 and isinstance(stated, (int, float)):
        return "The supplied eligibility terms state no minimum credit-score requirement, so your stated score of %s does not exclude you from applying." % stated
    if isinstance(required, (int, float)) and isinstance(stated, (int, float)):
        return "Its disclosed minimum credit score is %s; your stated score of %s meets that disclosed threshold." % (required, stated)
    if isinstance(required, (int, float)):
        return "Its disclosed minimum credit score is %s." % required
    return "The supplied terms do not document a minimum credit-score requirement."


def fit_paragraph(assessment, criteria, customer):
    terms = assessment["documented_terms"]
    name = assessment["name"]
    parts = ["Based on the supplied product terms, %s is a documented match for your stated needs." % name]
    fee_cap = criteria.get("max_foreign_transaction_fee_pct")
    payment_cap = criteria.get("max_minimum_payment_pct")
    fee = pct(terms.get("foreign_transaction_fee_pct"))
    payment = pct(terms.get("minimum_payment_pct"))
    if isinstance(fee_cap, (int, float)):
        parts.append("Its foreign transaction fee is %s%%, within your %s%% cap." % (fee, pct(fee_cap)))
    else:
        parts.append("Its foreign transaction fee is %s%%." % fee)
    if isinstance(payment_cap, (int, float)):
        parts.append("Its minimum monthly payment is %s%% of the outstanding balance, within your %s%% cap." % (payment, pct(payment_cap)))
    else:
        parts.append("Its minimum monthly payment is %s%% of the outstanding balance." % payment)
    parts.append("Virtual card management is available.")
    parts.append(score_sentence(terms, customer))
    parts.append("This comparison does not guarantee approval; final approval can require identity and income information and underwriting review.")
    return " ".join(parts)


def alternative_paragraph(alternatives):
    blocked = [item for item in alternatives if item["eligibility_blockers"]]
    if not blocked:
        return ""
    item = blocked[0]
    return "%s is not a qualifying alternative based on the supplied information: %s." % (item["name"], "; ".join(item["eligibility_blockers"]))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["stdin must contain one JSON object: %s" % exc]}))
        return
    result = screen(payload)
    if not result.get("ok"):
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return
    fits = result["recommendations"]
    if fits:
        message = "\n\n".join(fit_paragraph(item, payload["criteria"], payload["customer"]) for item in fits)
    else:
        details = []
        for item in result["alternatives"]:
            reasons = item["preference_failures"] + item["eligibility_blockers"]
            if reasons:
                details.append("%s: %s" % (item["name"], "; ".join(reasons)))
        message = "I could not identify a documented match from the supplied terms. " + (" ".join(details) if details else "Required product facts are not fully documented.")
    alternative = alternative_paragraph(result["alternatives"])
    if alternative and not fits:
        # The no-fit message already lists documented blockers.
        alternative = ""
    if alternative:
        message += "\n\n" + alternative
    print(json.dumps({"ok": True, "message": message, "recommendations": fits,
                      "alternatives": result["alternatives"], "disclaimer": result["disclaimer"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
