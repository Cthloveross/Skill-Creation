#!/usr/bin/env python3
"""Rank eligible savings/checking combinations by effective APY.

Reads one JSON object from stdin and writes one JSON object to stdout.  APY and
money inputs are decimal strings/numbers. APY inputs are percentage points.
The caller is responsible for product eligibility and verifying which bonus
categories are legally/documentarily stackable.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def dec(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a decimal number")
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def text_decimal(value):
    # Plain normalized decimal notation, retaining a useful zero representation.
    value = value.normalize()
    result = format(value, "f")
    return "0" if result in ("-0", "") else result


def bonus_max(values, field, reasons):
    if values is None:
        return Decimal("0")
    if not isinstance(values, list):
        reasons.append(f"{field} must be a list")
        return Decimal("0")
    try:
        parsed = [dec(v, field) for v in values]
    except ValueError as exc:
        reasons.append(str(exc))
        return Decimal("0")
    if any(v < 0 for v in parsed):
        reasons.append(f"{field} cannot contain a negative APY bonus")
        return Decimal("0")
    return max(parsed, default=Decimal("0"))


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    balance = dec(payload.get("savings_balance"), "savings_balance")
    if balance < 0:
        raise ValueError("savings_balance cannot be negative")
    options = payload.get("options")
    if not isinstance(options, list):
        raise ValueError("options must be a list")

    eligible_ranked = []
    ineligible = []
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            ineligible.append({"index": index, "reasons": ["option must be an object"]})
            continue
        savings = option.get("savings_account_class")
        checking = option.get("checking_account_class")
        result_id = {"index": index, "savings_account_class": savings,
                     "checking_account_class": checking}
        reasons = []
        if not isinstance(savings, str) or not savings.strip():
            reasons.append("savings_account_class is required")
        if not isinstance(checking, str) or not checking.strip():
            reasons.append("checking_account_class is required")
        if option.get("eligible") is not True:
            reasons.append("option is not marked eligible")
        try:
            opening = dec(option.get("minimum_opening_deposit", 0), "minimum_opening_deposit")
            ongoing = dec(option.get("minimum_ongoing_balance", 0), "minimum_ongoing_balance")
            base = dec(option.get("base_apy"), "base_apy")
            if opening < 0 or ongoing < 0 or base < 0:
                reasons.append("minimums and base_apy cannot be negative")
            if balance < opening:
                reasons.append("balance is below the minimum opening deposit")
            if balance < ongoing:
                reasons.append("balance is below the minimum ongoing balance")
        except ValueError as exc:
            reasons.append(str(exc))
            opening = ongoing = base = Decimal("0")
        checking_bonus = bonus_max(option.get("checking_boosts", []), "checking_boosts", reasons)
        card_bonus = bonus_max(option.get("card_bonuses", []), "card_bonuses", reasons)
        other = option.get("other_stackable_bonuses", [])
        if not isinstance(other, list):
            reasons.append("other_stackable_bonuses must be a list")
            other_total = Decimal("0")
        else:
            try:
                parsed_other = [dec(v, "other_stackable_bonuses") for v in other]
                if any(v < 0 for v in parsed_other):
                    reasons.append("other_stackable_bonuses cannot contain a negative APY bonus")
                other_total = sum(parsed_other, Decimal("0"))
            except ValueError as exc:
                reasons.append(str(exc))
                other_total = Decimal("0")
        if reasons:
            result_id["reasons"] = reasons
            ineligible.append(result_id)
            continue
        effective = base + checking_bonus + card_bonus + other_total
        eligible_ranked.append({
            **result_id,
            "base_apy": text_decimal(base),
            "selected_checking_boost": text_decimal(checking_bonus),
            "selected_card_bonus": text_decimal(card_bonus),
            "other_stackable_bonus_total": text_decimal(other_total),
            "effective_apy": text_decimal(effective),
            "notes": option.get("notes", []) if isinstance(option.get("notes", []), list) else []
        })

    eligible_ranked.sort(key=lambda row: (Decimal(row["effective_apy"]),
                                          row["savings_account_class"],
                                          row["checking_account_class"]), reverse=True)
    return {"eligible_ranked": eligible_ranked, "ineligible": ineligible,
            "winner": eligible_ranked[0] if eligible_ranked else None}


if __name__ == "__main__":
    try:
        output = main(json.load(sys.stdin))
        print(json.dumps(output, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
