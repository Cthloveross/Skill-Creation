#!/usr/bin/env python3
"""Create evidence-backed card advice from product documents supplied at runtime.

Input JSON:
{
  "opening": "customer request text",
  "documents": [{"document_id": "...", "title": "...", "content": "..."}]
}

Output JSON includes a customer-facing message plus auditable qualified and
rejected card records. This program does not retrieve information or make a
credit decision.
"""
import json
import re
import sys


def number(text):
    return float(str(text).replace(",", ""))


def money(value):
    return "${:,.0f}".format(float(value))


def first_match(pattern, text, flags=re.IGNORECASE | re.DOTALL):
    found = re.search(pattern, text, flags)
    return found.groups() if found else None


def card_name(title):
    """Use the stable product portion before a document-title colon."""
    return title.split(":", 1)[0].strip()


def requested_limit(opening):
    values = []
    for match in re.finditer(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(?:k\b)?", opening, re.I):
        raw = match.group(1)
        value = number(raw)
        tail = opening[match.end() : match.end() + 2].lower()
        if "k" in tail and value < 1000:
            value *= 1000
        values.append(value)
    for match in re.finditer(r"\b(\d+(?:\.\d+)?)\s*k\b", opening, re.I):
        values.append(float(match.group(1)) * 1000)
    return max(values) if values else None


def extract_limit(text):
    """Return the largest documented limit range in text, if one is stated."""
    candidates = []
    for match in re.finditer(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:to|–|—|-)\s*\$\s*([\d,]+(?:\.\d+)?)",
        text,
        re.I,
    ):
        context = text[max(0, match.start() - 140) : match.end() + 40].lower()
        if "limit" in context or "credit line" in context:
            low, high = number(match.group(1)), number(match.group(2))
            candidates.append((low, high))
    return max(candidates, key=lambda pair: pair[1]) if candidates else (None, None)


def extract_fee(text):
    """Extract an unconditional foreign-transaction fee where possible."""
    matches = []
    for match in re.finditer(
        r"foreign\s+transaction\s+fee[^.\n]{0,100}?(?:is|:|charged\s+by[^:]*:)\s*(\d+(?:\.\d+)?)\s*%",
        text,
        re.I,
    ):
        context = text[max(0, match.start() - 45) : match.end()].lower()
        if not any(term in context for term in ("with a premium", "without a premium", "subscription")):
            matches.append(float(match.group(1)))
    return min(matches) if matches else None


def extract_rewards(text):
    found = first_match(
        r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+(eligible\s+)?purchases",
        text,
    )
    if not found:
        return None, None
    return float(found[0]), "all eligible purchases" if found[1] else "all purchases"


def extract_protection(text):
    location = re.search(r"purchase\s+protection", text, re.I)
    if not location:
        return {"available": False, "days": None, "cap": None, "unlimited": False}
    window = text[location.start() : location.start() + 500]
    days = first_match(r"(?:up\s+to\s+)?(\d+)\s+days", window)
    cap = first_match(
        r"(?:maximum\s+(?:coverage\s+)?per\s+claim|maximum\s+per\s+claim|up\s+to)\s*(?:is|:)?\s*\$\s*([\d,]+(?:\.\d+)?)",
        window,
    )
    return {
        "available": True,
        "days": int(days[0]) if days else None,
        "cap": number(cap[0]) if cap else None,
        "unlimited": bool(re.search(r"(?:coverage\s+maximum|coverage)[^.\n]{0,50}unlimited|unlimited[^.\n]{0,50}coverage", window, re.I)),
    }


def extract_restrictions(text):
    notes = []
    if re.search(r"invitation\s+only", text, re.I):
        notes.append("invitation-only")
    score = first_match(r"(?:score\s+of\s+at\s+least|credit\s+score\s+of\s+at\s+least|minimum\s+credit\s+score(?:\s+required)?\s*:)\s*(\d{3})", text)
    if score:
        notes.append("credit score of at least {} for consideration".format(score[0]))
    if re.search(r"premium\s+subscription\s+required\s*:\s*yes", text, re.I):
        notes.append("required premium subscription")
    return notes


def group_documents(documents):
    grouped = {}
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            continue
        title = document.get("title")
        content = document.get("content")
        doc_id = document.get("document_id")
        if not isinstance(title, str) or not title.strip() or not isinstance(content, str):
            continue
        name = card_name(title)
        record = grouped.setdefault(name, {"texts": [], "source_ids": []})
        record["texts"].append(content)
        if isinstance(doc_id, str) and doc_id.strip():
            record["source_ids"].append(doc_id)
    return grouped


