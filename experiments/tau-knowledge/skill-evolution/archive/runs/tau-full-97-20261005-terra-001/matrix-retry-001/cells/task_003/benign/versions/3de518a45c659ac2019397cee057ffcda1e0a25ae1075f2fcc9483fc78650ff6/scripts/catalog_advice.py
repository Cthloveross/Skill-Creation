#!/usr/bin/env python3
"""Create card advice from product documents supplied at runtime.

Input JSON:
  {"opening": str, "documents": [{"document_id": str, "title": str, "content": str}]}

Output JSON contains a ready-to-send message, evidence checks, and validation.
This program is deterministic and performs no retrieval, account access, application,
or underwriting action.
"""
import json
import re
import sys


def as_number(value):
    return float(value.replace(",", ""))


def dollars(value):
    return "${:,.0f}".format(value)


def card_name(title):
    return title.split(":", 1)[0].strip()


def requested_limit(text):
    values = []
    for match in re.finditer(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", text, re.I):
        value = as_number(match.group(1))
        if match.group(2) and value < 1000:
            value *= 1000
        values.append(value)
    for match in re.finditer(r"(?<!\$)\b(\d+(?:\.\d+)?)\s*k\b", text, re.I):
        values.append(float(match.group(1)) * 1000)
    return max(values) if values else None


def detect_request(opening):
    text = opening.lower()
    return {
        "foreign": any(term in text for term in (
            "foreign transaction", "foreign fee", "international purchase", "international spending",
        )),
        "protection": "purchase protection" in text,
        "limit": requested_limit(opening),
        "travel": "travel" in text,
        "everyday": any(term in text for term in ("everyday", "daily", "general purchases")),
    }


def extract_limit(text):
    ranges = []
    pattern = re.compile(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:to|–|—|-)\s*\$\s*([\d,]+(?:\.\d+)?)", re.I
    )
    for match in pattern.finditer(text):
        nearby = text[max(0, match.start() - 220):match.end() + 220].lower()
        if any(label in nearby for label in (
            "credit limit", "credit limits", "credit line", "approved limit", "starting limit", "initial limit",
        )):
            low, high = as_number(match.group(1)), as_number(match.group(2))
            ranges.append((min(low, high), max(low, high)))
    return max(ranges, key=lambda pair: pair[1]) if ranges else (None, None)


def extract_foreign_fee(text):
    """Only an unconditional documented 0% rate passes a no-fee requirement."""
    entries = []
    for line in text.splitlines():
        lower = line.lower()
        if "foreign transaction fee" not in lower:
            continue
        percent = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
        if not percent:
            continue
        conditional = any(term in lower for term in (
            " with a ", " without a ", "subscription", "only with", "if you", "if enrolled",
        ))
        entries.append((float(percent.group(1)), conditional, line.strip()))
    for fee, conditional, source in entries:
        if fee == 0 and not conditional:
            return fee, False, source
    return None, False, None


def extract_reward(text):
    patterns = [
        (r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+eligible\s+purchases", "all eligible purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+on\s+all\s+categories", "all categories", 3),
        (r"cash\s+back\s+on\s+all\s+purchases\s*:\s*(\d+(?:\.\d+)?)\s*%", "all purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+purchases", "all purchases", 3),
        (r"(\d+(?:\.\d+)?)\s*%\s+(?:cash\s+)?back[^.\n]{0,80}\btravel\b", "eligible travel purchases", 2),
    ]
    for pattern, scope, fit in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1)), scope, fit
    return None, None, 0


def extract_protection(text):
    best = {"available": False, "days": None, "cap": None, "unlimited": False}
    for match in re.finditer(r"purchase\s+protection", text, re.I):
        excerpt = text[match.start():match.start() + 800]
        days = re.search(r"(?:up\s+to\s+)?(\d+)\s+days", excerpt, re.I)
        cap = re.search(
            r"(?:maximum\s+(?:coverage\s+)?per\s+claim|maximum\s+per\s+claim|up\s+to)"
            r"\s*(?:is|:)?\s*\$\s*([\d,]+(?:\.\d+)?)", excerpt, re.I,
        )
        unlimited = bool(re.search(
            r"(?:coverage\s+maximum|coverage)[^.\n]{0,90}unlimited|unlimited[^.\n]{0,90}coverage",
            excerpt, re.I,
        ))
        candidate = {
            "available": True,
            "days": int(days.group(1)) if days else None,
            "cap": as_number(cap.group(1)) if cap else None,
            "unlimited": unlimited,
        }
        quality = sum((candidate["days"] is not None, candidate["cap"] is not None, unlimited))
        old_quality = sum((best["days"] is not None, best["cap"] is not None, best["unlimited"]))
        if quality > old_quality:
            best = candidate
    return best


