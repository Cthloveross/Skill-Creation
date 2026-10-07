#!/usr/bin/env python3
"""Compare savings/card combinations without taking banking actions.

Read one JSON object from stdin and write one JSON object to stdout.
Only the Python standard library is used.

Input schema
============
{
  "balance": number|string,                 // non-negative stable balance assumption
  "withdrawals_per_month": integer,         // expected maximum; use 0 if unspecified
  "savings_accounts": [
    {
      "name": string,
      "base_apy_pct": number|string,
      "opening_minimum": number|string,
      "ongoing_minimum": number|string,
      "monthly_fee_if_below_minimum": number|string,
      "withdrawal_limit": integer,          // -1 only where documentation defines unlimited
      "eligibility_status": "eligible"|"unknown"|"ineligible", // optional; defaults unknown
      "other_additive_apy_pct": number|string, // optional; only documented, verified bonuses
      "notes": string                         // optional
    }
  ],
  "cards": [
    {
      "name": string,
      "annual_fee": number|string,
      "is_crypto_related": boolean,
      "eligibility_status": "eligible"|"unknown"|"ineligible",
      "bonus_apy_by_savings": {"Exact Savings Account Name": number|string},
      "notes": string                         // optional
    }
  ],
  "held_cards": [                            // optional already-held active cards
    {
      "name": string,
      "eligibility_status": "eligible"|"unknown"|"ineligible",
      "bonus_apy_by_savings": {"Exact Savings Account Name": number|string}
    }
  ],
  "checking_boosts": [                       // optional, only documented matching pairings
    {
      "savings_name": string,
      "apy_pct": number|string,
      "eligibility_status": "eligible"|"unknown"|"ineligible",
      "name": string
    }
  ],
  "exclude_crypto": boolean                  // optional; defaults false
}

Output schema
=============
{
  "ok": boolean,
  "assumptions": [string],
  "eligible": [combination],
  "conditional": [combination],
  "excluded": [{"savings": string, "card": string, "reasons": [string]}],
  "errors": [string]
}

Each combination has savings/card names, the selected highest card and checking
bonuses, effective APY, annual interest, annual fees, expected net value, and
warnings. Monetary and percentage outputs are decimal strings to avoid binary
floating-point ambiguity. The script treats APY bonuses as additive percentage
points only because callers must supply bonuses whose documentation permits that.
It applies a maintenance fee for 12 months only when the supplied stable balance
is below the supplied ongoing minimum. It reports the fee as conditional when the
balance is at or above that minimum, because future balance declines may trigger it.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

VALID_STATUS = {"eligible", "unknown", "ineligible"}
ZERO = Decimal("0")
TWELVE = Decimal("12")


def decimal_value(value, field, errors, minimum=None):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be a valid decimal number.")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite.")
        return None
    if minimum is not None and result < minimum:
        errors.append(f"{field} must be at least {minimum}.")
        return None
    return result


def amount(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def percent(value):
    return format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), ".4f")


def status_of(item):
    status = item.get("eligibility_status", "unknown")
    return status if status in VALID_STATUS else None


def bonus_candidates(cards, savings_name, errors, label):
    candidates = []
    for index, card in enumerate(cards):
        status = status_of(card)
        if status is None:
            errors.append(f"{label}[{index}].eligibility_status is invalid.")
            continue
        if status == "ineligible":
            continue
        mapping = card.get("bonus_apy_by_savings", {})
        if not isinstance(mapping, dict) or savings_name not in mapping:
            continue
        value = decimal_value(mapping[savings_name],
                              f"{label}[{index}].bonus_apy_by_savings[{savings_name!r}]",
                              errors, ZERO)
        if value is not None:
            candidates.append({"name": card.get("name", "Unnamed card"),
                               "apy": value, "status": status})
    return candidates


def highest_bonus(candidates):
    if not candidates:
        return {"name": None, "apy": ZERO, "status": "eligible"}
    # On an exact tie, prefer an eligible item so the outcome does not become
    # conditional merely because an equivalent unverified bonus exists.
    return sorted(candidates,
                  key=lambda item: (item["apy"], item["status"] == "eligible"),
                  reverse=True)[0]


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"Invalid JSON input: {exc.msg}"],
                          "eligible": [], "conditional": [], "excluded": []}))
        return

    errors = []
    if not isinstance(data, dict):
        print(json.dumps({"ok": False, "errors": ["Input must be a JSON object."],
                          "eligible": [], "conditional": [], "excluded": []}))
        return

    balance = decimal_value(data.get("balance"), "balance", errors, ZERO)
    withdrawal_count = data.get("withdrawals_per_month")
    if not isinstance(withdrawal_count, int) or isinstance(withdrawal_count, bool) or withdrawal_count < 0:
        errors.append("withdrawals_per_month must be a non-negative integer.")

    savings_accounts = data.get("savings_accounts")
    cards = data.get("cards")
    held_cards = data.get("held_cards", [])
    checking_boosts = data.get("checking_boosts", [])
    if not isinstance(savings_accounts, list):
        errors.append("savings_accounts must be an array.")
        savings_accounts = []
    if not isinstance(cards, list):
        errors.append("cards must be an array.")
        cards = []
    if not isinstance(held_cards, list):
        errors.append("held_cards must be an array.")
        held_cards = []
    if not isinstance(checking_boosts, list):
        errors.append("checking_boosts must be an array.")
        checking_boosts = []

    if errors:
        print(json.dumps({"ok": False, "errors": errors, "eligible": [],
                          "conditional": [], "excluded": []}))
        return

    exclude_crypto = data.get("exclude_crypto", False)
    if not isinstance(exclude_crypto, bool):
        print(json.dumps({"ok": False, "errors": ["exclude_crypto must be boolean."],
                          "eligible": [], "conditional": [], "excluded": []}))
        return

    eligible = []
    conditional = []
    excluded = []

    for savings_index, savings in enumerate(savings_accounts):
        name = savings.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"savings_accounts[{savings_index}].name must be a nonempty string.")
            continue
        savings_status = status_of(savings)
        if savings_status is None:
            errors.append(f"savings_accounts[{savings_index}].eligibility_status is invalid.")
            continue
        base = decimal_value(savings.get("base_apy_pct"), f"{name}.base_apy_pct", errors, ZERO)
        opening = decimal_value(savings.get("opening_minimum"), f"{name}.opening_minimum", errors, ZERO)
        ongoing = decimal_value(savings.get("ongoing_minimum"), f"{name}.ongoing_minimum", errors, ZERO)
        monthly_fee = decimal_value(savings.get("monthly_fee_if_below_minimum"),
                                    f"{name}.monthly_fee_if_below_minimum", errors, ZERO)
        other_bonus = decimal_value(savings.get("other_additive_apy_pct", 0),
                                    f"{name}.other_additive_apy_pct", errors, ZERO)
        limit = savings.get("withdrawal_limit")
        if (base is None or opening is None or ongoing is None or monthly_fee is None or
                other_bonus is None or not isinstance(limit, int) or isinstance(limit, bool) or limit < -1):
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < -1:
                errors.append(f"{name}.withdrawal_limit must be an integer no less than -1.")
            continue

        checking_candidates = []
        for boost_index, boost in enumerate(checking_boosts):
            if not isinstance(boost, dict) or boost.get("savings_name") != name:
                continue
            boost_status = status_of(boost)
            if boost_status is None:
                errors.append(f"checking_boosts[{boost_index}].eligibility_status is invalid.")
                continue
            if boost_status == "ineligible":
                continue
            boost_amount = decimal_value(boost.get("apy_pct"),
                                         f"checking_boosts[{boost_index}].apy_pct", errors, ZERO)
            if boost_amount is not None:
                checking_candidates.append({"name": boost.get("name", "Unnamed checking boost"),
                                            "apy": boost_amount, "status": boost_status})
        best_checking = highest_bonus(checking_candidates)

        for card_index, card in enumerate(cards):
            card_name = card.get("name") if isinstance(card, dict) else None
            if not isinstance(card_name, str) or not card_name:
                errors.append(f"cards[{card_index}].name must be a nonempty string.")
                continue
            card_status = status_of(card)
            if card_status is None:
                errors.append(f"{card_name}.eligibility_status is invalid.")
                continue
            annual_fee = decimal_value(card.get("annual_fee"), f"{card_name}.annual_fee", errors, ZERO)
            crypto = card.get("is_crypto_related")
            if annual_fee is None or not isinstance(crypto, bool):
                if not isinstance(crypto, bool):
                    errors.append(f"{card_name}.is_crypto_related must be boolean.")
                continue

            reasons = []
            if savings_status == "ineligible":
                reasons.append("Savings-account eligibility is documented as unmet.")
            if card_status == "ineligible":
                reasons.append("Card eligibility is documented as unmet.")
            if exclude_crypto and crypto:
                reasons.append("Card is excluded because it is crypto-related.")
            if balance < opening:
                reasons.append("Stable balance is below the documented opening minimum.")
            if limit != -1 and withdrawal_count > limit:
                reasons.append("Expected withdrawals exceed the documented monthly limit.")
            if reasons:
                excluded.append({"savings": name, "card": card_name, "reasons": reasons})
                continue

            # The selected new card and active held cards compete in the same
            # non-stacking card-bonus category.
            card_bonus_options = bonus_candidates(held_cards, name, errors, "held_cards")
            card_bonus_options.extend(bonus_candidates([card], name, errors, f"cards[{card_index}]") )
            best_card = highest_bonus(card_bonus_options)
            effective_apy = base + other_bonus + best_checking["apy"] + best_card["apy"]
            annual_interest = balance * effective_apy / Decimal("100")
            expected_maintenance = monthly_fee * TWELVE if balance < ongoing else ZERO
            net = annual_interest - annual_fee - expected_maintenance

            warnings = []
            if balance >= ongoing and monthly_fee > ZERO:
                warnings.append("Maintenance fee is shown as $0 under the stable-balance assumption; it may apply if the balance falls below the ongoing minimum.")
            if limit == -1:
                withdrawal_description = "unlimited (only if supplied documentation defines -1 as unlimited)"
            else:
                withdrawal_description = str(limit)
            if card_status == "unknown":
                warnings.append("New-card eligibility is unverified.")
            if savings_status == "unknown":
                warnings.append("Customer-level savings-opening eligibility is unverified.")
            if best_card["status"] == "unknown":
                warnings.append("The highest selected credit-card APY bonus is unverified.")
            if best_checking["status"] == "unknown":
                warnings.append("The selected checking APY boost is unverified.")

            result = {
                "savings": name,
                "card": card_name,
                "base_apy_pct": percent(base),
                "other_additive_apy_pct": percent(other_bonus),
                "selected_card_bonus": {"source": best_card["name"], "apy_pct": percent(best_card["apy"])},
                "selected_checking_boost": {"source": best_checking["name"], "apy_pct": percent(best_checking["apy"])},
                "effective_apy_pct": percent(effective_apy),
                "annual_interest": amount(annual_interest),
                "annual_card_fee": amount(annual_fee),
                "expected_annual_maintenance_fee": amount(expected_maintenance),
                "estimated_one_year_net": amount(net),
                "opening_minimum": amount(opening),
                "ongoing_minimum": amount(ongoing),
                "withdrawal_limit_per_month": withdrawal_description,
                "warnings": warnings,
            }
            if (savings_status == "eligible" and card_status == "eligible" and
                    best_card["status"] == "eligible" and best_checking["status"] == "eligible"):
                eligible.append(result)
            else:
                conditional.append(result)

    eligible.sort(key=lambda item: Decimal(item["estimated_one_year_net"]), reverse=True)
    conditional.sort(key=lambda item: Decimal(item["estimated_one_year_net"]), reverse=True)
    output = {
        "ok": not errors,
        "assumptions": [
            "Balance remains constant for one year.",
            "Documented APY is treated as annual yield and is not compounded again.",
            "Cash-back earnings, taxes, and unprovided transaction fees are excluded.",
            "Only the highest applicable card bonus and highest applicable checking boost are used.",
        ],
        "eligible": eligible,
        "conditional": conditional,
        "excluded": excluded,
        "errors": errors,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