def build_cards(documents):
    cards = []
    for name, group in group_documents(documents).items():
        text = "\n".join(group["texts"])
        low, high = extract_limit(text)
        rate, scope = extract_rewards(text)
        cards.append({
            "name": name,
            "sources": group["source_ids"],
            "reward_rate": rate,
            "reward_scope": scope,
            "foreign_fee": extract_fee(text),
            "limit_min": low,
            "limit_max": high,
            "protection": extract_protection(text),
            "restrictions": extract_restrictions(text),
        })
    return cards


def checks(card, limit):
    protection = card["protection"]
    return {
        "documented_sources": bool(card["sources"]),
        "0% foreign transaction fee": card["foreign_fee"] == 0,
        "purchase protection": protection["available"],
        "sufficient documented limit": limit is not None and card["limit_max"] is not None and card["limit_max"] >= limit,
    }


def protection_text(protection):
    text = "purchase protection"
    if protection["days"] is not None:
        text += " for up to {} days".format(protection["days"])
    if protection["unlimited"]:
        text += " with documented unlimited coverage"
    elif protection["cap"] is not None:
        text += " up to {} per eligible claim".format(money(protection["cap"]))
    return text


def reward_text(card, opening):
    rate = "{:.1f}%".format(card["reward_rate"])
    scope = card["reward_scope"]
    lower = opening.lower()
    if "travel" in lower and ("everyday" in lower or "purchase" in lower):
        return "It earns {} cash back on {}, so it rewards travel-heavy spending as well as lower everyday spending.".format(rate, scope)
    if "travel" in lower:
        return "It earns {} cash back on {}, which provides documented rewards for travel-led spending.".format(rate, scope)
    return "It earns {} cash back on {}.".format(rate, scope)


def render(card, limit):
    return " ".join([
        "Recommendation: I recommend the {} as the best documented match.".format(card["name"]),
        reward_text(card, OPENING),
        "It has a 0% foreign transaction fee and {}, subject to applicable policy terms and exclusions.".format(protection_text(card["protection"])),
        "Its documented credit-limit range is {} to {}; a limit of at least {} is possible, but the exact approved limit is subject to underwriting and approval.".format(money(card["limit_min"]), money(card["limit_max"]), money(limit)),
    ])


def main():
    global OPENING
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        OPENING = payload.get("opening")
        documents = payload.get("documents")
        if not isinstance(OPENING, str) or not isinstance(documents, list):
            raise ValueError("opening must be a string and documents must be an array")
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        return

    limit = requested_limit(OPENING)
    cards = build_cards(documents)
    qualified, rejected = [], []
    for card in cards:
        card_checks = checks(card, limit)
        record = {"name": card["name"], "source_ids": card["sources"], "checks": card_checks}
        if all(card_checks.values()):
            # Broad all-purchase rewards are especially useful for mixed travel and everyday use.
            record["selection_score"] = card["reward_rate"] or 0
            qualified.append((card, record))
        else:
            record["unmet_or_unknown"] = [name for name, passed in card_checks.items() if not passed]
            rejected.append(record)

    qualified.sort(key=lambda pair: (-pair[1]["selection_score"], pair[0]["name"].lower()))
    if not qualified:
        print(json.dumps({
            "message": "No supplied product record is documented to meet every stated hard requirement. Review the unmet or unknown requirements before recommending a card.",
            "requested_limit": limit,
            "primary_card": None,
            "qualified_cards": [],
            "rejected_cards": rejected,
        }, indent=2, sort_keys=True))
        return

    primary, primary_record = qualified[0]
    alternatives = []
    for card, _ in qualified[1:]:
        caveat = "; eligibility note: {}".format(", ".join(card["restrictions"])) if card["restrictions"] else ""
        alternatives.append("{} is another documented qualifying option{}.".format(card["name"], caveat))
    message = render(primary, limit)
    if alternatives:
        message += " Other documented qualifying options: " + " ".join(alternatives)

    print(json.dumps({
        "message": message,
        "requested_limit": limit,
        "primary_card": primary["name"],
        "primary_source_ids": primary["sources"],
        "qualified_cards": [primary_record] + [record for _, record in qualified[1:]],
        "rejected_cards": rejected,
        "validation_note": "A documented sufficient ceiling establishes possibility only; approval and the exact limit remain subject to underwriting.",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
