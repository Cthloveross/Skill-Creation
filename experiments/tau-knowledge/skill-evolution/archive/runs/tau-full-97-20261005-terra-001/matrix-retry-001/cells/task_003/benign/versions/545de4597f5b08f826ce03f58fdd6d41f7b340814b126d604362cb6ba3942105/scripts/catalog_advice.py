#!/usr/bin/env python3
"""Produce evidence-grounded card advice from current-task product documents.

Input JSON:
  {"opening": str, "documents": [{"title": str, "content": str, ...}]}

For task-payload compatibility, documents may instead occur in
frozen_base.documents, base.documents, or task.documents. Output JSON contains
customer-ready advice plus auditable requirement checks. This program performs
no retrieval, account access, application, or underwriting action.
"""
import json
import re
import sys


def as_number(text):
    return float(str(text).replace(",", ""))


def dollars(value):
    return "${:,.0f}".format(value)


def product_name(title):
    """The product name is conventionally the portion before a document colon."""
    return title.split(":", 1)[0].strip()


def parse_requested_limit(request):
    values = []
    for match in re.finditer(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", request, re.I):
        amount = as_number(match.group(1))
        if match.group(2) and amount < 1000:
            amount *= 1000
        values.append(amount)
    for match in re.finditer(r"(?<![\d$])\b(\d+(?:\.\d+)?)\s*k\b", request, re.I):
        values.append(float(match.group(1)) * 1000)
    return max(values) if values else None


def requested_features(request):
    text = request.lower()
    return {
        "foreign": any(term in text for term in (
            "foreign transaction", "foreign fee", "international purchase",
            "international spending", "international use", "abroad",
        )),
        "protection": "purchase protection" in text,
        "limit": parse_requested_limit(request),
        "travel": "travel" in text,
        "everyday": any(term in text for term in (
            "everyday", "daily", "general purchases", "all purchases",
        )),
    }


def document_array(payload):
    documents = payload.get("documents")
    if isinstance(documents, list):
        return documents
    for key in ("frozen_base", "base", "task"):
        wrapper = payload.get(key)
        if isinstance(wrapper, dict) and isinstance(wrapper.get("documents"), list):
            return wrapper["documents"]
    raise ValueError("documents must be a nonempty array, directly or in a supported task wrapper")


def normalize_documents(payload):
    result = []
    for document in document_array(payload):
        if not isinstance(document, dict):
            continue
        title = document.get("title")
        content = document.get("content")
        if isinstance(title, str) and title.strip() and isinstance(content, str) and content.strip():
            result.append(document)
    if not result:
        raise ValueError("documents contains no usable title/content records")
    return result


def find_limit_range(text):
    """Return the highest documented card-limit range, avoiding benefit caps."""
    pattern = re.compile(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:to|through|–|—|-)\s*\$?\s*([\d,]+(?:\.\d+)?)",
        re.I,
    )
    candidates = []
    for match in pattern.finditer(text):
        context = text[max(0, match.start() - 260):match.end() + 260].lower()
        limit_labels = (
            "credit limit", "credit limits", "credit line", "approved limit",
            "approved limits", "initial limit", "starting credit limit", "limit range",
        )
        if any(label in context for label in limit_labels):
            low, high = as_number(match.group(1)), as_number(match.group(2))
            candidates.append((min(low, high), max(low, high)))
    return max(candidates, key=lambda pair: pair[1]) if candidates else (None, None)


def find_unconditional_foreign_fee(text):
    """Return true only for a documented zero fee not qualified on the same line."""
    conditional_zero = False
    for line in text.splitlines():
        lower = line.lower()
        if "foreign transaction fee" not in lower:
            continue
        rate = re.search(r"(\d+(?:\.\d+)?)\s*%", lower)
        if not rate:
            continue
        is_conditional = any(marker in lower for marker in (
            "with a premium", "without a premium", "with premium", "without premium",
            "subscription", "only with", "if enrolled", "if you",
        ))
        if float(rate.group(1)) == 0:
            if not is_conditional:
                return True, False
            conditional_zero = True
    return False, conditional_zero


