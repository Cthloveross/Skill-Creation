#!/usr/bin/env python3
"""Generate evidence-grounded card advice from current-task product documents.

Input (JSON object on stdin):
  {"opening": str, "documents": [{"document_id": str, "title": str, "content": str}]}

Output (JSON object on stdout) includes a customer-facing message, qualification
checks, and validation. The program performs no retrieval, banking action,
application, or underwriting decision.
"""
import json
import re
import sys


def money(value):
    return "${:,.0f}".format(value)


def numeric(value):
    return float(value.replace(",", ""))


def name_from_title(title):
    return title.split(":", 1)[0].strip()


def requested_limit(text):
    """Extract the largest dollar request, including a compact k suffix."""
    amounts = []
    for match in re.finditer(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", text, re.I):
        amount = numeric(match.group(1))
        if match.group(2) and amount < 1000:
            amount *= 1000
        amounts.append(amount)
    for match in re.finditer(r"(?<!\$)\b(\d+(?:\.\d+)?)\s*k\b", text, re.I):
        amounts.append(float(match.group(1)) * 1000)
    return max(amounts) if amounts else None


def needs(opening):
    low = opening.lower()
    return {
        "foreign": "foreign transaction" in low or "international" in low or "foreign fee" in low,
        "protection": "purchase protection" in low or "protection" in low,
        "limit": requested_limit(opening),
        "travel": "travel" in low,
        "everyday": "everyday" in low or "daily" in low,
    }


def extract_limits(text):
    values = []
    pattern = re.compile(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:to|–|—|-)\s*\$\s*([\d,]+(?:\.\d+)?)",
        re.I,
    )
    for match in pattern.finditer(text):
        context = text[max(0, match.start() - 200):match.end() + 200].lower()
        if any(term in context for term in ("credit limit", "credit line", "approved limit", "starting limit")):
            first, second = numeric(match.group(1)), numeric(match.group(2))
            values.append((min(first, second), max(first, second)))
    return max(values, key=lambda item: item[1]) if values else (None, None)


def extract_foreign_fee(text):
    """Return documented fee and whether its statement is conditional."""
    candidates = []
    for line in text.splitlines():
        low = line.lower()
        if "foreign transaction fee" not in low:
            continue
        match = re.search(r"foreign\s+transaction\s+fee[^\n]{0,100}?(\d+(?:\.\d+)?)\s*%", line, re.I)
        if not match:
            continue
        conditional = any(token in low for token in (
            "with a premium", "without a premium", "with premium", "without premium",
            "subscription", "only with", "if you",
        ))
        candidates.append((float(match.group(1)), conditional, line.strip()))
    unconditional_zero = [item for item in candidates if item[0] == 0 and not item[1]]
    if unconditional_zero:
        return unconditional_zero[0]
    zero = [item for item in candidates if item[0] == 0]
    return zero[0] if zero else (None, False, None)


def extract_reward(text):
    patterns = (
        (r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+eligible\s+purchases", "all eligible purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+(?:back|cash\s+back)\s+on\s+all\s+categories", "all categories", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+purchases", "all purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+(?:cash\s+)?back[^.\n]{0,70}?\btravel\b", "eligible travel purchases", 2),
    )
    for pattern, scope, fit_rank in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1)), scope, fit_rank
    return None, None, 0


def extract_protection(text):
    best = None
    for match in re.finditer(r"purchase\s+protection", text, re.I):
        window = text[match.start():match.start() + 900]
        day_match = re.search(r"(?:up\s+to\s+)?(\d+)\s+days", window, re.I)
        cap_match = re.search(
            r"(?:maximum\s+(?:coverage\s+)?per\s+claim|maximum\s+per\s+claim|up\s+to)\s*"
            r"(?:is|:)?\s*\$\s*([\d,]+(?:\.\d+)?)",
            window, re.I,
        )
        unlimited = bool(re.search(
            r"(?:coverage\s+maximum|coverage)[^.\n]{0,80}unlimited|"
            r"unlimited[^.\n]{0,80}coverage", window, re.I,
        ))
        item = {
            "available": True,
            "days": int(day_match.group(1)) if day_match else None,
            "cap": numeric(cap_match.group(1)) if cap_match else None,
            "unlimited": unlimited,
        }
        detail = int(item["days"] is not None) + int(item["cap"] is not None) + int(unlimited)
        if best is None or detail > best[0]:
            best = (detail, item)
    return best[1] if best else {"available": False, "days": None, "cap": None, "unlimited": False}


