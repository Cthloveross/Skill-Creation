#!/usr/bin/env python3
"""Compare savings/card return options from JSON stdin.

Input schema:
{
  "balance": number|string,                         # non-negative dollars
  "profile": {"credit_score": number|null,
              "has_subscription": true|false|null}, # optional
  "options": [{
    "name": string,
    "base_apy_pct": number|string,
    "annual_fee": number|string,
    "card_bonus_pct": number|string,                # optional, default 0
    "card_bonuses_pct": [number|string, ...],        # optional; highest wins
    "checking_boost_pct": number|string,             # optional, default 0
    "checking_boosts_pct": [number|string, ...],     # optional; highest wins
    "additive_bonus_pct": number|string,             # optional, default 0
    "minimum_credit_score": number|string,           # optional
    "requires_subscription": true|false,             # optional
    "eligible": true|false|null,                     # optional explicit status
    "notes": [string, ...]                           # optional
  }]
}

If `eligible` is supplied, false makes an option ineligible and true confirms it,
except that known unmet score/subscription requirements remain ineligible. If no
known requirement fails but a required profile value is absent, the option is
conditional. Otherwise it is eligible. `card_bonuses_pct` and
`checking_boosts_pct` let callers supply multiple applicable candidates; this
script selects the maximum from each list rather than summing it.

Output schema:
{
  "assumptions": {...},
  "confirmed_ranked": [calculated option...],
  "conditional_ranked": [calculated option...],
  "ineligible": [calculated option...]
}
Money values are decimal strings rounded to cents. APY figures are decimal
percentage strings. Each calculated option contains `eligibility_reasons` for
customer-facing explanation.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def as_decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a finite decimal number")
    if not result.is_finite():
        raise ValueError(f"{field} must be a finite decimal number")
    return result


def nonnegative(value, field):
    result = as_decimal(value, field)
    if result < ZERO:
        raise ValueError(f"{field} must be non-negative")
    return result


def max_bonus(option, singular_key, plural_key):
    values = []
    if singular_key in option and option[singular_key] is not None:
        values.append(nonnegative(option[singular_key], singular_key))
    if plural_key in option and option[plural_key] is not None:
        if not isinstance(option[plural_key], list):
            raise ValueError(f"{plural_key} must be an array")
        values.extend(nonnegative(v, plural_key) for v in option[plural_key])
    return max(values) if values else ZERO


def fmt_money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def fmt_pct(value):
    return format(value.normalize(), "f") if value != ZERO else "0"


def eligibility(option, profile):
    reasons = []
    status = "eligible"
    explicit = option.get("eligible")
    if explicit not in (None, True, False):
        raise ValueError("eligible must be true, false, or null")
    if explicit is False:
        status = "ineligible"
        reasons.append("marked not eligible by supplied facts")

    minimum = option.get("minimum_credit_score")
    if minimum is not None:
        minimum = nonnegative(minimum, "minimum_credit_score")
        score = profile.get("credit_score")
        if score is None:
            if status != "ineligible":
                status = "conditional"
            reasons.append("credit score must be confirmed (minimum " + fmt_pct(minimum) + ")")
        else:
            score = nonnegative(score, "profile.credit_score")
            if score < minimum:
                status = "ineligible"
                reasons.append("credit score is below stated minimum " + fmt_pct(minimum))

    if option.get("requires_subscription") is True:
        subscribed = profile.get("has_subscription")
        if subscribed is None:
            if status != "ineligible":
                status = "conditional"
            reasons.append("required subscription must be confirmed")
        elif subscribed is not True:
            status = "ineligible"
            reasons.append("required subscription is not confirmed active")
    elif option.get("requires_subscription") not in (None, False):
        raise ValueError("requires_subscription must be true, false, or omitted")

    if explicit is True and status == "eligible":
        reasons.append("marked eligible by supplied facts")
    if not reasons:
        reasons.append("no unmet or unknown supplied eligibility requirement")
    return status, reasons


def calculate(option, balance, profile):
    if not isinstance(option, dict):
        raise ValueError("each option must be an object")
    name = option.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("each option requires a nonempty name")

    base = nonnegative(option.get("base_apy_pct"), "base_apy_pct")
    fee = nonnegative(option.get("annual_fee", 0), "annual_fee")
    card = max_bonus(option, "card_bonus_pct", "card_bonuses_pct")
    checking = max_bonus(option, "checking_boost_pct", "checking_boosts_pct")
    additive = nonnegative(option.get("additive_bonus_pct", 0), "additive_bonus_pct")
    effective = base + card + checking + additive
    gross = balance * effective / Decimal("100")
    net = gross - fee
    status, reasons = eligibility(option, profile)
    notes = option.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(n, str) for n in notes):
        raise ValueError("notes must be an array of strings")
    return {
        "name": name,
        "eligibility": status,
        "eligibility_reasons": reasons,
        "base_apy_pct": fmt_pct(base),
        "selected_card_bonus_pct": fmt_pct(card),
        "selected_checking_boost_pct": fmt_pct(checking),
        "additive_bonus_pct": fmt_pct(additive),
        "effective_apy_pct": fmt_pct(effective),
        "estimated_gross_interest": fmt_money(gross),
        "annual_fee": fmt_money(fee),
        "estimated_net_one_year_return": fmt_money(net),
        "notes": notes,
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        balance = nonnegative(data.get("balance"), "balance")
        profile = data.get("profile", {})
        if profile is None:
            profile = {}
        if not isinstance(profile, dict):
            raise ValueError("profile must be an object")
        options = data.get("options")
        if not isinstance(options, list) or not options:
            raise ValueError("options must be a nonempty array")
        calculated = [calculate(option, balance, profile) for option in options]
        groups = {"eligible": [], "conditional": [], "ineligible": []}
        for item in calculated:
            groups[item["eligibility"]].append(item)
        for items in groups.values():
            items.sort(key=lambda x: Decimal(x["estimated_net_one_year_return"]), reverse=True)
        output = {
            "assumptions": {
                "constant_balance": fmt_money(balance),
                "method": "balance times effective APY less annual fee; APY is not compounded again",
                "card_bonus_selection": "highest supplied card bonus only",
                "checking_boost_selection": "highest supplied checking boost only",
            },
            "confirmed_ranked": groups["eligible"],
            "conditional_ranked": groups["conditional"],
            "ineligible": groups["ineligible"],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
