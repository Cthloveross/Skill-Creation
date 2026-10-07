#!/usr/bin/env python3
"""Rank documented savings/card combinations without taking any bank action.

Reads one JSON object from stdin and emits one JSON object on stdout. Values are
supplied at runtime from current product disclosures; this module has no product
catalog or hardcoded recommendation.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
PAIR_STATUSES = {"eligible", "unknown", "ineligible"}
CONDITION_STATUSES = {"met", "unknown", "unmet"}


def output(ok, recommendation=None, eligible=None, conditional=None, excluded=None,
           message="", errors=None):
    print(json.dumps({
        "ok": ok,
        "recommendation": recommendation,
        "eligible": eligible or [],
        "conditional": conditional or [],
        "excluded": excluded or [],
        "message": message,
        "errors": errors or [],
    }, ensure_ascii=False, sort_keys=True, default=str))


def as_decimal(value, label, errors, minimum=ZERO):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{label} must be a decimal number.")
        return None
    if not number.is_finite() or number < minimum:
        errors.append(f"{label} must be finite and at least {minimum}.")
        return None
    return number


def as_status(value, valid, label, errors):
    if value not in valid:
        errors.append(f"{label} has invalid status {value!r}.")
        return None
    return value


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def pct(value):
    text = format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), ".4f")
    return text.rstrip("0").rstrip(".")


def parse_account(raw, index, errors):
    tag = f"savings_accounts[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{tag} must be an object.")
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{tag}.name must be a nonempty string.")
        return None
    name = name.strip()
    data = {"name": name}
    for key in ("base_apy_pct", "opening_minimum", "ongoing_minimum",
                "monthly_fee_if_below_minimum"):
        data[key] = as_decimal(raw.get(key), f"{name}.{key}", errors)
    data["other_additive_apy_pct"] = as_decimal(
        raw.get("other_additive_apy_pct", 0), f"{name}.other_additive_apy_pct", errors
    )
    data["eligibility_status"] = as_status(
        raw.get("eligibility_status", "unknown"), PAIR_STATUSES,
        f"{name}.eligibility_status", errors
    )
    limit = raw.get("withdrawal_limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < -1:
        errors.append(f"{name}.withdrawal_limit must be an integer no less than -1.")
    data["withdrawal_limit"] = limit
    return data


def parse_card(raw, index, errors):
    tag = f"cards[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{tag} must be an object.")
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{tag}.name must be a nonempty string.")
        return None
    name = name.strip()
    crypto = raw.get("is_crypto_related")
    linkage = raw.get("same_profile_required", False)
    bonuses = raw.get("bonus_apy_by_savings", {})
    raw_requirements = raw.get("requirements", [])
    if not isinstance(crypto, bool):
        errors.append(f"{name}.is_crypto_related must be boolean.")
    if not isinstance(linkage, bool):
        errors.append(f"{name}.same_profile_required must be boolean.")
    if not isinstance(bonuses, dict):
        errors.append(f"{name}.bonus_apy_by_savings must be an object.")
        bonuses = {}
    if not isinstance(raw_requirements, list):
        errors.append(f"{name}.requirements must be an array.")
        raw_requirements = []

    requirements = []
    for i, item in enumerate(raw_requirements):
        req_tag = f"{name}.requirements[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{req_tag} must be an object.")
            continue
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            errors.append(f"{req_tag}.label must be a nonempty string.")
            continue
        req_status = as_status(item.get("status"), CONDITION_STATUSES, req_tag, errors)
        if req_status is not None:
            requirements.append({"label": label.strip(), "status": req_status})

    profile_status = "met"
    if linkage:
        profile_status = as_status(raw.get("same_profile_status", "unknown"),
                                   CONDITION_STATUSES,
                                   f"{name}.same_profile_status", errors)
    return {
        "name": name,
        "annual_fee": as_decimal(raw.get("annual_fee"), f"{name}.annual_fee", errors),
        "is_crypto_related": crypto,
        "eligibility_status": as_status(raw.get("eligibility_status", "unknown"),
                                         PAIR_STATUSES, f"{name}.eligibility_status", errors),
        "same_profile_required": linkage,
        "same_profile_status": profile_status,
        "requirements": requirements,
        "bonus_apy_by_savings": bonuses,
    }


def render(choice, balance, withdrawals):
    if choice["withdrawal_limit"] == -1:
        limit = "unlimited monthly withdrawals"
    else:
        limit = f"{choice['withdrawal_limit']} monthly withdrawals"
    if balance >= choice["ongoing_minimum"]:
        maintenance = (
            f"The assumed ${money(balance)} balance is above the ${money(choice['ongoing_minimum'])} "
            "ongoing minimum, so no below-minimum maintenance fee is estimated while that balance is maintained."
        )
    else:
        maintenance = (
            f"The assumed ${money(balance)} balance is below the ${money(choice['ongoing_minimum'])} "
            f"ongoing minimum, so the estimate includes ${money(choice['annual_maintenance'])} in annual maintenance fees."
        )
    condition = ""
    if choice["conditions"]:
        condition = (
            " This recommendation is conditional: " + "; ".join(choice["conditions"]) +
            ". Approval, eligibility, and any card-linked APY bonus are not guaranteed."
        )
    profile = ""
    if choice["same_profile_required"]:
        profile = " The card APY bonus applies only while both products are held under the same customer profile."
    return (
        f"My single recommendation is the {choice['savings']} paired with the {choice['card']}. "
        f"The account's {pct(choice['base_apy'])}% base APY plus the {pct(choice['card_bonus'])}% card bonus "
        f"equals {pct(choice['effective_apy'])}% APY. On a stable ${money(balance)} balance for one year, "
        f"${money(balance)} × {pct(choice['effective_apy'])}% is approximately ${money(choice['annual_interest'])} "
        f"in interest. The card annual fee is ${money(choice['annual_card_fee'])}, so estimated one-year interest "
        f"minus annual card and expected maintenance fees is approximately ${money(choice['net'])}, before taxes. "
        f"The account permits {limit}, so the expected {withdrawals} monthly withdrawals fit within the documented limit. "
        + maintenance + profile + condition +
        " This estimate assumes the eligible balance remains stable for one year and rates and eligibility remain in effect; "
        "actual interest is lower to the extent withdrawals reduce the daily balance. No account was opened and no card application was submitted."
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        output(False, errors=[f"Invalid JSON input: {exc.msg}"])
        return
    if not isinstance(payload, dict):
        output(False, errors=["Input must be a JSON object."])
        return

    errors = []
    balance = as_decimal(payload.get("balance"), "balance", errors)
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

    accounts = [parse_account(item, i, errors) for i, item in enumerate(raw_accounts)]
    cards = [parse_card(item, i, errors) for i, item in enumerate(raw_cards)]
    accounts = [item for item in accounts if item is not None]
    cards = [item for item in cards if item is not None]
    if errors:
        output(False, errors=errors)
        return

    eligible, conditional, excluded = [], [], []
    for account in accounts:
        for card in cards:
            reasons = []
            if account["eligibility_status"] == "ineligible":
                reasons.append("Savings-account eligibility is known to be unmet.")
            if card["eligibility_status"] == "ineligible":
                reasons.append("Card eligibility is known to be unmet.")
            if exclude_crypto and card["is_crypto_related"]:
                reasons.append("Card is excluded because it is crypto-related.")
            if balance < account["opening_minimum"]:
                reasons.append("Balance is below the documented opening minimum.")
            if account["withdrawal_limit"] != -1 and withdrawals > account["withdrawal_limit"]:
                reasons.append("Expected withdrawals exceed the documented monthly limit.")
            unmet = [r["label"] for r in card["requirements"] if r["status"] == "unmet"]
            if card["same_profile_required"] and card["same_profile_status"] == "unmet":
                unmet.append("same-customer-profile linkage")
            if unmet:
                reasons.append("Known unmet card condition(s): " + "; ".join(unmet))
            if reasons:
                excluded.append({"savings": account["name"], "card": card["name"], "reasons": reasons})
                continue

            bonus = as_decimal(card["bonus_apy_by_savings"].get(account["name"], 0),
                               f"{card['name']}.bonus_apy_by_savings[{account['name']}]", errors)
            if bonus is None:
                continue
            conditions = [r["label"] for r in card["requirements"] if r["status"] == "unknown"]
            if account["eligibility_status"] == "unknown":
                conditions.append("savings-account opening eligibility is unverified")
            if card["eligibility_status"] == "unknown":
                conditions.append("card eligibility is unverified")
            if card["same_profile_required"] and card["same_profile_status"] == "unknown":
                conditions.append("same-customer-profile linkage must be established for the APY bonus")

            effective = account["base_apy_pct"] + account["other_additive_apy_pct"] + bonus
            interest = balance * effective / Decimal("100")
            maintenance = (account["monthly_fee_if_below_minimum"] * Decimal("12")
                           if balance < account["ongoing_minimum"] else ZERO)
            pair = {
                "savings": account["name"], "card": card["name"],
                "base_apy": account["base_apy_pct"], "card_bonus": bonus,
                "effective_apy": effective, "annual_interest": interest,
                "annual_card_fee": card["annual_fee"], "annual_maintenance": maintenance,
                "net": interest - card["annual_fee"] - maintenance,
                "ongoing_minimum": account["ongoing_minimum"],
                "withdrawal_limit": account["withdrawal_limit"],
                "same_profile_required": card["same_profile_required"],
                "conditions": conditions,
            }
            (conditional if conditions else eligible).append(pair)

    if errors:
        output(False, errors=errors)
        return
    eligible.sort(key=lambda pair: pair["net"], reverse=True)
    conditional.sort(key=lambda pair: pair["net"], reverse=True)
    choice = eligible[0] if eligible else (conditional[0] if conditional else None)
    output(True, recommendation=choice, eligible=eligible, conditional=conditional,
           excluded=excluded,
           message=render(choice, balance, withdrawals) if choice else
           "No documented pairing meets the supplied constraints.")


if __name__ == "__main__":
    main()
