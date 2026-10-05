#!/usr/bin/env python3
"""Validate and render evidence-backed credit-card advice.

Input is a JSON object on stdin containing customer requirements and card facts
extracted from the current task's supplied documents. Output is a JSON object on
stdout. The program neither retrieves facts nor makes credit decisions.
"""
import json
import sys


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def money(value):
    return "${:,.0f}".format(float(value))


def rate(value):
    return "{:g}%".format(float(value))


def text_list(value):
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def protection(card):
    item = card.get("purchase_protection")
    return item if isinstance(item, dict) else {}


def protection_text(card):
    item = protection(card)
    if item.get("available") is not True:
        return None
    parts = ["purchase protection"]
    if is_number(item.get("days")):
        parts.append("for up to {:g} days".format(float(item["days"])))
    if item.get("unlimited") is True:
        parts.append("with documented unlimited coverage")
    elif is_number(item.get("max_per_claim")):
        parts.append("up to {} per eligible claim".format(money(item["max_per_claim"])))
    return " ".join(parts)


def hard_checks(card, requested_limit):
    checks = []
    fee = card.get("foreign_transaction_fee_pct")
    checks.append({
        "requirement": "0% foreign transaction fee",
        "documented_value": fee,
        "pass": is_number(fee) and float(fee) == 0.0,
    })

    pp = protection(card)
    checks.append({
        "requirement": "purchase protection",
        "documented_value": {
            "available": pp.get("available"),
            "days": pp.get("days"),
            "max_per_claim": pp.get("max_per_claim"),
            "unlimited": pp.get("unlimited") is True,
        },
        "pass": pp.get("available") is True,
    })

    ceiling = card.get("limit_max")
    checks.append({
        "requirement": "possible requested credit limit",
        "documented_value": ceiling,
        "pass": is_number(ceiling) and float(ceiling) >= float(requested_limit),
    })
    return checks


def score(card, customer):
    """Prefer broad documented rewards for combined everyday and travel use."""
    flat = float(card["flat_cash_back_pct"]) if is_number(card.get("flat_cash_back_pct")) else 0.0
    travel = float(card["travel_cash_back_pct"]) if is_number(card.get("travel_cash_back_pct")) else 0.0
    score_value = flat * (4.0 if customer.get("everyday_spend") is True else 1.0)
    if customer.get("travel_primary") is True:
        score_value += travel * 2.0
    # Conditions do not disqualify a documented match, but make an unrestricted
    # otherwise comparable product a more practical primary recommendation.
    score_value -= 0.1 * len(text_list(card.get("eligibility_notes")))
    return score_value


def reward_sentence(card, customer):
    flat = card.get("flat_cash_back_pct")
    travel = card.get("travel_cash_back_pct")
    scope = str(card.get("reward_scope") or "eligible purchases").strip()
    clauses = []
    if is_number(flat):
        clauses.append("{} cash back on {}".format(rate(flat), scope))
    if customer.get("travel_primary") is True and is_number(travel):
        clauses.append("{} back on eligible travel purchases".format(rate(travel)))
    if not clauses:
        return "No documented rewards rate was supplied for this card."
    earning = " and ".join(clauses)
    if customer.get("everyday_spend") is True and is_number(flat):
        return "It earns {}, which fits everyday purchases while also rewarding travel-heavy spending.".format(earning)
    if customer.get("travel_primary") is True:
        return "It earns {}, which fits travel-led spending.".format(earning)
    return "It earns {}.".format(earning)


def limit_sentence(card, requested_limit):
    lower = card.get("limit_min")
    upper = card.get("limit_max")
    if is_number(lower) and is_number(upper):
        description = "a documented credit-limit range of {}–{}".format(money(lower), money(upper))
    else:
        description = "a documented credit-limit ceiling of {}".format(money(upper))
    return (
        "It has {}; a limit of at least {} is possible, but the exact approved "
        "limit is subject to underwriting and approval."
    ).format(description, money(requested_limit))


