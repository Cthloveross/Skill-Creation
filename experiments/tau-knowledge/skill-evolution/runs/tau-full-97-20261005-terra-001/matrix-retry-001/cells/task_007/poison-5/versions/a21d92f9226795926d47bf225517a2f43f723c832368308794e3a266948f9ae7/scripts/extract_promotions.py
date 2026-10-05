#!/usr/bin/env python3
"""Conservatively extract dated sign-up-bonus candidates from document JSON.
Reads JSON from stdin and emits {as_of, offers, warnings} JSON to stdout.
"""
import json
import re
import sys

DATE = r"(20\d{2}-\d{2}-\d{2})"


def tidy(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def card_name(title):
    return tidy(title).split(":", 1)[0] or "Unnamed card"


def dollars(value):
    return int(value.replace(",", ""))


def dates(text):
    found = re.findall(DATE, text)
    return (found[0], found[1]) if len(found) >= 2 else (None, None)


def reward(text):
    match = re.search(r"\$([\d,]+)\s+(statement credit|cash back|cash)\b", text, re.I)
    if match:
        kind = {"statement credit": "statement_credit", "cash back": "cash_back", "cash": "cash"}[match.group(2).lower()]
        return {"kind": kind, "amount": dollars(match.group(1)), "currency": "USD"}
    match = re.search(r"(?:earn|receive)\s+([\d,]+)\s+((?:sustainability )?points?)\b", text, re.I)
    if match:
        return {"kind": "points", "amount": dollars(match.group(1)), "currency": "POINTS", "point_type": match.group(2).lower()}
    return None


def facts(text, title):
    lower = text.lower()
    result = {}
    if "invitation only" in lower or "accept your invitation" in lower:
        result["invitation_required"] = True
        result["required_event"] = "accept the invitation during the campaign window"
    elif re.search(r"open (?:a )?new account|accounts? (?:must be )?opened|account opening", lower):
        result["required_event"] = "open a new account during the campaign window"
    if "new customer" in lower or "new customer" in title.lower():
        result["new_customer_required"] = True
    match = re.search(r"(?:spend|purchases totaling|complete eligible purchases totaling|make net new purchases totaling)[^$]{0,65}\$([\d,]+)", text, re.I)
    if match:
        result["spend_requirement"] = "$%s in eligible or net purchases" % format(dollars(match.group(1)), ",")
    match = re.search(r"within (?:your |the )?(?:first )?(\d+)\s+months?", text, re.I)
    if match:
        plural = "s" if match.group(1) != "1" else ""
        result["spend_window"] = "within %s month%s" % (match.group(1), plural)
    if "good standing" in lower:
        result["good_standing"] = "account must remain open and in good standing"
    exclusions = [term for term in ("returns", "credits", "chargebacks", "disputed transactions", "balance transfers", "cash equivalents", "fees") if term in lower]
    if exclusions:
        result["exclusions"] = exclusions
    fee = re.search(r"(?:standard |normal )?annual fee[^$]{0,45}\$([\d,]+(?:\.\d{2})?)", text, re.I)
    if fee:
        result["standard_fee"] = "$" + fee.group(1)
    if "annual fee waived" in lower or "fee is waived" in lower:
        result["waiver_condition"] = "annual fee is waived only after meeting the promotion's documented spend requirement"
    return result


def is_candidate(title, text):
    start, end = dates(text)
    labelled = any(word in title.lower() for word in ("promo", "promotion", "bonus", "offer"))
    return bool(start and end and labelled and reward(text))


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        return {"ok": False, "errors": ["documents must be an array"], "warnings": []}
    cards, source_docs, rate = {}, [], None
    for raw in payload["documents"]:
        if not isinstance(raw, dict):
            continue
        title, text = tidy(raw.get("title")), tidy(raw.get("content"))
        if not title or not text:
            continue
        name = card_name(title)
        key = name.lower()
        record = cards.setdefault(key, {"card": name, "product_scope": "business" if "business" in title.lower() else "consumer", "qualification": {}, "annual_fee": {}})
        found = facts(text, title)
        for field in ("invitation_required", "required_event", "new_customer_required", "spend_requirement", "spend_window", "good_standing", "exclusions"):
            if field in found:
                record["qualification"][field] = found[field]
        if "standard_fee" in found:
            record["annual_fee"]["standard"] = found["standard_fee"]
        if "waiver_condition" in found:
            record["annual_fee"]["waiver_condition"] = found["waiver_condition"]
        if re.search(r"redeem at\s+\$0\.01\s+per point", text, re.I):
            rate = 0.01
        source_docs.append((title, text, key))

    offers = []
    for title, text, key in source_docs:
        if not is_candidate(title, text):
            continue
        start, end = dates(text)
        base = cards[key]
        offer = {"card": base["card"], "offer_type": "signup_bonus", "window_start": start, "window_end": end,
                 "reward": reward(text), "qualification": base["qualification"], "product_scope": base["product_scope"],
                 "source_title": title}
        if base["annual_fee"]:
            offer["annual_fee"] = base["annual_fee"]
        offers.append(offer)
    for offer in offers:
        if offer["reward"]["kind"] == "points" and rate is not None:
            offer["reward"]["redemption_value_per_point"] = rate
    warnings = [] if offers else ["No fully structured dated sign-up bonus was extracted; review source documents manually."]
    return {"ok": True, "as_of": payload.get("as_of"), "offers": offers, "warnings": warnings, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
