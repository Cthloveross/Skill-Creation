#!/usr/bin/env python3
"""Filter and rank supplied savings/card candidates without product-specific hardcoding."""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def decimal_value(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a decimal number")
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def required_bool(obj, field):
    value = obj.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def main(request):
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    deposit = decimal_value(request.get("deposit_amount"), "deposit_amount")
    if deposit <= 0:
        raise ValueError("deposit_amount must be positive")

    customer = request.get("customer")
    candidates = request.get("candidates")
    if not isinstance(customer, dict) or not isinstance(candidates, list):
        raise ValueError("customer must be an object and candidates must be an array")

    paper_required = required_bool(customer, "requires_paper_statements")
    credit_check_required = required_bool(customer, "requires_credit_check")
    premium_subscription = required_bool(customer, "premium_subscription")
    raw_score = customer.get("credit_score")
    score = None if raw_score is None else decimal_value(raw_score, "customer.credit_score")

    eligible = []
    ineligible = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        account_class = candidate.get("account_class")
        if not isinstance(account_class, str) or not account_class.strip():
            raise ValueError(f"candidates[{index}].account_class must be a nonempty string")

        minimum = decimal_value(candidate.get("minimum_opening_deposit"),
                                f"candidates[{index}].minimum_opening_deposit")
        base_apy = decimal_value(candidate.get("applicable_base_apy_percent"),
                                 f"candidates[{index}].applicable_base_apy_percent")
        bonus = decimal_value(candidate.get("card_apy_bonus_percent", 0),
                              f"candidates[{index}].card_apy_bonus_percent")
        annual_fee = decimal_value(candidate.get("card_annual_fee", 0),
                                   f"candidates[{index}].card_annual_fee")
        if minimum < 0 or base_apy < 0 or bonus < 0 or annual_fee < 0:
            raise ValueError(f"candidates[{index}] contains a negative rate, fee, or minimum")

        supports_paper = required_bool(candidate, "paper_statements_supported")
        paperless_required = required_bool(candidate, "paperless_required")
        subscription_required = candidate.get("card_subscription_required", False)
        if not isinstance(subscription_required, bool):
            raise ValueError(f"candidates[{index}].card_subscription_required must be boolean")

        card_name = candidate.get("card_name")
        card_check = candidate.get("card_requires_credit_check")
        card_min_score = candidate.get("card_min_credit_score")
        if card_name is None:
            if card_check is not None or card_min_score is not None:
                raise ValueError(f"candidates[{index}] has card requirements without card_name")
        elif not isinstance(card_name, str) or not card_name.strip():
            raise ValueError(f"candidates[{index}].card_name must be a nonempty string or null")
        elif card_check is not None and not isinstance(card_check, bool):
            raise ValueError(f"candidates[{index}].card_requires_credit_check must be boolean or null")

        reasons = []
        if deposit < minimum:
            reasons.append("deposit_below_opening_minimum")
        if paper_required and (not supports_paper or paperless_required):
            reasons.append("paper_statements_not_compatible")
        if subscription_required and not premium_subscription:
            reasons.append("required_subscription_absent")
        if card_name is not None and credit_check_required and card_check is not True:
            reasons.append("does_not_meet_credit_check_preference")
        if card_name is not None and card_min_score is not None:
            needed_score = decimal_value(card_min_score, f"candidates[{index}].card_min_credit_score")
            if score is None:
                reasons.append("credit_score_not_provided")
            elif score < needed_score:
                reasons.append("credit_score_below_minimum")

        record = {
            "account_class": account_class,
            "card_name": card_name,
            "reasons": reasons,
        }
        if reasons:
            ineligible.append(record)
            continue

        effective_apy = base_apy + bonus
        interest = (deposit * effective_apy / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        net_value = (interest - annual_fee).quantize(CENT, rounding=ROUND_HALF_UP)
        record.update({
            "effective_apy_percent": str(effective_apy),
            "estimated_first_year_savings_interest": money(interest),
            "card_annual_fee": money(annual_fee),
            "estimated_first_year_net_value": money(net_value),
            "conditional_card_bonus": card_name is not None and bonus > 0,
        })
        eligible.append(record)

    eligible.sort(key=lambda item: (Decimal(item["estimated_first_year_net_value"]),
                                    Decimal(item["effective_apy_percent"])), reverse=True)
    return {
        "deposit_amount": money(deposit),
        "eligible_ranked": eligible,
        "ineligible": ineligible,
        "note": "Card-related bonuses remain conditional on satisfying product eligibility and card approval/active status.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(1)
