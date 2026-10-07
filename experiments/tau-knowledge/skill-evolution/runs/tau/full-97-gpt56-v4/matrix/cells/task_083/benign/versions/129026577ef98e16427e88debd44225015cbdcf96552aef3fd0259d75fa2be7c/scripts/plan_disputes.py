#!/usr/bin/env python3
"""Deterministic preflight for debit-card dispute facts; JSON stdin to JSON stdout."""
import json
import sys
from collections import Counter

ACTIONS = {
    "card_present_fraud": "close_and_reissue", "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active", "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active", "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active", "recurring_charge_after_cancellation": "keep_active",
}
LIMITS = {"Entry": 2, "Mid": 3, "Premium": 4, "Elite": 5}
MIN_LIMIT = min(LIMITS.values())
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def provisional(item):
    required = (item.get("statement_timely") is True and item.get("written_statement_provided") is True
                and item.get("account_open_unrestricted") is True and item.get("category") in PC_CATEGORIES)
    third_party_atm = item.get("category") == "atm_cash_discrepancy" and item.get("third_party_atm") is True
    excluded = ((item.get("merchant_contact_required") is True and item.get("contacted_merchant") is not True and not third_party_atm)
                or item.get("pin_compromised") == "yes_shared"
                or item.get("new_account_card_not_present") is True)
    return required and not excluded


def main():
    data = json.load(sys.stdin)
    accounts = data.get("account_limits", {})
    items = data.get("items", [])
    requested = Counter(x.get("account_id") for x in items if x.get("account_id"))
    output, by_card = [], {}
    seen_duplicate_groups = set()

    for index, item in enumerate(items):
        errors, account_id, category = [], item.get("account_id"), item.get("category")
        amount, debit = item.get("amount"), item.get("matched_debit_amount")
        if category not in ACTIONS:
            errors.append("invalid_or_missing_category")
        if not is_number(amount) or amount < 1:
            errors.append("amount_must_be_at_least_1")
        if is_number(debit) and is_number(amount) and amount > abs(debit):
            errors.append("disputed_amount_exceeds_matched_debit")
        age = item.get("age_days")
        if not is_number(age): errors.append("missing_transaction_age")
        elif age > 60: errors.append("transaction_older_than_60_days")
        for key, error in (("verified", "customer_not_verified"), ("transaction_matched", "transaction_not_authoritatively_matched"), ("linked_account_open", "linked_checking_not_open")):
            if item.get(key) is False: errors.append(error)
        if category == "duplicate_charge":
            group = item.get("duplicate_group")
            rank = item.get("duplicate_rank")
            if not group or not isinstance(rank, int) or isinstance(rank, bool):
                errors.append("missing_duplicate_earliest_selection_facts")
            elif rank != 1:
                errors.append("duplicate_must_file_earliest_transaction")
            elif group in seen_duplicate_groups:
                errors.append("duplicate_group_requested_more_than_once")
            else:
                seen_duplicate_groups.add(group)
        if not account_id or account_id not in accounts:
            errors.append("missing_account_limit_facts")
        else:
            facts, tier, existing = accounts[account_id], accounts[account_id].get("tier"), accounts[account_id].get("existing_active")
            if not isinstance(existing, int) or isinstance(existing, bool):
                errors.append("invalid_account_limit_facts")
            elif tier in LIMITS and existing + requested[account_id] > LIMITS[tier]:
                errors.append("open_dispute_limit_exceeded")
            elif tier not in LIMITS and existing + requested[account_id] > MIN_LIMIT:
                errors.append("unmapped_tier_limit_not_confirmed")
        action = ACTIONS.get(category)
        output.append({"index": index, "account_id": account_id, "card_id": item.get("card_id"), "card_action": action,
                       "provisional_credit_eligible": provisional(item), "errors": errors})
        card = item.get("card_id")
        if card and action and (card not in by_card or SEVERITY[action] > SEVERITY[by_card[card]]): by_card[card] = action

    totals = {aid: {"existing_active": facts.get("existing_active"), "new_filings_requested": requested[aid],
                    "tier": facts.get("tier"), "maximum": LIMITS.get(facts.get("tier"), MIN_LIMIT)} for aid, facts in accounts.items()}
    json.dump({"items": output, "account_totals": totals, "most_severe_action_by_card": by_card}, sys.stdout)

if __name__ == "__main__":
    main()
