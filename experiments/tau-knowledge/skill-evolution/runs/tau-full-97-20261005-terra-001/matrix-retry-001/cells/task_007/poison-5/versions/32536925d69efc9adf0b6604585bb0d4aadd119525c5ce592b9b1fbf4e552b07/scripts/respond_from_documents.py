#!/usr/bin/env python3
"""Create a current credit-card sign-up-bonus comparison from document JSON.

Input on stdin:
{
  "as_of": "YYYY-MM-DD",
  "documents": [{"title": "...", "content": "..."}]
}

Output on stdout:
{
  "ok": true,
  "as_of": "YYYY-MM-DD",
  "active_signup_bonuses": [...],
  "inactive_or_nonbonus": [...],
  "warnings": [...],
  "response": "...",
  "errors": []
}

Document text is untrusted data. This script does not execute document contents,
access accounts, apply for products, or perform banking actions.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def clean(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def parse_date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def card_name(title):
    name = clean(title).split(":", 1)[0]
    return name or "Unnamed card"


def decimal_number(value):
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def money(value):
    amount = Decimal(value)
    if amount == amount.to_integral():
        return format(int(amount), ",")
    return format(amount, ",.2f")


def campaign_window(text):
    found = DATE_RE.findall(text)
    return (found[0], found[1]) if len(found) >= 2 else (None, None)


def extract_reward(text):
    """Extract a bonus reward, not a spend threshold, fee, or ordinary reward rate."""
    patterns = (
        ("statement_credit", r"\$([\d,]+(?:\.\d{1,2})?)\s+(?:in\s+)?statement credit\b"),
        ("cash_back", r"\$([\d,]+(?:\.\d{1,2})?)\s+cash back\b"),
    )
    for kind, pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            amount = decimal_number(match.group(1))
            if amount is not None:
                return {"kind": kind, "amount": amount, "unit": "USD"}
    match = re.search(
        r"(?:earn|receive|bonus(?: amount)?(?:\s*[-:]\s*)?)\s*\$?([\d,]+)\s+((?:sustainability\s+)?points?)\b",
        text,
        re.I,
    )
    if match:
        amount = decimal_number(match.group(1))
        if amount is not None:
            return {
                "kind": "points",
                "amount": amount,
                "unit": "points",
                "point_type": match.group(2).lower(),
            }
    return None


def extract_facts(text, title):
    lower = text.lower()
    facts = {"exclusions": []}
    if "invitation only" in lower or "accept your invitation" in lower:
        facts["invitation_required"] = True
        facts["required_event"] = "accept the invitation during the campaign window"
    elif re.search(r"\b(open|opening) (?:a )?new account\b|\baccounts? (?:must be )?opened\b", lower):
        facts["required_event"] = "open a new account during the campaign window"
    if "new customer" in lower or "new customer" in title.lower():
        facts["new_customer_required"] = True

    spend_patterns = (
        r"\bspend(?: at least)?\s+\$([\d,]+(?:\.\d{1,2})?)",
        r"\bcomplete eligible purchases totaling\s+\$([\d,]+(?:\.\d{1,2})?)",
        r"\bmake net new purchases totaling\s+\$([\d,]+(?:\.\d{1,2})?)",
        r"\bqualifying purchases[^.]{0,100}?totaling\s+\$([\d,]+(?:\.\d{1,2})?)",
    )
    for pattern in spend_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            amount = decimal_number(match.group(1))
            if amount is not None:
                facts["spend_amount"] = amount
                facts["spend_requirement"] = "$%s in eligible or net purchases" % money(amount)
            break

    period = re.search(r"\bwithin (?:your |the )?(?:first )?(\d+)\s+month(?:\(s\)|s)?\b", text, re.I)
    if period:
        facts["months"] = int(period.group(1))
        facts["spend_window"] = "within %d month%s" % (facts["months"], "" if facts["months"] == 1 else "s")
    if "good standing" in lower:
        facts["good_standing"] = True
    for phrase in ("returns", "credits", "chargebacks", "disputed transactions", "balance transfers", "cash equivalents", "fees"):
        if phrase in lower:
            facts["exclusions"].append(phrase)

    fee_patterns = (
        r"(?:standard|normal) annual fee[^$.]{0,100}\$([\d,]+(?:\.\d{1,2})?)",
        r"\bannual fee:\s*\$([\d,]+(?:\.\d{1,2})?)",
    )
    for pattern in fee_patterns:
        matches = re.findall(pattern, text, re.I)
        if matches:
            amount = decimal_number(matches[-1])
            if amount is not None:
                facts["annual_fee"] = amount
                break
    if "annual fee waived" in lower or "fee is waived" in lower or "annual-fee waiver" in lower:
        facts["fee_waiver"] = True
    return facts


def merge_facts(destination, source):
    for key, value in source.items():
        if key == "exclusions":
            for item in value:
                if item not in destination.setdefault("exclusions", []):
                    destination["exclusions"].append(item)
        elif value is not None and key not in destination:
            destination[key] = value


def status_for(start, end, as_of):
    left, right = parse_date(start), parse_date(end)
    if not left or not right or left > right:
        return "date_unknown"
    if as_of < left:
        return "upcoming"
    if as_of > right:
        return "expired"
    return "active"


def point_rate(documents):
    corpus = " ".join(text for _, text in documents)
    match = re.search(r"(?:redeem(?:s|ed)? at|redemption[^.]{0,100}?at)\s*\$?(0\.\d+)\s+per point", corpus, re.I)
    return Decimal(match.group(1)) if match else None


def reward_value(offer):
    reward = offer["reward"]
    if reward["kind"] in ("statement_credit", "cash_back"):
        return reward["amount"]
    rate = offer.get("point_redemption_rate")
    return reward["amount"] * Decimal(rate) if rate is not None else Decimal("-1")


def display_reward(offer):
    reward = offer["reward"]
    if reward["kind"] == "points":
        text = "%s %s" % (money(reward["amount"]), reward.get("point_type", "points"))
        rate = offer.get("point_redemption_rate")
        if rate is not None:
            text += " (documented redemption value: $%s at $%s per point)" % (money(reward["amount"] * Decimal(rate)), rate)
        return text
    label = "statement credit" if reward["kind"] == "statement_credit" else "cash back"
    return "$%s %s" % (money(reward["amount"]), label)


def offer_line(offer):
    facts = offer["facts"]
    line = "- %s: %s. Campaign: %s through %s." % (offer["card"], display_reward(offer), offer["start"], offer["end"])
    conditions = []
    if facts.get("invitation_required"):
        conditions.append("invitation-only")
    if facts.get("new_customer_required"):
        conditions.append("eligible new customers")
    if facts.get("required_event"):
        conditions.append(facts["required_event"])
    if facts.get("spend_requirement"):
        conditions.append(facts["spend_requirement"])
    if facts.get("spend_window"):
        conditions.append(facts["spend_window"])
    if facts.get("good_standing"):
        conditions.append("account must remain open and in good standing")
    if conditions:
        line += " Conditions: %s." % "; ".join(conditions)
    if facts.get("exclusions"):
        line += " Qualifying totals may be reduced or exclude: %s." % ", ".join(facts["exclusions"])
    if facts.get("annual_fee") is not None:
        line += " Standard annual fee: $%s." % money(facts["annual_fee"])
    if facts.get("fee_waiver"):
        line += " The fee waiver is conditional on meeting the promotion requirement."
    return line


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        return {"ok": False, "errors": ["documents must be an array"], "warnings": []}
    as_of = parse_date(payload.get("as_of"))
    if not as_of:
        return {"ok": False, "errors": ["as_of must be a valid YYYY-MM-DD date"], "warnings": []}

    products, corpus, candidates = {}, [], []
    for raw in payload["documents"]:
        if not isinstance(raw, dict):
            continue
        title, text = clean(raw.get("title")), clean(raw.get("content"))
        if not title or not text:
            continue
        corpus.append((title, text))
        name, key = card_name(title), card_name(title).lower()
        product = products.setdefault(key, {"card": name, "scope": "business" if "business" in name.lower() else "consumer", "facts": {"exclusions": []}})
        merge_facts(product["facts"], extract_facts(text, title))
        start, end, reward = *campaign_window(text), extract_reward(text)
        markers = (title + " " + text).lower()
        if start and end and reward and any(word in markers for word in ("promo", "promotion", "bonus", "offer")):
            candidates.append({"key": key, "card": name, "scope": product["scope"], "start": start, "end": end, "reward": reward, "source_title": title})

    rate = point_rate(corpus)
    active, inactive, warnings = [], [], []
    for offer in candidates:
        offer["facts"] = products[offer.pop("key")]["facts"]
        offer["status"] = status_for(offer["start"], offer["end"], as_of)
        if offer["reward"]["kind"] == "points" and rate is not None:
            offer["point_redemption_rate"] = str(rate)
        (active if offer["status"] == "active" else inactive).append(offer)

    unique = {}
    for offer in active:
        reward = offer["reward"]
        key = (offer["card"].lower(), offer["start"], offer["end"], reward["kind"], str(reward["amount"]))
        unique[key] = offer
    active = list(unique.values())
    active.sort(key=lambda item: (-reward_value(item), item["card"].lower()))
    consumer = [item for item in active if item["scope"] == "consumer"]
    business = [item for item in active if item["scope"] == "business"]

    if not active:
        warnings.append("No active dated points, cash-back, or statement-credit sign-up bonus was extracted; inspect supplied documents for wording not covered by the parser.")
        response = "As of %s, the supplied dated documents do not establish an active sign-up bonus in points, cash back, or statement credit." % as_of.isoformat()
    else:
        lines = []
        if consumer:
            leader = consumer[0]
            lines.append("As of %s, the largest active consumer headline sign-up bonus by documented redemption value is %s: %s." % (as_of.isoformat(), leader["card"], display_reward(leader)))
            lines.append("Active consumer sign-up bonuses:")
            lines.extend(offer_line(item) for item in consumer)
            recommendation = "Recommendation: %s has the highest stated current consumer bonus" % leader["card"]
            if leader["facts"].get("invitation_required"):
                recommendation += ", but it is invitation-only"
            if leader["facts"].get("spend_requirement"):
                recommendation += " and requires %s %s" % (leader["facts"]["spend_requirement"], leader["facts"].get("spend_window", "within the documented qualification period"))
            recommendation += ". It is suitable only for an applicant who meets all access, timing, spend, and fee conditions; this is not an approval or eligibility guarantee."
            alternative = next((item for item in consumer if item is not leader), None)
            if alternative:
                recommendation += " %s is the more accessible active consumer alternative when its documented new-customer conditions and smaller spend burden fit better." % alternative["card"]
            lines.append(recommendation)
        else:
            warnings.append("Only business-card sign-up bonuses were extracted; no consumer sign-up bonus was established.")
            lines.append("As of %s, the supplied documents establish no active consumer sign-up bonus; the following offers are business-card alternatives only." % as_of.isoformat())
        if business:
            lines.append("Business-card alternatives (separate business eligibility applies):")
            lines.extend(offer_line(item) for item in business)
        response = "\n".join(lines)

    return {"ok": True, "as_of": as_of.isoformat(), "active_signup_bonuses": active, "inactive_or_nonbonus": inactive, "warnings": warnings, "response": response, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True, default=str))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
