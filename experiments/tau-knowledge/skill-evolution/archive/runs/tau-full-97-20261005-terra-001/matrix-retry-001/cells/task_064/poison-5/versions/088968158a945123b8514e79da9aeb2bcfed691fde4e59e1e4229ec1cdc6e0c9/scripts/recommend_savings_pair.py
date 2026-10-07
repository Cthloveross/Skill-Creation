#!/usr/bin/env python3
"""Calculate and rank documented savings/card pairings without taking bank action.

Reads one JSON object from stdin and writes one JSON object to stdout. The script
uses only Python's standard library. See SKILL.md for the complete schema.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
PAIR_STATUSES = {"eligible", "unknown", "ineligible"}
REQUIREMENT_STATUSES = {"met", "unknown", "unmet"}


def fail(errors):
    print(json.dumps({
        "ok": False,
        "recommendation": None,
        "eligible": [],
        "conditional": [],
        "excluded": [],
        "message": "",
        "errors": errors,
    }, ensure_ascii=False, sort_keys=True))


def decimal(value, label, errors, minimum=ZERO):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{label} must be a decimal number.")
        return None
    if not result.is_finite() or result < minimum:
        errors.append(f"{label} must be finite and at least {minimum}.")
        return None
    return result


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def percent(value):
    text = format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), ".4f")
    return text.rstrip("0").rstrip(".")


def status(value, valid, label, errors):
    if value not in valid:
        errors.append(f"{label} has invalid status {value!r}.")
        return None
    return value


def parse_account(raw, index, errors):
    label = f"savings_accounts[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{label} must be an object.")
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{label}.name must be a nonempty string.")
        return None
    parsed = {"name": name.strip()}
    for field in ("base_apy_pct", "opening_minimum", "ongoing_minimum", "monthly_fee_if_below_minimum"):
        parsed[field] = decimal(raw.get(field), f"{name}.{field}", errors)
    parsed["other_additive_apy_pct"] = decimal(
        raw.get("other_additive_apy_pct", 0), f"{name}.other_additive_apy_pct", errors
    )
    parsed["eligibility_status"] = status(
        raw.get("eligibility_status", "unknown"), PAIR_STATUSES,
        f"{name}.eligibility_status", errors
    )
    limit = raw.get("withdrawal_limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < -1:
        errors.append(f"{name}.withdrawal_limit must be an integer no less than -1.")
        parsed["withdrawal_limit"] = None
    else:
        parsed["withdrawal_limit"] = limit
    return parsed


def parse_card(raw, index, errors):
    label = f"cards[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{label} must be an object.")
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{label}.name must be a nonempty string.")
        return None
    crypto = raw.get("is_crypto_related")
    linkage = raw.get("same_profile_required", False)
    bonuses = raw.get("bonus_apy_by_savings", {})
    requirements = raw.get("requirements", [])
    if not isinstance(crypto, bool):
        errors.append(f"{name}.is_crypto_related must be boolean.")
    if not isinstance(linkage, bool):
        errors.append(f"{name}.same_profile_required must be boolean.")
    if not isinstance(bonuses, dict):
        errors.append(f"{name}.bonus_apy_by_savings must be an object.")
        bonuses = {}
    if not isinstance(requirements, list):
        errors.append(f"{name}.requirements must be an array.")
        requirements = []

    parsed_requirements = []
    for req_index, requirement in enumerate(requirements):
        req_label = f"{name}.requirements[{req_index}]"
        if not isinstance(requirement, dict):
            errors.append(f"{req_label} must be an object.")
            continue
        text = requirement.get("label")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{req_label}.label must be nonempty text.")
            continue
        req_status = status(requirement.get("status"), REQUIREMENT_STATUSES, req_label, errors)
        if req_status is not None:
            parsed_requirements.append({"label": text.strip(), "status": req_status})

    return {
        "name": name.strip(),
        "annual_fee": decimal(raw.get("annual_fee"), f"{name}.annual_fee", errors),
        "is_crypto_related": crypto,
        "same_profile_required": linkage,
        "eligibility_status": status(raw.get("eligibility_status", "unknown"), PAIR_STATUSES,
                                      f"{name}.eligibility_status", errors),
        "requirements": parsed_requirements,
        "bonus_apy_by_savings": bonuses,
    }


def render(pair, balance, withdrawals):
    unknown = pair["unknown_requirements"]
    if pair["withdrawal_limit"] == -1:
        limit_text = "unlimited monthly withdrawals"
    else:
        limit_text = f"{pair['withdrawal_limit']} monthly withdrawals"

    if balance >= pair["ongoing_minimum"]:
        maintenance = (
            f"The assumed ${money(balance)} balance exceeds the ${money(pair['ongoing_minimum'])} ongoing minimum, "
            "so no below-minimum maintenance fee is estimated while that balance is maintained."
        )
    else:
        maintenance = (
            f"The assumed ${money(balance)} balance is below the ${money(pair['ongoing_minimum'])} ongoing minimum, "
            f"so the estimate includes ${money(pair['annual_maintenance_fee'])} in annual maintenance fees."
        )

    if unknown:
        conditions = (
            " This recommendation is conditional: " + "; ".join(unknown) +
            ". Card approval, eligibility, and any card-linked APY bonus are not guaranteed."
        )
    else:
        conditions = ""

    linkage = ""
    if pair["same_profile_required"]:
        linkage = " The card APY bonus applies only while both products are held under the same customer profile."

    return (
        f"My single recommendation is the {pair['savings']} paired with the {pair['card']}. "
        f"The account's {percent(pair['base_apy_pct'])}% base APY plus the {percent(pair['card_bonus_apy_pct'])}% card bonus "
        f"equals {percent(pair['effective_apy_pct'])}% APY. "
        f"For a stable ${money(balance)} balance over one year, ${money(balance)} × {percent(pair['effective_apy_pct'])}% "
        f"is approximately ${money(pair['annual_interest'])} in interest. The card annual fee is ${money(pair['annual_card_fee'])}, "
        f"so estimated one-year interest minus the annual card fee and expected maintenance fees is approximately "
        f"${money(pair['net'])}, before taxes. "
        f"The account permits {limit_text}, so the expected {withdrawals} monthly withdrawals fit within the documented limit. "
        + maintenance + linkage + conditions +
        " This estimate assumes the eligible balance remains stable for one year and documented rates and eligibility remain in effect; "
        "actual interest will be lower to the extent withdrawals reduce the daily balance. No account was opened and no card application was submitted."
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail([f"Invalid JSON input: {exc.msg}"])
        return
    if not isinstance(payload, dict):
        fail(["Input must be a JSON object."])
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

    accounts = [parse_account(item, i, errors) for i, item in enumerate(raw_accounts)]
    cards = [parse_card(item, i, errors) for i, item in enumerate(raw_cards)]
    accounts = [item for item in accounts if item is not None]
    cards = [item for item in cards if item is not None]
    if errors:
        fail(errors)
        return

    eligible = []
    conditional = []
    excluded = []
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
            unmet = [req["label"] for req in card["requirements"] if req["status"] == "unmet"]
            if unmet:
                reasons.append("Known unmet card requirement(s): " + "; ".join(unmet))
            if reasons:
                excluded.append({"savings": account["name"], "card": card["name"], "reasons": reasons})
                continue

            bonus = decimal(card["bonus_apy_by_savings"].get(account["name"], 0),
                            f"{card['name']}.bonus_apy_by_savings[{account['name']}]", errors)
            if bonus is None:
                continue
            effective_apy = account["base_apy_pct"] + account["other_additive_apy_pct"] + bonus
            annual_interest = balance * effective_apy / Decimal("100")
            annual_maintenance = (
                account["monthly_fee_if_below_minimum"] * Decimal("12")
                if balance < account["ongoing_minimum"] else ZERO
            )
            unknown = [req["label"] for req in card["requirements"] if req["status"] == "unknown"]
            if account["eligibility_status"] == "unknown":
                unknown.append("savings-account opening eligibility is unverified")
            if card["eligibility_status"] == "unknown" and not any("eligib" in item.lower() for item in unknown):
                unknown.append("card eligibility is unverified")

            pair = {
                "savings": account["name"],
                "card": card["name"],
                "base_apy_pct": account["base_apy_pct"],
                "card_bonus_apy_pct": bonus,
                "effective_apy_pct": effective_apy,
                "annual_interest": annual_interest,
                "annual_card_fee": card["annual_fee"],
                "annual_maintenance_fee": annual_maintenance,
                "net": annual_interest - card["annual_fee"] - annual_maintenance,
                "opening_minimum": account["opening_minimum"],
                "ongoing_minimum": account["ongoing_minimum"],
                "withdrawal_limit": account["withdrawal_limit"],
                "same_profile_required": card["same_profile_required"],
                "unknown_requirements": unknown,
            }
            (conditional if unknown else eligible).append(pair)

    if errors:
        fail(errors)
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
