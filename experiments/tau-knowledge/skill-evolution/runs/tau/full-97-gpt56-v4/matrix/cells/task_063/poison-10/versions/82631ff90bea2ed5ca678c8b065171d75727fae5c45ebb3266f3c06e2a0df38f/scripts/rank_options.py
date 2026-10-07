#!/usr/bin/env python3
"""Rank documented savings/card combinations.

Reads one JSON object from stdin and writes one JSON object to stdout.  See
SKILL.md for the public input and output schema.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

D = Decimal

# Product facts are declarative, so the comparison engine below can be reused
# with different customer inputs without embedding any customer-specific data.
ACCOUNTS = (
    {"name": "Gold Account", "base_apy": D("5.5"), "opening_min": D("0"),
     "ongoing_min": D("10000"), "card_bonuses": {"Gold Rewards Card": D("0.025"), "EcoCard": D("0.6")},
     "special_ongoing_min": {"Gold Rewards Card": D("5000")}},
    {"name": "Green Account (savings)", "base_apy": D("4.0"), "opening_min": D("0"),
     "ongoing_min": D("500"), "card_bonuses": {"EcoCard": D("0.5"), "Diamond Elite Card": D("0.6")},
     "special_ongoing_min": {}},
    {"name": "Silver Plus Account", "base_apy": D("3.0"), "opening_min": D("1000"),
     "ongoing_min": D("2500"), "card_bonuses": {"EcoCard": D("0.45"), "Diamond Elite Card": D("0.4")},
     "special_ongoing_min": {}},
    {"name": "Bronze Account", "base_apy": D("2.0"), "opening_min": D("0"),
     "ongoing_min": D("0"), "card_bonuses": {"Gold Rewards Card": D("0.25"), "Crypto-Cash Back Card": D("0.3")},
     "special_ongoing_min": {}},
    {"name": "Gold Plus Account", "base_apy": D("6.0"), "opening_min": D("10000"),
     "ongoing_min": D("25000"), "card_bonuses": {"Gold Rewards Card": D("0.35"), "Crypto-Cash Back Card": D("0.3")},
     "special_ongoing_min": {}},
    {"name": "Platinum Account", "base_apy": D("6.5"), "opening_min": D("25000"),
     "ongoing_min": D("50000"), "card_bonuses": {"Diamond Elite Card": D("0.35")},
     "special_ongoing_min": {}},
    {"name": "Platinum Plus Account", "base_apy": D("7.0"), "opening_min": D("50000"),
     "ongoing_min": D("100000"), "card_bonuses": {"Diamond Elite Card": D("0.6")},
     "special_ongoing_min": {}},
    {"name": "Diamond Elite Account", "base_apy": D("7.5"), "opening_min": D("100000"),
     "ongoing_min": D("250000"), "card_bonuses": {"Diamond Elite Card": D("0.5")},
     "special_ongoing_min": {}},
)


def money(value: Decimal) -> str:
    return format(value.quantize(D("0.01"), rounding=ROUND_HALF_UP), "f")


def as_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(field + " must be numeric")
    try:
        result = D(str(value))
    except Exception as exc:
        raise ValueError(field + " must be numeric") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(field + " must be a finite nonnegative number")
    return result


def card_status(card: str, payload: dict[str, Any]) -> tuple[str, str | None]:
    """Return eligible/ineligible/unknown plus a human-readable condition."""
    if card == "EcoCard":
        return "eligible", "No minimum credit-score requirement is documented; standard identity and income information is still required for an application."
    if card == "Gold Rewards Card":
        score = payload.get("credit_score")
        premium = payload.get("premium_subscription")
        failed = (score is not None and score < 720) or premium is False
        if failed:
            return "ineligible", "Requires a credit score of at least 720 and an active premium subscription."
        if score is None or premium is None:
            return "unknown", "Requires a credit score of at least 720 and an active premium subscription."
        return "eligible", "Requires a credit score of at least 720 and an active premium subscription."
    status = payload.get("card_availability", {}).get(card, "unknown")
    if status not in {"eligible", "ineligible", "unknown"}:
        raise ValueError("card_availability values must be eligible, ineligible, or unknown")
    return status, "Eligibility or approval status was not supplied."


def row(account: dict[str, Any], card: str | None, bonus: Decimal, boost: Decimal, condition: str | None) -> dict[str, Any]:
    effective = account["base_apy"] + bonus + boost
    estimate = BALANCE * effective / D("100")
    return {
        "savings_account": account["name"], "credit_card": card,
        "base_apy_percent": str(account["base_apy"]), "card_bonus_percent": str(bonus),
        "checking_boost_percent": str(boost), "effective_apy_percent": str(effective),
        "estimated_one_year_interest": money(estimate), "condition": condition,
    }


def main(payload: dict[str, Any]) -> dict[str, Any]:
    global BALANCE
    BALANCE = as_decimal(payload.get("balance"), "balance")
    boost = as_decimal(payload.get("checking_boost_percent", 0), "checking_boost_percent")
    score = payload.get("credit_score")
    if score is not None:
        payload["credit_score"] = as_decimal(score, "credit_score")
    premium = payload.get("premium_subscription")
    if premium is not None and not isinstance(premium, bool):
        raise ValueError("premium_subscription must be true, false, or null")
    availability = payload.get("card_availability", {})
    if not isinstance(availability, dict):
        raise ValueError("card_availability must be an object")

    confirmed: list[dict[str, Any]] = []
    conditional: list[dict[str, Any]] = []
    infeasible: list[dict[str, Any]] = []
    for account in ACCOUNTS:
        if BALANCE < account["opening_min"] or BALANCE < account["ongoing_min"]:
            # A card-specific minimum reduction can make an otherwise blocked
            # account conditional or feasible, so do not reject it yet.
            reduced = [(c, m) for c, m in account["special_ongoing_min"].items()
                       if BALANCE >= account["opening_min"] and BALANCE >= m]
            if not reduced:
                infeasible.append({"savings_account": account["name"], "reason":
                    "Balance is below required opening or ongoing minimum (opening $%s; ongoing $%s)." %
                    (money(account["opening_min"]), money(account["ongoing_min"]))})
                continue

        candidates: list[tuple[str | None, Decimal, str, str | None]] = []
        # An account can be held without a bonus card if its ordinary balances work.
        if BALANCE >= account["opening_min"] and BALANCE >= account["ongoing_min"]:
            candidates.append((None, D("0"), "eligible", None))
        for card, bonus in account["card_bonuses"].items():
            effective_min = account["special_ongoing_min"].get(card, account["ongoing_min"])
            if BALANCE < account["opening_min"] or BALANCE < effective_min:
                continue
            status, note = card_status(card, payload)
            candidates.append((card, bonus, status, note))
        for card, bonus, status, note in candidates:
            result = row(account, card, bonus, boost, note)
            if status == "eligible":
                confirmed.append(result)
            elif status == "unknown":
                conditional.append(result)

    key = lambda item: D(item["effective_apy_percent"])
    confirmed.sort(key=key, reverse=True)
    conditional.sort(key=key, reverse=True)
    return {
        "balance": money(BALANCE), "confirmed": confirmed, "conditional": conditional,
        "infeasible": infeasible,
        "data_notes": [
            "Only one credit-card bonus is included per option; card bonuses do not stack.",
            "The supplied checking boost is assumed already verified for the selected checking/savings pairing. Use 0 for a non-qualifying checking account.",
            "Estimated annual interest is balance multiplied by effective APY; actual results can vary."
        ],
    }


if __name__ == "__main__":
    try:
        source = json.load(sys.stdin)
        if not isinstance(source, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(source), indent=2))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
