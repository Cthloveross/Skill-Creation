#!/usr/bin/env python3
"""Rank disclosed savings/card pairings without performing banking actions.

Reads one JSON object from stdin and emits one JSON object to stdout. Product
terms are always supplied at runtime; this module contains no product catalog.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
ELIGIBILITY = {"eligible", "unknown", "ineligible"}
CONDITION = {"met", "unknown", "unmet"}


def emit(ok, recommendation=None, eligible=None, conditional=None, excluded=None,
         message="", errors=None):
    print(json.dumps({
        "ok": ok,
        "recommendation": recommendation,
        "eligible": eligible or [],
        "conditional": conditional or [],
        "excluded": excluded or [],
        "message": message,
        "errors": errors or [],
    }, default=str, ensure_ascii=False, sort_keys=True))


def parse_decimal(value, label, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{label} must be a decimal number.")
        return None
    if not result.is_finite() or result < ZERO:
        errors.append(f"{label} must be finite and non-negative.")
        return None
    return result


def parse_status(value, choices, label, errors):
    if value not in choices:
        errors.append(f"{label} must be one of: {', '.join(sorted(choices))}.")
        return None
    return value


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def percent(value):
    result = format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), ".4f")
    return result.rstrip("0").rstrip(".")


def nonempty_name(value, label, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a nonempty string.")
        return None
    return value.strip()


def parse_account(raw, index, errors):
    label = f"savings_accounts[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{label} must be an object.")
        return None
    name = nonempty_name(raw.get("name"), f"{label}.name", errors)
    if name is None:
        return None
    limit = raw.get("withdrawal_limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < -1:
        errors.append(f"{name}.withdrawal_limit must be an integer no less than -1.")
    return {
        "name": name,
        "base_apy": parse_decimal(raw.get("base_apy_pct"), f"{name}.base_apy_pct", errors),
        "opening_minimum": parse_decimal(raw.get("opening_minimum"), f"{name}.opening_minimum", errors),
        "ongoing_minimum": parse_decimal(raw.get("ongoing_minimum"), f"{name}.ongoing_minimum", errors),
        "monthly_fee": parse_decimal(raw.get("monthly_fee_if_below_minimum"), f"{name}.monthly_fee_if_below_minimum", errors),
        "other_bonus": parse_decimal(raw.get("other_additive_apy_pct", 0), f"{name}.other_additive_apy_pct", errors),
        "withdrawal_limit": limit,
        "eligibility": parse_status(raw.get("eligibility_status", "unknown"), ELIGIBILITY, f"{name}.eligibility_status", errors),
    }


def parse_card(raw, index, errors):
    label = f"cards[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{label} must be an object.")
        return None
    name = nonempty_name(raw.get("name"), f"{label}.name", errors)
    if name is None:
        return None
    crypto = raw.get("is_crypto_related")
    profile_required = raw.get("same_profile_required", False)
    bonuses = raw.get("bonus_apy_by_savings", {})
    raw_requirements = raw.get("requirements", [])
    if not isinstance(crypto, bool):
        errors.append(f"{name}.is_crypto_related must be boolean.")
    if not isinstance(profile_required, bool):
        errors.append(f"{name}.same_profile_required must be boolean.")
    if not isinstance(bonuses, dict):
        errors.append(f"{name}.bonus_apy_by_savings must be an object.")
        bonuses = {}
    if not isinstance(raw_requirements, list):
        errors.append(f"{name}.requirements must be an array.")
        raw_requirements = []

    requirements = []
    for requirement_index, item in enumerate(raw_requirements):
        item_label = f"{name}.requirements[{requirement_index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_label} must be an object.")
            continue
        requirement_name = nonempty_name(item.get("label"), f"{item_label}.label", errors)
        requirement_status = parse_status(item.get("status"), CONDITION, item_label, errors)
        if requirement_name is not None and requirement_status is not None:
            requirements.append({"label": requirement_name, "status": requirement_status})

    profile_status = "met"
    if profile_required:
        profile_status = parse_status(raw.get("same_profile_status", "unknown"), CONDITION,
                                      f"{name}.same_profile_status", errors)
    return {
        "name": name,
        "annual_fee": parse_decimal(raw.get("annual_fee"), f"{name}.annual_fee", errors),
        "is_crypto_related": crypto,
        "eligibility": parse_status(raw.get("eligibility_status", "unknown"), ELIGIBILITY, f"{name}.eligibility_status", errors),
        "same_profile_required": profile_required,
        "same_profile_status": profile_status,
        "requirements": requirements,
        "bonuses": bonuses,
    }


def build_message(choice, balance, withdrawals):
    if choice["withdrawal_limit"] == -1:
        access = "The account permits unlimited monthly withdrawals"
    else:
        access = f"The account permits {choice['withdrawal_limit']} monthly withdrawals"

    if balance >= choice["ongoing_minimum"]:
        balance_terms = (
            f"The documented opening minimum is ${money(choice['opening_minimum'])}, and the ongoing minimum is "
            f"${money(choice['ongoing_minimum'])}. The assumed ${money(balance)} balance is above the ongoing minimum, "
            f"so the ${money(choice['monthly_fee'])} monthly below-minimum maintenance fee is not estimated while that balance is maintained."
        )
    else:
        balance_terms = (
            f"The documented opening minimum is ${money(choice['opening_minimum'])}, and the ongoing minimum is "
            f"${money(choice['ongoing_minimum'])}. The assumed ${money(balance)} balance is below that threshold, so the "
            f"estimate includes ${money(choice['annual_maintenance'])} in annual maintenance fees based on the documented "
            f"${money(choice['monthly_fee'])} monthly below-minimum fee."
        )

    linkage = ""
    if choice["same_profile_required"]:
        linkage = " The card-linked APY bonus applies only while both products are held under the same customer profile."

    conditions = ""
    if choice["conditions"]:
        conditions = (
            " This recommendation is conditional on " + "; ".join(choice["conditions"]) +
            ". Card approval, eligibility, and any linked APY bonus are not guaranteed."
        )

    return (
        f"My single recommendation is the {choice['savings']} paired with the {choice['card']}. "
        f"The {percent(choice['base_apy'])}% base APY plus the {percent(choice['card_bonus'])}% documented card bonus "
        f"equals {percent(choice['effective_apy'])}% APY. On a stable ${money(balance)} balance for one year, the estimated "
        f"interest is ${money(choice['annual_interest'])}. The card annual fee is ${money(choice['annual_card_fee'])}, and expected "
        f"annual maintenance fees are ${money(choice['annual_maintenance'])}, so the estimated one-year interest-minus-fee result "
        f"is ${money(choice['net'])}, before taxes. {access}, so the expected {withdrawals} monthly withdrawals fit the documented limit. "
        f"{balance_terms}{linkage}{conditions} This estimate assumes the eligible balance remains stable for the year and disclosed "
        "rates and benefits remain in effect; interest is lower if withdrawals reduce the daily balance. No account was opened and no card application was submitted."
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit(False, errors=[f"Invalid JSON input: {exc.msg}"])
        return
    if not isinstance(payload, dict):
        emit(False, errors=["Input must be a JSON object."])
        return

    errors = []
    balance = parse_decimal(payload.get("balance"), "balance", errors)
    withdrawals = payload.get("withdrawals_per_month")
    if not isinstance(withdrawals, int) or isinstance(withdrawals, bool) or withdrawals < 0:
        errors.append("withdrawals_per_month must be a non-negative integer.")
    exclude_crypto = payload.get("exclude_crypto", False)
    if not isinstance(exclude_crypto, bool):
        errors.append("exclude_crypto must be boolean.")

    raw_accounts = payload.get("savings_accounts")
    raw_cards = payload.get("cards")
    if not isinstance(raw_accounts, list) or not raw_accounts:
        errors.append("savings_accounts must be a nonempty array.")
        raw_accounts = []
    if not isinstance(raw_cards, list) or not raw_cards:
        errors.append("cards must be a nonempty array.")
        raw_cards = []

    accounts = [parse_account(item, index, errors) for index, item in enumerate(raw_accounts)]
    cards = [parse_card(item, index, errors) for index, item in enumerate(raw_cards)]
    accounts = [item for item in accounts if item is not None]
    cards = [item for item in cards if item is not None]
    if errors:
        emit(False, errors=errors)
        return

    eligible, conditional, excluded = [], [], []
    for account in accounts:
        for card in cards:
            reasons = []
            if account["eligibility"] == "ineligible":
                reasons.append("Savings-account eligibility is known to be unmet.")
            if card["eligibility"] == "ineligible":
                reasons.append("Card eligibility is known to be unmet.")
            if exclude_crypto and card["is_crypto_related"]:
                reasons.append("Card is excluded because it is crypto-related.")
            if balance < account["opening_minimum"]:
                reasons.append("Balance is below the documented opening minimum.")
            if account["withdrawal_limit"] != -1 and withdrawals > account["withdrawal_limit"]:
                reasons.append("Expected withdrawals exceed the documented monthly limit.")

            unmet = [entry["label"] for entry in card["requirements"] if entry["status"] == "unmet"]
            if card["same_profile_required"] and card["same_profile_status"] == "unmet":
                unmet.append("same-customer-profile linkage")
            if unmet:
                reasons.append("Known unmet card condition(s): " + "; ".join(unmet) + ".")
            if reasons:
                excluded.append({"savings": account["name"], "card": card["name"], "reasons": reasons})
                continue

            bonus = parse_decimal(card["bonuses"].get(account["name"], 0),
                                  f"{card['name']}.bonus_apy_by_savings[{account['name']}]", errors)
            if bonus is None:
                continue
            conditions = [entry["label"] for entry in card["requirements"] if entry["status"] == "unknown"]
            if account["eligibility"] == "unknown":
                conditions.append("savings-account opening eligibility")
            if card["eligibility"] == "unknown":
                conditions.append("card eligibility")
            if card["same_profile_required"] and card["same_profile_status"] == "unknown":
                conditions.append("same-customer-profile linkage for the APY bonus")

            effective_apy = account["base_apy"] + account["other_bonus"] + bonus
            annual_interest = balance * effective_apy / Decimal("100")
            annual_maintenance = account["monthly_fee"] * Decimal("12") if balance < account["ongoing_minimum"] else ZERO
            candidate = {
                "savings": account["name"],
                "card": card["name"],
                "base_apy": account["base_apy"],
                "card_bonus": bonus,
                "effective_apy": effective_apy,
                "annual_interest": annual_interest,
                "annual_card_fee": card["annual_fee"],
                "annual_maintenance": annual_maintenance,
                "net": annual_interest - card["annual_fee"] - annual_maintenance,
                "opening_minimum": account["opening_minimum"],
                "ongoing_minimum": account["ongoing_minimum"],
                "monthly_fee": account["monthly_fee"],
                "withdrawal_limit": account["withdrawal_limit"],
                "same_profile_required": card["same_profile_required"],
                "conditions": conditions,
            }
            (conditional if conditions else eligible).append(candidate)

    if errors:
        emit(False, errors=errors)
        return

    eligible.sort(key=lambda item: item["net"], reverse=True)
    conditional.sort(key=lambda item: item["net"], reverse=True)
    recommendation = eligible[0] if eligible else (conditional[0] if conditional else None)
    message = build_message(recommendation, balance, withdrawals) if recommendation else "No documented pairing meets the supplied constraints."
    emit(True, recommendation=recommendation, eligible=eligible, conditional=conditional,
         excluded=excluded, message=message)


if __name__ == "__main__":
    main()
