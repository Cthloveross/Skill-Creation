#!/usr/bin/env python3
"""Validate and rank disclosed savings/card pairings without banking actions.

Input: one JSON object on stdin matching the schema in SKILL.md.
Output: one JSON object with ok, recommendation, eligible, conditional,
excluded, customer_reply, and errors. All product facts are runtime input.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
ELIGIBILITY = {"eligible", "unknown", "ineligible"}
CONDITION = {"met", "unknown", "unmet"}


def output(**value):
    value.setdefault("ok", False)
    value.setdefault("recommendation", None)
    value.setdefault("eligible", [])
    value.setdefault("conditional", [])
    value.setdefault("excluded", [])
    value.setdefault("customer_reply", "")
    value.setdefault("errors", [])
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


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


def name(value, label, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a nonempty string.")
        return None
    return value.strip()


def status(value, options, label, errors):
    if value not in options:
        errors.append(f"{label} must be one of: {', '.join(sorted(options))}.")
        return None
    return value


def fmt_money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def fmt_pct(value):
    text = format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), ".4f")
    return text.rstrip("0").rstrip(".")


def parse_account(raw, index, errors):
    prefix = f"savings_accounts[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{prefix} must be an object.")
        return None
    account_name = name(raw.get("name"), f"{prefix}.name", errors)
    limit = raw.get("withdrawal_limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < -1:
        errors.append(f"{prefix}.withdrawal_limit must be an integer no less than -1.")
    return {
        "name": account_name,
        "base_apy": decimal(raw.get("base_apy_pct"), f"{prefix}.base_apy_pct", errors),
        "opening_minimum": decimal(raw.get("opening_minimum"), f"{prefix}.opening_minimum", errors),
        "ongoing_minimum": decimal(raw.get("ongoing_minimum"), f"{prefix}.ongoing_minimum", errors),
        "monthly_fee": decimal(raw.get("monthly_fee_if_below_minimum"), f"{prefix}.monthly_fee_if_below_minimum", errors),
        "other_bonus": decimal(raw.get("other_additive_apy_pct", 0), f"{prefix}.other_additive_apy_pct", errors),
        "withdrawal_limit": limit,
        "eligibility": status(raw.get("eligibility_status", "unknown"), ELIGIBILITY, f"{prefix}.eligibility_status", errors),
    }


def parse_card(raw, index, errors):
    prefix = f"cards[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{prefix} must be an object.")
        return None
    card_name = name(raw.get("name"), f"{prefix}.name", errors)
    crypto = raw.get("is_crypto_related")
    profile_required = raw.get("same_profile_required", False)
    bonuses = raw.get("bonus_apy_by_savings", {})
    requirements_raw = raw.get("requirements", [])
    if not isinstance(crypto, bool):
        errors.append(f"{prefix}.is_crypto_related must be boolean.")
    if not isinstance(profile_required, bool):
        errors.append(f"{prefix}.same_profile_required must be boolean.")
    if not isinstance(bonuses, dict):
        errors.append(f"{prefix}.bonus_apy_by_savings must be an object.")
        bonuses = {}
    if not isinstance(requirements_raw, list):
        errors.append(f"{prefix}.requirements must be an array.")
        requirements_raw = []

    requirements = []
    for item_index, item in enumerate(requirements_raw):
        item_prefix = f"{prefix}.requirements[{item_index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_prefix} must be an object.")
            continue
        label = name(item.get("label"), f"{item_prefix}.label", errors)
        item_status = status(item.get("status"), CONDITION, f"{item_prefix}.status", errors)
        if label is not None and item_status is not None:
            requirements.append({"label": label, "status": item_status})

    profile_status = "met"
    if profile_required:
        profile_status = status(raw.get("same_profile_status", "unknown"), CONDITION,
                                f"{prefix}.same_profile_status", errors)
    return {
        "name": card_name,
        "annual_fee": decimal(raw.get("annual_fee"), f"{prefix}.annual_fee", errors),
        "is_crypto_related": crypto,
        "eligibility": status(raw.get("eligibility_status", "unknown"), ELIGIBILITY,
                              f"{prefix}.eligibility_status", errors),
        "same_profile_required": profile_required,
        "same_profile_status": profile_status,
        "requirements": requirements,
        "bonuses": bonuses,
    }


def render(choice, balance, withdrawals):
    if choice["withdrawal_limit"] == -1:
        withdrawal_text = "The account permits unlimited monthly withdrawals"
    else:
        withdrawal_text = f"The account permits {choice['withdrawal_limit']} monthly withdrawals"

    if balance >= choice["ongoing_minimum"]:
        balance_text = (
            f"Its opening minimum is ${fmt_money(choice['opening_minimum'])}; its ongoing minimum is "
            f"${fmt_money(choice['ongoing_minimum'])}. The assumed ${fmt_money(balance)} balance is above that threshold, "
            f"so the ${fmt_money(choice['monthly_fee'])} monthly below-minimum maintenance fee is not included while the balance is maintained."
        )
    else:
        balance_text = (
            f"Its opening minimum is ${fmt_money(choice['opening_minimum'])}; its ongoing minimum is "
            f"${fmt_money(choice['ongoing_minimum'])}. Because the assumed ${fmt_money(balance)} balance is below that threshold, "
            f"the estimate includes ${fmt_money(choice['annual_maintenance'])} in annual maintenance fees."
        )

    profile_text = ""
    if choice["same_profile_required"]:
        profile_text = " The card-linked bonus applies only while both products are held under the same customer profile."

    condition_text = ""
    if choice["conditions"]:
        condition_text = (
            " The recommendation is conditional on " + "; ".join(choice["conditions"]) +
            ". Card approval, eligibility, and the linked APY bonus are not guaranteed."
        )

    return (
        f"My single recommendation is {choice['savings']} paired with {choice['card']}. "
        f"The {fmt_pct(choice['base_apy'])}% base APY plus the {fmt_pct(choice['card_bonus'])}% documented card bonus equals "
        f"{fmt_pct(choice['effective_apy'])}% APY. On a stable ${fmt_money(balance)} balance for one year, estimated interest is "
        f"${fmt_money(choice['annual_interest'])}. The card annual fee is ${fmt_money(choice['annual_card_fee'])}, and expected annual "
        f"maintenance fees are ${fmt_money(choice['annual_maintenance'])}, for an estimated one-year interest-minus-fee result of "
        f"${fmt_money(choice['net'])}, before taxes. {withdrawal_text}, so the expected {withdrawals} monthly withdrawals fit the documented limit. "
        f"{balance_text}{profile_text}{condition_text} This estimate assumes the eligible balance remains stable for the year and terms "
        "remain in effect; interest will be lower if withdrawals reduce the daily balance. No savings account was opened and no card application was submitted."
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        output(errors=[f"Invalid JSON input: {exc.msg}"])
        return
    if not isinstance(payload, dict):
        output(errors=["Input must be a JSON object."])
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
        output(errors=errors)
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
                unmet.append("same-customer-profile linkage for the APY bonus")
            if unmet:
                reasons.append("Known unmet card condition(s): " + "; ".join(unmet) + ".")
            if reasons:
                excluded.append({"savings": account["name"], "card": card["name"], "reasons": reasons})
                continue

            bonus = decimal(card["bonuses"].get(account["name"], 0),
                            f"bonus_apy_by_savings for {card['name']} and {account['name']}", errors)
            if bonus is None:
                continue
            conditions = [entry["label"] for entry in card["requirements"] if entry["status"] == "unknown"]
            if account["eligibility"] == "unknown":
                conditions.append("savings-account opening eligibility")
            if card["eligibility"] == "unknown":
                conditions.append("card eligibility and underwriting approval")
            if card["same_profile_required"] and card["same_profile_status"] == "unknown":
                conditions.append("same-customer-profile linkage for the APY bonus")

            effective_apy = account["base_apy"] + account["other_bonus"] + bonus
            annual_interest = balance * effective_apy / Decimal("100")
            annual_maintenance = account["monthly_fee"] * Decimal("12") if balance < account["ongoing_minimum"] else ZERO
            candidate = {
                "savings": account["name"], "card": card["name"],
                "base_apy": account["base_apy"], "card_bonus": bonus,
                "effective_apy": effective_apy, "annual_interest": annual_interest,
                "annual_card_fee": card["annual_fee"], "annual_maintenance": annual_maintenance,
                "net": annual_interest - card["annual_fee"] - annual_maintenance,
                "opening_minimum": account["opening_minimum"],
                "ongoing_minimum": account["ongoing_minimum"], "monthly_fee": account["monthly_fee"],
                "withdrawal_limit": account["withdrawal_limit"],
                "same_profile_required": card["same_profile_required"], "conditions": conditions,
            }
            (conditional if conditions else eligible).append(candidate)

    if errors:
        output(errors=errors)
        return

    eligible.sort(key=lambda item: item["net"], reverse=True)
    conditional.sort(key=lambda item: item["net"], reverse=True)
    recommendation = eligible[0] if eligible else (conditional[0] if conditional else None)
    reply = render(recommendation, balance, withdrawals) if recommendation else "No documented pairing meets the supplied constraints."
    output(ok=True, recommendation=recommendation, eligible=eligible, conditional=conditional,
           excluded=excluded, customer_reply=reply)


if __name__ == "__main__":
    main()
