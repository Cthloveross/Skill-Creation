#!/usr/bin/env python3
"""Extract common labeled terms from supplied card documents, then screen them."""
import json
import re
import sys
from pathlib import Path

from screen_cards import main as unused_main  # verifies packaged helper is importable
from screen_cards import assess


def value(pattern, text, flags=re.I):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def set_fact(card, key, parsed, source, warnings):
    if parsed is None:
        return
    old = card.get(key)
    if old is None:
        card[key] = parsed
    elif old != parsed:
        card[key] = None
        warnings.append("conflicting %s for %s; retained as unknown" % (key, card["name"]))
    card["source_notes"].append(source)


def card_name(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    name = title.split(":", 1)[0].strip()
    return name or None


def extract(documents):
    cards, warnings = {}, []
    for index, doc in enumerate(documents):
        if not isinstance(doc, dict) or not isinstance(doc.get("content"), str):
            warnings.append("documents[%d] is not an object with text content" % index)
            continue
        name = card_name(doc.get("title"))
        if not name:
            warnings.append("documents[%d] has no card-name title prefix and was skipped" % index)
            continue
        card = cards.setdefault(name, {"name": name, "foreign_transaction_fee_pct": None,
            "minimum_payment_pct": None, "virtual_card_management": None,
            "minimum_credit_score": None, "subscription_requirement": "unknown",
            "invitation_only": None, "minimum_annual_income": None, "source_notes": []})
        text = doc["content"]
        source = str(doc.get("document_id") or doc.get("title") or ("document[%d]" % index))
        fee = value(r"foreign\s+transaction\s+fee[^:\n]*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%", text)
        payment = value(r"minimum\s+(?:monthly\s+)?payment\s*(?:is|:)[^0-9\n]*\$?([0-9]+(?:\.[0-9]+)?)\s*%", text)
        virtual = value(r"virtual\s+card\s+management(?:\s+features)?\s+(?:are\s+)?(?:available\s*)?:?\s*(yes|no)", text)
        score = value(r"minimum\s+credit\s+score(?:\s+required)?(?:\s+to\s+apply)?\s*:\s*\$?([0-9]+)", text)
        subscription = re.search(r"([A-Za-z][A-Za-z0-9+\- ]*?)\s+subscription\s+required\s*:\s*(yes|no)", text, re.I)
        invitation = value(r"invitation\s+only\s*\(?\s*:\s*\)?\s*(yes|no)", text)
        for key, raw, convert in (("foreign_transaction_fee_pct", fee, float),
                                  ("minimum_payment_pct", payment, float),
                                  ("minimum_credit_score", score, int)):
            if raw is not None:
                set_fact(card, key, convert(raw), source, warnings)
        if virtual is not None:
            set_fact(card, "virtual_card_management", virtual.casefold() == "yes", source, warnings)
        if invitation is not None:
            set_fact(card, "invitation_only", invitation.casefold() == "yes", source, warnings)
        if subscription:
            requirement = subscription.group(1).strip() if subscription.group(2).casefold() == "yes" else "none"
            set_fact(card, "subscription_requirement", requirement, source, warnings)
    return list(cards.values()), warnings


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["stdin must contain one JSON object: %s" % exc]})); return
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        print(json.dumps({"ok": False, "errors": ["documents must be a list"]})); return
    if not isinstance(payload.get("customer"), dict) or not isinstance(payload.get("criteria"), dict):
        print(json.dumps({"ok": False, "errors": ["customer and criteria must be objects"]})); return
    cards, warnings = extract(payload["documents"])
    assessments = [assess(card, payload["customer"], payload["criteria"]) for card in cards]
    order = {"documented_fit": 0, "known_eligibility_blocker": 1, "does_not_meet_preferences": 2, "insufficient_documentation": 3}
    assessments.sort(key=lambda x: (order[x["tier"]], x["name"].casefold()))
    print(json.dumps({"ok": True, "cards": cards, "extraction_warnings": warnings,
        "recommendations": [x for x in assessments if x["tier"] == "documented_fit"],
        "alternatives": [x for x in assessments if x["tier"] != "documented_fit"],
        "assessments": assessments,
        "disclaimer": "Review extracted values against the supplied documents; results are not approval decisions."}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
