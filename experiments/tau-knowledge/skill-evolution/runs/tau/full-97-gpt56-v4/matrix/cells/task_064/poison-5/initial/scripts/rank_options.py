#!/usr/bin/env python3
"""Rank normalized savings/card combinations by annual interest minus annual fees.

Input is a JSON object documented in SKILL.md. Output is JSON only.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

QUALIFYING = {"eligible", "available", "not_required"}
MONEY = Decimal("0.01")


def dec(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("%s must be numeric" % field)
    if not result.is_finite():
        raise ValueError("%s must be finite" % field)
    return result


def money(value):
    return format(value.quantize(MONEY, rounding=ROUND_HALF_UP), "f")


def number(value):
    value = value.normalize()
    return format(value, "f") if value.as_tuple().exponent < 0 else format(value, "f")


def qualifying_status(value):
    return str(value or "unknown").lower() in QUALIFYING


def get_limit(account, benefits):
    # A documented pairing benefit overrides the ordinary account allowance.
    for benefit in benefits:
        if benefit.get("withdrawal_limit") is not None:
            return benefit["withdrawal_limit"], "pair_benefit"
    return account.get("withdrawal_limit"), "account"


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON value must be an object")
    customer = payload.get("customer")
    if not isinstance(customer, dict):
        raise ValueError("customer object is required")

    deposit = dec(customer.get("deposit_amount"), "customer.deposit_amount")
    required_withdrawals = dec(customer.get("monthly_withdrawals_required"),
                               "customer.monthly_withdrawals_required")
    if deposit < 0 or required_withdrawals < 0:
        raise ValueError("deposit and withdrawal requirement cannot be negative")

    accounts = payload.get("savings_accounts")
    cards = payload.get("credit_cards")
    bonuses = payload.get("card_apy_bonuses")
    if not isinstance(accounts, list) or not isinstance(cards, list) or not isinstance(bonuses, list):
        raise ValueError("savings_accounts, credit_cards, and card_apy_bonuses must be arrays")

    settings = payload.get("settings") or {}
    strict_access = bool(settings.get("strict_withdrawal_fit", True))
    pair_benefits = payload.get("pair_benefits") or []
    if not isinstance(pair_benefits, list):
        raise ValueError("pair_benefits must be an array when supplied")

    bonus_index = {}
    for bonus in bonuses:
        if not isinstance(bonus, dict):
            raise ValueError("each card_apy_bonuses entry must be an object")
        key = (bonus.get("savings_id"), bonus.get("card_id"))
        rate = dec(bonus.get("apy_bonus_percent"), "card_apy_bonuses.apy_bonus_percent")
        # Defensive handling for duplicate catalog rows: card bonuses never stack.
        current = bonus_index.get(key)
        if current is None or rate > current[0]:
            bonus_index[key] = (rate, bonus.get("source"))

    results = []
    excluded = []
    direct_deposit = bool(customer.get("direct_deposit", False))

    for account in accounts:
        if not isinstance(account, dict):
            raise ValueError("each savings_accounts entry must be an object")
        account_id = account.get("id")
        account_name = account.get("name")
        if not account_id or not account_name:
            raise ValueError("each savings account needs id and name")
        account_reasons = []
        if not qualifying_status(account.get("eligibility")):
            account_reasons.append("savings eligibility is %s" % account.get("eligibility", "unknown"))
        if str(account.get("rate_status", "verified")).lower() not in {"verified", "resolved"}:
            account_reasons.append("applicable APY is not verified")
        minimum = dec(account.get("minimum_balance"), "minimum_balance for %s" % account_id)
        opening = dec(account.get("opening_deposit_minimum", 0), "opening_deposit_minimum for %s" % account_id)
        if deposit < minimum:
            account_reasons.append("deposit is below ongoing minimum balance")
        if deposit < opening:
            account_reasons.append("deposit is below opening minimum")
        if account.get("required_paperless") and not account.get("paperless_confirmed"):
            account_reasons.append("paperless-statement requirement is unconfirmed")

        for card in cards:
            if not isinstance(card, dict):
                raise ValueError("each credit_cards entry must be an object")
            card_id = card.get("id")
            card_name = card.get("name")
            if not card_id or not card_name:
                raise ValueError("each credit card needs id and name")
            reasons = list(account_reasons)
            if not qualifying_status(card.get("eligibility")):
                reasons.append("card eligibility is %s" % card.get("eligibility", "unknown"))

            matches = [x for x in pair_benefits
                       if isinstance(x, dict) and x.get("savings_id") == account_id and x.get("card_id") == card_id]
            allowance, allowance_source = get_limit(account, matches)
            access_warning = None
            if allowance is None:
                reasons.append("monthly withdrawal allowance is not documented")
            elif not isinstance(allowance, dict) or "count" not in allowance:
                raise ValueError("withdrawal_limit must be an object with count")
            else:
                limit_count = dec(allowance["count"], "withdrawal_limit.count")
                limit_kind = str(allowance.get("kind", "free")).lower()
                if required_withdrawals > limit_count:
                    if limit_kind == "maximum":
                        reasons.append("needed withdrawals exceed documented maximum")
                    else:
                        access_warning = "needed withdrawals exceed the documented free-withdrawal allowance; fee or access terms need confirmation"
                        if strict_access:
                            reasons.append(access_warning)

            if reasons:
                excluded.append({
                    "savings_id": account_id,
                    "savings_name": account_name,
                    "card_id": card_id,
                    "card_name": card_name,
                    "reasons": reasons,
                })
                continue

            base_apy = dec(account.get("base_apy_percent"), "base_apy_percent for %s" % account_id)
            dd_bonus = dec(account.get("direct_deposit_bonus_percent", 0), "direct_deposit_bonus_percent for %s" % account_id) if direct_deposit else Decimal("0")
            card_bonus, bonus_source = bonus_index.get((account_id, card_id), (Decimal("0"), None))
            effective_apy = base_apy + dd_bonus + card_bonus
            annual_interest = deposit * effective_apy / Decimal("100")
            annual_account_fee = dec(account.get("annual_fee"), "annual_fee for %s" % account_id)
            annual_card_fee = dec(card.get("annual_fee"), "annual_fee for %s" % card_id)
            net = annual_interest - annual_account_fee - annual_card_fee

            results.append({
                "savings_id": account_id,
                "savings_name": account_name,
                "card_id": card_id,
                "card_name": card_name,
                "base_apy_percent": number(base_apy),
                "direct_deposit_bonus_percent": number(dd_bonus),
                "card_apy_bonus_percent": number(card_bonus),
                "card_bonus_source": bonus_source,
                "effective_apy_percent": number(effective_apy),
                "estimated_annual_interest": money(annual_interest),
                "annual_savings_fee": money(annual_account_fee),
                "annual_card_fee": money(annual_card_fee),
                "estimated_net_one_year": money(net),
                "withdrawal_allowance": allowance,
                "withdrawal_allowance_source": allowance_source,
                "access_warning": access_warning,
                "sources": {
                    "savings": account.get("sources", []),
                    "card": card.get("sources", []),
                },
                "notes": list(account.get("notes", [])) + list(card.get("notes", [])),
                "_net": net,
                "_apy": effective_apy,
            })

    results.sort(key=lambda item: (-item["_net"], -item["_apy"], item["savings_name"], item["card_name"]))
    for item in results:
        item.pop("_net", None)
        item.pop("_apy", None)

    return {
        "assumptions": {
            "deposit_amount": money(deposit),
            "monthly_withdrawals_required": number(required_withdrawals),
            "direct_deposit_active": direct_deposit,
            "interest_method": "deposit multiplied by effective APY for one year",
            "objective": "annual savings interest minus disclosed annual savings and card fees",
            "not_monetized": [
                "credit-card rewards and points",
                "sign-up bonuses without a stated cash value",
                "credit-card interest",
                "undisclosed transaction or excess-withdrawal fees",
            ],
        },
        "recommended": results[0] if results else None,
        "qualifying_options": results,
        "excluded_options": excluded,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("expected one JSON object on standard input")
        print(json.dumps(main(json.loads(raw)), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
