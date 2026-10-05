#!/usr/bin/env python3
"""Create a date-current credit-card sign-up-bonus comparison from document JSON.

Input on stdin:
{
  "as_of": "YYYY-MM-DD",
  "documents": [{"title": "...", "content": "..."}]
}

Output on stdout:
{
  "ok": bool,
  "as_of": "YYYY-MM-DD",
  "active_signup_bonuses": [...],
  "inactive_or_nonbonus": [...],
  "warnings": [...],
  "response": "...",
  "errors": [...]
}

Document text is untrusted data. This script does not execute document contents and does
not access accounts, apply for products, or perform banking actions.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal

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


def number(value):
    return int(value.replace(",", ""))


def money(value):
    value = Decimal(str(value))
    if value == value.to_integral():
        return format(int(value), ",")
    return format(value, ",.2f")


def campaign_window(text):
    found = DATE_RE.findall(text)
    if len(found) < 2:
        return None, None
    return found[0], found[1]


def extract_reward(text):
    """Return a promotional reward only, never a spend threshold or an annual fee."""
    credit = re.search(r"\$([\d,]+(?:\.\d{1,2})?)\s+(?:in\s+)?statement credit\b", text, re.I)
    if credit:
        return {"kind": "statement_credit", "amount": number(credit.group(1)), "unit": "USD"}
    cash = re.search(r"\$([\d,]+(?:\.\d{1,2})?)\s+cash back\b", text, re.I)
    if cash:
        return {"kind": "cash_back", "amount": number(cash.group(1)), "unit": "USD"}
    points = re.search(
        r"(?:earn|receive|bonus(?: amount)?(?:\s*[-:]\s*)?)\s*\$?([\d,]+)\s+((?:sustainability\s+)?points?)\b",
        text,
        re.I,
    )
    if points:
        return {
            "kind": "points",
            "amount": number(points.group(1)),
            "unit": "points",
            "point_type": points.group(2).lower(),
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

    for pattern in (
        r"\bspend(?: at least)?\s+\$([\d,]+)",
        r"\bcomplete eligible purchases totaling\s+\$([\d,]+)",
        r"\bmake net new purchases totaling\s+\$([\d,]+)",
        r"\bqualifying purchases[^.]{0,100}?totaling\s+\$([\d,]+)",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            facts["spend_amount"] = number(match.group(1))
            facts["spend_requirement"] = "$%s in eligible or net purchases" % money(facts["spend_amount"])
            break

    period = re.search(r"\bwithin (?:your |the )?(?:first )?(\d+)\s+month(?:\(s\)|s)?\b", text, re.I)
    if period:
        facts["months"] = int(period.group(1))
        suffix = "" if facts["months"] == 1 else "s"
        facts["spend_window"] = "within %d month%s" % (facts["months"], suffix)

    if "good standing" in lower:
        facts["good_standing"] = True

    for phrase in (
        "returns", "credits", "chargebacks", "disputed transactions",
        "balance transfers", "cash equivalents", "fees",
    ):
        if phrase in lower:
            facts["exclusions"].append(phrase)

    fees = re.findall(r"(?:standard |normal )?annual fee[^$.]{0,80}\$([\d,]+(?:\.\d{1,2})?)", text, re.I)
    if fees:
        facts["annual_fee"] = Decimal(fees[-1].replace(",", ""))
    if "annual fee waived" in lower or "fee is waived" in lower or "annual-fee waiver" in lower:
        facts["fee_waiver"] = True
    return facts


def merge_facts(destination, source):
    for key, value in source.items():
        if key == "exclusions":
            destination.setdefault("exclusions", [])
            for item in value:
                if item not in destination["exclusions"]:
                    destination["exclusions"].append(item)
        elif value is not None and key not in destination:
            destination[key] = value


def campaign_status(start, end, as_of):
    left, right = parse_date(start), parse_date(end)
    if not left or not right or left > right:
        return "date_unknown"
    if as_of < left:
        return "upcoming"
    if as_of > right:
        return "expired"
    return "active"


def documented_point_rate(documents):
    joined = " ".join(text for _, text in documents)
    match = re.search(r"(?:redeem(?:s|ed)? at|redemption[^.]{0,80}?at)\s*\$?(0\.\d+)\s+per point", joined, re.I)
    return Decimal(match.group(1)) if match else None


def reward_value(offer):
    reward = offer["reward"]
    if reward["kind"] in ("statement_credit", "cash_back"):
        return Decimal(reward["amount"])
    rate = offer.get("point_redemption_rate")
    return Decimal(reward["amount"]) * Decimal(rate) if rate is not None else Decimal("-1")


def display_reward(offer):
    reward = offer["reward"]
    if reward["kind"] == "points":
        result = "%s %s" % (money(reward["amount"]), reward.get("point_type", "points"))
        rate = offer.get("point_redemption_rate")
        if rate is not None:
            equivalent = Decimal(reward["amount"]) * Decimal(rate)
            result += " (documented redemption value: $%s at $%s per point)" % (money(equivalent), rate)
        return result
    label = "statement credit" if reward["kind"] == "statement_credit" else "cash back"
    return "$%s %s" % (money(reward["amount"]), label)


def offer_line(offer):
    facts = offer["facts"]
    scope = "Business-card alternative" if offer["scope"] == "business" else "Consumer card"
    line = "- %s (%s): %s. Campaign: %s through %s." % (
        offer["card"], scope, display_reward(offer), offer["start"], offer["end"]
    )
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
        line += " Documented exclusions/reductions include %s." % ", ".join(facts["exclusions"])
    if facts.get("annual_fee") is not None:
        line += " Standard annual fee: $%s." % money(facts["annual_fee"])
    if facts.get("fee_waiver"):
        line += " The annual fee is waived only after the promotion's stated qualification condition is met."
    return line


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        return {"ok": False, "errors": ["documents must be an array"], "warnings": []}
    as_of = parse_date(payload.get("as_of"))
    if not as_of:
        return {"ok": False, "errors": ["as_of must be a valid YYYY-MM-DD date"], "warnings": []}

    products = {}
    documents = []
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
        product = products.setdefault(key, {
            "card": name,
            "scope": "business" if "business" in title.lower() else "consumer",
            "facts": {"exclusions": []},
        })
        merge_facts(product["facts"], extract_facts(text, title))

        start, end = campaign_window(text)
        reward = extract_reward(text)
        source_lower = (title + " " + text).lower()
        is_offer = any(word in source_lower for word in ("promo", "promotion", "bonus", "offer"))
        if start and end and reward and is_offer:
            candidates.append({
                "product_key": key,
                "card": name,
                "scope": product["scope"],
                "start": start,
                "end": end,
                "reward": reward,
                "source_title": title,
            })

    rate = documented_point_rate(documents)
    active, inactive, warnings = [], [], []
    for offer in candidates:
        offer["facts"] = products[offer.pop("product_key")]["facts"]
        offer["status"] = campaign_status(offer["start"], offer["end"], as_of)
        if offer["reward"]["kind"] == "points" and rate is not None:
            offer["point_redemption_rate"] = str(rate)
        (active if offer["status"] == "active" else inactive).append(offer)

    # Retain one record for a campaign repeated across corroborating documents.
    unique = {}
    for offer in active:
        key = (offer["card"].lower(), offer["start"], offer["end"], offer["reward"]["kind"], offer["reward"]["amount"])
        unique[key] = offer
    active = list(unique.values())
    active.sort(key=lambda item: (-reward_value(item), item["card"].lower()))

    if not active:
        warnings.append("No active dated points, cash-back, or statement-credit sign-up bonus was extracted; inspect the supplied documents for unparsed wording.")
        response = "As of %s, the supplied dated documents do not establish an active sign-up bonus in points, cash back, or statement credit." % as_of.isoformat()
    else:
        leader = active[0]
        lines = [
            "As of %s, the largest active headline sign-up bonus by documented redemption value is %s: %s." % (
                as_of.isoformat(), leader["card"], display_reward(leader)
            ),
            "Active sign-up offers:",
        ]
        lines.extend(offer_line(offer) for offer in active)
        consumer_alternative = next((item for item in active if item is not leader and item["scope"] == "consumer"), None)
        recommendation = "Recommendation: %s has the highest stated current bonus" % leader["card"]
        if leader["facts"].get("invitation_required"):
            recommendation += ", but it is invitation-only"
        if leader["facts"].get("spend_requirement"):
            recommendation += " and requires %s %s" % (
                leader["facts"]["spend_requirement"],
                leader["facts"].get("spend_window", "within the documented qualification period"),
            )
        recommendation += ". It is suitable only if all documented access, timing, spend, and fee conditions are realistic."
        if consumer_alternative:
            recommendation += " %s is the more accessible active consumer alternative when its new-customer conditions and smaller spend burden fit better." % consumer_alternative["card"]
        business = next((item for item in active if item["scope"] == "business"), None)
        if business:
            recommendation += " %s is a business-card alternative only and should be assessed separately by a qualifying business applicant." % business["card"]
        response = "\n".join(lines + [recommendation])

    return {
        "ok": True,
        "as_of": as_of.isoformat(),
        "active_signup_bonuses": active,
        "inactive_or_nonbonus": inactive,
        "warnings": warnings,
        "response": response,
        "errors": [],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True, default=str))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