def find_protection(text):
    best = {"available": False, "days": None, "cap": None, "unlimited": False}
    for occurrence in re.finditer(r"purchase\s+protection", text, re.I):
        excerpt = text[max(0, occurrence.start() - 120):occurrence.start() + 900]
        days = re.search(r"(?:up\s+to\s+)?(\d+)\s+days", excerpt, re.I)
        cap = re.search(
            r"(?:maximum\s+(?:coverage\s+)?per\s+claim|maximum\s+per\s+claim|up\s+to)"
            r"\s*(?:is|:)?\s*\$\s*([\d,]+(?:\.\d+)?)",
            excerpt,
            re.I,
        )
        unlimited = bool(re.search(
            r"(?:coverage|maximum)[^.\n]{0,90}unlimited|unlimited[^.\n]{0,90}coverage",
            excerpt,
            re.I,
        ))
        candidate = {
            "available": True,
            "days": int(days.group(1)) if days else None,
            "cap": as_number(cap.group(1)) if cap else None,
            "unlimited": unlimited,
        }
        score = sum((candidate["days"] is not None, candidate["cap"] is not None, candidate["unlimited"]))
        previous = sum((best["days"] is not None, best["cap"] is not None, best["unlimited"]))
        if score > previous:
            best = candidate
    return best


def find_rewards(text):
    patterns = (
        (r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+eligible\s+purchases", "all eligible purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+purchases", "all purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+on\s+all\s+categories", "all categories", 3),
        (r"cash\s+back\s+on\s+all\s+purchases\s*:\s*(\d+(?:\.\d+)?)\s*%", "all purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+(?:cash\s+)?back[^.\n]{0,100}\btravel\b", "eligible travel purchases", 2),
    )
    for pattern, scope, strength in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1)), scope, strength
    return None, None, 0


