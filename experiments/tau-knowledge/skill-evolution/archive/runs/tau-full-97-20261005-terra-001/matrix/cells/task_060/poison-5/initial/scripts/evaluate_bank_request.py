#!/usr/bin/env python3
"""Deterministic banking preflight evaluator. Reads one JSON object from stdin, writes one JSON object."""
import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

CLOSURE_TERMS = {
    "Light Blue Account": (15, 30, 0),
    "Light Green Account": (15, 30, 0),
    "Green Fee-Free Account": (15, 30, 0),
    "Blue Account": (25, 60, 3),
    "Green Account": (25, 60, 3),
    "Evergreen Account": (50, 90, 7),
    "Bluest Account": (100, 180, 14),
}
OPENING_MINIMUMS = {
    "Green Account": Decimal("100"),
    "Silver Account": Decimal("500"),
    "Silver Plus Account": Decimal("1000"),
    "Platinum Account": Decimal("25000"),
    "Platinum Plus Account": Decimal("50000"),
}


def parse_dt(value):
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def to_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def status_open(account):
    return str(account.get("status", "")).upper() in {"OPEN", "ACTIVE"}


def class_for_closure(account):
    klass = str(account.get("account_class", "")).strip()
    # Account data may distinguish Green checking in prose but the class value is Green Account.
    return klass.replace(" (checking)", "")


