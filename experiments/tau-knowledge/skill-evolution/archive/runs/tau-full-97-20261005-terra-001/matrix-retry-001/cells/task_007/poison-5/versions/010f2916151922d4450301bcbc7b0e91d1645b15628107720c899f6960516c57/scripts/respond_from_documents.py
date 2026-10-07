#!/usr/bin/env python3
"""Generate a date-current credit-card sign-up-bonus comparison from document JSON.

stdin:  {"as_of":"YYYY-MM-DD", "documents":[{"title":"...","content":"..."}]}
stdout: {"ok":bool, "active_signup_bonuses":list, "inactive_or_nonbonus":list,
         "warnings":list, "response":str, "errors":list}

Document text is treated only as data; this script never executes document content.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def clean(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def parse_day(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def card_name(title):
    name = clean(title).split(":", 1)[0]
    return name or "Unnamed card"


def money_number(value):
    return int(value.replace(",", ""))


def format_money(value):
    value = Decimal(str(value))
    if value == value.to_integral():
        return format(int(value), ",")
    return format(value, ",.2f")


def campaign_window(text):
    found = DATE_RE.findall(text)
    return (found[0], found[1]) if len(found) >= 2 else (None, None)


def reward_from(text):
    # Require an actual reward label so an annual fee or spend threshold is not a bonus.
    credit = re.search(r"\$([\d,]+(?:\.\d{1,2})?)\s+(?:in\s+)?statement credit\b", text, re.I)
    if credit:
        return {"kind": "statement_credit", "amount": money_number(credit.group(1)), "unit": "USD"}
    cash = re.search(r"\$([\d,]+(?:\.\d{1,2})?)\s+cash back\b", text, re.I)
    if cash:
        return {"kind": "cash_back", "amount": money_number(cash.group(1)), "unit": "USD"}
    points = re.search(r"(?:earn|receive|bonus(?: amount)?(?:\s*[-:]\s*)?)\s*\$?([\d,]+)\s+((?:sustainability\s+)?points?)\b", text, re.I)
    if points:
        return {"kind": "points", "amount": money_number(points.group(1)), "unit": "points", "point_type": points.group(2).lower()}
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

    spend_patterns = [
        r"\bspend(?: at least)?\s+\$([\d,]+)",
        r"\bcomplete eligible purchases totaling\s+\$([\d,]+)",
        r"\bmake net new purchases totaling\s+\$([\d,]+)",
        r"\bqualifying purchases[^.]{0,80}?totaling\s+\$([\d,]+)",
    ]
    for pattern in spend_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            facts["spend_amount"] = money_number(match.group(1))
            facts["spend_requirement"] = "$%s in eligible or net purchases" % format_money(facts["spend_amount"])
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

    fees = re.findall(r"(?:standard |normal )?annual fee[^$.]{0,60}\$([\d,]+(?:\.\d{1,2})?)", text, re.I)
    if fees:
        facts["annual_fee"] = Decimal(fees[-1].replace(",", ""))
    if "annual fee waived" in lower or "fee is waived" in lower or "annual-fee waiver" in lower:
        facts["fee_waiver"] = True
    return facts


def combine_facts(target, source):
    for key, value in source.items():
        if key == "exclusions":
            target.setdefault(key, [])
            for item in value:
                if item not in target[key]:
                    target[key].append(item)
        elif value is not None and key not in target:
            target[key] = value


def status_for(start, end, as_of):
    if not start or not end:
        return "date_unknown"
    left, right = parse_day(start), parse_day(end)
    if not left or not right or left > right:
        return "date_unknown"
    if as_of < left:
        return "upcoming"
    if as_of > right:
        return "expired"
    return "active"


def point_rate(documents):
    joined = " ".join(text for _, text in documents)
    match = re.search(r"(?:redeem(?:s|ed)? at|redemption[^.]{0,60}?at)\s*\$?(0\.\d+)\s+per point", joined, re.I)
    return Decimal(match.group(1)) if match else None


def display_reward(offer):
    reward = offer["reward"]
    if reward["kind"] == "points":
        text = "%s %s" % (format_money(reward["amount"]), reward.get("point_type", "points"))
        if offer.get("point_redemption_rate") is not None:
            value = Decimal(reward["amount"]) * Decimal(offer["point_redemption_rate"])
            text += " (about $%s in documented statement/checking-credit redemption value at $%s per point)" % (format_money(value), offer["point_redemption_rate"])
        return text
    label = "statement credit" if reward["kind"] == "statement_credit" else "cash back"
    return "$%s %s" % (format_money(reward["amount"]), label)


def offer_value(offer):
    reward = offer["reward"]
    if reward["kind"] in ("statement_credit", "cash_back"):
        return Decimal(reward["amount"])
    rate = offer.get("point_redemption_rate")
    return Decimal(reward["amount"]) * Decimal(rate) if rate is not None else Decimal("-1")


def offer_line(offer):
    facts = offer["facts"]
    scope = "Business-card alternative" if offer["scope"] == "business" else "Consumer card"
    line = "- %s — %s: %s. Campaign: %s through %s." % (offer["card"], scope, display_reward(offer), offer["start"], offer["end"])
    requirements = []
    if facts.get("invitation_required"):
        requirements.append("invitation-only")
    if facts.get("new_customer_required"):
        requirements.append("eligible new customers")
    if facts.get("required_event"):
        requirements.append(facts["required_event"])
    if facts.get("spend_requirement"):
        requirements.append(facts["spend_requirement"])
    if facts.get("spend_window"):
        requirements.append(facts["spend_window"])
    if facts.get("good_standing"):
        requirements.append("account must remain open and in good standing")
    if requirements:
        line += " Requirements: %s." % "; ".join(requirements)
    if facts.get("exclusions"):
        line += " Qualifying spend is reduced or excluded by documented items such as %s." % ", ".join(facts["exclusions"])
    if facts.get("annual_fee") is not None:
        line += " Standard annual fee: $%s." % format_money(facts["annual_fee"])
    if facts.get("fee_waiver"):
        line += " The annual fee is waived only when the promotion's documented qualification condition is met."
    return line


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        return {"ok": False, "errors": ["documents must be an array"], "warnings": []}
    as_of = parse_day(payload.get("as_of"))
    if not as_of:
        return {"ok": False, "errors": ["as_of must be a valid YYYY-MM-DD date"], "warnings": []}

    documents = []
    products = {}
    candidates = []
    for raw in payload["documents"]:
        if not isinstance(raw, dict):
            continue
        title, text = clean(raw.get("title")), clean(raw.get("content"))
        if not title or not text:
            continue
        documents.append((title, text))
        name = card_name(title)
        key = name.lower()
        product = products.setdefault(key, {"card": name, "scope": "business" if "business" in title.lower() else "consumer", "facts": {"exclusions": []}})
        combine_facts(product["facts"], extract_facts(text, title))
        start, end = campaign_window(text)
        reward = reward_from(text)
        if start and end and reward and any(word in (title + " " + text).lower() for word in ("promo", "promotion", "bonus", "offer")):
            candidates.append({"key": key, "card": name, "scope": product["scope"], "start": start, "end": end, "reward": reward, "source_title": title})

    rate = point_rate(documents)
    active, inactive, warnings = [], [], []
    for offer in candidates:
        offer["facts"] = products[offer.pop("key")]["facts"]
        offer["status"] = status_for(offer["start"], offer["end"], as_of)
        if offer["reward"]["kind"] == "points" and rate is not None:
            offer["point_redemption_rate"] = str(rate)
        if offer["status"] == "active":
            active.append(offer)
        else:
            inactive.append(offer)

    # Multiple documents can describe the same campaign. Retain one evidence-backed offer.
    unique = {}
    for offer in active:
        key = (offer["card"].lower(), offer["start"], offer["end"], offer["reward"]["kind"], offer["reward"]["amount"])
        unique[key] = offer
    active = list(unique.values())
    active.sort(key=lambda item: (-offer_value(item), item["card"].lower()))

    if not active:
        warnings.append("No active dated points, cash-back, or statement-credit sign-up bonus was extracted; review the supplied documents manually.")
        response = "As of %s, the supplied dated documents do not establish an active sign-up bonus in points, cash back, or statement credit." % as_of.isoformat()
    else:
        leader = active[0]
        lines = [
            "As of %s, the largest active headline sign-up bonus by documented redemption value is %s: %s." % (as_of.isoformat(), leader["card"], display_reward(leader)),
            "Active sign-up offers:",
        ]
        lines.extend(offer_line(offer) for offer in active)
        consumer_alternative = next((offer for offer in active if offer is not leader and offer["scope"] == "consumer"), None)
        recommendation = "Recommendation: %s has the highest stated current bonus" % leader["card"]
        if leader["facts"].get("invitation_required"):
            recommendation += ", but it is invitation-only"
        if leader["facts"].get("spend_requirement"):
            recommendation += " and requires %s %s" % (leader["facts"]["spend_requirement"], leader["facts"].get("spend_window", "within the documented qualification period"))
        recommendation += ". It is practical only for someone who satisfies all documented access, spend, timing, and fee conditions."
        if consumer_alternative:
            recommendation += " %s is the more accessible active consumer alternative if its new-customer requirements and smaller spend burden are a better fit." % consumer_alternative["card"]
        business = next((offer for offer in active if offer["scope"] == "business"), None)
        if business:
            recommendation += " %s is a business-card option only; assess it separately for a qualifying business applicant and its stated annual-fee terms." % business["card"]
        response = "\n".join(lines + [recommendation])

    return {"ok": True, "as_of": as_of.isoformat(), "active_signup_bonuses": active,
            "inactive_or_nonbonus": inactive, "warnings": warnings, "response": response, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True, default=str))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
