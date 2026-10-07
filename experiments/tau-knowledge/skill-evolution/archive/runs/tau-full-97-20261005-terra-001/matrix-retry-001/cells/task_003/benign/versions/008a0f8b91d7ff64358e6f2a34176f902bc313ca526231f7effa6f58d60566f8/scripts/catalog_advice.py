#!/usr/bin/env python3
"""Draft evidence-backed card advice from documents passed at runtime.

Input JSON:
{"opening": str, "documents": [{"document_id": str, "title": str, "content": str}]}

Output JSON contains a customer-facing draft, the selected card, qualification
checks, source identifiers, and rejected-card reasons. The program performs no
retrieval, application, account action, or credit decision.
"""
import json
import re
import sys


def as_number(value):
    return float(str(value).replace(",", ""))


def money(value):
    return "${:,.0f}".format(value)


def product_name(title):
    return title.split(":", 1)[0].strip()


def requested_limit(text):
    """Find the largest dollar amount or K amount in a customer request."""
    values = []
    for match in re.finditer(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", text, re.I):
        value = as_number(match.group(1))
        if match.group(2) and value < 1000:
            value *= 1000
        values.append(value)
    for match in re.finditer(r"\b(\d+(?:\.\d+)?)\s*k\b", text, re.I):
        values.append(float(match.group(1)) * 1000)
    return max(values) if values else None


def limit_range(text):
    candidates = []
    pattern = r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:to|–|—|-)\s*\$\s*([\d,]+(?:\.\d+)?)"
    for match in re.finditer(pattern, text, re.I):
        context = text[max(0, match.start() - 160): match.end() + 80].lower()
        if "limit" in context or "credit line" in context:
            candidates.append((as_number(match.group(1)), as_number(match.group(2))))
    return max(candidates, key=lambda item: item[1]) if candidates else (None, None)


def foreign_fee(text):
    """Return an unconditional documented foreign transaction fee, if available."""
    values = []
    for line in text.splitlines():
        normalized = line.lower()
        if "foreign transaction fee" not in normalized:
            continue
        if any(word in normalized for word in ("with a premium", "without a premium", "if you", "subscription")):
            continue
        match = re.search(r"foreign\s+transaction\s+fee[^\n]*?(\d+(?:\.\d+)?)\s*%", line, re.I)
        if match:
            values.append(float(match.group(1)))
    return min(values) if values else None


def reward(text):
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+(eligible\s+)?purchases",
        text,
        re.I,
    )
    if not match:
        return None, None
    return float(match.group(1)), "all eligible purchases" if match.group(2) else "all purchases"


def protection(text):
    match = re.search(r"purchase\s+protection", text, re.I)
    if not match:
        return {"available": False, "days": None, "cap": None, "unlimited": False}
    window = text[match.start():match.start() + 700]
    days_match = re.search(r"(?:up\s+to\s+)?(\d+)\s+days", window, re.I)
    cap_match = re.search(
        r"(?:maximum\s+(?:coverage\s+)?per\s+claim|maximum\s+per\s+claim|up\s+to)\s*(?:is|:)?\s*\$\s*([\d,]+(?:\.\d+)?)",
        window,
        re.I,
    )
    unlimited = bool(re.search(r"(?:coverage\s+maximum|coverage)[^.\n]{0,60}unlimited|unlimited[^.\n]{0,60}coverage", window, re.I))
    return {
        "available": True,
        "days": int(days_match.group(1)) if days_match else None,
        "cap": as_number(cap_match.group(1)) if cap_match else None,
        "unlimited": unlimited,
    }


def restrictions(text):
    notes = []
    if re.search(r"invitation\s*-?\s*only", text, re.I):
        notes.append("invitation-only")
    score = re.search(r"(?:score|credit\s+score)\s+(?:of\s+)?at\s+least\s*(\d{3})", text, re.I)
    if score:
        notes.append("at least a {} credit score for consideration".format(score.group(1)))
    membership = re.search(r"([A-Za-z0-9+\-‐‑]+)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes", text, re.I)
    if membership:
        notes.append("requires {} subscription".format(membership.group(1)))
    elif re.search(r"premium\s+subscription\s+required\s*:\s*yes", text, re.I):
        notes.append("requires a premium subscription")
    return notes


