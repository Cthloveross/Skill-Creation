#!/usr/bin/env python3
"""Create evidence-grounded credit-card advice from current-task documents.

Input JSON on stdin:
{
  "opening": str,
  "documents": [{"document_id": str, "title": str, "content": str}]
}

Output JSON includes a customer-facing draft, qualification evidence, and a
send-ready validation result. This program does not retrieve information, take
bank actions, submit applications, or make underwriting decisions.
"""
import json
import re
import sys


def number(text):
    return float(str(text).replace(",", ""))


def dollars(value):
    return "${:,.0f}".format(value)


def card_name(title):
    return title.split(":", 1)[0].strip()


def requested_limit(opening):
    """Return the largest requested monetary amount, including shorthand K."""
    values = []
    for match in re.finditer(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", opening, re.I):
        value = number(match.group(1))
        if match.group(2) and value < 1000:
            value *= 1000
        values.append(value)
    for match in re.finditer(r"(?<!\$)\b(\d+(?:\.\d+)?)\s*k\b", opening, re.I):
        values.append(float(match.group(1)) * 1000)
    return max(values) if values else None


def extract_limit_range(text):
    """Find the highest documented monetary range in a credit-limit context."""
    pattern = re.compile(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:to|–|—|-)\s*\$\s*([\d,]+(?:\.\d+)?)",
        re.I,
    )
    found = []
    for match in pattern.finditer(text):
        context = text[max(0, match.start() - 180):match.end() + 180].lower()
        if "credit limit" in context or "credit-line" in context or "credit line" in context:
            low, high = number(match.group(1)), number(match.group(2))
            found.append((min(low, high), max(low, high)))
    return max(found, key=lambda pair: pair[1]) if found else (None, None)


def extract_foreign_fee(text):
    """Return 0 only when an unconditional 0% foreign transaction fee is found."""
    results = []
    for line in text.splitlines():
        normalized = line.lower()
        if "foreign transaction fee" not in normalized:
            continue
        percentage = re.search(r"foreign\s+transaction\s+fee[^\n]*?(\d+(?:\.\d+)?)\s*%", line, re.I)
        if not percentage:
            continue
        conditional = any(token in normalized for token in (
            "with a premium", "without a premium", "with premium", "without premium",
            "if you", "only with", "subscription",
        ))
        if not conditional:
            results.append(float(percentage.group(1)))
    return min(results) if results else None


