#!/usr/bin/env python3
"""Rank documented savings/card combinations and render an advice-only response.

Reads one JSON object from stdin and writes one JSON object to stdout. This uses
only the Python standard library and performs no banking action.

See SKILL.md for the input/output schema. Rates are percentage points, not
fractions. Customer-level unknown requirements remain conditional; known unmet
requirements are excluded.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
VALID_ELIGIBILITY = {"eligible", "unknown", "ineligible"}
VALID_REQUIREMENT = {"met", "unknown", "unmet"}


def number(value, label, errors, minimum=ZERO):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{label} must be a valid decimal number.")
        return None
    if not result.is_finite() or result < minimum:
        errors.append(f"{label} must be finite and at least {minimum}.")
        return None
    return result


def fmt_money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def fmt_pct(value):
    return format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), ".4f").rstrip("0").rstrip(".")


def valid_status(value, valid, label, errors):
    if value not in valid:
        errors.append(f"{label} has an invalid status.")
        return None
    return value


def account_values(account, index, errors):
    if not isinstance(account, dict):
        errors.append(f"savings_accounts[{index}] must be an object.")
        return None
    name = account.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"savings_accounts[{index}].name must be a nonempty string.")
        return None
    result = {"name": name}
    for field in ("base_apy_pct", "opening_minimum", "ongoing_minimum", "monthly_fee_if_below_minimum"):
        result[field] = number(account.get(field), f"{name}.{field}", errors)
    result["other_additive_apy_pct"] = number(
        account.get("other_additive_apy_pct", 0), f"{name}.other_additive_apy_pct", errors
    )
    result["eligibility_status"] = valid_status(
        account.get("eligibility_status", "unknown"), VALID_ELIGIBILITY,
        f"{name}.eligibility_status", errors
    )
    limit = account.get("withdrawal_limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < -1:
        errors.append(f"{name}.withdrawal_limit must be an integer no less than -1.")
        result["withdrawal_limit"] = None
    else:
        result["withdrawal_limit"] = limit
    return result


def card_values(card, index, errors):
    if not isinstance(card, dict):
        errors.append(f"cards[{index}] must be an object.")
        return None
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"cards[{index}].name must be a nonempty string.")
        return None
    crypto = card.get("is_crypto_related")
    linkage = card.get("same_profile_required", False)
    bonuses = card.get("bonus_apy_by_savings", {})
    requirements = card.get("requirements", [])
    if not isinstance(crypto, bool):
        errors.append(f"{name}.is_crypto_related must be boolean.")
    if not isinstance(linkage, bool):
        errors.append(f"{name}.same_profile_required must be boolean.")
    if not isinstance(bonuses, dict):
        errors.append(f"{name}.bonus_apy_by_savings must be an object.")
    if not isinstance(requirements, list):
        errors.append(f"{name}.requirements must be an array.")
        requirements = []

    parsed_requirements = []
    for r_index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict) or not isinstance(requirement.get("label"), str):
            errors.append(f"{name}.requirements[{r_index}] must have a text label.")
            continue
        status = valid_status(requirement.get("status"), VALID_REQUIREMENT,
                              f"{name}.requirements[{r_index}]", errors)
        if status is not None:
            parsed_requirements.append({"label": requirement["label"], "status": status})

    return {
        "name": name,
        "annual_fee": number(card.get("annual_fee"), f"{name}.annual_fee", errors),
        "is_crypto_related": crypto,
        "same_profile_required": linkage,
        "bonus_apy_by_savings": bonuses,
        "eligibility_status": valid_status(card.get("eligibility_status", "unknown"),
                                             VALID_ELIGIBILITY,
                                             f"{name}.eligibility_status", errors),
        "requirements": parsed_requirements,
    }


def output_failure(errors):
    print(json.dumps({
        "ok": False, "recommendation": None, "eligible": [], "conditional": [],
        "excluded": [], "message": "", "errors": errors
    }, ensure_ascii=False, sort_keys=True))


def render(pair, balance, withdrawals):
    condition_text = ""
    unknown = pair["unknown_requirements"]
    if unknown:
        condition_text = (
            " This is conditional: " + "; ".join(unknown) +
            ". Card approval, eligibility, and the card-linked APY bonus are not guaranteed."
        )
    else:
        condition_text = " Documented eligibility requirements are established for this comparison; final approval is still subject to applicable processes."

    withdrawal = "unlimited" if pair["withdrawal_limit"] == -1 else str(pair["withdrawal_limit"])
    maintenance = (
        f"The ${fmt_money(balance)} balance is at or above the ${fmt_money(pair['ongoing_minimum'])} ongoing minimum, "
        f"so no below-minimum maintenance fee is estimated while that balance is maintained."
        if balance >= pair["ongoing_minimum"] else
        f"The ${fmt_money(balance)} balance is below the ${fmt_money(pair['ongoing_minimum'])} ongoing minimum, so the estimate includes ${fmt_money(pair['annual_maintenance_fee'])} of annual maintenance fees."
    )
    linkage = (
        " The APY bonus applies only while both products are held under the same customer profile."
        if pair["same_profile_required"] else ""
    )
    return (
        f"My single recommendation is {pair['savings']} with the {pair['card']}. "
        f"The savings account's {fmt_pct(pair['base_apy_pct'])}% base APY plus the {fmt_pct(pair['card_bonus_apy_pct'])}% card bonus equals {fmt_pct(pair['effective_apy_pct'])}% APY. "
        f"On a stable ${fmt_money(balance)} balance for one year, ${fmt_money(balance)} × {fmt_pct(pair['effective_apy_pct'])}% = approximately ${fmt_money(pair['annual_interest'])} interest. "
        f"The card annual fee is ${fmt_money(pair['annual_card_fee'])}, so the estimated one-year interest minus annual card fee and expected maintenance fees is approximately ${fmt_money(pair['net'])}, before taxes. "
        f"It permits {withdrawal} monthly withdrawals, so the expected {withdrawals} monthly withdrawals fit within the documented limit. "
        + maintenance + linkage + condition_text +
        " This estimate assumes the balance remains stable for one year and documented rates and eligibility remain in effect. No account was opened and no card application was submitted."
    )


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        output_failure([f"Invalid JSON input: {exc.msg}"])
        return
    if not isinstance(data, dict):
        output_failure(["Input must be a JSON object."])
        return

    errors = []
    balance = number(data.get("balance"), "balance", errors)
    withdrawals = data.get("withdrawals_per_month")
    if not isinstance(withdrawals, int) or isinstance(withdrawals, bool) or withdrawals < 0:
        errors.append("withdrawals_per_month must be a non-negative integer.")
    exclude_crypto = data.get("exclude_crypto", False)
    if not isinstance(exclude_crypto, bool):
        errors.append("exclude_crypto must be boolean.")
    raw_accounts = data.get("savings_accounts")
    raw_cards = data.get("cards")
    if not isinstance(raw_accounts, list):
        errors.append("savings_accounts must be an array.")
        raw_accounts = []
    if not isinstance(raw_cards, list):
        errors.append("cards must be an array.")
        raw_cards = []

    accounts = [account_values(a, i, errors) for i, a in enumerate(raw_accounts)]
    cards = [card_values(c, i, errors) for i, c in enumerate(raw_cards)]
    accounts = [a for a in accounts if a is not None]
    cards = [c for c in cards if c is not None]
    if errors:
        output_failure(errors)
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
            if unmet:
                reasons.append("Known unmet card requirement(s): " + "; ".join(unmet))
            if reasons:
                excluded.append({"savings": account["name"], "card": card["name"], "reasons": reasons})
                continue

            bonus = number(card["bonus_apy_by_savings"].get(account["name"], 0),
                           f"{card['name']}.bonus_apy_by_savings[{account['name']}]", errors)
            if bonus is None:
                continue
            effective = account["base_apy_pct"] + account["other_additive_apy_pct"] + bonus
            interest = balance * effective / Decimal("100")
            maintenance = (account["monthly_fee_if_below_minimum"] * Decimal("12")
                           if balance < account["ongoing_minimum"] else ZERO)
            unknown = [r["label"] for r in card["requirements"] if r["status"] == "unknown"]
            if account["eligibility_status"] == "unknown":
                unknown.append("Savings-account eligibility is unverified")
            if card["eligibility_status"] == "unknown" and not unknown:
                unknown.append("Card eligibility is unverified")
            pair = {
                "savings": account["name"], "card": card["name"],
                "base_apy_pct": account["base_apy_pct"], "card_bonus_apy_pct": bonus,
                "effective_apy_pct": effective, "annual_interest": interest,
                "annual_card_fee": card["annual_fee"], "annual_maintenance_fee": maintenance,
                "net": interest - card["annual_fee"] - maintenance,
                "opening_minimum": account["opening_minimum"], "ongoing_minimum": account["ongoing_minimum"],
                "withdrawal_limit": account["withdrawal_limit"],
                "same_profile_required": card["same_profile_required"],
                "unknown_requirements": unknown,
            }
            (conditional if unknown else eligible).append(pair)

    if errors:
        output_failure(errors)
        return
    eligible.sort(key=lambda item: item["net"], reverse=True)
    conditional.sort(key=lambda item: item["net"], reverse=True)
    choice = eligible[0] if eligible else (conditional[0] if conditional else None)
    result = {
        "ok": True,
        "recommendation": choice,
        "eligible": eligible,
        "conditional": conditional,
        "excluded": excluded,
        "message": render(choice, balance, withdrawals) if choice else "No documented pairing meets the supplied constraints.",
        "errors": [],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
