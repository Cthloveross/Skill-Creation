#!/usr/bin/env python3
"""Create evidence-grounded card advice from documents supplied at runtime.

Input JSON:
  {"opening": str, "documents": [{"document_id": str, "title": str, "content": str}]}

Output JSON contains a customer-ready message, evidence checks, and validation.
The script performs no retrieval, account access, application, or underwriting action.
"""
import json
import re
import sys


def money(value):
    return "${:,.0f}".format(value)


def number(value):
    return float(value.replace(",", ""))


def card_name(title):
    return title.split(":", 1)[0].strip()


def requested_limit(text):
    values = []
    for match in re.finditer(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", text, re.I):
        value = number(match.group(1))
        if match.group(2) and value < 1000:
            value *= 1000
        values.append(value)
    for match in re.finditer(r"(?<![$\d])\b(\d+(?:\.\d+)?)\s*k\b", text, re.I):
        values.append(float(match.group(1)) * 1000)
    return max(values) if values else None


def request_features(opening):
    text = opening.lower()
    return {
        "foreign": any(term in text for term in (
            "foreign transaction", "foreign fee", "international purchase", "international spending",
            "international use", "abroad",
        )),
        "protection": "purchase protection" in text,
        "limit": requested_limit(opening),
        "travel": "travel" in text,
        "everyday": any(term in text for term in ("everyday", "daily", "general purchases")),
    }


def extract_limits(text):
    ranges = []
    pattern = re.compile(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:to|through|–|—|-)\s*\$?\s*([\d,]+(?:\.\d+)?)",
        re.I,
    )
    for match in pattern.finditer(text):
        nearby = text[max(0, match.start() - 260):match.end() + 260].lower()
        if any(label in nearby for label in (
            "credit limit", "credit limits", "credit line", "approved limit", "starting limit",
            "initial limit", "limit range",
        )):
            low, high = number(match.group(1)), number(match.group(2))
            ranges.append((min(low, high), max(low, high)))
    if not ranges:
        return None, None
    return max(ranges, key=lambda pair: pair[1])


def extract_foreign_fee(text):
    # A conditional zero-fee statement does not satisfy an unconditional no-fee request.
    candidates = []
    for line in text.splitlines():
        normalized = line.lower()
        if "foreign transaction fee" not in normalized:
            continue
        percentage = re.search(r"(\d+(?:\.\d+)?)\s*%", normalized)
        if not percentage:
            continue
        conditional = any(marker in normalized for marker in (
            "with a premium", "without a premium", "with premium", "without premium",
            "subscription", "only with", "if enrolled", "if you",
        ))
        candidates.append((float(percentage.group(1)), conditional))
    for fee, conditional in candidates:
        if fee == 0 and not conditional:
            return 0.0, False
    return None, any(fee == 0 and conditional for fee, conditional in candidates)


def extract_protection(text):
    best = {"available": False, "days": None, "cap": None, "unlimited": False}
    for found in re.finditer(r"purchase\s+protection", text, re.I):
        # Product documents commonly put the duration and cap immediately after
        # the heading, but include preceding text as well for inline descriptions.
        excerpt = text[max(0, found.start() - 120):found.start() + 1100]
        days_match = re.search(r"(?:up\s+to\s+)?(\d+)\s+days", excerpt, re.I)
        cap_match = re.search(
            r"(?:maximum\s+(?:coverage\s+)?per\s+claim|maximum\s+per\s+claim|up\s+to)"
            r"\s*(?:is|:)?\s*\$\s*([\d,]+(?:\.\d+)?)",
            excerpt,
            re.I,
        )
        unlimited = bool(re.search(r"(?:coverage|maximum)[^.\n]{0,80}unlimited|unlimited[^.\n]{0,80}coverage", excerpt, re.I))
        candidate = {
            "available": True,
            "days": int(days_match.group(1)) if days_match else None,
            "cap": number(cap_match.group(1)) if cap_match else None,
            "unlimited": unlimited,
        }
        score = sum((candidate["days"] is not None, candidate["cap"] is not None, candidate["unlimited"]))
        best_score = sum((best["days"] is not None, best["cap"] is not None, best["unlimited"]))
        if score > best_score:
            best = candidate
    return best