def extract_reward(text):
    patterns = (
        r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+eligible\s+purchases",
        r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+categories",
        r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+purchases",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            if "eligible" in match.group(0).lower():
                return float(match.group(1)), "all eligible purchases"
            if "categories" in match.group(0).lower():
                return float(match.group(1)), "all categories"
            return float(match.group(1)), "all purchases"
    return None, None


def extract_protection(text):
    """Extract the most detailed purchase-protection statement in a card corpus."""
    candidates = []
    for match in re.finditer(r"purchase\s+protection", text, re.I):
        window = text[match.start():match.start() + 850]
        days = re.search(r"(?:up\s+to\s+)?(\d+)\s+days", window, re.I)
        cap = re.search(
            r"(?:maximum\s+(?:coverage\s+)?per\s+claim|maximum\s+per\s+claim|up\s+to)\s*(?:is|:)?\s*\$\s*([\d,]+(?:\.\d+)?)",
            window,
            re.I,
        )
        unlimited = bool(re.search(r"(?:coverage\s+maximum|coverage)[^.\n]{0,80}unlimited|unlimited[^.\n]{0,80}coverage", window, re.I))
        candidates.append({
            "available": True,
            "days": int(days.group(1)) if days else None,
            "cap": number(cap.group(1)) if cap else None,
            "unlimited": unlimited,
        })
    if not candidates:
        return {"available": False, "days": None, "cap": None, "unlimited": False}
    return max(candidates, key=lambda item: sum(value is not None for value in (item["days"], item["cap"])) + int(item["unlimited"]))


def extract_restrictions(text):
    restrictions = []
    if re.search(r"invitation\s*-?\s*only", text, re.I):
        restrictions.append("it is invitation-only")
    score = re.search(r"(?:credit\s+score|score)[^\n.]{0,40}?at\s+least\s*\$?\s*(\d{3})", text, re.I)
    if score:
        restrictions.append("a credit score of at least {} is stated for consideration".format(score.group(1)))
    subscription = re.search(r"([\w+\-‐‑]+)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes", text, re.I)
    if subscription:
        restrictions.append("it requires a {} subscription".format(subscription.group(1)))
    elif re.search(r"premium\s+subscription\s+required\s*:\s*yes", text, re.I):
        restrictions.append("it requires a premium subscription")
    fee = re.search(r"annual\s+fee\s*:\s*\$\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if fee and number(fee.group(1)) > 0:
        restrictions.append("annual fee: {}".format(dollars(number(fee.group(1)))))
    return restrictions


def collect_cards(documents):
    grouped = {}
    for document in documents:
        if not isinstance(document, dict):
            continue
        title, content = document.get("title"), document.get("content")
        if not isinstance(title, str) or not title.strip() or not isinstance(content, str):
            continue
        name = card_name(title)
        group = grouped.setdefault(name, {"text": [], "source_ids": []})
        group["text"].append(content)
        if isinstance(document.get("document_id"), str) and document["document_id"]:
            group["source_ids"].append(document["document_id"])

    cards = []
    for name, group in grouped.items():
        corpus = "\n".join(group["text"])
        low, high = extract_limit_range(corpus)
        rate, scope = extract_reward(corpus)
        cards.append({
            "name": name,
            "source_ids": group["source_ids"],
            "limit_min": low,
            "limit_max": high,
            "foreign_fee": extract_foreign_fee(corpus),
            "reward_rate": rate,
            "reward_scope": scope,
            "protection": extract_protection(corpus),
            "restrictions": extract_restrictions(corpus),
        })
    return cards


def checks_for(card, limit):
    return {
        "documented_0_percent_foreign_transaction_fee": card["foreign_fee"] == 0,
        "documented_purchase_protection": card["protection"]["available"],
        "documented_limit_reaches_requested_amount": (
            limit is not None and card["limit_max"] is not None and card["limit_max"] >= limit
        ),
        "documented_all_purchase_reward": card["reward_rate"] is not None,
    }


def protection_text(protection):
    phrase = "purchase protection"
    if protection["days"] is not None:
        phrase += " for up to {} days".format(protection["days"])
    if protection["unlimited"]:
        phrase += " with documented unlimited coverage"
    elif protection["cap"] is not None:
        phrase += " up to {} per eligible claim".format(dollars(protection["cap"]))
    return phrase


def recommendation_text(card, limit, opening):
    travel_fit = "travel-heavy spending as well as lower everyday purchases" if "travel" in opening.lower() else "everyday purchases"
    text = (
        "Recommendation: I recommend the {name} as the best documented match. "
        "It earns {rate:.1f}% cash back on {scope}, which fits {fit}. "
        "It has a 0% foreign transaction fee and {protection}, subject to applicable policy terms and exclusions. "
        "Its documented credit-limit range is {low} to {high}, so a limit of at least {requested} is possible; "
        "the actual approved limit is subject to underwriting and approval."
    ).format(
        name=card["name"], rate=card["reward_rate"], scope=card["reward_scope"], fit=travel_fit,
        protection=protection_text(card["protection"]), low=dollars(card["limit_min"]),
        high=dollars(card["limit_max"]), requested=dollars(limit),
    )
    if card["restrictions"]:
        text += " Important terms: {}.".format("; ".join(card["restrictions"]))
    return text


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        opening, documents = payload.get("opening"), payload.get("documents")
        if not isinstance(opening, str):
            raise ValueError("opening must be a string")
        if not isinstance(documents, list):
            raise ValueError("documents must be an array")
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    limit = requested_limit(opening)
    qualified, rejected = [], []
    for card in collect_cards(documents):
        checks = checks_for(card, limit)
        record = {"name": card["name"], "source_ids": card["source_ids"], "checks": checks}
        if all(checks.values()):
            qualified.append((card, record))
        else:
            record["unmet_or_unknown"] = [name for name, passed in checks.items() if not passed]
            rejected.append(record)

    qualified.sort(key=lambda item: (-item[0]["reward_rate"], item[0]["name"].lower()))
    if not qualified:
        message = (
            "No supplied card is documented to meet every stated hard requirement with a documented "
            "all-purchase rewards rationale. Review the per-card unmet or unknown requirements before recommending a card."
        )
        output = {
            "message": message,
            "primary_card": None,
            "requested_limit": limit,
            "qualified_cards": [],
            "rejected_cards": rejected,
            "validation": {"send_ready": False, "issues": ["No documented qualifying card was found."]},
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return

    primary, primary_record = qualified[0]
    message = recommendation_text(primary, limit, opening)
    if len(qualified) > 1:
        alternatives = []
        for card, _ in qualified[1:]:
            caveat = "; ".join(card["restrictions"]) if card["restrictions"] else "review its documented terms"
            alternatives.append("{} is another qualifying option, but {}.".format(card["name"], caveat))
        message += " Alternatives: " + " ".join(alternatives)

    output = {
        "message": message,
        "primary_card": primary["name"],
        "primary_source_ids": primary["source_ids"],
        "requested_limit": limit,
        "qualified_cards": [record for _, record in qualified],
        "rejected_cards": rejected,
        "validation": {
            "send_ready": True,
            "issues": [],
            "note": "A documented sufficient limit establishes possibility only; approval and assigned limit remain underwriting decisions.",
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
