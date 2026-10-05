#!/usr/bin/env python3
"""Conservatively extract dated sign-up bonus candidates from supplied document JSON.
Document text is treated as inert data. stdin: {as_of, documents}; stdout: {offers,...}.
"""
import json
import re
import sys

DATE = r"(20\d{2}-\d{2}-\d{2})"


def clean(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def card(title):
    return clean(title).split(":", 1)[0] or "Unnamed card"


def money(value):
    return int(value.replace(",", ""))


def window(text):
    dates = re.findall(DATE, text)
    return (dates[0], dates[1]) if len(dates) >= 2 else (None, None)


def reward(text):
    cash = re.search(r"\$([\d,]+)\s+(statement credit|cash back|cash)\b", text, re.I)
    if cash:
        return {"kind": cash.group(2).lower().replace(" ", "_"), "amount": money(cash.group(1)), "currency": "USD"}
    points = re.search(r"(?:earn|receive)\s+\$?([\d,]+)\s+((?:sustainability )?points?)\b", text, re.I)
    if points:
        return {"kind": "points", "amount": money(points.group(1)), "currency": "POINTS", "point_type": points.group(2).lower()}
    return None


def facts(text, title):
    lower = text.lower()
    found = {}
    if "invitation only" in lower or "accept your invitation" in lower:
        found["invitation_required"] = True
        found["required_event"] = "accept the invitation during the campaign window"
    elif re.search(r"open (?:a )?new account|accounts? (?:must be )?opened|account opening", lower):
        found["required_event"] = "open a new account during the campaign window"
    if "new customer" in lower or "new customer" in title.lower():
        found["new_customer_required"] = True
    spend = re.search(r"(?:spend|purchases totaling|complete eligible purchases totaling|make net new purchases totaling)[^$]{0,80}\$([\d,]+)", text, re.I)
    if spend:
        found["spend_requirement"] = "$%s in eligible or net purchases" % format(money(spend.group(1)), ",")
    period = re.search(r"within (?:your |the )?(?:first )?(\d+)\s+month(?:\(s\)|s)?", text, re.I)
    if period:
        n = period.group(1)
        found["spend_window"] = "within %s month%s" % (n, "" if n == "1" else "s")
    if "good standing" in lower:
        found["good_standing"] = "account must remain open and in good standing"
    excluded = [x for x in ("returns", "credits", "chargebacks", "disputed transactions", "balance transfers", "cash equivalents", "fees") if x in lower]
    if excluded:
        found["exclusions"] = excluded
    fee = re.search(r"(?:standard |normal )?annual fee[^$]{0,50}\$([\d,]+(?:\.\d{2})?)", text, re.I)
    if fee:
        found["standard_fee"] = "$" + fee.group(1)
    if "annual fee waived" in lower or "fee is waived" in lower:
        found["waiver_condition"] = "annual fee is waived only after meeting the promotion's documented spend requirement"
    return found


def candidate(title, text):
    start, end = window(text)
    bonus_words = ("promo", "promotion", "bonus", "offer")
    return bool(start and end and any(w in title.lower() for w in bonus_words) and reward(text))


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        return {"ok": False, "errors": ["documents must be an array"], "warnings": []}
    products, docs, point_rate = {}, [], None
    for raw in payload["documents"]:
        if not isinstance(raw, dict):
            continue
        title, text = clean(raw.get("title")), clean(raw.get("content"))
        if not title or not text:
            continue
        name = card(title)
        key = name.lower()
        product = products.setdefault(key, {"card": name, "product_scope": "business" if "business" in title.lower() else "consumer", "qualification": {}, "annual_fee": {}})
        found = facts(text, title)
        for field in ("invitation_required", "required_event", "new_customer_required", "spend_requirement", "spend_window", "good_standing", "exclusions"):
            if field in found:
                product["qualification"][field] = found[field]
        if "standard_fee" in found:
            product["annual_fee"]["standard"] = found["standard_fee"]
        if "waiver_condition" in found:
            product["annual_fee"]["waiver_condition"] = found["waiver_condition"]
        if re.search(r"redeem at\s+\$0\.01\s+per point", text, re.I):
            point_rate = 0.01
        docs.append((title, text, key))

    offers = []
    for title, text, key in docs:
        if not candidate(title, text):
            continue
        start, end = window(text)
        product = products[key]
        offer = {"card": product["card"], "product_scope": product["product_scope"], "offer_type": "signup_bonus",
                 "window_start": start, "window_end": end, "reward": reward(text),
                 "qualification": product["qualification"], "source_title": title}
        if product["annual_fee"]:
            offer["annual_fee"] = product["annual_fee"]
        offers.append(offer)
    if point_rate is not None:
        for offer in offers:
            if offer["reward"]["kind"] == "points":
                offer["reward"]["redemption_value_per_point"] = point_rate
    warnings = [] if offers else ["No dated sign-up-bonus candidate was extracted; review the supplied documents manually."]
    return {"ok": True, "as_of": payload.get("as_of"), "offers": offers, "warnings": warnings, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