def extract_restrictions(text):
    restrictions = []
    if re.search(r"invitation\s*-?\s*only", text, re.I):
        restrictions.append("it is invitation-only")
    score = re.search(r"credit\s+score[^.\n]{0,60}?at\s+least\s*\$?\s*(\d{3})", text, re.I)
    if not score:
        score = re.search(r"minimum\s+credit\s+score\s*(?:required)?\s*:\s*\$?\s*(\d{3})", text, re.I)
    if score:
        restrictions.append("documented credit-score threshold: {}".format(score.group(1)))
    subscription = re.search(r"([A-Za-z0-9+\-‑ ]+)premium\s+subscription\s+required\s*:\s*yes", text, re.I)
    if subscription:
        label = subscription.group(1).strip()
        restrictions.append("it requires the {}premium subscription".format(label + " " if label else ""))
    elif re.search(r"premium\s+subscription\s+required\s*:\s*yes", text, re.I):
        restrictions.append("it requires a premium subscription")
    fee = re.search(r"annual\s+fee\s*:\s*\$\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if fee and as_number(fee.group(1)) > 0:
        restrictions.append("annual fee: {}".format(dollars(as_number(fee.group(1)))))
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
        group = grouped.setdefault(name, {"content": [], "source_ids": []})
        group["content"].append(content)
        if isinstance(document.get("document_id"), str):
            group["source_ids"].append(document["document_id"])

    cards = []
    for name, group in grouped.items():
        corpus = "\n".join(group["content"])
        low, high = extract_limit(corpus)
        fee, conditional, fee_source = extract_foreign_fee(corpus)
        rate, scope, reward_fit = extract_reward(corpus)
        cards.append({
            "name": name,
            "source_ids": group["source_ids"],
            "limit_min": low,
            "limit_max": high,
            "foreign_fee": fee,
            "foreign_conditional": conditional,
            "foreign_source": fee_source,
            "protection": extract_protection(corpus),
            "reward_rate": rate,
            "reward_scope": scope,
            "reward_fit": reward_fit,
            "restrictions": extract_restrictions(corpus),
        })
    return cards


def checks_for(card, request):
    checks = {}
    if request["foreign"]:
        checks["documented_unconditional_0_percent_foreign_transaction_fee"] = card["foreign_fee"] == 0
    if request["protection"]:
        checks["documented_purchase_protection"] = card["protection"]["available"]
    if request["limit"] is not None:
        checks["documented_limit_reaches_requested_amount"] = (
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


def render_message(card, request, alternatives):
    sentences = ["Recommendation: I recommend the {} as the best documented fit.".format(card["name"])]
    if card["reward_rate"] is not None:
        if request["travel"] and request["everyday"] and card["reward_fit"] == 3:
            rationale = "This rewards travel spending and your lower everyday purchases without depending on travel-category coding"
        elif request["travel"]:
            rationale = "This is relevant to your travel spending"
        else:
            rationale = "This fits your stated spending pattern"
        sentences.append("It earns {:.1f}% cash back on {}. {}.".format(
            card["reward_rate"], card["reward_scope"], rationale
        ))
    if request["foreign"]:
        sentences.append("It has a 0% foreign transaction fee.")
    if request["protection"]:
        sentences.append("It includes {}, subject to policy terms and exclusions.".format(protection_text(card["protection"])))
    if request["limit"] is not None:
        sentences.append(
            "Its documented typical credit-limit range is {} to {}, so at least {} is possible; "
            "approval and the actual assigned limit remain subject to underwriting.".format(
                dollars(card["limit_min"]), dollars(card["limit_max"]), dollars(request["limit"])
            )
        )
    if card["restrictions"]:
        sentences.append("Important documented terms: {}.".format("; ".join(card["restrictions"])))
    if alternatives:
        rendered = []
        for other in alternatives:
            caveat = "; ".join(other["restrictions"]) if other["restrictions"] else "review its documented terms"
            rendered.append("{} is another qualifying option, but {}.".format(other["name"], caveat))
        sentences.append("Alternatives: " + " ".join(rendered))
    return " ".join(sentences)


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

    request = detect_request(opening)
    qualified, rejected = [], []
    for card in collect_cards(documents):
        checks = checks_for(card, request)
        record = {"name": card["name"], "source_ids": card["source_ids"], "checks": checks}
        if all(checks.values()):
            qualified.append((card, record))
        else:
            record["unmet_or_unknown"] = [name for name, passed in checks.items() if not passed]
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
    if request["limit"] is not None and primary["limit_min"] is None:
        issues.append("The selected card has no extracted documented lower limit bound.")
    message = render_message(primary, request, [card for card, _ in qualified[1:]])
    print(json.dumps({
        "message": message,
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
