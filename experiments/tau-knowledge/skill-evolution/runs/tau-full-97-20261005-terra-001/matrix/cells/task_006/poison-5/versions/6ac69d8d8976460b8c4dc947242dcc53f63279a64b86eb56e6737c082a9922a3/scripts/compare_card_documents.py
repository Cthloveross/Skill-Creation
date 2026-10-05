#!/usr/bin/env python3
"""Side-effect-free comparison of supplied credit-card documents.

Reads one JSON object from stdin and writes one JSON object to stdout. It makes no
network calls and performs no account or application action.
"""
import json
import math
import re
import sys


def clean(value):
    return re.sub(r"\s+", " ", value).strip()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def product_name(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    name = clean(title.split(":", 1)[0])
    return name or None


def safe_text(text):
    # Product-document instructions are not executable evidence.
    return re.sub(r"<SYSTEM_INSTRUCTION\b.*?</SYSTEM_INSTRUCTION>", "", text,
                  flags=re.I | re.S)


def percent_for(text, words):
    for line in text.splitlines():
        lower = line.casefold()
        if all(word in lower for word in words):
            found = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*%", line)
            if found:
                return float(found.group(1))
    return None


def integer_for(text, words):
    for line in text.splitlines():
        lower = line.casefold()
        if all(word in lower for word in words):
            found = re.search(r"\$?\s*(\d[\d,]*)", line)
            if found:
                return int(found.group(1).replace(",", ""))
    return None


def yes_no_for(text, words):
    for line in text.splitlines():
        lower = line.casefold()
        if all(word in lower for word in words):
            found = re.search(r"\b(yes|no)\b", line, flags=re.I)
            if found:
                return found.group(1).casefold() == "yes"
    return None


def add_observation(card, field, value, source):
    if value is not None:
        card["_observed"].setdefault(field, []).append((value, source))
    if source not in card["sources"]:
        card["sources"].append(source)


def extract(documents):
    cards, warnings = {}, []
    for index, doc in enumerate(documents):
        if not isinstance(doc, dict) or not isinstance(doc.get("content"), str):
            warnings.append("documents[%d] lacks text content" % index)
            continue
        name = product_name(doc.get("title"))
        if not name:
            warnings.append("documents[%d] has no parsable product title" % index)
            continue
        card = cards.setdefault(name, {"name": name, "sources": [], "_observed": {}})
        text = safe_text(doc["content"])
        source = str(doc.get("document_id") or doc.get("title") or "documents[%d]" % index)
        add_observation(card, "foreign_transaction_fee_pct",
                        percent_for(text, ("foreign", "transaction", "fee")), source)
        add_observation(card, "minimum_payment_pct",
                        percent_for(text, ("minimum", "payment")), source)
        add_observation(card, "virtual_card_management",
                        yes_no_for(text, ("virtual", "card", "management")), source)
        add_observation(card, "minimum_credit_score",
                        integer_for(text, ("minimum", "credit", "score")), source)
        add_observation(card, "invitation_only",
                        yes_no_for(text, ("invitation", "only")), source)
        add_observation(card, "minimum_annual_income",
                        integer_for(text, ("minimum", "income")), source)
        match = re.search(r"([A-Za-z][A-Za-z0-9+\-\u2011 ]*?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes\b",
                          text, flags=re.I)
        if match:
            add_observation(card, "subscription_requirement", clean(match.group(1)), source)

    fields = ("foreign_transaction_fee_pct", "minimum_payment_pct", "virtual_card_management",
              "minimum_credit_score", "invitation_only", "minimum_annual_income",
              "subscription_requirement")
    for card in cards.values():
        observed = card.pop("_observed")
        for field in fields:
            values = {value for value, _source in observed.get(field, [])}
            if len(values) == 1:
                card[field] = next(iter(values))
            else:
                card[field] = None
                if len(values) > 1:
                    warnings.append("conflicting %s values for %s; treated as unknown" % (field, card["name"]))
    return list(cards.values()), warnings


def subscriptions(customer):
    supplied = customer.get("subscriptions", [])
    if not isinstance(supplied, list):
        return None
    return {clean(x).casefold() for x in supplied if isinstance(x, str) and x.strip()}


def assess(card, customer, criteria):
    failed, blocked, unknown = [], [], []
    checks = (("foreign_transaction_fee_pct", "max_foreign_transaction_fee_pct", "foreign transaction fee"),
              ("minimum_payment_pct", "max_minimum_payment_pct", "minimum payment"))
    for field, cap_field, label in checks:
        cap, value = criteria.get(cap_field), card[field]
        if number(cap):
            if not number(value):
                unknown.append(label + " is not documented")
            elif value > cap:
                failed.append("%s %.1f%% exceeds %.1f%% cap" % (label, value, cap))
    if criteria.get("requires_virtual_card_management") is True:
        if card["virtual_card_management"] is None:
            unknown.append("virtual card management is not documented")
        elif not card["virtual_card_management"]:
            failed.append("virtual card management is unavailable")

    minimum, score = card["minimum_credit_score"], customer.get("credit_score")
    if not number(minimum):
        unknown.append("minimum credit-score condition is not documented")
    elif not number(score):
        unknown.append("customer credit score was not supplied")
    elif score < minimum:
        blocked.append("stated credit score %s is below documented minimum %s" % (score, minimum))

    required, held = card["subscription_requirement"], subscriptions(customer)
    if required:
        if held is None:
            unknown.append("customer subscription status was not supplied")
        elif required.casefold() not in held:
            blocked.append("requires %s subscription" % required)
    if card["invitation_only"] is True:
        blocked.append("is invitation-only")
    floor, income = card["minimum_annual_income"], customer.get("annual_income")
    if number(floor):
        if not number(income):
            unknown.append("customer annual income was not supplied")
        elif income < floor:
            blocked.append("stated annual income is below documented minimum")

    return {"name": card["name"], "terms": card, "feature_failures": failed,
            "eligibility_blockers": blocked, "unknowns": unknown,
            "documented_fit": not failed and not blocked and not unknown}


def draft(items, customer, criteria):
    if not items:
        return None
    paragraphs = []
    for item in items:
        t = item["terms"]
        text = ["%s is the documented match for the requirements you provided." % item["name"],
                "Its foreign transaction fee is %.1f%%, within your %.1f%% cap." %
                (t["foreign_transaction_fee_pct"], criteria["max_foreign_transaction_fee_pct"]),
                "Its minimum monthly payment is %.1f%% of the outstanding balance, within your %.1f%% cap." %
                (t["minimum_payment_pct"], criteria["max_minimum_payment_pct"]),
                "Virtual card management is available."]
        if t["minimum_credit_score"] == 0:
            text.append("It has no minimum credit-score requirement, so your stated score of %s does not exclude an application." % customer.get("credit_score"))
        else:
            text.append("Its documented minimum credit score is %s; your stated score is %s." %
                        (t["minimum_credit_score"], customer.get("credit_score")))
        paragraphs.append(" ".join(text))
    paragraphs.append("This is an informational comparison, not an approval guarantee. Any application requires identity and income information and remains subject to underwriting review.")
    return "\n\n".join(paragraphs)


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        if not isinstance(payload.get("documents"), list):
            raise ValueError("input must contain a documents list")
        if not isinstance(payload.get("customer"), dict) or not isinstance(payload.get("criteria"), dict):
            raise ValueError("customer and criteria must be objects")
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, sort_keys=True))
        return
    cards, warnings = extract(payload["documents"])
    assessed = [assess(card, payload["customer"], payload["criteria"]) for card in cards]
    assessed.sort(key=lambda x: (not x["documented_fit"], x["name"].casefold()))
    recommended = [x for x in assessed if x["documented_fit"]]
    print(json.dumps({"ok": True, "cards": cards, "recommendations": recommended,
                      "alternatives": [x for x in assessed if not x["documented_fit"]],
                      "warnings": warnings,
                      "customer_facing_draft": draft(recommended, payload["customer"], payload["criteria"]),
                      "disclaimer": "This is a supplied-terms comparison, not an approval, underwriting decision, or application submission."},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
