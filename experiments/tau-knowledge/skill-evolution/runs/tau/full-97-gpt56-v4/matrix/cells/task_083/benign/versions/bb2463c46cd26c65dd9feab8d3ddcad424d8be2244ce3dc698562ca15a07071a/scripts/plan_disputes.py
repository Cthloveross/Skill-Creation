#!/usr/bin/env python3
"""Validate debit-dispute planning facts from JSON stdin; emit JSON to stdout."""
import json
import sys
from collections import Counter

ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active",
    "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active",
    "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active",
    "recurring_charge_after_cancellation": "keep_active",
}
LIMITS = {"Entry": 2, "Mid": 3, "Premium": 4, "Elite": 5}
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud",
    "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge",
}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def provisional(item):
    required = (
        item.get("statement_timely") is True
        and item.get("written_statement_provided") is True
        and item.get("account_open_unrestricted") is True
        and item.get("category") in PC_CATEGORIES
    )
    # Apply documented exclusions only when their applicability is explicit.
    excluded = (
        (item.get("merchant_contact_required") is True and item.get("contacted_merchant") is not True)
        or item.get("pin_compromised") == "yes_shared"
        or item.get("new_account_card_not_present") is True
    )
    return required and not excluded


def main():
    data = json.load(sys.stdin)
    accounts = data.get("account_limits", {})
    items = data.get("items", [])
    additions = Counter(x.get("account_id") for x in items if x.get("account_id"))
    output_items = []
    per_card = {}

    for index, item in enumerate(items):
        errors = []
        category = item.get("category")
        account_id = item.get("account_id")
        if category not in ACTIONS:
            errors.append("invalid_or_missing_category")
        amount = item.get("amount")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
            errors.append("amount_must_be_at_least_1")
        age = item.get("age_days")
        if not isinstance(age, (int, float)) or isinstance(age, bool):
            errors.append("missing_transaction_age")
        elif age > 60:
            errors.append("transaction_older_than_60_days")
        if item.get("verified") is False:
            errors.append("customer_not_verified")
        if item.get("transaction_matched") is False:
            errors.append("transaction_not_authoritatively_matched")
        if item.get("linked_account_open") is False:
            errors.append("linked_checking_not_open")
        if not account_id or account_id not in accounts:
            errors.append("missing_account_limit_facts")
        else:
            facts = accounts[account_id]
            tier = facts.get("tier")
            existing = facts.get("existing_active")
            if tier not in LIMITS or not isinstance(existing, int) or isinstance(existing, bool):
                errors.append("invalid_account_limit_facts")
            elif existing + additions[account_id] > LIMITS[tier]:
                errors.append("open_dispute_limit_exceeded")
        action = ACTIONS.get(category)
        eligible = provisional(item)
        output_items.append({
            "index": index,
            "account_id": account_id,
            "card_id": item.get("card_id"),
            "card_action": action,
            "provisional_credit_eligible": eligible,
            "errors": errors,
        })
        card = item.get("card_id")
        if card and action and (card not in per_card or SEVERITY[action] > SEVERITY[per_card[card]]):
            per_card[card] = action

    account_totals = {}
    for account_id, facts in accounts.items():
        account_totals[account_id] = {
            "existing_active": facts.get("existing_active"),
            "new_filings_requested": additions[account_id],
            "tier": facts.get("tier"),
            "maximum": LIMITS.get(facts.get("tier")),
        }
    json.dump({"items": output_items, "account_totals": account_totals,
               "most_severe_action_by_card": per_card}, sys.stdout)


if __name__ == "__main__":
    main()
