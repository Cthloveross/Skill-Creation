#!/usr/bin/env python3
"""Create documented credit-card advice from product documents supplied at runtime.

Reads JSON on stdin. Required: opening and a nonempty documents array, either at
root or below frozen_base/base/task. Writes JSON only; no retrieval or account
operations are performed.
"""
import json
import re
import sys


def money(value):
    return "${:,.0f}".format(value)


def number(value):
    return float(value.replace(",", ""))


def documents_from(payload):
    if isinstance(payload.get("documents"), list):
        docs = payload["documents"]
    else:
        docs = None
        for key in ("frozen_base", "base", "task"):
            wrapped = payload.get(key)
            if isinstance(wrapped, dict) and isinstance(wrapped.get("documents"), list):
                docs = wrapped["documents"]
                break
    if not isinstance(docs, list):
        raise ValueError("a documents array is required")
    usable = [d for d in docs if isinstance(d, dict) and isinstance(d.get("title"), str)
              and isinstance(d.get("content"), str) and d["title"].strip() and d["content"].strip()]
    if not usable:
        raise ValueError("documents contains no usable title/content records")
    return usable


def card_name(title):
    return title.split(":", 1)[0].strip()


def requested_limit(text):
    found = []
    for match in re.finditer(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", text, re.I):
        value = number(match.group(1))
        found.append(value * 1000 if match.group(2) and value < 1000 else value)
    for match in re.finditer(r"(?<![\d$])(\d+(?:\.\d+)?)\s*k\b", text, re.I):
        found.append(float(match.group(1)) * 1000)
    return max(found) if found else None


def request_features(opening):
    lower = opening.lower()
    return {
        "foreign": any(x in lower for x in ("foreign transaction", "foreign fee", "international", "abroad")),
        "protection": "purchase protection" in lower,
        "limit": requested_limit(opening),
        "travel": "travel" in lower,
        "everyday": any(x in lower for x in ("everyday", "daily", "all purchases", "general purchases")),
    }


def limit_range(text):
    choices = []
    pattern = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:to|through|–|—|-)\s*\$?\s*([\d,]+(?:\.\d+)?)", re.I)
    for match in pattern.finditer(text):
        context = text[max(0, match.start() - 180):match.end() + 180].lower()
        if "limit" in context or "credit line" in context:
            a, b = number(match.group(1)), number(match.group(2))
            choices.append((min(a, b), max(a, b)))
    return max(choices, key=lambda x: x[1]) if choices else (None, None)


def foreign_fee(text):
    unconditional = False
    conditional = False
    for line in text.splitlines():
        low = line.lower()
        if "foreign transaction fee" not in low:
            continue
        rate = re.search(r"(\d+(?:\.\d+)?)\s*%", low)
        if not rate or float(rate.group(1)) != 0:
            continue
        if any(word in low for word in ("with a premium", "subscription", "if enrolled", "without a premium")):
            conditional = True
        else:
            unconditional = True
    return unconditional, conditional


def protection(text):
    result = {"available": False, "days": None, "cap": None, "unlimited": False}
    for hit in re.finditer(r"purchase\s+protection", text, re.I):
        excerpt = text[hit.start():hit.start() + 1000]
        day = re.search(r"(?:up\s+to\s+)?(\d+)\s+days", excerpt, re.I)
        cap = re.search(r"(?:per\s+claim|coverage\s+per\s+claim)[^$\n.]{0,80}\$\s*([\d,]+(?:\.\d+)?)|\$\s*([\d,]+(?:\.\d+)?)[^.\n]{0,80}per\s+claim", excerpt, re.I)
        unlimited = bool(re.search(r"(?:coverage|maximum)[^.\n]{0,100}unlimited|unlimited[^.\n]{0,100}(?:coverage|maximum)", excerpt, re.I))
        candidate = {
            "available": True,
            "days": int(day.group(1)) if day else None,
            "cap": number(cap.group(1) or cap.group(2)) if cap else None,
            "unlimited": unlimited,
        }
        if sum(v is not None and v is not False for v in candidate.values()) > sum(v is not None and v is not False for v in result.values()):
            result = candidate
    return result