def extract_reward(text):
    patterns = (
        (r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+eligible\s+purchases", "all eligible purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+purchases", "all purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+on\s+all\s+categories", "all categories", 3),
        (r"cash\s+back\s+on\s+all\s+purchases\s*:\s*(\d+(?:\.\d+)?)\s*%", "all purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+(?:cash\s+)?back[^.\n]{0,100}\btravel\b", "eligible travel purchases", 2),
    )
    for pattern, scope, fit in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1)), scope, fit
    return None, None, 0


def extract_restrictions(text):
    restrictions = []
    if re.search(r"invitation\s*-?\s*only", text, re.I):
        restrictions.append("it is invitation-only")
    score = re.search(r"(?:minimum\s+credit\s+score(?:\s+required)?|credit\s+score)[^\n.]{0,70}?(?:at\s+least\s*)?:?\s*\$?\s*(\d{3})", text, re.I)
    if score:
        restrictions.append("documented credit-score threshold: {}".format(score.group(1)))
    subscription = re.search(r"([A-Za-z0-9+\-‑ ]*?)premium\s+subscription\s+required\s*:\s*yes", text, re.I)
    if subscription:
        label = subscription.group(1).strip()
        restrictions.append("it requires the {}premium subscription".format((label + " ") if label else ""))
    fee = re.search(r"annual\s+fee\s*:\s*\$\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if fee and number(fee.group(1)) > 0:
        restrictions.append("annual fee: {}".format(money(number(fee.group(1)))))
    return restrictions


def normalize_documents(payload):
    documents = payload.get("documents")
    # Accept common wrappers while retaining the declared direct-array interface.
    if not isinstance(documents, list):
        for wrapper_key in ("base", "frozen_base"):
            wrapper = payload.get(wrapper_key)
            if isinstance(wrapper, dict) and isinstance(wrapper.get("documents"), list):
                documents = wrapper["documents"]
                break
    if not isinstance(documents, list):
        raise ValueError("documents must be an array")
    usable = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        title, content = document.get("title"), document.get("content")
        if isinstance(title, str) and title.strip() and isinstance(content, str) and content.strip():
            usable.append(document)
    if not usable:
        raise ValueError("documents must contain at least one document with title and content")
    return usable


def collect_cards(documents):
    grouped = {}
    for document in documents:
        name = card_name(document["title"])
        group = grouped.setdefault(name, {"content": [], "source_ids": []})
        group["content"].append(document["content"])
        identifier = document.get("document_id")
        if isinstance(identifier, str):
            group["source_ids"].append(identifier)

    cards = []
    for name, group in grouped.items():
        corpus = "\n".join(group["content"])
        limit_min, limit_max = extract_limits(corpus)
        foreign_fee, foreign_conditional = extract_foreign_fee(corpus)
        reward_rate, reward_scope, reward_fit = extract_reward(corpus)
        cards.append({
            "name": name,
            "source_ids": group["source_ids"],
            "limit_min": limit_min,
            "limit_max": limit_max,
            "foreign_fee": foreign_fee,
            "foreign_conditional": foreign_conditional,
            "protection": extract_protection(corpus),
            "reward_rate": reward_rate,
            "reward_scope": reward_scope,
            "reward_fit": reward_fit,
            "restrictions": extract_restrictions(corpus),
        })
    return cards


def checks(card, request):
    result = {}
    if request["foreign"]:
        result["documented_unconditional_0_percent_foreign_transaction_fee"] = card["foreign_fee"] == 0
    if request["protection"]:
        result["documented_purchase_protection"] = card["protection"]["available"]
    if request["limit"] is not None:
        result["documented_limit_reaches_requested_amount"] = (
            card["limit_max"] is not None and card["limit_max"] >= request["limit"]
        )
    return result


def protection_phrase(protection):
    phrase = "purchase protection"
    if protection["days"] is not None:
        phrase += " for up to {} days".format(protection["days"])
    if protection["unlimited"]:
        phrase += " with stated unlimited coverage"
    elif protection["cap"] is not None:
        phrase += " up to {} per eligible claim".format(money(protection["cap"]))
    return phrase


def message_for(card, request):
    parts = ["Recommendation: I recommend the {} as the best documented fit.".format(card["name"])]
    if card["reward_rate"] is not None:
        if request["travel"] and request["everyday"] and card["reward_fit"] == 3:
            reason = "That supports both travel spending and lower everyday purchases without relying on travel-category coding"
        elif request["travel"]:
            reason = "That is directly relevant to your travel-heavy spending"
        else:
            reason = "That fits the spending pattern you described"
        parts.append("It earns {:.1f}% cash back on {}. {}.".format(card["reward_rate"], card["reward_scope"], reason))
    if request["foreign"]:
        parts.append("It has a 0% foreign transaction fee.")
    if request["protection"]:
        parts.append("It includes {}, subject to policy terms and exclusions.".format(protection_phrase(card["protection"])))
    if request["limit"] is not None:
        if card["limit_min"] is not None:
            range_text = "{} to {}".format(money(card["limit_min"]), money(card["limit_max"]))
        else:
            range_text = "up to {}".format(money(card["limit_max"]))
        parts.append("Its documented typical credit-limit range is {}, so at least {} is possible; approval and the actual assigned limit remain subject to underwriting.".format(range_text, money(request["limit"])))
    if card["restrictions"]:
        parts.append("Important documented terms: {}.".format("; ".join(card["restrictions"])))
    return " ".join(parts)


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        opening = payload.get("opening")
        if not isinstance(opening, str) or not opening.strip():
            raise ValueError("opening must be a nonempty string")
        documents = normalize_documents(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    request = request_features(opening)
    qualified, rejected = [], []
    for card in collect_cards(documents):
        card_checks = checks(card, request)
        record = {"name": card["name"], "source_ids": card["source_ids"], "checks": card_checks}
        if all(card_checks.values()):
            qualified.append((card, record))
        else:
            record["unmet_or_unknown"] = [key for key, passed in card_checks.items() if not passed]
            rejected.append(record)

    qualified.sort(key=lambda item: (
        -item[0]["reward_fit"],
        -(item[0]["reward_rate"] if item[0]["reward_rate"] is not None else -1),
        item[0]["name"].lower(),
    ))

    if not qualified:
        print(json.dumps({
            "message": "No supplied card is documented to meet every stated hard requirement. Review the documented unmet or unknown requirements before recommending a card.",
            "primary_card": None,
            "requested_limit": request["limit"],
            "qualified_cards": [],
            "rejected_cards": rejected,
            "validation": {"send_ready": False, "issues": ["No documented qualifying card was found."]},
        }, indent=2, sort_keys=True))
        return

    primary, primary_record = qualified[0]
    issues = []
    if primary["reward_rate"] is None:
        issues.append("The selected card has no extracted documented reward rate.")
    if request["limit"] is not None and primary["limit_max"] is None:
        issues.append("The selected card has no extracted documented credit-limit ceiling.")
    print(json.dumps({
        "message": message_for(primary, request),
        "primary_card": primary["name"],
        "primary_source_ids": primary["source_ids"],
        "requested_limit": request["limit"],
        "qualified_cards": [record for _, record in qualified],
        "rejected_cards": rejected,
        "validation": {
            "send_ready": not issues,
            "issues": issues,
            "note": "A documented range establishes possible eligibility, not a promised approval or credit limit.",
        },
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
