#!/usr/bin/env python3
"""Generate evidence-grounded card advice from runtime-supplied product documents.

Input is one JSON object on stdin. It must contain a nonempty `opening` string
and a nonempty documents array at root or nested beneath frozen_base, base, or
task. The script performs no retrieval and no account or application action.
Output is one JSON object on stdout.
"""
import json
import re
import sys


def as_money(value):
    return "${:,.0f}".format(value)


def numeric(value):
    return float(value.replace(",", ""))


def get_documents(payload):
    docs = payload.get("documents")
    if not isinstance(docs, list):
        for key in ("frozen_base", "base", "task"):
            nested = payload.get(key)
            if isinstance(nested, dict) and isinstance(nested.get("documents"), list):
                docs = nested["documents"]
                break
    if not isinstance(docs, list):
        raise ValueError("a documents array is required")
    usable = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        title, content = doc.get("title"), doc.get("content")
        if isinstance(title, str) and title.strip() and isinstance(content, str) and content.strip():
            usable.append({"title": title, "content": content})
    if not usable:
        raise ValueError("documents contains no usable title/content records")
    return usable


def card_from_title(title):
    return title.split(":", 1)[0].strip()


def find_requested_limit(text):
    values = []
    for match in re.finditer(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", text, re.I):
        value = numeric(match.group(1))
        values.append(value * 1000 if match.group(2) and value < 1000 else value)
    for match in re.finditer(r"(?<![\d$])(\d+(?:\.\d+)?)\s*k\b", text, re.I):
        values.append(float(match.group(1)) * 1000)
    return max(values) if values else None


def parse_request(opening):
    lower = opening.lower()
    return {
        "foreign_fee": any(word in lower for word in (
            "foreign transaction", "foreign fee", "international fee", "international purchases", "abroad"
        )),
        "protection": "purchase protection" in lower,
        "minimum_limit": find_requested_limit(opening),
        "travel": "travel" in lower,
        "everyday": any(word in lower for word in (
            "everyday", "daily", "general purchases", "all purchases"
        )),
    }


def parse_limit(text):
    candidates = []
    pattern = re.compile(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:to|through|–|—|-)\s*\$?\s*([\d,]+(?:\.\d+)?)",
        re.I,
    )
    for match in pattern.finditer(text):
        context = text[max(0, match.start() - 200): match.end() + 200].lower()
        if "limit" in context or "credit line" in context:
            left, right = numeric(match.group(1)), numeric(match.group(2))
            candidates.append((min(left, right), max(left, right)))
    return max(candidates, key=lambda item: item[1]) if candidates else (None, None)


def parse_zero_foreign_fee(text):
    # A zero rate must be stated for the card without a separate subscription
    # condition; conditional zero rates do not satisfy an unconditional request.
    unconditional = False
    conditional = False
    for line in text.splitlines():
        lowered = line.lower()
        if "foreign transaction fee" not in lowered:
            continue
        rate = re.search(r"(\d+(?:\.\d+)?)\s*%", lowered)
        if not rate or float(rate.group(1)) != 0:
            continue
        if any(marker in lowered for marker in (
            "with a premium", "without a premium", "subscription", "if enrolled", "if you enroll"
        )):
            conditional = True
        else:
            unconditional = True
    return unconditional, conditional


def parse_protection(text):
    best = {"available": False, "days": None, "cap": None, "unlimited": False}
    for match in re.finditer(r"purchase\s+protection", text, re.I):
        excerpt = text[match.start(): match.start() + 900]
        days = re.search(r"(?:up\s+to\s+)?(\d+)\s+days", excerpt, re.I)
        cap = re.search(
            r"(?:up\s+to\s+)?\$\s*([\d,]+(?:\.\d+)?)[^.\n]{0,90}per\s+(?:eligible\s+|covered\s+)?claim|"
            r"per\s+(?:eligible\s+|covered\s+)?claim[^$\n.]{0,90}\$\s*([\d,]+(?:\.\d+)?)",
            excerpt,
            re.I,
        )
        unlimited = bool(re.search(r"\bunlimited\b", excerpt, re.I))
        candidate = {
            "available": True,
            "days": int(days.group(1)) if days else None,
            "cap": numeric(cap.group(1) or cap.group(2)) if cap else None,
            "unlimited": unlimited,
        }
        score = int(candidate["available"]) + int(candidate["days"] is not None) + int(candidate["cap"] is not None) + int(candidate["unlimited"])
        old_score = int(best["available"]) + int(best["days"] is not None) + int(best["cap"] is not None) + int(best["unlimited"])
        if score > old_score:
            best = candidate
    return best


def parse_rewards(text):
    rules = (
        (r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+eligible\s+purchases", "all eligible purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+(?:cash\s+back\s+)?on\s+all\s+categories", "all categories", 3),
        (r"cash\s+back\s+on\s+all\s+purchases\s*:\s*(\d+(?:\.\d+)?)\s*%", "all purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+(?:cash\s+back\s+)?(?:on|back)[^.\n]{0,100}\btravel\b", "eligible travel purchases", 2),
    )
    for pattern, scope, breadth in rules:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1)), scope, breadth
    return None, None, 0


