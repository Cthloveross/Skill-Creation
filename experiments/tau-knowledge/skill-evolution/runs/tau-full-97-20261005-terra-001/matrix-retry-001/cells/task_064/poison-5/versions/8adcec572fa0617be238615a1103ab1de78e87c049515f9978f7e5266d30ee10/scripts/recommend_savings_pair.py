#!/usr/bin/env python3
"""Rank disclosed savings/card pairs without accessing customer systems or taking actions.

Read one JSON object from stdin using the schema in SKILL.md. Write one JSON
object to stdout. All product facts must be supplied at runtime.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
ELIGIBILITY = {"eligible", "unknown", "ineligible"}
CONDITIONS = {"met", "unknown", "unmet"}


def emit(ok=False, errors=None, eligible=None, conditional=None, excluded=None,
         recommendation=None, customer_reply=""):
    print(json.dumps({
        "ok": ok,
        "errors": errors or [],
        "eligible": eligible or [],
        "conditional": conditional or [],
        "excluded": excluded or [],
        "recommendation": recommendation,
        "customer_reply": customer_reply,
    }, ensure_ascii=False, default=str, sort_keys=True))


def decimal(value, label, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{label} must be a decimal number.")
        return None
    if not result.is_finite() or result < ZERO:
        errors.append(f"{label} must be finite and non-negative.")
        return None
    return result


def string(value, label, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a nonempty string.")
        return None
    return value.strip()


def state(value, allowed, label, errors):
    if value not in allowed:
        errors.append(f"{label} must be one of: {', '.join(sorted(allowed))}.")
        return None
    return value


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def percent(value):
    result = format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def parse_account(raw, index, errors):
    path = f"savings_accounts[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{path} must be an object.")
        return None
    limit = raw.get("withdrawal_limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < -1:
        errors.append(f"{path}.withdrawal_limit must be an integer no less than -1.")
    return {
        "name": string(raw.get("name"), f"{path}.name", errors),
        "base": decimal(raw.get("base_apy_pct"), f"{path}.base_apy_pct", errors),
        "opening": decimal(raw.get("opening_minimum"), f"{path}.opening_minimum", errors),
        "ongoing": decimal(raw.get("ongoing_minimum"), f"{path}.ongoing_minimum", errors),
        "monthly_fee": decimal(raw.get("monthly_fee_if_below_minimum"), f"{path}.monthly_fee_if_below_minimum", errors),
        "other_bonus": decimal(raw.get("other_additive_apy_pct", 0), f"{path}.other_additive_apy_pct", errors),
        "limit": limit,
        "status": state(raw.get("eligibility_status", "unknown"), ELIGIBILITY,
                        f"{path}.eligibility_status", errors),
    }


def parse_card(raw, index, errors):
    path = f"cards[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{path} must be an object.")
        return None
    crypto = raw.get("is_crypto_related")
    linked = raw.get("same_profile_required", False)
    bonuses = raw.get("bonus_apy_by_savings", {})
    raw_requirements = raw.get("requirements", [])
    if not isinstance(crypto, bool):
        errors.append(f"{path}.is_crypto_related must be boolean.")
    if not isinstance(linked, bool):
        errors.append(f"{path}.same_profile_required must be boolean.")
    if not isinstance(bonuses, dict):
        errors.append(f"{path}.bonus_apy_by_savings must be an object.")
        bonuses = {}
    if not isinstance(raw_requirements, list):
        errors.append(f"{path}.requirements must be an array.")
        raw_requirements = []
    requirements = []
    for requirement_index, requirement in enumerate(raw_requirements):
        requirement_path = f"{path}.requirements[{requirement_index}]"
        if not isinstance(requirement, dict):
            errors.append(f"{requirement_path} must be an object.")
            continue
        label = string(requirement.get("label"), f"{requirement_path}.label", errors)
        requirement_state = state(requirement.get("status"), CONDITIONS,
                                  f"{requirement_path}.status", errors)
        if label is not None and requirement_state is not None:
            requirements.append({"label": label, "status": requirement_state})
    profile_state = "met"
    if linked:
        profile_state = state(raw.get("same_profile_status", "unknown"), CONDITIONS,
                              f"{path}.same_profile_status", errors)
    return {
        "name": string(raw.get("name"), f"{path}.name", errors),
        "fee": decimal(raw.get("annual_fee"), f"{path}.annual_fee", errors),
        "crypto": crypto,
        "status": state(raw.get("eligibility_status", "unknown"), ELIGIBILITY,
                        f"{path}.eligibility_status", errors),
        "linked": linked,
        "profile_state": profile_state,
        "requirements": requirements,
        "bonuses": bonuses,
    }


def customer_draft(choice, balance, withdrawals):
    withdrawal_text = "unlimited monthly withdrawals" if choice["limit"] == -1 else f"{choice['limit']} monthly withdrawals"
    if balance >= choice["ongoing"]:
        maintenance = (
            f"The assumed ${money(balance)} balance is above the ${money(choice['ongoing'])} ongoing minimum, "
            f"so the ${money(choice['monthly_fee'])} below-minimum monthly fee is not expected while that balance is maintained."
        )
    else:
        maintenance = (
            f"The assumed balance is below the ${money(choice['ongoing'])} ongoing minimum, so the estimate includes "
            f"${money(choice['annual_maintenance'])} in expected annual maintenance fees."
        )
    linkage = ""
    if choice["linked"]:
        linkage = " The card-linked bonus applies only when both products are held under the same customer profile."
    conditions = ""
    if choice["conditions"]:
        conditions = (
            " This is a conditional recommendation: " + "; ".join(choice["conditions"]) +
            ". Card approval and the linked APY bonus are not guaranteed."
        )
    return (
        f"My single recommendation is {choice['savings']} paired with {choice['card']}. "
        f"The account has a {percent(choice['base'])}% base APY and this card contributes a {percent(choice['card_bonus'])}% applicable APY bonus, "
        f"for {percent(choice['apy'])}% APY. ${money(balance)} × {percent(choice['apy'])}% equals approximately "
        f"${money(choice['interest'])} over one year. The card annual fee is ${money(choice['card_fee'])}; expected annual maintenance fees are "
        f"${money(choice['annual_maintenance'])}; estimated one-year interest minus those fees is ${money(choice['net'])}, before taxes. "
        f"The account permits {withdrawal_text}, so the planned {withdrawals} monthly withdrawals fit the documented limit. "
        f"Its opening minimum is ${money(choice['opening'])}. {maintenance}{linkage}{conditions} "
        "This illustration assumes the balance remains eligible and stable for the year and terms remain in effect; interest will be lower if withdrawals reduce the daily balance. "
        "This is informational only; no account was opened and no card application was submitted."
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit(errors=[f"Invalid JSON input: {exc.msg}"])
        return
    if not isinstance(payload, dict):
        emit(errors=["Input must be a JSON object."])
        return

    errors = []
    balance = decimal(payload.get("balance"), "balance", errors)
    withdrawals = payload.get("withdrawals_per_month")
    exclude_crypto = payload.get("exclude_crypto", False)
    if not isinstance(withdrawals, int) or isinstance(withdrawals, bool) or withdrawals < 0:
        errors.append("withdrawals_per_month must be a non-negative integer.")
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
        emit(errors=errors)
        return

    eligible, conditional, excluded = [], [], []
    for account in accounts:
        for card in cards:
            reasons = []
            if account["status"] == "ineligible":
                reasons.append("Savings-account eligibility is known to be unmet.")
            if card["status"] == "ineligible":
                reasons.append("Card eligibility is known to be unmet.")
            if exclude_crypto and card["crypto"]:
                reasons.append("The customer excludes crypto-related cards.")
            if balance < account["opening"]:
                reasons.append("The assumed balance is below the documented opening minimum.")
            if account["limit"] != -1 and withdrawals > account["limit"]:
                reasons.append("Planned withdrawals exceed the documented monthly limit.")
            unmet = [item["label"] for item in card["requirements"] if item["status"] == "unmet"]
            if card["linked"] and card["profile_state"] == "unmet":
                unmet.append("same-customer-profile linkage for the APY bonus")
            if unmet:
                reasons.append("Known unmet condition(s): " + "; ".join(unmet) + ".")
            if reasons:
                excluded.append({"savings": account["name"], "card": card["name"], "reasons": reasons})
                continue

            card_bonus = decimal(card["bonuses"].get(account["name"], 0),
                                 f"bonus_apy_by_savings for {card['name']} and {account['name']}", errors)
            if card_bonus is None:
                continue
            conditions = [item["label"] for item in card["requirements"] if item["status"] == "unknown"]
            if account["status"] == "unknown":
                conditions.append("savings-account opening eligibility")
            if card["status"] == "unknown":
                conditions.append("card eligibility and underwriting approval")
            if card["linked"] and card["profile_state"] == "unknown":
                conditions.append("same-customer-profile linkage for the APY bonus")
            apy = account["base"] + account["other_bonus"] + card_bonus
            interest = balance * apy / Decimal("100")
            annual_maintenance = account["monthly_fee"] * 12 if balance < account["ongoing"] else ZERO
            candidate = {
                "savings": account["name"], "card": card["name"],
                "base": account["base"], "card_bonus": card_bonus, "apy": apy,
                "interest": interest, "card_fee": card["fee"],
                "annual_maintenance": annual_maintenance,
                "net": interest - card["fee"] - annual_maintenance,
                "opening": account["opening"], "ongoing": account["ongoing"],
                "monthly_fee": account["monthly_fee"], "limit": account["limit"],
                "linked": card["linked"], "conditions": conditions,
            }
            (conditional if conditions else eligible).append(candidate)

    if errors:
        emit(errors=errors)
        return
    eligible.sort(key=lambda item: item["net"], reverse=True)
    conditional.sort(key=lambda item: item["net"], reverse=True)
    recommendation = eligible[0] if eligible else (conditional[0] if conditional else None)
    reply = customer_draft(recommendation, balance, withdrawals) if recommendation else "No disclosed pairing meets the supplied constraints."
    emit(ok=True, eligible=eligible, conditional=conditional, excluded=excluded,
         recommendation=recommendation, customer_reply=reply)


if __name__ == "__main__":
    main()