def rewards(text):
    patterns = [
        (r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+eligible\s+purchases", "all eligible purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+(?:cash\s+back\s+)?on\s+all\s+categories", "all categories", 3),
        (r"cash\s+back\s+on\s+all\s+purchases\s*:\s*(\d+(?:\.\d+)?)\s*%", "all purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back[^.\n]{0,90}\btravel\b", "eligible travel purchases", 2),
    ]
    for pattern, scope, strength in patterns:
        hit = re.search(pattern, text, re.I)
        if hit:
            return float(hit.group(1)), scope, strength
    return None, None, 0


def restrictions(text):
    items = []
    if re.search(r"invitation\s*-?\s*only", text, re.I):
        items.append("invitation-only access")
    subscription = re.search(r"([A-Za-z0-9+\-‑ ]*?)premium\s+subscription\s+required\s*:\s*yes", text, re.I)
    if subscription:
        label = subscription.group(1).strip()
        items.append("required {}premium subscription".format((label + " ") if label else ""))
    score = re.search(r"(?:minimum\s+credit\s+score(?:\s+required)?|credit\s+score)[^\n.]{0,60}?(\d{3})", text, re.I)
    if score:
        items.append("documented credit-score threshold of {}".format(score.group(1)))
    fee = re.search(r"annual\s+fee\s*:\s*\$\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if fee and number(fee.group(1)) > 0:
        items.append("annual fee of {}".format(money(number(fee.group(1)))))
    return items


def build_cards(docs):
    grouped = {}
    for doc in docs:
        grouped.setdefault(card_name(doc["title"]), []).append(doc["content"])
    cards = []
    for name, texts in grouped.items():
        corpus = "\n".join(texts)
        low, high = limit_range(corpus)
        zero, conditional = foreign_fee(corpus)
        rate, scope, breadth = rewards(corpus)
        cards.append({"name": name, "low": low, "high": high, "zero_fee": zero,
                      "conditional_fee": conditional, "protection": protection(corpus),
                      "rate": rate, "scope": scope, "breadth": breadth,
                      "restrictions": restrictions(corpus)})
    return cards


def qualifies(card, req):
    checks = {}
    if req["foreign"]:
        checks["0_percent_foreign_transaction_fee"] = card["zero_fee"]
    if req["protection"]:
        checks["purchase_protection"] = card["protection"]["available"]
    if req["limit"] is not None:
        checks["requested_limit_possible"] = card["high"] is not None and card["high"] >= req["limit"]
    return checks


def protection_words(value):
    phrase = "purchase protection"
    if value["days"] is not None:
        phrase += " for up to {} days".format(value["days"])
    if value["unlimited"]:
        phrase += " with stated unlimited coverage"
    elif value["cap"] is not None:
        phrase += " up to {} per eligible claim".format(money(value["cap"]))
    return phrase


def message_for(card, req):
    parts = ["Recommendation: {} is the strongest documented fit for your requirements.".format(card["name"])]
    if card["rate"] is not None:
        if req["travel"] and req["everyday"] and card["breadth"] == 3:
            rationale = "That rewards travel and lower everyday spending without relying on travel-category coding."
        elif req["travel"]:
            rationale = "That is relevant to travel-heavy spending."
        else:
            rationale = "That supports the spending pattern you described."
        parts.append("It earns {:.1f}% cash back on {}. {}".format(card["rate"], card["scope"], rationale))
    if req["foreign"]:
        parts.append("It has a 0% foreign transaction fee.")
    if req["protection"]:
        parts.append("It includes {}, subject to policy terms and exclusions.".format(protection_words(card["protection"])))
    if req["limit"] is not None:
        limits = "{} to {}".format(money(card["low"]), money(card["high"])) if card["low"] is not None else "up to {}".format(money(card["high"]))
        parts.append("Its documented typical credit-limit range is {}, so a limit of at least {} is possible; approval and the actual assigned limit depend on underwriting.".format(limits, money(req["limit"])))
    if card["restrictions"]:
        parts.append("Important documented terms: {}.".format("; ".join(card["restrictions"])))
    return " ".join(parts)


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("opening"), str) or not payload["opening"].strip():
            raise ValueError("opening must be a nonempty string")
        docs = documents_from(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    req = request_features(payload["opening"])
    qualified, rejected = [], []
    for card in build_cards(docs):
        checks = qualifies(card, req)
        record = {"name": card["name"], "checks": checks}
        if all(checks.values()):
            qualified.append((card, record))
        else:
            record["unmet_or_unknown"] = [key for key, value in checks.items() if not value]
            rejected.append(record)
    qualified.sort(key=lambda pair: (-pair[0]["breadth"], -(pair[0]["rate"] or -1), pair[0]["name"].lower()))

    if not qualified:
        output = {"message": None, "primary_card": None, "qualified_cards": [], "rejected_cards": rejected,
                  "validation": {"send_ready": False, "issues": ["No documented card passed all extracted hard filters."]}}
    else:
        card, record = qualified[0]
        issues = []
        if card["rate"] is None:
            issues.append("No documented reward rate was extracted for the selected card.")
        output = {"message": message_for(card, req), "primary_card": card["name"],
                  "qualified_cards": [record for _, record in qualified], "rejected_cards": rejected,
                  "validation": {"send_ready": not issues, "issues": issues}}
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
