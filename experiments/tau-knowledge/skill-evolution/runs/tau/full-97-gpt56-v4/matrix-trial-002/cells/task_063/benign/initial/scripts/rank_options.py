#!/usr/bin/env python3
"""Rank savings/card combinations supplied as JSON on stdin.

The program reads the schema documented in SKILL.md and writes a JSON object to
stdout. APY is an annual yield, so projected interest for a constant balance is
balance * APY / 100; it is not compounded a second time.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
RATE = Decimal("0.001")
ZERO = Decimal("0")


def fail(message):
    print(json.dumps({"error": message}))
    raise SystemExit(2)


def decimal_value(value, field, allow_missing=False):
    if value is None and allow_missing:
        return ZERO
    if isinstance(value, bool):
        fail(f"{field} must be a decimal number, not a boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{field} must be a valid decimal number")
    if not result.is_finite() or result < ZERO:
        fail(f"{field} must be a finite nonnegative decimal number")
    return result


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def rate(value):
    return format(value.quantize(RATE, rounding=ROUND_HALF_UP), ".3f")


def main():
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"stdin must contain one JSON object: {exc.msg}")
    if not isinstance(request, dict):
        fail("input must be a JSON object")

    balance = decimal_value(request.get("balance"), "balance")
    options = request.get("options")
    if not isinstance(options, list) or not options:
        fail("options must be a nonempty array")
    include_fees = request.get("include_card_fees", True)
    if not isinstance(include_fees, bool):
        fail("include_card_fees must be boolean")

    ranked = []
    ineligible = []
    for index, option in enumerate(options):
        prefix = f"options[{index}]"
        if not isinstance(option, dict):
            fail(f"{prefix} must be an object")
        label = option.get("label")
        if not isinstance(label, str) or not label.strip():
            fail(f"{prefix}.label must be a nonempty string")
        eligible = option.get("eligible")
        if not isinstance(eligible, bool):
            fail(f"{prefix}.eligible must be an explicit boolean")
        notes = option.get("eligibility_notes", [])
        if not isinstance(notes, list) or not all(isinstance(x, str) for x in notes):
            fail(f"{prefix}.eligibility_notes must be an array of strings")

        if not eligible:
            ineligible.append({"label": label, "eligibility_notes": notes})
            continue

        base = decimal_value(option.get("base_apy_percent"), f"{prefix}.base_apy_percent")
        card = decimal_value(option.get("card_bonus_percent", ZERO), f"{prefix}.card_bonus_percent")
        checking = decimal_value(option.get("checking_bonus_percent", ZERO), f"{prefix}.checking_bonus_percent")
        other = decimal_value(option.get("other_bonus_percent", ZERO), f"{prefix}.other_bonus_percent")
        annual_fee = decimal_value(option.get("annual_card_fee", ZERO), f"{prefix}.annual_card_fee")
        total_apy = base + card + checking + other
        interest = balance * total_apy / Decimal("100")
        net = interest - annual_fee if include_fees else interest
        ranked.append({
            "label": label,
            "total_apy_percent": rate(total_apy),
            "projected_interest": money(interest),
            "annual_card_fee": money(annual_fee),
            "net_after_annual_card_fee": money(net),
            "eligibility_notes": notes,
            "_interest": interest,
            "_net": net,
        })

    ranked.sort(key=lambda row: (row["_net"], row["_interest"], row["label"]), reverse=True)
    for row in ranked:
        row.pop("_interest")
        row.pop("_net")

    print(json.dumps({
        "balance": money(balance),
        "ranked_eligible": ranked,
        "ineligible": ineligible,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