def cards_from_documents(documents):
    grouped = {}
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        title, content = doc.get("title"), doc.get("content")
        if not isinstance(title, str) or not title.strip() or not isinstance(content, str):
            continue
        name = product_name(title)
        group = grouped.setdefault(name, {"texts": [], "sources": []})
        group["texts"].append(content)
        if isinstance(doc.get("document_id"), str) and doc["document_id"]:
            group["sources"].append(doc["document_id"])

    result = []
    for name, group in grouped.items():
        text = "\n".join(group["texts"])
        low, high = limit_range(text)
        rate, scope = reward(text)
        result.append({
            "name": name,
            "sources": group["sources"],
            "limit_min": low,
            "limit_max": high,
            "foreign_fee": foreign_fee(text),
            "reward_rate": rate,
            "reward_scope": scope,
            "protection": protection(text),
            "restrictions": restrictions(text),
        })
    return result


def qualification_checks(card, requested):
    return {
        "documented_0_percent_foreign_transaction_fee": card["foreign_fee"] == 0,
        "documented_purchase_protection": card["protection"]["available"],
        "documented_limit_reaches_requested_amount": (
            requested is not None and card["limit_max"] is not None and card["limit_max"] >= requested
        ),
        "documented_all_purchase_reward_for_spending_rationale": card["reward_rate"] is not None,
    }


def protection_phrase(data):
    result = "purchase protection"
    if data["days"] is not None:
        result += " for up to {} days".format(data["days"])
    if data["unlimited"]:
        result += " with documented unlimited coverage"
    elif data["cap"] is not None:
        result += " up to {} per eligible claim".format(money(data["cap"]))
    return result


def draft(card, requested, opening):
    rate = "{:.1f}%".format(card["reward_rate"])
    opening_lower = opening.lower()
    if "travel" in opening_lower:
        fit = "which rewards travel-heavy spending as well as lower everyday purchases"
    else:
        fit = "which fits everyday spending"
    return (
        "Recommendation: I recommend the {name} as the best documented match. "
        "It earns {rate} cash back on {scope}, {fit}. "
        "It has a 0% foreign transaction fee and {protection}, subject to applicable policy terms and exclusions. "
        "Its documented credit-limit range is {low} to {high}, so a limit of at least {requested} is possible; "
        "the exact approved limit is subject to underwriting and approval."
    ).format(
        name=card["name"], rate=rate, scope=card["reward_scope"], fit=fit,
        protection=protection_phrase(card["protection"]), low=money(card["limit_min"]),
        high=money(card["limit_max"]), requested=money(requested),
    )


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        opening = payload.get("opening")
        documents = payload.get("documents")
        if not isinstance(opening, str):
            raise ValueError("opening must be a string")
        if not isinstance(documents, list):
            raise ValueError("documents must be an array")
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        return

    requested = requested_limit(opening)
    qualified, rejected = [], []
    for card in cards_from_documents(documents):
        checks = qualification_checks(card, requested)
        record = {"name": card["name"], "source_ids": card["sources"], "checks": checks}
        if all(checks.values()):
            record["selection_score"] = card["reward_rate"]
            qualified.append((card, record))
        else:
            record["unmet_or_unknown"] = [key for key, value in checks.items() if not value]
            rejected.append(record)

    qualified.sort(key=lambda item: (-item[1]["selection_score"], item[0]["name"].lower()))
    if not qualified:
        print(json.dumps({
            "message": "No supplied product is documented to meet every stated hard requirement and provide a documented all-purchase rewards rationale. Review the unmet or unknown requirements before recommending a card.",
            "primary_card": None,
            "requested_limit": requested,
            "qualified_cards": [],
            "rejected_cards": rejected,
            "validation_note": "Missing evidence is not treated as a qualifying benefit.",
        }, indent=2, sort_keys=True))
        return

    primary, primary_record = qualified[0]
    message = draft(primary, requested, opening)
    if len(qualified) > 1:
        alternatives = []
        for card, _ in qualified[1:]:
            caveat = "; eligibility note: {}".format(", ".join(card["restrictions"])) if card["restrictions"] else ""
            alternatives.append("{} is another documented qualifying option{}.".format(card["name"], caveat))
        message += " Other documented qualifying options: " + " ".join(alternatives)

    print(json.dumps({
        "message": message,
        "primary_card": primary["name"],
        "primary_source_ids": primary["sources"],
        "requested_limit": requested,
        "qualified_cards": [record for _, record in qualified],
        "rejected_cards": rejected,
        "validation_note": "A sufficient documented limit establishes possibility only; approval and the exact assigned limit remain subject to underwriting.",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
