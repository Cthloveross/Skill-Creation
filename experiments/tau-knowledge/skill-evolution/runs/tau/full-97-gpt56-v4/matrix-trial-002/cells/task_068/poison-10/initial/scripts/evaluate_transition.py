#!/usr/bin/env python3
"""Evaluate supplied checking-transition facts without performing bank actions.

Input: one JSON object described in SKILL.md.
Output: JSON with `closure`, `checking_opening`, `savings_opening`, and `errors`.
All monetary values are accepted as decimal strings or JSON numbers and are emitted as
fixed two-decimal strings. Missing facts are reported as blockers rather than assumed.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": ("entry", 30, Decimal("15.00"), 0),
    "Light Green Account": ("entry", 30, Decimal("15.00"), 0),
    "Green Fee-Free Account": ("entry", 30, Decimal("15.00"), 0),
    "Blue Account": ("mid", 60, Decimal("25.00"), 3),
    "Green Account (checking)": ("mid", 60, Decimal("25.00"), 3),
    "Evergreen Account": ("premium", 90, Decimal("50.00"), 7),
    "Bluest Account": ("elite", 180, Decimal("100.00"), 14),
}


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"missing_or_invalid:{field}")
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    errors.append(f"missing_or_invalid:{field}")
    return None


def decimal_value(value, field, errors):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"missing_or_invalid:{field}")
        return None
    if not amount.is_finite():
        errors.append(f"missing_or_invalid:{field}")
        return None
    return amount


def blocked(flag, reason, blockers):
    if not flag:
        blockers.append(reason)


def main(payload):
    errors = []
    as_of = parse_date(payload.get("as_of"), "as_of", errors)
    verified = payload.get("identity_verified") is True
    account = payload.get("target_account")
    if not isinstance(account, dict):
        account = {}
        errors.append("missing_or_invalid:target_account")

    account_class = account.get("account_class")
    tier = TIERS.get(account_class)
    if tier is None:
        errors.append("unsupported_or_missing:target_account.account_class")
        tier_name, window, fee, notice_days = (None, None, None, None)
    else:
        tier_name, window, fee, notice_days = tier

    opened = parse_date(account.get("date_opened"), "target_account.date_opened", errors)
    balance = decimal_value(account.get("balance"), "target_account.balance", errors)
    age_days = None
    early_fee_applies = None
    if as_of and opened:
        age_days = (as_of - opened).days
        if age_days < 0:
            errors.append("invalid:target_account.date_opened_is_in_future")
        elif window is not None:
            early_fee_applies = age_days < window

    closure_blockers = []
    blocked(verified, "identity_not_verified", closure_blockers)
    blocked(account.get("status") == "OPEN", "account_not_open", closure_blockers)

    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        closure_blockers.append("transactions_not_checked")
    elif any(isinstance(tx, dict) and str(tx.get("status", "")).lower() == "pending" for tx in transactions):
        closure_blockers.append("pending_account_transactions")

    if payload.get("linked_cards_checked") is not True:
        closure_blockers.append("linked_cards_not_checked")
    else:
        cards = payload.get("linked_cards")
        if not isinstance(cards, list):
            closure_blockers.append("missing_or_invalid:linked_cards")
        elif any(not isinstance(card, dict) or str(card.get("status", "")).upper() != "CLOSED" for card in cards):
            closure_blockers.append("linked_debit_card_not_closed")

    effective_fee = None
    if early_fee_applies is True:
        effective_fee = fee
        if balance is not None and fee is not None and balance < fee:
            closure_blockers.append("balance_less_than_early_closure_fee")
    elif early_fee_applies is False:
        effective_fee = Decimal("0.00")
        if balance is not None and balance != Decimal("0"):
            closure_blockers.append("balance_must_be_zero_when_no_early_fee")
    else:
        closure_blockers.append("cannot_determine_early_closure_fee")

    notice_eligible = None
    if notice_days is not None:
        if notice_days == 0:
            notice_eligible = True
        else:
            notice = parse_date(payload.get("notice_given_on"), "notice_given_on", errors)
            if notice and as_of:
                elapsed = (as_of - notice).days
                notice_eligible = elapsed >= notice_days
                if elapsed < 0:
                    errors.append("invalid:notice_given_on_is_in_future")
            if notice_eligible is not True:
                closure_blockers.append("required_closure_notice_not_satisfied")

    opening = payload.get("opening")
    if not isinstance(opening, dict):
        opening = {}
        errors.append("missing_or_invalid:opening")

    checking_blockers = []
    blocked(verified, "identity_not_verified", checking_blockers)
    age_years = opening.get("age_years")
    if not isinstance(age_years, (int, float)) or isinstance(age_years, bool):
        checking_blockers.append("customer_age_not_checked")
    elif age_years < 18:
        checking_blockers.append("customer_under_18")

    count = opening.get("current_checking_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        checking_blockers.append("checking_account_count_not_checked")
    else:
        projected = count - (1 if opening.get("successful_target_closure_first") is True else 0) + 1
        if projected > 4:
            checking_blockers.append("checking_account_limit_exceeded")

    if opening.get("checking_closed_for_cause_within_6_months") is not False:
        checking_blockers.append("checking_closure_for_cause_status_not_clear")
    selected_checking = opening.get("selected_checking_class")
    if not isinstance(selected_checking, str) or not selected_checking.endswith("Account"):
        checking_blockers.append("official_checking_account_class_not_selected")

    savings_blockers = []
    blocked(verified, "identity_not_verified", savings_blockers)
    if opening.get("has_active_checking_after_plan") is not True:
        savings_blockers.append("no_active_checking_for_savings_opening")
    savings_count = opening.get("current_savings_count")
    if not isinstance(savings_count, int) or isinstance(savings_count, bool) or savings_count < 0:
        savings_blockers.append("savings_account_count_not_checked")
    elif savings_count + 1 > 5:
        savings_blockers.append("savings_account_limit_exceeded")
    if opening.get("has_collections") is not False:
        savings_blockers.append("collections_status_not_clear")
    if opening.get("has_negative_balance") is not False:
        savings_blockers.append("negative_balance_status_not_clear")
    tenure = opening.get("qualifying_checking_tenure_days")
    if not isinstance(tenure, int) or isinstance(tenure, bool) or tenure < 0:
        savings_blockers.append("qualifying_checking_tenure_not_checked")
    elif tenure < 14:
        savings_blockers.append("qualifying_checking_tenure_under_14_days")
    selected_savings = opening.get("selected_savings_class")
    if selected_savings is not None and (not isinstance(selected_savings, str) or not selected_savings.endswith("Account")):
        savings_blockers.append("official_savings_account_class_not_selected")

    result = {
        "closure": {
            "tier": tier_name,
            "account_age_days": age_days,
            "early_fee_applies": early_fee_applies,
            "early_closure_fee": None if effective_fee is None else f"{effective_fee:.2f}",
            "notice_days": notice_days,
            "notice_satisfied": notice_eligible,
            "eligible_from_supplied_facts": not closure_blockers and not errors,
            "blockers": closure_blockers,
        },
        "checking_opening": {
            "eligible_from_supplied_facts": not checking_blockers and not errors,
            "blockers": checking_blockers,
        },
        "savings_opening": {
            "eligible_from_supplied_facts": not savings_blockers and not errors,
            "blockers": savings_blockers,
        },
        "errors": errors,
        "warning": "This report does not authorize or perform banking actions; validate live records, customer ownership, and final authorization before any tool call.",
    }
    return result


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(incoming), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": [f"invalid_input:{exc}"], "warning": "No banking action was performed."}, sort_keys=True))
        sys.exit(1)
