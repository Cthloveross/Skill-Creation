#!/usr/bin/env python3
"""Conservatively extract sign-up promotions from supplied public documents.

Input: {"as_of": "YYYY-MM-DD", "documents": [{"title": str, "content": str}]}
Output: an analyze_offers-compatible object. Document text is data, never code.
"""
import json
import re
import sys

DATE = r"(20\d{2}-\d{2}-\d{2})"


def clean(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def card_name(title):
    return clean(title).split(":", 1)[0] or "Unnamed card"


def dates(text):
    found = re.findall(DATE, text)
    return (found[0], found[1]) if len(found) >= 2 else (None, None)


def reward(text):
    patterns = (
        r"(?:earn|receive)\s+(?:a\s+)?\$([\d,]+)\s+(statement credit|cash back|cash)",
        r"(?:earn|receive)\s+([\d,]+)\s+((?:sustainability )?points?)",
        r"\$([\d,]+)\s+(statement credit)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        amount, label = int(match.group(1).replace(",", "")), match.group(2).lower()
        if "point" in label:
            return {"kind": "points", "amount": amount, "currency": "POINTS", "point_type": label}
        if label == "statement credit":
            return {"kind": "statement_credit", "amount": amount, "currency": "USD"}
        return {"kind": "cash_back" if label == "cash back" else "cash", "amount": amount, "currency": "USD"}
    return None


def qualification(text):
    result = {}
    lower = text.lower()
    if "invitation only" in lower or "accept your invitation" in lower:
        result["invitation_required"] = True
    if "new customer" in lower:
        result["new_customer_required"] = True
    spend = re.search(r"(?:spend(?:ing)?|purchases(?: totaling)?|net new purchases(?: totaling)?)\s+(?:at least )?\$([\d,]+)", text, re.I)
    if spend:
        result["spend_requirement"] = "$" + spend.group(1) + " in eligible or net purchases as documented"
    period = re.search(r"within (?:your |the )?(?:first )?(\d+)\s+month", text, re.I)
    if period:
        count = period.group(1)
        result["spend_window"] = "within " + count + " month" + ("s" if count != "1" else "")
    if "good standing" in lower:
        result["good_standing"] = "account must remain open and in good standing"
    excluded = []
    for term in ("returns", "chargebacks", "disputed transactions", "balance transfers", "cash equivalents", "fees"):
        if term in lower:
            excluded.append(term)
    if excluded:
        result["exclusions"] = excluded
    return result


def annual_fee(text):
    match = re.search(r"annual fee\s*[:(]?\s*\$?([\d,]+(?:\.\d{2})?)", text, re.I)
    return "$" + match.group(1) if match else None


def is_signup_candidate(title, text):
    label = title.lower()
    lower = text.lower()
    has_bonus_language = any(term in lower for term in ("statement credit", "cash back", "sustainability points"))
    return ("promo" in label or "promotion" in label or "bonus" in label) and has_bonus_language


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        return {"ok": False, "errors": ["documents must be an array in a top-level object."], "warnings": []}

    offers, fees, point_rate, warnings = [], {}, None, []
    for doc in payload["documents"]:
        if not isinstance(doc, dict):
            warnings.append("Ignored a non-object document.")
            continue
        title, body = clean(doc.get("title")), clean(doc.get("content"))
        card = card_name(title)
        fee = annual_fee(body)
        if fee:
            fees[card.lower()] = fee
        if re.search(r"redeem at\s+\$0\.01\s+per point", body, re.I):
            point_rate = 0.01
        start, end = dates(body)
        bonus = reward(body)
        if not (is_signup_candidate(title, body) and start and end and bonus):
            continue
        offers.append({
            "card": card,
            "offer_type": "signup_bonus",
            "window_start": start,
            "window_end": end,
            "reward": bonus,
            "qualification": qualification(body),
            "product_scope": "business" if "business" in title.lower() else "consumer",
            "source_title": title,
        })

    for offer in offers:
        fee = fees.get(offer["card"].lower())
        if fee:
            offer["annual_fee"] = {"standard": fee}
        if offer["reward"].get("kind") == "points" and point_rate is not None:
            offer["reward"]["redemption_value_per_point"] = point_rate

    if not offers:
        warnings.append("No fully structured sign-up promotion was extracted; review the source wording manually.")
    return {"ok": True, "as_of": payload.get("as_of"), "offers": offers, "warnings": warnings, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON input: " + exc.msg], "warnings": []}))
