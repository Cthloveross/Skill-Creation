#!/usr/bin/env python3
"""Render a complete, non-actionable conditional banking recommendation.

Reads one JSON object from stdin and emits {"message": "..."}. All product facts
must be supplied from current documentation by the caller; this script performs no
product lookup and makes no banking action.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

HUNDRED = Decimal("100")
CENT = Decimal("0.01")


def decimal(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not number.is_finite() or number < 0:
        raise ValueError(f"{field} must be a finite nonnegative number")
    return number


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_money(value):
    return f"${money(value):,.2f}"


def fmt_rate(value):
    text = format(value.normalize(), "f")
    return f"{text}%"


def required_text(payload, field, allow_null=False):
    value = payload.get(field)
    if allow_null and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")
    return value.strip()


def render(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    account = required_text(payload, "savings_account")
    card = required_text(payload, "card")
    deposit = decimal(payload.get("deposit"), "deposit")
    years = decimal(payload.get("term_years"), "term_years")
    if years <= 0:
        raise ValueError("term_years must be positive")
    base = decimal(payload.get("base_apy"), "base_apy")
    card_bonus = decimal(payload.get("card_apy_bonus", 0), "card_apy_bonus")
    other_bonus = decimal(payload.get("other_apy_bonus", 0), "other_apy_bonus")
    annual_fee = decimal(payload.get("annual_card_fee", 0), "annual_card_fee")
    opening_minimum = decimal(payload.get("opening_minimum", 0), "opening_minimum")
    ongoing_minimum = decimal(payload.get("ongoing_minimum", 0), "ongoing_minimum")
    withdrawal_limit = payload.get("monthly_withdrawal_limit")
    planned_withdrawals = payload.get("planned_monthly_withdrawals")
    if not isinstance(withdrawal_limit, int) or withdrawal_limit < 0:
        raise ValueError("monthly_withdrawal_limit must be a nonnegative integer")
    if not isinstance(planned_withdrawals, int) or planned_withdrawals < 0:
        raise ValueError("planned_monthly_withdrawals must be a nonnegative integer")
    pairing = required_text(payload, "checking_pairing_status")
    if pairing not in {"qualifying documented boost", "no documented pairing boost"}:
        raise ValueError("checking_pairing_status is invalid")
    unresolved = payload.get("unresolved_requirements")
    if not isinstance(unresolved, list) or not unresolved or not all(isinstance(x, str) and x.strip() for x in unresolved):
        raise ValueError("unresolved_requirements must be a nonempty array of text")

    effective = base + card_bonus + other_bonus
    interest = money(deposit * effective / HUNDRED * years)
    net = money(interest - annual_fee * years)
    opening_fit = "meets" if deposit >= opening_minimum else "does not meet"
    ongoing_fit = "meets" if deposit >= ongoing_minimum else "does not meet"
    withdrawal_fit = "accommodates" if planned_withdrawals <= withdrawal_limit else "does not accommodate"
    missing = "; ".join(sorted(set(x.strip() for x in unresolved)))

    bonus_terms = [fmt_rate(base)]
    if card_bonus:
        bonus_terms.append(fmt_rate(card_bonus))
    if other_bonus:
        bonus_terms.append(fmt_rate(other_bonus))
    arithmetic = " + ".join(bonus_terms) + " = " + fmt_rate(effective)
    message = (
        f"Assuming the remaining requirements are met, the leading documented combination is {account} with {card}. "
        f"Its documented rate calculation is {arithmetic} APY. On a constant {fmt_money(deposit)} balance for {years} year(s), "
        f"that is approximately {fmt_money(interest)} in APY-based interest. The documented annual card fee is {fmt_money(annual_fee)}, "
        f"so the estimated net value is {fmt_money(net)}. "
        f"The proposed balance {opening_fit} the {fmt_money(opening_minimum)} opening minimum and {ongoing_fit} the {fmt_money(ongoing_minimum)} ongoing minimum. "
        f"The account permits {withdrawal_limit} withdrawals per month, which {withdrawal_fit} the planned {planned_withdrawals} monthly withdrawals. "
        f"For the existing checking account, there is {pairing}. "
        f"This is conditional, not confirmation of eligibility: the following still must be verified: {missing}. "
        "No savings account has been opened, no credit-card application has been submitted, and no funds have been transferred."
    )
    return {"message": message}


def main():
    try:
        print(json.dumps(render(json.load(sys.stdin)), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
