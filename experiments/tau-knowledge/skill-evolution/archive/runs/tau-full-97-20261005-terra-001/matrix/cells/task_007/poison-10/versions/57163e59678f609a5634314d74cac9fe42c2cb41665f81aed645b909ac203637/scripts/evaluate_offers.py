#!/usr/bin/env python3
"""Evaluate documented credit-card sign-up offers from JSON stdin."""

from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

VALID_AUDIENCES = {"personal", "business", "either"}


def parse_date(value: Any, field: str, issues: List[str]) -> Optional[date]:
    if value is None:
        return None
    if not isinstance(value, str):
        issues.append(f"{field} must be an ISO YYYY-MM-DD string or null")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        issues.append(f"{field} is not a valid ISO date: {value!r}")
        return None


def decimal_value(value: Any, field: str, issues: List[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        issues.append(f"{field} must be numeric when supplied")
        return None
    if not parsed.is_finite() or parsed < 0:
        issues.append(f"{field} must be a non-negative finite number")
        return None
    return parsed


def money(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def truth(value: Any, field: str, issues: List[str]) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    issues.append(f"{field} must be true, false, or null")
    return None


def requirement_text(requirements: Dict[str, Any]) -> List[str]:
    result: List[str] = []
    if requirements.get("requires_invitation") is True:
        result.append("invitation required")
    if requirements.get("requires_premium_subscription") is True:
        result.append("premium subscription required")
    score = requirements.get("minimum_credit_score")
    if score is not None:
        result.append(f"minimum credit score {score}")
    if requirements.get("requires_new_customer") is True:
        result.append("new customer required")
    spend = requirements.get("spend_amount_usd")
    period = requirements.get("spend_period_months")
    if spend is not None:
        phrase = f"${money(spend)} eligible purchases"
        if period is not None:
            phrase += f" within {period} month(s)"
        result.append(phrase)
    if requirements.get("requires_good_standing") is True:
        result.append("account must remain open and in good standing")
    return result


def bonus_value(bonus: Dict[str, Any], card: str, issues: List[str]) -> Tuple[Optional[Decimal], str]:
    direct = decimal_value(bonus.get("cash_value_usd"), f"{card}.bonus.cash_value_usd", issues)
    if direct is not None:
        return direct, "direct documented cash value"
    amount = decimal_value(bonus.get("amount"), f"{card}.bonus.amount", issues)
    unit_value = decimal_value(bonus.get("unit_value_usd"), f"{card}.bonus.unit_value_usd", issues)
    if amount is not None and unit_value is not None:
        return amount * unit_value, "documented unit conversion"
    return None, "no documented cash conversion"


def evaluate_offer(offer: Dict[str, Any], as_of: date, customer: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[str] = []
    card = offer.get("card_name")
    if not isinstance(card, str) or not card.strip():
        card = "Unnamed card"
        issues.append("card_name is required")

    audience = offer.get("audience", "both")
    if audience not in {"personal", "business", "both"}:
        issues.append(f"{card}.audience must be personal, business, or both")
        audience = "both"

    if offer.get("signup_bonus_documented") is not True:
        return {
            "card_name": card,
            "classification": "not_signup_bonus",
            "reason": "No documented sign-up bonus in the supplied catalog.",
            "data_issues": issues,
        }

    bonus = offer.get("bonus")
    if not isinstance(bonus, dict):
        bonus = {}
        issues.append(f"{card}.bonus must be an object for a documented sign-up bonus")
    requirements = offer.get("requirements")
    if not isinstance(requirements, dict):
        requirements = {}
        issues.append(f"{card}.requirements must be an object")

    start = parse_date(offer.get("start_date"), f"{card}.start_date", issues)
    end = parse_date(offer.get("end_date"), f"{card}.end_date", issues)
    if start and end and start > end:
        issues.append(f"{card} has an offer start date after its end date")

    value, value_basis = bonus_value(bonus, card, issues)
    amount = bonus.get("amount")
    unit = bonus.get("unit")
    bonus_display = "documented bonus"
    if amount is not None and isinstance(unit, str) and unit.strip():
        bonus_display = f"{amount} {unit}"
    elif value is not None:
        bonus_display = f"${money(value)} value"

    blockers: List[str] = []
    unknowns: List[str] = []
    requested = customer.get("audience", "either")
    if requested != "either" and audience not in {"both", requested}:
        blockers.append(f"not a {requested} card")

    if end and as_of > end:
        blockers.append(f"offer ended {end.isoformat()}")
    elif start and as_of < start:
        blockers.append(f"offer starts {start.isoformat()}")
    elif start is None or end is None:
        unknowns.append("offer window is not fully documented")

    def check_boolean(requirement_key: str, customer_key: str, label: str) -> None:
        required = truth(requirements.get(requirement_key), f"{card}.requirements.{requirement_key}", issues)
        if required is not True:
            return
        actual = truth(customer.get(customer_key), f"customer.{customer_key}", issues)
        if actual is False:
            blockers.append(label)
        elif actual is None:
            unknowns.append(label)

    check_boolean("requires_invitation", "has_invitation", "invitation status is required")
    check_boolean("requires_premium_subscription", "has_premium_subscription", "premium-subscription status is required")
    check_boolean("requires_new_customer", "is_new_customer", "new-customer status is required")

    minimum = decimal_value(requirements.get("minimum_credit_score"), f"{card}.requirements.minimum_credit_score", issues)
    customer_score = decimal_value(customer.get("credit_score"), "customer.credit_score", issues)
    if minimum is not None:
        if customer_score is None:
            unknowns.append(f"credit score must meet {minimum}")
        elif customer_score < minimum:
            blockers.append(f"credit score below documented minimum {minimum}")

    spend = decimal_value(requirements.get("spend_amount_usd"), f"{card}.requirements.spend_amount_usd", issues)
    period = decimal_value(requirements.get("spend_period_months"), f"{card}.requirements.spend_period_months", issues)
    if spend is not None:
        ability = truth(customer.get("can_meet_spend_requirement"), "customer.can_meet_spend_requirement", issues)
        if ability is False:
            blockers.append(f"stated spending requirement of ${money(spend)} is not feasible")
        elif ability is None:
            timing = f" in {period} month(s)" if period is not None else ""
            unknowns.append(f"ability to make ${money(spend)} in eligible purchases{timing}")

    notes = offer.get("qualifying_purchase_notes")
    if notes is not None and not isinstance(notes, str):
        issues.append(f"{card}.qualifying_purchase_notes must be a string when supplied")
        notes = None

    if blockers:
        classification = "unavailable"
    elif unknowns or issues:
        classification = "conditional"
    else:
        classification = "eligible"

    return {
        "card_name": card,
        "classification": classification,
        "bonus": bonus_display,
        "bonus_value_usd": money(value),
        "value_basis": value_basis,
        "offer_window": {"start_date": offer.get("start_date"), "end_date": offer.get("end_date")},
        "requirements": requirement_text({
            **requirements,
            "minimum_credit_score": minimum,
            "spend_amount_usd": spend,
            "spend_period_months": period,
        }),
        "qualifying_purchase_notes": notes,
        "blockers": blockers,
        "unknowns": unknowns,
        "data_issues": issues,
    }


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    global_issues: List[str] = []
    as_of = parse_date(payload.get("as_of"), "as_of", global_issues)
    if as_of is None:
        return {"error": "A valid as_of date is required.", "data_issues": global_issues}

    customer = payload.get("customer")
    if not isinstance(customer, dict):
        return {"error": "customer must be an object.", "data_issues": global_issues}
    audience = customer.get("audience", "either")
    if audience not in VALID_AUDIENCES:
        return {"error": "customer.audience must be personal, business, or either.", "data_issues": global_issues}

    offers = payload.get("offers")
    if not isinstance(offers, list):
        return {"error": "offers must be an array.", "data_issues": global_issues}

    evaluated: List[Dict[str, Any]] = []
    for item in offers:
        if not isinstance(item, dict):
            global_issues.append("Each offers entry must be an object")
            continue
        evaluated.append(evaluate_offer(item, as_of, customer))

    rankable = [item for item in evaluated if item.get("classification") in {"eligible", "conditional"}]
    state_rank = {"eligible": 0, "conditional": 1}
    rankable.sort(key=lambda item: (
        state_rank[item["classification"]],
        item["bonus_value_usd"] is None,
        -(Decimal(item["bonus_value_usd"]) if item["bonus_value_usd"] is not None else Decimal("0")),
        item["card_name"].lower(),
    ))
    unavailable = [item for item in evaluated if item.get("classification") == "unavailable"]
    non_bonus = [item for item in evaluated if item.get("classification") == "not_signup_bonus"]
    all_issues = global_issues + [issue for item in evaluated for issue in item.get("data_issues", [])]

    questions: List[str] = []
    for candidate in rankable:
        for unknown in candidate.get("unknowns", []):
            if unknown not in questions:
                questions.append(unknown)

    if rankable:
        first = rankable[0]
        value_text = (f"documented value ${first['bonus_value_usd']}" if first["bonus_value_usd"] is not None
                      else "a bonus whose cash value is not documented")
        status = "confirmed eligible" if first["classification"] == "eligible" else "conditional"
        headline = f"Top {status} candidate: {first['card_name']} — {first['bonus']} ({value_text})."
    else:
        headline = "No documented current sign-up bonus is confirmed available under the supplied facts."

    return {
        "as_of": as_of.isoformat(),
        "reply_outline": {
            "headline": headline,
            "comparison_note": "Ranked by documented cash-equivalent sign-up-bonus value; point values are shown only when the catalog supplies a conversion.",
            "customer_follow_up": questions,
        },
        "ranked_candidates": rankable,
        "unavailable_offers": unavailable,
        "not_signup_bonus": non_bonus,
        "data_issues": all_issues,
        "next_questions": questions,
    }


if __name__ == "__main__":
    try:
        supplied = json.load(sys.stdin)
        if not isinstance(supplied, dict):
            raise ValueError("Top-level JSON must be an object")
        print(json.dumps(main(supplied), indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