def parse_restrictions(text):
    restrictions = []
    if re.search(r"invitation\s*-?\s*only", text, re.I):
        restrictions.append("it is invitation-only")
    if re.search(r"rho[\-‑ ]bank\+\s+premium\s+subscription\s+required\s*:\s*yes", text, re.I):
        restrictions.append("an active Rho-Bank+ premium subscription is required")
    score = re.search(r"(?:minimum\s+credit\s+score(?:\s+required)?|score\s+of\s+at\s+least)[^\n.]{0,50}?(\d{3})", text, re.I)
    if score:
        restrictions.append("the documented credit-score threshold is {}".format(score.group(1)))
    fee = re.search(r"annual\s+fee\s*:\s*\$\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if fee and numeric(fee.group(1)) > 0:
        restrictions.append("the annual fee is {}".format(as_money(numeric(fee.group(1)))))
    return restrictions


def build_catalog(documents):
    grouped = {}
    for document in documents:
        grouped.setdefault(card_from_title(document["title"]), []).append(document["content"])
    cards = []
    for name, fragments in grouped.items():
        corpus = "\n".join(fragments)
        low, high = parse_limit(corpus)
        zero_fee, conditional_fee = parse_zero_foreign_fee(corpus)
        rate, scope, breadth = parse_rewards(corpus)
        cards.append({
            "name": name,
            "low": low,
            "high": high,
            "zero_fee": zero_fee,
            "conditional_zero_fee": conditional_fee,
            "protection": parse_protection(corpus),
            "rate": rate,
            "scope": scope,
            "breadth": breadth,
            "restrictions": parse_restrictions(corpus),
        })
    return cards


def hard_checks(card, request):
    checks = {}
    if request["foreign_fee"]:
        checks["0_percent_foreign_transaction_fee"] = card["zero_fee"]
    if request["protection"]:
        checks["purchase_protection"] = card["protection"]["available"]
    if request["minimum_limit"] is not None:
        checks["requested_limit_possible"] = card["high"] is not None and card["high"] >= request["minimum_limit"]
    return checks


def protection_phrase(protection):
    phrase = "purchase protection"
    if protection["days"] is not None:
        phrase += " for up to {} days".format(protection["days"])
    if protection["unlimited"]:
        phrase += " with stated unlimited coverage"
    elif protection["cap"] is not None:
        phrase += " up to {} per eligible claim".format(as_money(protection["cap"]))
    return phrase


def customer_message(card, request):
    result = ["I recommend {} as the strongest documented fit for your requirements.".format(card["name"])]
    if card["rate"] is not None:
        if request["travel"] and request["everyday"] and card["breadth"] == 3:
            rationale = "Because the rate applies broadly, it rewards travel and lower everyday spending without relying on travel merchant-category coding."
        elif request["travel"]:
            rationale = "This is relevant to your travel-heavy spending."
        else:
            rationale = "This supports the spending pattern you described."
        result.append("It earns {:.1f}% cash back on {}. {}".format(card["rate"], card["scope"], rationale))
    if request["foreign_fee"]:
        result.append("It has a 0% foreign transaction fee.")
    if request["protection"]:
        result.append("It includes {}, subject to policy terms and exclusions.".format(protection_phrase(card["protection"])))
    if request["minimum_limit"] is not None:
        if card["low"] is not None:
            limit_text = "{} to {}".format(as_money(card["low"]), as_money(card["high"]))
        else:
            limit_text = "up to {}".format(as_money(card["high"]))
        result.append(
            "Its documented typical approved credit-limit range is {}, so a limit of at least {} is possible, not guaranteed; approval and the actual assigned limit depend on underwriting.".format(
                limit_text, as_money(request["minimum_limit"])
            )
        )
    if card["restrictions"]:
        result.append("Important documented tradeoffs: {}.".format("; ".join(card["restrictions"])))
    return " ".join(result)


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        opening = payload.get("opening")
        if not isinstance(opening, str) or not opening.strip():
            raise ValueError("opening must be a nonempty string")
        documents = get_documents(payload)
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        return

    request = parse_request(opening)
    qualified, rejected = [], []
    for card in build_catalog(documents):
        checks = hard_checks(card, request)
        record = {"name": card["name"], "checks": checks}
        if all(checks.values()):
            qualified.append((card, record))
        else:
            record["unmet_or_unknown"] = [key for key, value in checks.items() if not value]
            rejected.append(record)

    # Prefer broad rewards, then the higher documented rate. This selects a
    # general everyday card over a narrower category card when both pass.
    qualified.sort(key=lambda item: (-item[0]["breadth"], -(item[0]["rate"] if item[0]["rate"] is not None else -1), item[0]["name"].lower()))

    if not qualified:
        output = {
            "message": None,
            "primary_card": None,
            "qualified_cards": [],
            "rejected_cards": rejected,
            "validation": {
                "send_ready": False,
                "issues": ["No documented card passed every extracted hard filter."],
            },
        }
    else:
        card, primary_record = qualified[0]
        issues = []
        if card["rate"] is None:
            issues.append("No documented reward rate was extracted for the selected card.")
        output = {
            "message": customer_message(card, request),
            "primary_card": card["name"],
            "qualified_cards": [record for _, record in qualified],
            "rejected_cards": rejected,
            "validation": {"send_ready": not issues, "issues": issues},
        }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
