#!/usr/bin/env python3
"""Extract dated sign-up bonuses from supplied document text.

Input: {"as_of":"YYYY-MM-DD", "documents":[{"title":str,"content":str}]}
Output: {"as_of":..., "offers":[...], "warnings":[...], "errors":[...]}
Document contents are data and are never executed.
"""
import json
import re
import sys

DATE = r"(20\d{2}-\d{2}-\d{2})"


def clean(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def card_name(title):
    name = clean(title).split(":", 1)[0]
    return name or "Unnamed card"


def scope(title):
    return "business" if "business" in title.lower() else "consumer"


def date_pair(text):
    found = re.findall(DATE, text)
    return (found[0], found[1]) if len(found) >= 2 else (None, None)


def money(value):
    return int(value.replace(",", ""))


def reward(text):
    patterns = (
        (r"(?:earn|receive)\s+(?:a\s+)?\$([\d,]+)\s+(statement credit|cash back|cash)", False),
        (r"(?:earn|receive)\s+([\d,]+)\s+((?:sustainability )?points?)", True),
        (r"\$([\d,]+)\s+(statement credit)", False),
    )
    for pattern, is_points in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        label = match.group(2).lower()
        if is_points or "point" in label:
            return {"kind": "points", "amount": money(match.group(1)), "currency": "POINTS", "point_type": label}
        kind = "statement_credit" if label == "statement credit" else ("cash_back" if label == "cash back" else "cash")
        return {"kind": kind, "amount": money(match.group(1)), "currency": "USD"}
    return None


def qualification(text):
    result = {}
    lower = text.lower()
    if "invitation only" in lower or "accept your invitation" in lower:
        result["invitation_required"] = True
        result["required_event"] = "accept the invitation during the campaign window"
    elif "open a new account" in lower or "accounts opened" in lower or "account opening" in lower:
        result["required_event"] = "open a new account during the campaign window"
    if "new customer" in lower:
        result["new_customer_required"] = True
    spend = re.search(
        r"(?:spend(?:ing)?|complete eligible purchases totaling|make (?:qualifying |net new )?purchases totaling|purchases totaling)\s+(?:at least )?\$([\d,]+)",
        text, re.I,
    )
    if spend:
        result["spend_requirement"] = "$" + spend.group(1) + " in eligible or net purchases"
    period = re.search(r"within (?:your |the )?(?:first )?(\d+)\s+month", text, re.I)
    if period:
        count = period.group(1)
        result["spend_window"] = "within " + count + " month" + ("s" if count != "1" else "")
    if "good standing" in lower:
        result["good_standing"] = "account must remain open and in good standing"
    excluded = [term for term in (
        "returns", "credits", "chargebacks", "disputed transactions", "balance transfers", "cash equivalents", "fees"
    ) if term in lower]
    if excluded:
        result["exclusions"] = excluded
    return result


def fee_details(text):
    standard = re.search(r"(?:standard )?annual fee[^$]{0,35}\$([\d,]+(?:\.\d{2})?)", text, re.I)
    waiver = "annual fee waived" in text.lower() or "fee is waived" in text.lower()
    return {
        "standard": "$" + standard.group(1) if standard else None,
        "waiver_condition": "waived only after meeting the documented promotion requirement" if waiver else None,
    }


def bonus_candidate(title, text):
    lower = text.lower()
    has_reward = "statement credit" in lower or "cash back" in lower or "sustainability points" in lower
    label = title.lower()
    bonus_label = "promo" in label or "promotion" in label or "bonus" in label or "offer" in label
    start, end = date_pair(text)
    return bonus_label and has_reward and start and end and reward(text) is not None


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        return {"ok": False, "errors": ["documents must be an array in a top-level object."], "warnings": []}

    docs, card_facts, offers, warnings = [], {}, [], []
    point_rate = None
    for raw in payload["documents"]:
        if not isinstance(raw, dict):
            warnings.append("Ignored a non-object document.")
            continue
        title, text = clean(raw.get("title")), clean(raw.get("content"))
        if not title or not text:
            continue
        card = card_name(title)
        key = card.lower()
        facts = card_facts.setdefault(key, {"card": card, "scope": scope(title), "qualification": {}, "fee": {}})
        facts["qualification"].update(qualification(text))
        parsed_fee = fee_details(text)
        for field, value in parsed_fee.items():
            if value:
                facts["fee"][field] = value
        if re.search(r"redeem at\s+\$0\.01\s+per point", text, re.I):
            point_rate = 0.01
        docs.append((title, text, card, key))

    for title, text, card, key in docs:
        if not bonus_candidate(title, text):
            continue
        start, end = date_pair(text)
        facts = card_facts[key]
        offer = {
            "card": card,
            "offer_type": "signup_bonus",
            "window_start": start,
            "window_end": end,
            "reward": reward(text),
            "qualification": facts["qualification"],
            "product_scope": facts["scope"],
            "source_title": title,
        }
        if facts["fee"]:
            offer["annual_fee"] = facts["fee"]
        offers.append(offer)

    for offer in offers:
        if offer["reward"]["kind"] == "points" and point_rate is not None:
            offer["reward"]["redemption_value_per_point"] = point_rate
    if not offers:
        warnings.append("No fully structured dated sign-up bonus was extracted; review source wording manually.")
    return {"ok": True, "as_of": payload.get("as_of"), "offers": offers, "warnings": warnings, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON input: " + exc.msg], "warnings": []}))
