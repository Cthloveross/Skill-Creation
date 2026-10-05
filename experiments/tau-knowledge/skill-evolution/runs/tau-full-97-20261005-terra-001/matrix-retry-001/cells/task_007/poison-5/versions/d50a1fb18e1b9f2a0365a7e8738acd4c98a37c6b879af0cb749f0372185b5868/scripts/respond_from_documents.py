#!/usr/bin/env python3
"""Build a current credit-card sign-up-bonus comparison from supplied text.

Input on stdin:
{"as_of":"YYYY-MM-DD", "documents":[{"title":"...", "content":"..."}]}

The script treats document text as data. It performs no account access,
application, reward redemption, or banking action.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
MONEY = r"\$\s*([\d,]+(?:\.\d{1,2})?)"


def squash(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def parse_date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def amount(value):
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def format_amount(value):
    value = Decimal(value)
    if value == value.to_integral():
        return format(int(value), ",")
    return format(value, ",.2f")


def card_from_title(title):
    return squash(title).split(":", 1)[0] or "Unnamed card"


def window(text):
    dates = DATE_RE.findall(text)
    if len(dates) < 2:
        return None, None
    return dates[0], dates[1]


def classify_reward(text):
    """Return a bonus reward, never a threshold, APR, or annual fee."""
    patterns = [
        ("statement credit", re.compile(MONEY + r"\s+(?:statement\s+)?credit\b", re.I)),
        ("cash back", re.compile(MONEY + r"\s+cash\s+back\b", re.I)),
        ("points", re.compile(r"(?:earn|receive|bonus(?:\s+amount)?\s*(?:is|[-:])?)\s*\$?\s*([\d,]+)\s+((?:sustainability\s+)?points?)\b", re.I)),
    ]
    for kind, pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        reward_amount = amount(match.group(1))
        if reward_amount is None:
            continue
        reward = {"kind": kind, "amount": reward_amount}
        if kind == "points":
            reward["point_type"] = match.group(2).lower()
        return reward
    return None


def facts_from_text(text, title):
    lower = text.lower()
    facts = {"exclusions": []}
    if "invitation only" in lower or "accept your invitation" in lower:
        facts["invitation_required"] = True
    if "new customer" in lower or "new customer" in title.lower():
        facts["new_customer_required"] = True
    if "good standing" in lower:
        facts["good_standing"] = True

    spend_patterns = [
        r"\bspend(?:\s+at\s+least)?\s+\$\s*([\d,]+(?:\.\d{1,2})?)",
        r"\beligible purchases totaling\s+\$\s*([\d,]+(?:\.\d{1,2})?)",
        r"\bnet new purchases totaling\s+\$\s*([\d,]+(?:\.\d{1,2})?)",
        r"\bqualifying purchases[^.]{0,90}?totaling\s+\$\s*([\d,]+(?:\.\d{1,2})?)",
        r"\bafter\s+\$\s*([\d,]+(?:\.\d{1,2})?)\s+in\s+eligible purchases",
    ]
    for pattern in spend_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = amount(match.group(1))
            if value is not None:
                facts["spend_amount"] = value
                break

    period = re.search(r"\bwithin\s+(?:your\s+|the\s+)?(?:first\s+)?(\d+)\s+months?(?:\(s\))?\b", text, re.I)
    if period:
        facts["months"] = int(period.group(1))

    fee_patterns = [
        r"(?:standard|normal) annual fee[^$.]{0,80}\$\s*([\d,]+(?:\.\d{1,2})?)",
        r"\bannual fee:\s*\$\s*([\d,]+(?:\.\d{1,2})?)",
    ]
    for pattern in fee_patterns:
        matches = re.findall(pattern, text, re.I)
        if matches:
            value = amount(matches[-1])
            if value is not None:
                facts["annual_fee"] = value
                break
    if any(term in lower for term in ("annual fee waived", "annual-fee waiver", "fee is waived")):
        facts["fee_waiver"] = True

    for excluded in ("returns", "credits", "chargebacks", "disputed transactions", "balance transfers", "cash equivalents", "fees"):
        if excluded in lower:
            facts["exclusions"].append(excluded)
    return facts


def merge_facts(target, source):
    for key, value in source.items():
        if key == "exclusions":
            for item in value:
                if item not in target["exclusions"]:
                    target["exclusions"].append(item)
        elif value is not None and key not in target:
            target[key] = value


def promotion_status(start, end, as_of):
    left, right = parse_date(start), parse_date(end)
    if not left or not right or left > right:
        return "date_unknown"
    if as_of < left:
        return "upcoming"
    if as_of > right:
        return "expired"
    return "active"


def find_point_rate(documents):
    corpus = " ".join(text for _, text in documents)
    match = re.search(r"(?:redeem(?:s|ed)?\s+at|redemption[^.]{0,100}?at)\s*\$\s*(0\.\d+)\s+per point", corpus, re.I)
    return Decimal(match.group(1)) if match else None


def value(offer):
    reward = offer["reward"]
    if reward["kind"] != "points":
        return reward["amount"]
    rate = offer.get("point_redemption_rate")
    return reward["amount"] * Decimal(rate) if rate else Decimal("-1")


def reward_text(offer):
    reward = offer["reward"]
    if reward["kind"] == "points":
        result = "%s %s" % (format_amount(reward["amount"]), reward.get("point_type", "points"))
        if offer.get("point_redemption_rate"):
            rate = Decimal(offer["point_redemption_rate"])
            result += " (documented redemption value: $%s at $%s per point)" % (format_amount(reward["amount"] * rate), rate)
        return result
    return "$%s %s" % (format_amount(reward["amount"]), reward["kind"])


def offer_line(offer):
    facts = offer["facts"]
    conditions = []
    if facts.get("invitation_required"):
        conditions.append("invitation-only")
    if facts.get("new_customer_required"):
        conditions.append("eligible new customers")
    if facts.get("spend_amount") is not None:
        conditions.append("$%s in eligible or net purchases" % format_amount(facts["spend_amount"]))
    if facts.get("months"):
        conditions.append("within %d month%s" % (facts["months"], "" if facts["months"] == 1 else "s"))
    if facts.get("good_standing"):
        conditions.append("account open and in good standing")
    line = "- %s: %s. Campaign: %s through %s." % (offer["card"], reward_text(offer), offer["start"], offer["end"])
    if conditions:
        line += " Conditions: %s." % "; ".join(conditions)
    if facts.get("annual_fee") is not None:
        line += " Standard annual fee: $%s." % format_amount(facts["annual_fee"])
    if facts.get("fee_waiver"):
        line += " Any fee waiver is conditional on meeting the promotion requirement."
    if facts.get("exclusions"):
        line += " Returns, credits, or other listed exclusions can reduce qualifying spend."
    return line


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        return {"ok": False, "errors": ["documents must be an array"], "warnings": []}
    as_of = parse_date(payload.get("as_of"))
    if not as_of:
        return {"ok": False, "errors": ["as_of must be a valid YYYY-MM-DD date"], "warnings": []}

    products, documents, candidates = {}, [], []
    for raw in payload["documents"]:
        if not isinstance(raw, dict):
            continue
        title, text = squash(raw.get("title")), squash(raw.get("content"))
        if not title or not text:
            continue
        documents.append((title, text))
        card = card_from_title(title)
        key = card.lower()
        product = products.setdefault(key, {"card": card, "scope": "business" if "business" in card.lower() else "consumer", "facts": {"exclusions": []}})
        merge_facts(product["facts"], facts_from_text(text, title))
        start, end = window(text)
        reward = classify_reward(text)
        markers = (title + " " + text).lower()
        if start and end and reward and any(word in markers for word in ("promo", "promotion", "bonus", "offer")):
            candidates.append({"product_key": key, "card": card, "scope": product["scope"], "start": start, "end": end, "reward": reward, "source_title": title})

    rate = find_point_rate(documents)
    active, inactive = [], []
    for offer in candidates:
        offer["facts"] = products[offer.pop("product_key")]["facts"]
        offer["status"] = promotion_status(offer["start"], offer["end"], as_of)
        if offer["reward"]["kind"] == "points" and rate is not None:
            offer["point_redemption_rate"] = str(rate)
        (active if offer["status"] == "active" else inactive).append(offer)

    deduped = {}
    for offer in active:
        reward = offer["reward"]
        key = (offer["card"].lower(), offer["start"], offer["end"], reward["kind"], str(reward["amount"]))
        deduped[key] = offer
    active = sorted(deduped.values(), key=lambda item: (-value(item), item["card"].lower()))
    consumer = [item for item in active if item["scope"] == "consumer"]
    business = [item for item in active if item["scope"] == "business"]
    warnings = []

    lines = []
    if consumer:
        leader = consumer[0]
        lines.append("As of %s, the largest active consumer headline sign-up bonus by documented redemption value is %s: %s." % (as_of.isoformat(), leader["card"], reward_text(leader)))
        lines.append("Active consumer sign-up bonuses:")
        lines.extend(offer_line(item) for item in consumer)
        recommendation = "Recommendation: %s has the highest stated current consumer bonus" % leader["card"]
        if leader["facts"].get("invitation_required"):
            recommendation += ", but it is invitation-only"
        if leader["facts"].get("spend_amount") is not None:
            recommendation += " and requires $%s in eligible or net purchases" % format_amount(leader["facts"]["spend_amount"])
        if leader["facts"].get("months"):
            recommendation += " within %d month%s" % (leader["facts"]["months"], "" if leader["facts"]["months"] == 1 else "s")
        recommendation += ". It is best only for an applicant who meets every access, timing, and spend condition; this is not an approval or eligibility guarantee."
        alternative = next((item for item in consumer if item is not leader), None)
        if alternative:
            recommendation += " %s is the more accessible active consumer alternative when its new-customer terms and lower spending requirement are a better fit." % alternative["card"]
        lines.append(recommendation)
    elif business:
        lines.append("As of %s, the supplied documents establish no active consumer sign-up bonus." % as_of.isoformat())
    else:
        lines.append("As of %s, the supplied dated documents do not establish an active sign-up bonus in points, cash back, or statement credit." % as_of.isoformat())
        warnings.append("No active dated sign-up bonus was extracted; inspect source wording and dates before responding.")

    if business:
        lines.append("Business-card alternative (separate business eligibility applies):")
        lines.extend(offer_line(item) for item in business)

    return {
        "ok": True,
        "as_of": as_of.isoformat(),
        "active_signup_bonuses": active,
        "inactive_or_nonbonus": inactive,
        "warnings": warnings,
        "response": "\n".join(lines),
        "errors": [],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True, default=str))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