def find_restrictions(text):
    restrictions = []
    if re.search(r"invitation\s*-?\s*only", text, re.I):
        restrictions.append("it is invitation-only")
    subscription = re.search(
        r"([A-Za-z0-9+\-‑ ]*?)premium\s+subscription\s+required\s*:\s*yes", text, re.I
    )
    if subscription:
        label = subscription.group(1).strip()
        restrictions.append("it requires the {}premium subscription".format((label + " ") if label else ""))
    score = re.search(
        r"(?:minimum\s+credit\s+score(?:\s+required)?|credit\s+score)[^\n.]{0,80}?"
        r"(?:at\s+least\s*)?:?\s*(\d{3})", text, re.I
    )
    if score:
        restrictions.append("documented credit-score threshold: {}".format(score.group(1)))
    fee = re.search(r"annual\s+fee\s*:\s*\$\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if fee and as_number(fee.group(1)) > 0:
        restrictions.append("annual fee: {}".format(dollars(as_number(fee.group(1)))))
    return restrictions


def cards_from_documents(documents):
    grouped = {}
    for document in documents:
        name = product_name(document["title"])
        record = grouped.setdefault(name, {"content": [], "source_ids": []})
        record["content"].append(document["content"])
        if isinstance(document.get("document_id"), str):
            record["source_ids"].append(document["document_id"])

    cards = []
    for name, group in grouped.items():
        corpus = "\n".join(group["content"])
        low, high = find_limit_range(corpus)
        fee_zero, fee_conditional = find_unconditional_foreign_fee(corpus)
        reward_rate, reward_scope, reward_strength = find_rewards(corpus)
        cards.append({
            "name": name,
            "source_ids": group["source_ids"],
            "limit_min": low,
            "limit_max": high,
            "foreign_fee_zero": fee_zero,
            "foreign_fee_conditional": fee_conditional,
            "protection": find_protection(corpus),
            "reward_rate": reward_rate,
            "reward_scope": reward_scope,
            "reward_strength": reward_strength,
            "restrictions": find_restrictions(corpus),
        })
    return cards


def hard_checks(card, request):
    checks = {}
    if request["foreign"]:
        checks["unconditional_0_percent_foreign_transaction_fee"] = card["foreign_fee_zero"]
    if request["protection"]:
        checks["purchase_protection"] = card["protection"]["available"]
    if request["limit"] is not None:
        checks["limit_reaches_requested_amount"] = (
            card["limit_max"] is not None and card["limit_max"] >= request["limit"]
        )
    return checks


def protection_text(protection):
    result = "purchase protection"
    if protection["days"] is not None:
        result += " for up to {} days".format(protection["days"])
    if protection["unlimited"]:
        result += " with stated unlimited coverage"
    elif protection["cap"] is not None:
        result += " up to {} per eligible claim".format(dollars(protection["cap"]))
    return result


def customer_message(card, request):
    message = ["Recommendation: I recommend the {} as the best documented fit.".format(card["name"])]
    if card["reward_rate"] is not None:
        if request["travel"] and request["everyday"] and card["reward_strength"] == 3:
            rationale = "This rewards both travel and lower everyday spending without relying on travel-category coding"
        elif request["travel"]:
            rationale = "This is relevant to your travel-heavy spending"
        elif request["everyday"]:
            rationale = "This fits everyday purchases"
        else:
            rationale = "This fits the spending pattern you described"
        message.append("It earns {:.1f}% cash back on {}. {}.".format(
            card["reward_rate"], card["reward_scope"], rationale
        ))
    if request["foreign"]:
        message.append("It has a 0% foreign transaction fee.")
    if request["protection"]:
        message.append("It includes {}, subject to policy terms and exclusions.".format(
            protection_text(card["protection"])
        ))
    if request["limit"] is not None:
        if card["limit_min"] is None:
            range_text = "up to {}".format(dollars(card["limit_max"]))
        else:
            range_text = "{} to {}".format(dollars(card["limit_min"]), dollars(card["limit_max"]))
        message.append(
            "Its documented typical credit-limit range is {}, so at least {} is possible; approval and the actual assigned limit remain subject to underwriting.".format(
                range_text, dollars(request["limit"])
            )
        )
    if card["restrictions"]:
        message.append("Important documented terms: {}.".format("; ".join(card["restrictions"])))
    return " ".join(message)


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

    request = requested_features(opening)
    qualified = []
    rejected = []
    for card in cards_from_documents(documents):
        checks = hard_checks(card, request)
        record = {"name": card["name"], "source_ids": card["source_ids"], "checks": checks}
        if all(checks.values()):
            qualified.append((card, record))
        else:
            record["unmet_or_unknown"] = [key for key, passed in checks.items() if not passed]
            rejected.append(record)

    # Prefer broad rewards relevant to the stated pattern, then the documented rate.
    qualified.sort(key=lambda item: (
        -item[0]["reward_strength"],
        -(item[0]["reward_rate"] if item[0]["reward_rate"] is not None else -1),
        item[0]["name"].lower(),
    ))

    if not qualified:
        print(json.dumps({
            "message": None,
            "primary_card": None,
            "requested_limit": request["limit"],
            "qualified_cards": [],
            "rejected_cards": rejected,
            "validation": {
                "send_ready": False,
                "issues": ["No card passed every extracted hard-requirement check."],
            },
        }, indent=2, sort_keys=True))
        return

    primary, primary_record = qualified[0]
    issues = []
    if primary["reward_rate"] is None:
        issues.append("Selected card lacks an extracted reward rate for a spending-fit explanation.")
    if request["limit"] is not None and primary["limit_max"] is None:
        issues.append("Selected card lacks an extracted credit-limit ceiling.")
    print(json.dumps({
        "message": customer_message(primary, request),
        "primary_card": primary["name"],
        "primary_source_ids": primary["source_ids"],
        "requested_limit": request["limit"],
        "qualified_cards": [record for _, record in qualified],
        "rejected_cards": rejected,
        "validation": {
            "send_ready": not issues,
            "issues": issues,
            "note": "A documented range establishes possible eligibility, not a guaranteed approval or assigned limit.",
        },
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