def main(data):
    now = parse_dt(data.get("now"))
    accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
    identity = data.get("identity_verified") is True
    authority = data.get("authority_confirmed") is True
    output = {
        "closure": {"eligible": None, "blocked_reasons": [], "warnings": []},
        "savings_opening": {"eligible": None, "blocked_reasons": [], "warnings": []},
        "funding": {"eligible": None, "blocked_reasons": [], "warnings": []},
    }

    closure = data.get("closure")
    closing_id = None
    if isinstance(closure, dict):
        closing_id = closure.get("account_id")
        result = output["closure"]
        target = next((a for a in accounts if a.get("account_id") == closing_id), None)
        if not identity:
            result["blocked_reasons"].append("Customer identity is not verified.")
        if not authority:
            result["blocked_reasons"].append("Closure authority is not confirmed.")
        if target is None:
            result["blocked_reasons"].append("Closure target was not found in supplied accounts.")
        else:
            result["account_id"] = closing_id
            if str(target.get("account_type", "")).lower() != "checking":
                result["blocked_reasons"].append("Closure target is not a checking account.")
            if str(target.get("status", "")).upper() != "OPEN":
                result["blocked_reasons"].append("Closure target status must be OPEN.")
            if closure.get("has_pending_transactions") is not False:
                result["blocked_reasons"].append("No conclusive evidence that account has no pending transactions.")
            terms = CLOSURE_TERMS.get(class_for_closure(target))
            opened = parse_dt(target.get("date_opened"))
            balance = to_decimal(target.get("balance"))
            if terms is None:
                result["blocked_reasons"].append("No documented closure tier for this account class.")
            elif now is None or opened is None or balance is None:
                result["blocked_reasons"].append("Current time, opening date, or balance is invalid or missing.")
            else:
                fee, window_days, notice_days = terms
                age_days = (now.date() - opened.date()).days
                fee_applies = age_days < window_days
                required_balance = Decimal(fee) if fee_applies else Decimal("0")
                result.update({"early_fee_applies": fee_applies, "early_fee": str(Decimal(fee) if fee_applies else Decimal("0")), "notice_days": notice_days, "required_balance": str(required_balance)})
                if fee_applies and balance < required_balance:
                    result["blocked_reasons"].append("Balance is below the applicable early-closure fee.")
                if not fee_applies and balance != Decimal("0"):
                    result["blocked_reasons"].append("Balance must be exactly zero when no early-closure fee applies.")
                notice_at = parse_dt(closure.get("notice_given_at"))
                if notice_days:
                    if notice_at is None:
                        result["blocked_reasons"].append("Required closure notice has not been evidenced.")
                    else:
                        eligible_at = notice_at + timedelta(days=notice_days)
                        result["earliest_closure_at"] = eligible_at.isoformat()
                        if now < eligible_at:
                            result["blocked_reasons"].append("Required closure notice period has not elapsed.")
            if closure.get("all_linked_cards_closed") is not True:
                result["blocked_reasons"].append("All linked active or pending debit cards must be closed first.")
        result["eligible"] = not result["blocked_reasons"]

    savings = data.get("savings")
    if isinstance(savings, dict):
        result = output["savings_opening"]
        if not identity:
            result["blocked_reasons"].append("Customer identity is not verified.")
        if not authority:
            result["blocked_reasons"].append("Customer authority is not confirmed.")
        klass = savings.get("account_class")
        if not isinstance(klass, str) or not klass.endswith("Account"):
            result["blocked_reasons"].append("Savings account class must be an exact official name ending in Account.")
        elif klass not in OPENING_MINIMUMS:
            result["warnings"].append("No packaged opening minimum is known for this account class; verify its product terms.")
        personal_savings = [a for a in accounts if str(a.get("account_type", "")).lower() == "savings"]
        if len(personal_savings) >= 5:
            result["blocked_reasons"].append("Customer already holds five or more personal savings accounts.")
        unknown_collections = [a.get("account_id") for a in accounts if not isinstance(a.get("in_collections"), bool)]
        if unknown_collections:
            result["blocked_reasons"].append("Collections status is missing for one or more accounts.")
        if any(a.get("in_collections") is True for a in accounts):
            result["blocked_reasons"].append("Customer has an account in collections.")
        for account in accounts:
            balance = to_decimal(account.get("balance"))
            if balance is None:
                result["blocked_reasons"].append("An account balance is missing or invalid.")
                break
            if balance < 0:
                result["blocked_reasons"].append("Customer has a negative account balance.")
                break
        retained = [a for a in accounts if a.get("account_id") != closing_id and str(a.get("account_type", "")).lower() == "checking" and status_open(a)]
        eligible_checkings = []
        if now is None:
            result["blocked_reasons"].append("Current time is missing or invalid for checking-tenure evaluation.")
        else:
            for account in retained:
                opened = parse_dt(account.get("date_opened"))
                if opened and (now.date() - opened.date()).days >= 14:
                    eligible_checkings.append(account.get("account_id"))
        if not eligible_checkings:
            result["blocked_reasons"].append("No retained active checking account with at least 14 days tenure was found.")
        result["retained_eligible_checking_ids"] = eligible_checkings
        result["savings_count"] = len(personal_savings)
        result["eligible"] = not result["blocked_reasons"]

        funding = output["funding"]
        if savings.get("immediate_funding_authorized") is not True:
            funding["warnings"].append("Immediate funding is not authorized; state the 30-day funding deadline.")
            funding["eligible"] = False
        else:
            source_id = savings.get("source_account_id")
            source = next((a for a in accounts if a.get("account_id") == source_id), None)
            amount = to_decimal(savings.get("opening_deposit"))
            minimum = OPENING_MINIMUMS.get(klass)
            if source is None:
                funding["blocked_reasons"].append("Funding source account was not found.")
            elif not status_open(source):
                funding["blocked_reasons"].append("Funding source is not OPEN or ACTIVE.")
            if amount is None or amount <= 0:
                funding["blocked_reasons"].append("Funding amount must be a positive USD value.")
            elif minimum is not None and amount < minimum:
                funding["blocked_reasons"].append("Funding amount is below the documented opening minimum.")
            if source is not None and amount is not None:
                balance = to_decimal(source.get("balance"))
                if balance is None or balance < amount:
                    funding["blocked_reasons"].append("Funding source has insufficient available balance.")
            funding["source_account_id"] = source_id
            funding["amount"] = str(amount) if amount is not None else None
            funding["eligible"] = not funding["blocked_reasons"]
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
