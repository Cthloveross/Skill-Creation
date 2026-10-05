#!/usr/bin/env python3
"""Rank disclosed savings/card pairings without performing banking actions.

Reads one JSON object from stdin and emits one JSON object to stdout. Product
terms are supplied at runtime; this module contains no product catalog.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
PAIR_STATUSES = {"eligible", "unknown", "ineligible"}
CONDITION_STATUSES = {"met", "unknown", "unmet"}


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


def decimal(value, label, errors):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{label} must be a decimal number.")
        return None
    if not number.is_finite() or number < ZERO:
        errors.append(f"{label} must be finite and non-negative.")
        return None
    return number


def status(value, permitted, label, errors):
    if value not in permitted:
        errors.append(f"{label} must be one of: {', '.join(sorted(permitted))}.")
        return None
    return value


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def percent(value):
    text = format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), ".4f")
    return text.rstrip("0").rstrip(".")


def parse_account(raw, index, errors):
    label = f"savings_accounts[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{label} must be an object.")
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{label}.name must be a nonempty string.")
        return None
    name = name.strip()
    limit = raw.get("withdrawal_limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < -1:
        errors.append(f"{name}.withdrawal_limit must be an integer no less than -1.")
    return {
        "name": name,
        "base_apy": decimal(raw.get("base_apy_pct"), f"{name}.base_apy_pct", errors),
        "opening_minimum": decimal(raw.get("opening_minimum"), f"{name}.opening_minimum", errors),
        "ongoing_minimum": decimal(raw.get("ongoing_minimum"), f"{name}.ongoing_minimum", errors),
        "monthly_fee": decimal(raw.get("monthly_fee_if_below_minimum"),
                               f"{name}.monthly_fee_if_below_minimum", errors),
        "other_bonus": decimal(raw.get("other_additive_apy_pct", 0),
                               f"{name}.other_additive_apy_pct", errors),
        "withdrawal_limit": limit,
        "eligibility": status(raw.get("eligibility_status", "unknown"), PAIR_STATUSES,
                              f"{name}.eligibility_status", errors),
    }


def parse_card(raw, index, errors):
    label = f"cards[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{label} must be an object.")
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{label}.name must be a nonempty string.")
        return None
    name = name.strip()
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
        requirement_label = f"{name}.requirements[{requirement_index}]"
        if not isinstance(item, dict):
            errors.append(f"{requirement_label} must be an object.")
            continue
        item_label = item.get("label")
        if not isinstance(item_label, str) or not item_label.strip():
            errors.append(f"{requirement_label}.label must be a nonempty string.")
            continue
        item_status = status(item.get("status"), CONDITION_STATUSES,
                             requirement_label, errors)
        if item_status is not None:
            requirements.append({"label": item_label.strip(), "status": item_status})

    profile_status = "met"
    if profile_required:
        profile_status = status(raw.get("same_profile_status", "unknown"),
                                CONDITION_STATUSES,
                                f"{name}.same_profile_status", errors)
    return {
        "name": name,
        "annual_fee": decimal(raw.get("annual_fee"), f"{name}.annual_fee", errors),
        "is_crypto_related": crypto,
        "eligibility": status(raw.get("eligibility_status", "unknown"), PAIR_STATUSES,
                              f"{name}.eligibility_status", errors),
        "same_profile_required": profile_required,
        "same_profile_status": profile_status,
        "requirements": requirements,
        "bonuses": bonuses,
    }


def build_message(choice, balance, withdrawals):
    if choice["withdrawal_limit"] == -1:
        access = "The account has unlimited monthly withdrawals"
    else:
        access = f"The account permits {choice['withdrawal_limit']} monthly withdrawals"

    if balance >= choice["ongoing_minimum"]:
        maintenance = (
            f"The assumed ${money(balance)} balance exceeds the ${money(choice['ongoing_minimum'])} "
            "ongoing minimum, so no below-minimum maintenance fee is estimated while that balance is maintained."
        )
    else:
        maintenance = (
            f"The assumed ${money(balance)} balance is below the ${money(choice['ongoing_minimum'])} "
            f"ongoing minimum, so the estimate includes ${money(choice['annual_maintenance'])} in annual maintenance fees."
        )

    conditions = ""
    if choice["conditions"]:
        conditions = (
            " This is conditional on " + "; ".join(choice["conditions"]) +
            ". Card approval, eligibility, and any card-linked APY bonus are not guaranteed."
        )
    linkage = ""
    if choice["same_profile_required"]:
        linkage = " The card-linked bonus applies only while both products are held under the same customer profile."

    return (
        f"My single recommendation is the {choice['savings']} paired with the {choice['card']}. "
        f"The {percent(choice['base_apy'])}% base APY plus the {percent(choice['card_bonus'])}% card bonus "
        f"equals {percent(choice['effective_apy'])}% APY. On a stable ${money(balance)} balance for one year, "
        f"that is approximately ${money(choice['annual_interest'])} in interest. The card annual fee is "
        f"${money(choice['annual_card_fee'])}, and expected maintenance fees are "
        f"${money(choice['annual_maintenance'])}, so the estimated one-year interest-minus-fee result is "
        f"approximately ${money(choice['net'])}, before taxes. {access}, so the expected "
        f"{withdrawals} monthly withdrawals fit the documented limit. {maintenance}{linkage}{conditions} "
        "This estimate assumes the eligible balance remains stable for the year and disclosed rates and benefits remain in effect; "
        "interest will be lower if withdrawals reduce the daily balance. No account was opened and no card application was submitted."
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
    balance = decimal(payload.get("balance"), "balance", errors)
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

    eligible = []
    conditional = []
    excluded = []

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

            unmet = [item["label"] for item in card["requirements"] if item["status"] == "unmet"]
            if card["same_profile_required"] and card["same_profile_status"] == "unmet":
                unmet.append("same-customer-profile linkage")
            if unmet:
                reasons.append("Known unmet card condition(s): " + "; ".join(unmet) + ".")
            if reasons:
                excluded.append({"savings": account["name"], "card": card["name"], "reasons": reasons})
                continue

            bonus = decimal(card["bonuses"].get(account["name"], 0),
                            f"{card['name']}.bonus_apy_by_savings[{account['name']}]", errors)
            if bonus is None:
                continue
            conditions = [item["label"] for item in card["requirements"] if item["status"] == "unknown"]
            if account["eligibility"] == "unknown":
                conditions.append("savings-account opening eligibility")
            if card["eligibility"] == "unknown":
                conditions.append("card eligibility")
            if card["same_profile_required"] and card["same_profile_status"] == "unknown":
                conditions.append("same-customer-profile linkage for the APY bonus")

            effective_apy = account["base_apy"] + account["other_bonus"] + bonus
            annual_interest = balance * effective_apy / Decimal("100")
            annual_maintenance = (
                account["monthly_fee"] * Decimal("12")
                if balance < account["ongoing_minimum"] else ZERO
            )
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
                "ongoing_minimum": account["ongoing_minimum"],
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
    message = (
        build_message(recommendation, balance, withdrawals)
        if recommendation else "No documented pairing meets the supplied constraints."
    )
    emit(True, recommendation=recommendation, eligible=eligible, conditional=conditional,
         excluded=excluded, message=message)


if __name__ == "__main__":
    main()
