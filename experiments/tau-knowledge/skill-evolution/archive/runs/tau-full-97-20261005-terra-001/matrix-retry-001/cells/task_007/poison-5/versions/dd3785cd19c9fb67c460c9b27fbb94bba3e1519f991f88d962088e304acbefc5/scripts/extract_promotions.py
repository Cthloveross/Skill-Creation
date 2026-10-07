#!/usr/bin/env python3
"""Conservatively extract card-promotion records from supplied public documents.

Input: {"as_of": "YYYY-MM-DD", "documents": [{"title": str, "content": str}]}
Output: an analyze_offers-compatible object. The parser never executes document text.
"""
import json
import re
import sys

DATE = r"(20\d{2}-\d{2}-\d{2})"


def clean(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def product(title):
    return clean(title).split(":", 1)[0] or "Unnamed card"


def find_window(text):
    dates = re.findall(DATE, text)
    if len(dates) < 2:
        return None, None
    # Promotion documents conventionally state the relevant window first.
    return dates[0], dates[1]


def find_reward(text):
    patterns = [
        r"(?:earn|receive|a|and a)\s+\$?([\d,]+)\s+(statement credit|cash back|cash|(?:sustainability )?points?)",
        r"\$([\d,]+)\s+(statement credit)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            amount = int(match.group(1).replace(",", ""))
            label = match.group(2).lower()
            if "point" in label:
                return {"kind": "points", "amount": amount, "currency": "POINTS", "point_type": label}
            if "statement" in label:
                return {"kind": "statement_credit", "amount": amount, "currency": "USD"}
            if "cash back" in label:
                return {"kind": "cash_back", "amount": amount, "currency": "USD"}
            return {"kind": "cash", "amount": amount, "currency": "USD"}
    return None


def qualification(text):
    result = {}
    lower = text.lower()
    if "invitation only" in lower or "accept your invitation" in lower:
        result["invitation_required"] = True
    if "new customer" in lower:
        result["new_customer_required"] = True
    spend = re.search(r"(?:spend|purchases(?: totaling)?|net new purchases(?: totaling)?)\s+(?:at least )?\$([\d,]+)", text, re.I)
    if spend:
        result["spend_requirement"] = "$" + spend.group(1) + " in eligible or net purchases as documented"
    period = re.search(r"within (?:your |the )?(?:first )?(\d+)\s+month", text, re.I)
    if period:
        result["spend_window"] = "within " + period.group(1) + " month" + ("s" if period.group(1) != "1" else "")
    if "good standing" in lower:
        result["good_standing"] = "account must remain open and in good standing"
    exclusions = []
    for phrase in ("returns", "chargebacks", "disputed transactions", "balance transfers", "cash equivalents", "fees"):
        if phrase in lower:
            exclusions.append(phrase + " do not count or reduce qualifying spend")
    if exclusions:
        result["exclusions"] = exclusions
    return result


def fee_from(text):
    match = re.search(r"annual fee[^\n$]{0,80}\$?([\d,]+(?:\.\d{2})?)", text, re.I)
    if not match:
        return None
    return "$" + match.group(1)


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        return {"ok": False, "errors": ["documents must be an array in a top-level object."], "warnings": []}
    as_of = payload.get("as_of")
    offers, warnings, fees = [], [], {}
    point_rate = None
    for doc in payload["documents"]:
        if not isinstance(doc, dict):
            warnings.append("Ignored a non-object document.")
            continue
        title, body = clean(doc.get("title")), clean(doc.get("content"))
        card = product(title)
        fee = fee_from(body)
        if fee:
            fees[card.lower()] = fee
        if "redeem at $0.01 per point" in body.lower():
            point_rate = 0.01
        start, end = find_window(body)
        reward = find_reward(body)
        promo_named = "promo" in title.lower() or "promotion" in title.lower()
        if not (promo_named and start and end and reward):
            continue
        scope = "business" if "business" in title.lower() else "consumer"
        offers.append({"card": card, "offer_type": "signup_bonus", "window_start": start,
                       "window_end": end, "reward": reward, "qualification": qualification(body),
                       "product_scope": scope, "source_title": title})
    for offer in offers:
        card_key = offer["card"].lower()
        if card_key in fees:
            offer["annual_fee"] = {"standard": fees[card_key]}
        if offer["reward"].get("kind") == "points" and point_rate is not None:
            offer["reward"]["redemption_value_per_point"] = point_rate
    if not offers:
        warnings.append("No fully structured sign-up promotion was extracted; review source wording manually.")
    return {"ok": True, "as_of": as_of, "offers": offers, "warnings": warnings, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON input: " + exc.msg], "warnings": []}))
