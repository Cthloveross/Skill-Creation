#!/usr/bin/env python3
"""Produce a deterministic eligibility, closure, and APY-benefit checklist.

Input is one JSON object on stdin. No fields are hardcoded to a particular
customer or product. Expected fields:
{
  "current_date": "YYYY-MM-DD" or timestamp beginning with that date,
  "identity_verified": true|false,                 # optional; false if absent
  "accounts": [{"account_id": str, "account_type": "checking"|"savings",
                "account_class": str, "status": str, "balance": number,
                "date_opened": "YYYY-MM-DD", "pending_transactions": bool,
                "in_collections": bool}],
  "savings_account_limit": 5, "minimum_checking_tenure_days": 14,
  "requested_savings_class": str,                  # optional
  "closure_account_id": str,                        # optional
  "closure_policies": {"Account class": {"early_fee": 25,
       "early_fee_days": 60, "notice_days": 3}},  # optional
  "expected_savings_balance": number,               # optional
  "benefit_policy": {                               # optional
    "base_tiers": [{"minimum_balance": 0, "apy": 3.0}],
    "checking_boosts": {"Checking class": 0.35},
    "card_bonuses": {"Card class": 0.20},
    "cards": [{"card_class": str, "status": "OPEN"}],
    "direct_deposit_active": true|false,
    "direct_deposit_bonus": 0.25,
    "relationship_qualified": true|false,
    "relationship_bonus": 0.025
  }
}

For a checking boost, `checking_boosts` must already correspond to the chosen
savings class. This prevents the helper from assuming a product pairing.
The output is JSON containing blocking/unknown conditions, a closure analysis,
and an APY-component estimate. It performs no tool calls and changes no state.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def number(value):
    """Return a JSON-safe float for Decimal values."""
    return float(value)


def active(account):
    return str(account.get("status", "")).upper() == "OPEN"


def opening_check(data, accounts, today):
    blockers, unknowns = [], []
    if data.get("identity_verified") is not True:
        blockers.append("Identity verification has not been confirmed and logged.")

    limit = data.get("savings_account_limit", 5)
    tenure_required = data.get("minimum_checking_tenure_days", 14)
    if not isinstance(limit, int) or limit < 1:
        unknowns.append("Savings-account limit is missing or invalid.")
    if not isinstance(tenure_required, int) or tenure_required < 0:
        unknowns.append("Checking-tenure requirement is missing or invalid.")

    savings = [a for a in accounts if str(a.get("account_type", "")).lower() == "savings"]
    if isinstance(limit, int) and limit >= 1 and len(savings) >= limit:
        blockers.append("Customer has reached the personal savings-account limit.")

    checking = [a for a in accounts if str(a.get("account_type", "")).lower() == "checking" and active(a)]
    qualified_checking = False
    if not checking:
        blockers.append("No active checking account was found.")
    elif today is None:
        unknowns.append("Current date is required to assess checking tenure.")
    else:
        for account in checking:
            opened = parse_date(account.get("date_opened"))
            if opened is None:
                continue
            if (today - opened).days >= tenure_required:
                qualified_checking = True
        if not qualified_checking:
            if any(parse_date(a.get("date_opened")) is None for a in checking):
                unknowns.append("At least one active checking opening date is unavailable.")
            else:
                blockers.append("No active checking account meets the required tenure.")

    missing_balance = False
    collections_unknown = False
    for account in accounts:
        balance = money(account.get("balance"))
        if balance is None:
            missing_balance = True
        elif balance < 0:
            blockers.append("An account has a negative balance.")
        if account.get("in_collections") is True:
            blockers.append("An account is in collections.")
        elif "in_collections" not in account:
            collections_unknown = True
    if missing_balance:
        unknowns.append("One or more account balances are unavailable.")
    if collections_unknown:
        unknowns.append("Collections status has not been supplied for every account.")
    if not data.get("requested_savings_class"):
        blockers.append("No exact official savings account class has been selected.")

    return {"eligible": not blockers and not unknowns,
            "blocking_items": sorted(set(blockers)), "unknowns": sorted(set(unknowns)),
            "savings_account_count": len(savings), "active_checking_count": len(checking)}


def closure_check(data, accounts, today):
    closure_id = data.get("closure_account_id")
    if not closure_id:
        return {"requested": False}
    account = next((a for a in accounts if a.get("account_id") == closure_id), None)
    if account is None:
        return {"requested": True, "assessable": False,
                "blocking_items": ["Requested closure account was not found."], "unknowns": []}

    blockers, unknowns = [], []
    if not active(account):
        blockers.append("Account status is not OPEN.")
    if account.get("pending_transactions") is True:
        blockers.append("Account has pending transactions.")
    elif "pending_transactions" not in account:
        unknowns.append("Pending-transaction status is unavailable.")

    policy = (data.get("closure_policies") or {}).get(account.get("account_class"))
    if not isinstance(policy, dict):
        unknowns.append("No closure policy was supplied for this account class.")
        return {"requested": True, "account_id": closure_id, "assessable": False,
                "blocking_items": blockers, "unknowns": unknowns}

    fee = money(policy.get("early_fee"))
    fee_days = policy.get("early_fee_days")
    notice_days = policy.get("notice_days")
    opened = parse_date(account.get("date_opened"))
    balance = money(account.get("balance"))
    if fee is None or not isinstance(fee_days, int) or not isinstance(notice_days, int):
        unknowns.append("Closure policy has invalid fee, fee-period, or notice data.")
    if today is None or opened is None:
        unknowns.append("Current date and account opening date are required for closure timing.")
    if balance is None:
        unknowns.append("Closure account balance is unavailable.")
    if unknowns:
        return {"requested": True, "account_id": closure_id, "assessable": False,
                "blocking_items": blockers, "unknowns": unknowns}

    age_days = (today - opened).days
    early_fee_applies = age_days < fee_days
    required_balance = fee if early_fee_applies else Decimal("0")
    balance_rule_met = balance >= fee if early_fee_applies else balance == 0
    if not balance_rule_met:
        blockers.append("Balance does not satisfy the applicable closure balance rule.")
    earliest = date.fromordinal(today.toordinal() + notice_days).isoformat()
    return {
        "requested": True, "account_id": closure_id, "assessable": True,
        "account_age_days": age_days, "early_fee_applies": early_fee_applies,
        "early_fee": number(fee) if early_fee_applies else 0.0,
        "required_balance": number(required_balance), "balance_rule_met": balance_rule_met,
        "pending_clear": account.get("pending_transactions") is False,
        "notice_days": notice_days, "earliest_close_date": earliest,
        "immediate_close_allowed": notice_days == 0 and not blockers,
        "blocking_items": sorted(set(blockers)), "unknowns": []
    }


def benefits_check(data, accounts):
    policy = data.get("benefit_policy")
    if not isinstance(policy, dict):
        return {"available": False, "components": [],
                "unknowns": ["No benefit policy was supplied."], "complete": False}
    components, unknowns = [], []
    total = Decimal("0")
    expected = money(data.get("expected_savings_balance"))
    tiers = policy.get("base_tiers")
    if expected is None:
        unknowns.append("Expected savings balance is required to select a base APY tier.")
    elif not isinstance(tiers, list) or not tiers:
        unknowns.append("Base APY tiers are missing.")
    else:
        eligible_tiers = []
        for tier in tiers:
            minimum, apy = money(tier.get("minimum_balance")), money(tier.get("apy"))
            if minimum is not None and apy is not None and expected >= minimum:
                eligible_tiers.append((minimum, apy))
        if not eligible_tiers:
            unknowns.append("No base APY tier matches the expected balance.")
        else:
            minimum, apy = max(eligible_tiers, key=lambda x: x[0])
            components.append({"category": "base_tier", "apy": number(apy), "minimum_balance": number(minimum)})
            total += apy

    boosts = policy.get("checking_boosts", {})
    if not isinstance(boosts, dict):
        unknowns.append("Checking-boost mapping is invalid.")
    else:
        candidates = []
        for account in accounts:
            value = money(boosts.get(account.get("account_class"))) if active(account) and str(account.get("account_type", "")).lower() == "checking" else None
            if value is not None:
                candidates.append((value, account.get("account_class")))
        if candidates:
            boost, source = max(candidates, key=lambda x: x[0])
            components.append({"category": "highest_checking_boost", "apy": number(boost), "source": source})
            total += boost

    cards = policy.get("cards")
    card_map = policy.get("card_bonuses", {})
    if cards is None:
        unknowns.append("Eligible credit-card holdings were not supplied.")
    elif not isinstance(cards, list) or not isinstance(card_map, dict):
        unknowns.append("Credit-card policy data is invalid.")
    else:
        candidates = [(money(card_map.get(c.get("card_class"))), c.get("card_class")) for c in cards if str(c.get("status", "")).upper() == "OPEN" and money(card_map.get(c.get("card_class"))) is not None]
        if candidates:
            bonus, source = max(candidates, key=lambda x: x[0])
            components.append({"category": "highest_card_bonus", "apy": number(bonus), "source": source})
            total += bonus

    direct = policy.get("direct_deposit_active")
    if direct is True:
        bonus = money(policy.get("direct_deposit_bonus"))
        if bonus is None:
            unknowns.append("Direct-deposit bonus amount is unavailable.")
        else:
            components.append({"category": "direct_deposit_bonus", "apy": number(bonus)})
            total += bonus
    elif direct is None:
        unknowns.append("Direct-deposit status is unknown.")

    relationship = policy.get("relationship_qualified")
    if relationship is True:
        bonus = money(policy.get("relationship_bonus"))
        if bonus is None:
            unknowns.append("Relationship bonus amount is unavailable.")
        else:
            components.append({"category": "relationship_bonus", "apy": number(bonus)})
            total += bonus
    elif relationship is None:
        unknowns.append("Relationship-bonus qualification is unknown.")

    return {"available": True, "components": components, "unknowns": sorted(set(unknowns)),
            "complete": not unknowns, "total_known_apy": number(total) if not unknowns else None}


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
        print(json.dumps({"error": "accounts_must_be_a_list"}))
        return
    today = parse_date(data.get("current_date"))
    accounts = data["accounts"]
    result = {
        "opening_eligibility": opening_check(data, accounts, today),
        "closure": closure_check(data, accounts, today),
        "benefits": benefits_check(data, accounts),
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