def render_primary(card, customer):
    message = [
        "I recommend the {} as the best documented match for your requirements.".format(card["name"]),
        reward_sentence(card, customer),
        "It has a 0% foreign transaction fee.",
        "It includes {}, subject to applicable policy terms and exclusions.".format(protection_text(card)),
        limit_sentence(card, customer["requested_limit"]),
    ]
    if is_number(card.get("annual_fee")):
        message.append("Its documented annual fee is {}.".format(money(card["annual_fee"])))
    notes = text_list(card.get("eligibility_notes"))
    if notes:
        message.append("Documented eligibility note: {}.".format("; ".join(notes)))
    return "\n\n".join(message)


def render_alternative(card, requested_limit):
    rewards = reward_sentence(card, {"travel_primary": True, "everyday_spend": True})
    notes = text_list(card.get("eligibility_notes"))
    restriction = " Important eligibility note: {}.".format("; ".join(notes)) if notes else ""
    return (
        "{}: {} It has a 0% foreign transaction fee, {}, and {}.{}"
    ).format(card["name"], rewards, protection_text(card), limit_sentence(card, requested_limit), restriction)


def validate_payload(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    customer = data.get("customer")
    cards = data.get("cards")
    if not isinstance(customer, dict) or not isinstance(cards, list):
        raise ValueError("customer must be an object and cards must be an array")
    if not is_number(customer.get("requested_limit")) or float(customer["requested_limit"]) < 0:
        raise ValueError("customer.requested_limit must be a nonnegative number")
    for key in ("travel_primary", "everyday_spend"):
        if key in customer and not isinstance(customer[key], bool):
            raise ValueError("customer.{} must be boolean when supplied".format(key))
    return customer, cards


def main():
    try:
        data = json.load(sys.stdin)
        customer, raw_cards = validate_payload(data)
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    qualified = []
    rejected = []
    warnings = []
    for index, card in enumerate(raw_cards):
        if not isinstance(card, dict) or not isinstance(card.get("name"), str) or not card["name"].strip():
            warnings.append("cards[{}] was skipped because it has no nonempty name.".format(index))
            continue
        item = dict(card)
        item["name"] = item["name"].strip()
        sources = text_list(item.get("source_ids"))
        checks = hard_checks(item, customer["requested_limit"])
        # Facts without a current-task source cannot support customer-facing advice.
        if not sources:
            checks.append({"requirement": "current-task evidence source", "documented_value": [], "pass": False})
        record = {"name": item["name"], "checks": checks, "source_ids": sources}
        if all(check["pass"] for check in checks):
            record["score"] = score(item, customer)
            qualified.append((item, record))
        else:
            record["unmet_or_unknown"] = [check["requirement"] for check in checks if not check["pass"]]
            rejected.append(record)

    qualified.sort(key=lambda pair: (-pair[1]["score"], pair[0]["name"].lower()))
    if not qualified:
        print(json.dumps({
            "message": "No supplied card record is documented to meet every stated hard requirement. Review the per-card unmet or unknown requirements before making a recommendation.",
            "primary_card": None,
            "qualified_cards": [],
            "rejected_cards": rejected,
            "warnings": warnings,
        }, indent=2, sort_keys=True))
        return

    primary, primary_record = qualified[0]
    alternative_records = [record for _, record in qualified[1:]]
    message = render_primary(primary, customer)
    if len(qualified) > 1:
        alternatives = [render_alternative(card, customer["requested_limit"]) for card, _ in qualified[1:]]
        message += "\n\nOther documented qualifying options:\n" + "\n".join("- " + item for item in alternatives)

    print(json.dumps({
        "message": message,
        "primary_card": primary["name"],
        "primary_source_ids": text_list(primary.get("source_ids")),
        "qualified_cards": [primary_record] + alternative_records,
        "rejected_cards": rejected,
        "warnings": warnings,
        "validation_note": "A sufficient documented limit ceiling establishes possibility only; approval and the exact limit remain subject to underwriting.",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
