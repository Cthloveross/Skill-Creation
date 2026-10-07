#!/usr/bin/env python3
"""Assess deterministic account-closure and savings-opening prerequisites.

Reads one JSON object from stdin and emits one JSON object. This helper performs
no I/O other than stdin/stdout and makes no banking actions.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TIER_RULES = {
    "Light Blue Account": (15, 30, 0),
    "Light Green Account": (15, 30, 0),
    "Green Fee-Free Account": (15, 30, 0),
    "Blue Account": (25, 60, 3),
    "Green Account": (25, 60, 3),  # Applicable only when target is checking.
    "Evergreen Account": (50, 90, 7),
    "Bluest Account": (100, 180, 14),
}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must use YYYY-MM-DD or MM/DD/YYYY")


def money(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a numeric USD amount")


def is_active_or_open(status):
    return isinstance(status, str) and status.upper() in {"ACTIVE", "OPEN"}


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    today = parse_date(payload.get("as_of"), "as_of")
    accounts = payload.get("accounts")
    transactions = payload.get("transactions", [])
    cards = payload.get("cards", [])
    target_id = payload.get("target_account_id")
    if not isinstance(accounts, list) or not isinstance(transactions, list) or not isinstance(cards, list):
        raise ValueError("accounts, transactions, and cards must be arrays")
    if not isinstance(target_id, str) or not target_id:
        raise ValueError("target_account_id is required")

    target = next((a for a in accounts if isinstance(a, dict) and a.get("account_id") == target_id), None)
    closure = {"target_found": target is not None, "blockers": [], "manual_review": [], "fee_usd": None, "notice_days": None, "notice_complete_on": None}
    card_review = {"cards_requiring_closure": [], "ineligible_cards": [], "age_restricted_cards": [], "manual_review": ["Confirm no pending card refunds; this helper cannot establish refund status."]}

    if target is None:
        closure["blockers"].append("Requested checking account was not found.")
    else:
        if str(target.get("account_type", "")).lower() != "checking":
            closure["blockers"].append("Requested account is not a checking account.")
        if target.get("status") != "OPEN":
            closure["blockers"].append("Checking account status must be OPEN for closure.")
        pending = [t for t in transactions if isinstance(t, dict) and t.get("account_id") == target_id and str(t.get("status", "")).lower() == "pending"]
        if pending:
            closure["blockers"].append("Checking account has pending transactions.")
        account_class = target.get("account_class")
        rule = TIER_RULES.get(account_class)
        if rule is None:
            closure["manual_review"].append("Account class has no packaged checking-closure tier rule.")
        else:
            fee, fee_window, notice_days = rule
            opened = parse_date(target.get("date_opened"), "target.date_opened")
            age_days = (today - opened).days
            if age_days < 0:
                closure["blockers"].append("Account opening date is in the future.")
            fee_applies = age_days < fee_window
            required_fee = Decimal(fee) if fee_applies else Decimal("0")
            balance = money(target.get("balance"), "target.balance")
            closure.update({
                "account_age_days": age_days,
                "early_fee_applies": fee_applies,
                "fee_usd": f"{required_fee:.2f}",
                "notice_days": notice_days,
                "notice_complete_on": (today.fromordinal(today.toordinal() + notice_days)).isoformat(),
            })
            if fee_applies and balance < required_fee:
                closure["blockers"].append("Balance is below the applicable early-closure fee.")
            if not fee_applies and balance != Decimal("0"):
                closure["blockers"].append("Balance must be exactly zero when no early-closure fee applies.")

        for card in cards:
            if not isinstance(card, dict) or card.get("account_id") != target_id:
                continue
            status = str(card.get("status", "")).upper()
            card_id = card.get("card_id")
            if status == "CLOSED":
                continue
            if status not in {"ACTIVE", "PENDING"}:
                card_review["ineligible_cards"].append({"card_id": card_id, "status": status})
                closure["blockers"].append("An associated debit card is not in a closable status.")
                continue
            issued = parse_date(card.get("date_issued"), f"card {card_id} date_issued")
            age = (today - issued).days
            item = {"card_id": card_id, "status": status, "age_days": age}
            card_review["cards_requiring_closure"].append(item)
            if age < 14:
                card_review["age_restricted_cards"].append(item)
                card_review["manual_review"].append(f"Card {card_id} is under 14 days old; only lost, stolen, or fraud_suspected bypasses age.")

    savings = {"blockers": [], "qualifying_checking_accounts": [], "savings_account_count": 0, "manual_review": []}
    for account in accounts:
        if not isinstance(account, dict):
            savings["manual_review"].append("An account record is malformed.")
            continue
        try:
            balance = money(account.get("balance"), f"account {account.get('account_id')} balance")
        except ValueError as exc:
            savings["manual_review"].append(str(exc))
            continue
        status = str(account.get("status", ""))
        if status.upper() == "COLLECTIONS":
            savings["blockers"].append("At least one account is in collections.")
        if balance < 0:
            savings["blockers"].append("At least one account has a negative balance.")
        if str(account.get("account_type", "")).lower() == "savings":
            savings["savings_account_count"] += 1
        if account.get("account_id") != target_id and str(account.get("account_type", "")).lower() == "checking" and is_active_or_open(status):
            try:
                opened = parse_date(account.get("date_opened"), f"account {account.get('account_id')} date_opened")
                tenure = (today - opened).days
                if tenure >= 14:
                    savings["qualifying_checking_accounts"].append({"account_id": account.get("account_id"), "tenure_days": tenure, "status": status})
            except ValueError as exc:
                savings["manual_review"].append(str(exc))
    if not savings["qualifying_checking_accounts"]:
        savings["blockers"].append("No other active/open checking account with at least 14 days tenure was found.")
    if savings["savings_account_count"] >= 5:
        savings["blockers"].append("Customer already has five or more savings accounts.")
    savings["manual_review"].append("Confirm all returned savings accounts are personal and verify collections data is complete.")

    return {"closure": closure, "linked_debit_cards": card_review, "savings_eligibility_after_target_closure": savings}


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