def extract_restrictions(text):
    restrictions = []
    if re.search(r"invitation\s*-?\s*only", text, re.I):
        restrictions.append("it is invitation-only")
    score = re.search(r"(?:credit\s+score|score)[^\n.]{0,55}?at\s+least\s*\$?\s*(\d{3})", text, re.I)
    if not score:
        score = re.search(r"minimum\s+credit\s+score\s+(?:required)?\s*:\s*\$?\s*(\d{3})", text, re.I)
    if score:
        restrictions.append("the documented credit-score threshold is {}".format(score.group(1)))
    subscription = re.search(r"([^\s:]+)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes", text, re.I)
    if subscription:
        restrictions.append("it requires a {} subscription".format(subscription.group(1)))
    elif re.search(r"premium\s+subscription\s+required\s*:\s*yes", text, re.I):
        restrictions.append("it requires a premium subscription")
    fee = re.search(r"annual\s+fee\s*:\s*\$\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if fee and numeric(fee.group(1)) > 0:
        restrictions.append("annual fee: {}".format(money(numeric(fee.group(1)))))
    return restrictions


def collect_cards(documents):
    groups = {}
    for document in documents:
        if not isinstance(document, dict):
            continue
        title, content = document.get("title"), document.get("content")
        if not isinstance(title, str) or not title.strip() or not isinstance(content, str):
            continue
        name = name_from_title(title)
        group = groups.setdefault(name, {"contents": [], "source_ids": []})
        group["contents"].append(content)
        doc_id = document.get("document_id")
        if isinstance(doc_id, str) and doc_id:
            group["source_ids"].append(doc_id)

    cards = []
    for name, group in groups.items():
        corpus = "\n".join(group["contents"])
        low, high = extract_limits(corpus)
        foreign_fee, foreign_conditional, foreign_line = extract_foreign_fee(corpus)
        reward_rate, reward_scope, reward_fit = extract_reward(corpus)
        cards.append({
            "name": name,
            "source_ids": group["source_ids"],
            "limit_min": low,
            "limit_max": high,
            "foreign_fee": foreign_fee,
            "foreign_conditional": foreign_conditional,
            "foreign_line": foreign_line,
            "protection": extract_protection(corpus),
            "reward_rate": reward_rate,
            "reward_scope": reward_scope,
            "reward_fit": reward_fit,
            "restrictions": extract_restrictions(corpus),
        })
    return cards


def qualification(card, request):
    checks = {}
    if request["foreign"]:
        checks["documented_0_percent_foreign_transaction_fee"] = card["foreign_fee"] == 0
    if request["protection"]:
        checks["documented_purchase_protection"] = card["protection"]["available"]
    if request["limit"] is not None:
        checks["documented_limit_reaches_requested_amount"] = (
            card["limit_max"] is not None and card["limit_max"] >= request["limit"]
        )
    return checks


def protection_phrase(protection):
    phrase = "purchase protection"
    if protection["days"] is not None:
        phrase += " for up to {} days".format(protection["days"])
    if protection["unlimited"]:
        phrase += " with documented unlimited coverage"
    elif protection["cap"] is not None:
        phrase += " up to {} per eligible claim".format(money(protection["cap"]))
    return phrase


def message_for(card, request):
    parts = ["Recommendation: I recommend the {} as the best documented fit.".format(card["name"])]
    if card["reward_rate"] is not None:
        if request["travel"] and request["everyday"] and card["reward_fit"] >= 3:
            fit = "which rewards travel-heavy spending as well as lower everyday purchases"
        elif request["travel"]:
            fit = "which is relevant to travel spending"
        else:
            fit = "which is relevant to your stated spending"
        parts.append("It earns {:.1f}% cash back on {}, {}.".format(card["reward_rate"], card["reward_scope"], fit))
    if request["foreign"]:
        suffix = ""
        if card["foreign_conditional"]:
            suffix = " under the documented condition"
        parts.append("It has a 0% foreign transaction fee{}.".format(suffix))
    if request["protection"]:
        parts.append("It includes {}, subject to applicable policy terms and exclusions.".format(protection_phrase(card["protection"])))
    if request["limit"] is not None:
        parts.append(
            "Its documented credit-limit range is {} to {}, so a limit of at least {} is possible; "
            "the actual approved limit remains subject to underwriting and approval.".format(
                money(card["limit_min"]), money(card["limit_max"]), money(request["limit"])
            )
        )
    if card["restrictions"]:
        parts.append("Important terms: {}.".format("; ".join(card["restrictions"])))
    return " ".join(parts)


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
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    request = needs(opening)
    qualified, rejected = [], []
    for card in collect_cards(documents):
        checks = qualification(card, request)
        record = {"name": card["name"], "source_ids": card["source_ids"], "checks": checks}
        if all(checks.values()):
            qualified.append((card, record))
        else:
            record["unmet_or_unknown"] = [key for key, passed in checks.items() if not passed]
            rejected.append(record)

    # Flat all-purchase rewards are preferred for mixed everyday/travel spending;
    # a documented rate then serves as a stable secondary ranking criterion.
    qualified.sort(key=lambda pair: (
        -pair[0]["reward_fit"],
        -(pair[0]["reward_rate"] if pair[0]["reward_rate"] is not None else -1),
        pair[0]["name"].lower(),
    ))

    if not qualified:
        print(json.dumps({
            "message": "No supplied card is documented to meet every stated hard requirement. Review the per-card unmet or unknown requirements before recommending a card.",
            "primary_card": None,
            "requested_limit": request["limit"],
            "qualified_cards": [],
            "rejected_cards": rejected,
            "validation": {"send_ready": False, "issues": ["No documented qualifying card was found."]},
        }, indent=2, sort_keys=True))
        return

    primary, primary_record = qualified[0]
    message = message_for(primary, request)
    if len(qualified) > 1:
        alternatives = []
        for card, _record in qualified[1:]:
            caveat = "; ".join(card["restrictions"]) if card["restrictions"] else "review its documented terms"
            alternatives.append("{} is another qualifying option, but {}.".format(card["name"], caveat))
        message += " Alternatives: " + " ".join(alternatives)

    issues = []
    if primary["reward_rate"] is None:
        issues.append("No documented rewards rate was found for the primary card.")
    print(json.dumps({
        "message": message,
        "primary_card": primary["name"],
        "primary_source_ids": primary["source_ids"],
        "requested_limit": request["limit"],
        "qualified_cards": [record for _card, record in qualified],
        "rejected_cards": rejected,
        "validation": {
            "send_ready": not issues,
            "issues": issues,
            "note": "A sufficient documented limit establishes possibility only; approval and assigned limit remain underwriting decisions.",
        },
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
