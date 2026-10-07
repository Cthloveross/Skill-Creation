#!/usr/bin/env python3
"""Rank disclosed savings/card combinations without taking banking actions.

Reads one JSON object from stdin using the schema in SKILL.md and writes one JSON
object to stdout. Product facts are supplied at runtime; this program does not
read customer systems, apply for products, or open accounts.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
ELIGIBILITY = {"eligible", "unknown", "ineligible"}
CONDITION = {"met", "unknown", "unmet"}


def emit(**data):
    data.setdefault("ok", False)
    data.setdefault("errors", [])
    data.setdefault("eligible", [])
    data.setdefault("conditional", [])
    data.setdefault("excluded", [])
    data.setdefault("recommendation", None)
    data.setdefault("customer_reply", "")
    print(json.dumps(data, ensure_ascii=False, sort_keys=True, default=str))


def dec(value, label, errors):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{label} must be a decimal number.")
        return None
    if not value.is_finite() or value < ZERO:
        errors.append(f"{label} must be finite and non-negative.")
        return None
    return value


def text(value, label, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a nonempty string.")
        return None
    return value.strip()


def enum(value, choices, label, errors):
    if value not in choices:
        errors.append(f"{label} must be one of: {', '.join(sorted(choices))}.")
        return None
    return value


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def pct(value):
    value = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return format(value, "f").rstrip("0").rstrip(".")


def parse_account(raw, i, errors):
    p = f"savings_accounts[{i}]"
    if not isinstance(raw, dict):
        errors.append(f"{p} must be an object.")
        return None
    limit = raw.get("withdrawal_limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < -1:
        errors.append(f"{p}.withdrawal_limit must be an integer no less than -1.")
    return {
        "name": text(raw.get("name"), f"{p}.name", errors),
        "base": dec(raw.get("base_apy_pct"), f"{p}.base_apy_pct", errors),
        "opening": dec(raw.get("opening_minimum"), f"{p}.opening_minimum", errors),
        "ongoing": dec(raw.get("ongoing_minimum"), f"{p}.ongoing_minimum", errors),
        "monthly_fee": dec(raw.get("monthly_fee_if_below_minimum"), f"{p}.monthly_fee_if_below_minimum", errors),
        "other_bonus": dec(raw.get("other_additive_apy_pct", 0), f"{p}.other_additive_apy_pct", errors),
        "limit": limit,
        "status": enum(raw.get("eligibility_status", "unknown"), ELIGIBILITY, f"{p}.eligibility_status", errors),
    }


def parse_card(raw, i, errors):
    p = f"cards[{i}]"
    if not isinstance(raw, dict):
        errors.append(f"{p} must be an object.")
        return None
    crypto = raw.get("is_crypto_related")
    profile_required = raw.get("same_profile_required", False)
    bonuses = raw.get("bonus_apy_by_savings", {})
    requirements_raw = raw.get("requirements", [])
    if not isinstance(crypto, bool):
        errors.append(f"{p}.is_crypto_related must be boolean.")
    if not isinstance(profile_required, bool):
        errors.append(f"{p}.same_profile_required must be boolean.")
    if not isinstance(bonuses, dict):
        errors.append(f"{p}.bonus_apy_by_savings must be an object.")
        bonuses = {}
    if not isinstance(requirements_raw, list):
        errors.append(f"{p}.requirements must be an array.")
        requirements_raw = []
    requirements = []
    for j, raw_requirement in enumerate(requirements_raw):
        q = f"{p}.requirements[{j}]"
        if not isinstance(raw_requirement, dict):
            errors.append(f"{q} must be an object.")
            continue
        label = text(raw_requirement.get("label"), f"{q}.label", errors)
        state = enum(raw_requirement.get("status"), CONDITION, f"{q}.status", errors)
        if label is not None and state is not None:
            requirements.append({"label": label, "status": state})
    profile_status = "met"
    if profile_required:
        profile_status = enum(raw.get("same_profile_status", "unknown"), CONDITION,
                              f"{p}.same_profile_status", errors)
    return {
        "name": text(raw.get("name"), f"{p}.name", errors),
        "fee": dec(raw.get("annual_fee"), f"{p}.annual_fee", errors),
        "crypto": crypto,
        "status": enum(raw.get("eligibility_status", "unknown"), ELIGIBILITY, f"{p}.eligibility_status", errors),
        "profile_required": profile_required,
        "profile_status": profile_status,
        "requirements": requirements,
        "bonuses": bonuses,
    }


def draft(choice, balance, withdrawals):
    limit_phrase = "unlimited monthly withdrawals" if choice["limit"] == -1 else f"{choice['limit']} monthly withdrawals"
    if balance >= choice["ongoing"]:
        maintenance = (
            f"The ${money(balance)} assumed balance exceeds the ${money(choice['ongoing'])} ongoing minimum, "
            f"so the ${money(choice['monthly_fee'])} below-minimum monthly fee is not expected while that balance is maintained."
        )
    else:
        maintenance = (
            f"The assumed balance is below the ${money(choice['ongoing'])} ongoing minimum, so the estimate includes "
            f"${money(choice['annual_maintenance'])} of annual maintenance fees."
        )
    conditions = ""
    if choice["conditions"]:
        conditions = " This recommendation is conditional on " + "; ".join(choice["conditions"]) + ". Approval and the linked APY bonus are not guaranteed."
    linkage = ""
    if choice["profile_required"]:
        linkage = " The card bonus applies only when both products are under the same customer profile."
    return (
        f"My single recommendation is {choice['savings']} paired with {choice['card']}. "
        f"It has a {pct(choice['base'])}% base APY plus a {pct(choice['card_bonus'])}% documented card bonus, for {pct(choice['apy'])}% APY. "
        f"${money(balance)} × {pct(choice['apy'])}% is approximately ${money(choice['interest'])} over one year. "
        f"The card annual fee is ${money(choice['card_fee'])}, expected annual maintenance fees are ${money(choice['annual_maintenance'])}, "
        f"and estimated one-year interest minus those fees is ${money(choice['net'])}, before taxes. "
        f"The account permits {limit_phrase}, so {withdrawals} expected monthly withdrawals fit the documented limit. "
        f"Its opening minimum is ${money(choice['opening'])}. {maintenance}{linkage}{conditions} "
        "This estimate assumes the balance remains eligible and stable for the year and terms remain in effect; interest will be lower if withdrawals reduce the daily balance. "
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
    balance = dec(payload.get("balance"), "balance", errors)
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

    accounts = [parse_account(item, i, errors) for i, item in enumerate(raw_accounts)]
    cards = [parse_card(item, i, errors) for i, item in enumerate(raw_cards)]
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
                reasons.append("Card is excluded because it is crypto-related.")
            if balance < account["opening"]:
                reasons.append("Balance is below the documented opening minimum.")
            if account["limit"] != -1 and withdrawals > account["limit"]:
                reasons.append("Expected withdrawals exceed the documented monthly limit.")
            unmet = [r["label"] for r in card["requirements"] if r["status"] == "unmet"]
            if card["profile_required"] and card["profile_status"] == "unmet":
                unmet.append("same-customer-profile linkage for the APY bonus")
            if unmet:
                reasons.append("Known unmet card condition(s): " + "; ".join(unmet) + ".")
            if reasons:
                excluded.append({"savings": account["name"], "card": card["name"], "reasons": reasons})
                continue

            bonus = dec(card["bonuses"].get(account["name"], 0),
                        f"bonus_apy_by_savings for {card['name']} and {account['name']}", errors)
            if bonus is None:
                continue
            conditions = [r["label"] for r in card["requirements"] if r["status"] == "unknown"]
            if account["status"] == "unknown":
                conditions.append("savings-account opening eligibility")
            if card["status"] == "unknown":
                conditions.append("card eligibility and underwriting approval")
            if card["profile_required"] and card["profile_status"] == "unknown":
                conditions.append("same-customer-profile linkage for the APY bonus")
            apy = account["base"] + account["other_bonus"] + bonus
            interest = balance * apy / Decimal("100")
            annual_maintenance = account["monthly_fee"] * 12 if balance < account["ongoing"] else ZERO
            candidate = {
                "savings": account["name"], "card": card["name"], "base": account["base"],
                "card_bonus": bonus, "apy": apy, "interest": interest, "card_fee": card["fee"],
                "annual_maintenance": annual_maintenance, "net": interest - card["fee"] - annual_maintenance,
                "opening": account["opening"], "ongoing": account["ongoing"], "monthly_fee": account["monthly_fee"],
                "limit": account["limit"], "profile_required": card["profile_required"], "conditions": conditions,
            }
            (conditional if conditions else eligible).append(candidate)

    if errors:
        emit(errors=errors)
        return
    eligible.sort(key=lambda item: item["net"], reverse=True)
    conditional.sort(key=lambda item: item["net"], reverse=True)
    recommendation = eligible[0] if eligible else (conditional[0] if conditional else None)
    reply = draft(recommendation, balance, withdrawals) if recommendation else "No documented pairing meets the supplied constraints."
    emit(ok=True, eligible=eligible, conditional=conditional, excluded=excluded,
         recommendation=recommendation, customer_reply=reply)


if __name__ == "__main__":
    main()
