#!/usr/bin/env python3
"""Conservatively extract dated sign-up-bonus candidates from document JSON."""
import json, re, sys

DATE = r"(20\d{2}-\d{2}-\d{2})"

def tidy(x): return " ".join(x.split()) if isinstance(x, str) else ""
def card(title): return tidy(title).split(":", 1)[0] or "Unnamed card"
def dollars(s): return int(s.replace(",", ""))

def dates(text):
    found = re.findall(DATE, text)
    return (found[0], found[1]) if len(found) >= 2 else (None, None)

def reward(text):
    m = re.search(r"\$([\d,]+)\s+(statement credit|cash back|cash)\b", text, re.I)
    if m:
        kind = {"statement credit":"statement_credit", "cash back":"cash_back", "cash":"cash"}[m.group(2).lower()]
        return {"kind":kind,"amount":dollars(m.group(1)),"currency":"USD"}
    m = re.search(r"(?:earn|receive)\s+([\d,]+)\s+((?:sustainability )?points?)\b", text, re.I)
    if m:
        return {"kind":"points","amount":dollars(m.group(1)),"currency":"POINTS","point_type":m.group(2).lower()}
    return None

def facts(text, title):
    low = text.lower(); out = {}
    if "invitation only" in low or "accept your invitation" in low:
        out["invitation_required"] = True
        out["required_event"] = "accept the invitation during the campaign window"
    elif re.search(r"open (?:a )?new account|accounts? (?:must be )?opened|account opening", low):
        out["required_event"] = "open a new account during the campaign window"
    if "new customer" in low or "new customer" in title.lower(): out["new_customer_required"] = True
    m = re.search(r"(?:spend|purchases totaling|complete eligible purchases totaling|make net new purchases totaling)[^$]{0,55}\$([\d,]+)", text, re.I)
    if m: out["spend_requirement"] = "$" + format(dollars(m.group(1)), ",") + " in eligible or net purchases"
    m = re.search(r"within (?:your |the )?(?:first )?(\d+)\s+months?", text, re.I)
    if m: out["spend_window"] = "within " + m.group(1) + " month" + ("s" if m.group(1) != "1" else "")
    if "good standing" in low: out["good_standing"] = "account must remain open and in good standing"
    excluded = [x for x in ("returns", "credits", "chargebacks", "disputed transactions", "balance transfers", "cash equivalents", "fees") if x in low]
    if excluded: out["exclusions"] = excluded
    fee = re.search(r"(?:standard |normal )?annual fee[^$]{0,45}\$([\d,]+(?:\.\d{2})?)", text, re.I)
    if fee: out["standard_fee"] = "$" + fee.group(1)
    if "annual fee waived" in low or "fee is waived" in low:
        out["waiver_condition"] = "annual fee is waived only after meeting the promotion's documented spend requirement"
    return out

def candidate(title, text):
    start, end = dates(text)
    label = title.lower()
    bonus_words = any(x in label for x in ("promo", "promotion", "bonus", "offer"))
    return bool(start and end and bonus_words and reward(text))

def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        return {"ok":False,"errors":["documents must be an array"],"warnings":[]}
    by_card, docs, warnings, rate = {}, [], [], None
    for raw in payload["documents"]:
        if not isinstance(raw, dict): continue
        title, text = tidy(raw.get("title")), tidy(raw.get("content"))
        if not title or not text: continue
        name = card(title); key = name.lower()
        rec = by_card.setdefault(key, {"card":name,"product_scope":"business" if "business" in title.lower() else "consumer","qualification":{},"annual_fee":{}})
        f = facts(text, title)
        for k in ("invitation_required","required_event","new_customer_required","spend_requirement","spend_window","good_standing","exclusions"):
            if k in f: rec["qualification"][k] = f[k]
        for k in ("standard_fee","waiver_condition"):
            if k in f: rec["annual_fee"]["standard" if k == "standard_fee" else k] = f[k]
        if re.search(r"redeem at\s+\$0\.01\s+per point", text, re.I): rate = 0.01
        docs.append((title, text, key))
    offers = []
    for title, text, key in docs:
        if not candidate(title, text): continue
        start, end = dates(text); base = by_card[key]
        offer = {"card":base["card"],"offer_type":"signup_bonus","window_start":start,"window_end":end,"reward":reward(text),"qualification":base["qualification"],"product_scope":base["product_scope"],"source_title":title}
        if base["annual_fee"]: offer["annual_fee"] = base["annual_fee"]
        offers.append(offer)
    for offer in offers:
        if offer["reward"]["kind"] == "points" and rate is not None: offer["reward"]["redemption_value_per_point"] = rate
    if not offers: warnings.append("No fully structured dated sign-up bonus was extracted; review source documents manually.")
    return {"ok":True,"as_of":payload.get("as_of"),"offers":offers,"warnings":warnings,"errors":[]}

if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as e: print(json.dumps({"ok":False,"errors":["Invalid JSON: "+e.msg],"warnings":[]}))
