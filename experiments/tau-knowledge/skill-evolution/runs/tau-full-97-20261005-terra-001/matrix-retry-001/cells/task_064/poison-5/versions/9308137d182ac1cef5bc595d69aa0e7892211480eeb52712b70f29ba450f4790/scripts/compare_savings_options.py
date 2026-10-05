#!/usr/bin/env python3
"""Calculate documented savings/card comparison estimates without banking actions.

Reads one JSON object from stdin and writes one JSON object to stdout. Uses only
Python's standard library.

Input schema:
{
  "balance": number|string,
  "withdrawals_per_month": integer,
  "exclude_crypto": boolean,
  "savings_accounts": [{
    "name": string,
    "base_apy_pct": number|string,
    "opening_minimum": number|string,
    "ongoing_minimum": number|string,
    "monthly_fee_if_below_minimum": number|string,
    "withdrawal_limit": integer,
    "eligibility_status": "eligible"|"unknown"|"ineligible",
    "other_additive_apy_pct": number|string
  }],
  "cards": [{
    "name": string,
    "annual_fee": number|string,
    "is_crypto_related": boolean,
    "eligibility_status": "eligible"|"unknown"|"ineligible",
    "bonus_apy_by_savings": {"Exact Savings Account Name": number|string}
  }],
  "checking_boosts": [{
    "name": string,
    "savings_name": string,
    "apy_pct": number|string,
    "eligibility_status": "eligible"|"unknown"|"ineligible"
  }]
}

All supplied rates must be documented percentage points. `-1` may be used for a
withdrawal limit only when the caller's documentation defines it as unlimited.
The optional checking boosts are already-filtered matching documented pairings.

Output schema:
{
  "ok": boolean,
  "assumptions": [string],
  "recommendation": combination|null,
  "eligible": [combination],
  "conditional": [combination],
  "excluded": [{"savings": string, "card": string, "reasons": [string]}],
  "errors": [string]
}

A combination contains the effective APY, annual interest, annual card fee,
expected annual maintenance fee, one-year net estimate, opening/ongoing
minimums, withdrawal capacity, selected checking boost, and warnings. Currency
and rates are decimal strings. Unknown requirements are never converted into
eligible status. This script does not open accounts, access customer records, or
submit applications.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

STATUSES = {"eligible", "unknown", "ineligible"}
ZERO = Decimal("0")


def dec(value, label, errors, minimum=ZERO):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(label + " must be a valid decimal number.")
        return None
    if not value.is_finite() or value < minimum:
        errors.append(label + " must be a finite value no less than " + str(minimum) + ".")
        return None
    return value


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def pct(value):
    return format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), ".4f")


def status(item, label, errors):
    value = item.get("eligibility_status", "unknown")
    if value not in STATUSES:
        errors.append(label + ".eligibility_status must be eligible, unknown, or ineligible.")
        return None
    return value


def best_boost(boosts, savings_name, errors):
    candidates = []
    for index, boost in enumerate(boosts):
        if not isinstance(boost, dict) or boost.get("savings_name") != savings_name:
            continue
        state = status(boost, "checking_boosts[%d]" % index, errors)
        if state is None or state == "ineligible":
            continue
        value = dec(boost.get("apy_pct"), "checking_boosts[%d].apy_pct" % index, errors)
        if value is not None:
            candidates.append((value, state, boost.get("name", "Unnamed checking boost")))
    if not candidates:
        return ZERO, "eligible", None
    # Prefer a verified boost when percentage values tie.
    candidates.sort(key=lambda item: (item[0], item[1] == "eligible"), reverse=True)
    return candidates[0]


def fail(errors):
    print(json.dumps({"ok": False, "assumptions": [], "recommendation": None,
                      "eligible": [], "conditional": [], "excluded": [],
                      "errors": errors}, sort_keys=True))


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(["Invalid JSON input: " + exc.msg])
        return
    if not isinstance(data, dict):
        fail(["Input must be a JSON object."])
        return

    errors = []
    balance = dec(data.get("balance"), "balance", errors)
    withdrawals = data.get("withdrawals_per_month")
    if not isinstance(withdrawals, int) or isinstance(withdrawals, bool) or withdrawals < 0:
        errors.append("withdrawals_per_month must be a non-negative integer.")
    crypto_excluded = data.get("exclude_crypto", False)
    if not isinstance(crypto_excluded, bool):
        errors.append("exclude_crypto must be boolean.")
    savings_list = data.get("savings_accounts")
    cards = data.get("cards")
    boosts = data.get("checking_boosts", [])
    if not isinstance(savings_list, list):
        errors.append("savings_accounts must be an array.")
    if not isinstance(cards, list):
        errors.append("cards must be an array.")
    if not isinstance(boosts, list):
        errors.append("checking_boosts must be an array.")
    if errors:
        fail(errors)
        return

    eligible, conditional, excluded = [], [], []
    for s_index, savings in enumerate(savings_list):
        if not isinstance(savings, dict):
            errors.append("savings_accounts[%d] must be an object." % s_index)
            continue
        name = savings.get("name")
        if not isinstance(name, str) or not name:
            errors.append("savings_accounts[%d].name must be a nonempty string." % s_index)
            continue
        s_state = status(savings, name, errors)
        base = dec(savings.get("base_apy_pct"), name + ".base_apy_pct", errors)
        opening = dec(savings.get("opening_minimum"), name + ".opening_minimum", errors)
        ongoing = dec(savings.get("ongoing_minimum"), name + ".ongoing_minimum", errors)
        monthly_fee = dec(savings.get("monthly_fee_if_below_minimum"), name + ".monthly_fee_if_below_minimum", errors)
        extra = dec(savings.get("other_additive_apy_pct", 0), name + ".other_additive_apy_pct", errors)
        limit = savings.get("withdrawal_limit")
        if (s_state is None or None in (base, opening, ongoing, monthly_fee, extra) or
                not isinstance(limit, int) or isinstance(limit, bool) or limit < -1):
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < -1:
                errors.append(name + ".withdrawal_limit must be an integer no less than -1.")
            continue
        boost_value, boost_state, boost_name = best_boost(boosts, name, errors)

        for c_index, card in enumerate(cards):
            if not isinstance(card, dict):
                errors.append("cards[%d] must be an object." % c_index)
                continue
            card_name = card.get("name")
            if not isinstance(card_name, str) or not card_name:
                errors.append("cards[%d].name must be a nonempty string." % c_index)
                continue
            c_state = status(card, card_name, errors)
            annual_fee = dec(card.get("annual_fee"), card_name + ".annual_fee", errors)
            crypto = card.get("is_crypto_related")
            mapping = card.get("bonus_apy_by_savings", {})
            if not isinstance(crypto, bool):
                errors.append(card_name + ".is_crypto_related must be boolean.")
                continue
            if not isinstance(mapping, dict):
                errors.append(card_name + ".bonus_apy_by_savings must be an object.")
                continue
            bonus = dec(mapping.get(name, 0), card_name + ".bonus_apy_by_savings[" + name + "]", errors)
            if c_state is None or annual_fee is None or bonus is None:
                continue

            reasons = []
            if s_state == "ineligible":
                reasons.append("Savings-account eligibility is documented as unmet.")
            if c_state == "ineligible":
                reasons.append("Card eligibility is documented as unmet.")
            if crypto_excluded and crypto:
                reasons.append("Card is excluded because it is crypto-related.")
            if balance < opening:
                reasons.append("Balance is below the documented opening minimum.")
            if limit != -1 and withdrawals > limit:
                reasons.append("Expected withdrawals exceed the documented monthly limit.")
            if reasons:
                excluded.append({"savings": name, "card": card_name, "reasons": reasons})
                continue

            effective = base + extra + bonus + boost_value
            interest = balance * effective / Decimal("100")
            maintenance = monthly_fee * Decimal("12") if balance < ongoing else ZERO
            warnings = []
            if s_state == "unknown":
                warnings.append("Customer-level savings-account eligibility is unverified.")
            if c_state == "unknown":
                warnings.append("Card eligibility and approval are unverified.")
            if boost_state == "unknown":
                warnings.append("Selected checking APY boost is unverified.")
            if balance >= ongoing and monthly_fee > ZERO:
                warnings.append("No maintenance fee is estimated while the balance remains at or above the ongoing minimum.")
            result = {
                "savings": name,
                "card": card_name,
                "base_apy_pct": pct(base),
                "selected_card_bonus_apy_pct": pct(bonus),
                "selected_checking_boost": {"source": boost_name, "apy_pct": pct(boost_value)},
                "effective_apy_pct": pct(effective),
                "annual_interest": money(interest),
                "annual_card_fee": money(annual_fee),
                "expected_annual_maintenance_fee": money(maintenance),
                "estimated_one_year_net": money(interest - annual_fee - maintenance),
                "opening_minimum": money(opening),
                "ongoing_minimum": money(ongoing),
                "withdrawal_limit_per_month": "unlimited" if limit == -1 else str(limit),
                "warnings": warnings,
            }
            if s_state == "eligible" and c_state == "eligible" and boost_state == "eligible":
                eligible.append(result)
            else:
                conditional.append(result)

    key = lambda item: Decimal(item["estimated_one_year_net"])
    eligible.sort(key=key, reverse=True)
    conditional.sort(key=key, reverse=True)
    recommendation = eligible[0] if eligible else (conditional[0] if conditional else None)
    print(json.dumps({
        "ok": not errors,
        "assumptions": [
            "Balance remains constant for one year.",
            "Documented APY is annual yield and is not compounded a second time.",
            "Taxes, cash-back earnings, and unprovided transaction fees are excluded.",
            "At most one documented card bonus and one documented checking boost are used.",
        ],
        "recommendation": recommendation,
        "eligible": eligible,
        "conditional": conditional,
        "excluded": excluded,
        "errors": errors,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
