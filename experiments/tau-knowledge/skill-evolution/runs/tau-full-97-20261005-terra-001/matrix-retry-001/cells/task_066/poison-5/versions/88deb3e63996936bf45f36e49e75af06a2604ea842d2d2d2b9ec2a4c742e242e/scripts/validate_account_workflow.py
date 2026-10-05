#!/usr/bin/env python3
"""Evaluate supplied personal-account opening and closure facts without taking action.

Input JSON:
{
  "now": "2025-11-14T03:40:00-05:00",
  "identity_verified": true,
  "accounts": [{"account_id":"...", "account_type":"checking", "account_class":"...",
                "status":"OPEN", "balance":"0", "date_opened":"2025-01-01",
                "in_collections":false, "closed_for_cause_date":null,
                "has_pending_transactions":false}],
  "savings_opening": {"requested": true},
  "checking_opening": {"requested": true, "customer_age": 34},
  "closure": {"requested": true, "account_id":"..."}
}

Output JSON reports passed, failed, and missing evidence. Pending-transaction data should be
obtained from transaction history; an omitted value is treated as missing, never as clear.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation


def parse_date(value, field):
    if not value:
        return None
    text = str(value).strip()
    for parser in (datetime.fromisoformat, lambda x: datetime.strptime(x, "%Y-%m-%d"), lambda x: datetime.strptime(x, "%m/%d/%Y")):
        try:
            return parser(text.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    raise ValueError(f"{field} is not a supported date")


def money(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")


def is_open(account):
    return str(account.get("status", "")).upper() == "OPEN"


def add(result, status, message):
    result[status].append(message)


def closure_terms(account_class, opened, now):
    tiers = {
        "Light Blue Account": (Decimal("15"), 30, 0),
        "Light Green Account": (Decimal("15"), 30, 0),
        "Green Fee-Free Account": (Decimal("15"), 30, 0),
        "Blue Account": (Decimal("25"), 60, 3),
        "Green Account (checking)": (Decimal("25"), 60, 3),
        "Evergreen Account": (Decimal("50"), 90, 7),
        "Bluest Account": (Decimal("100"), 180, 14),
    }
    if account_class not in tiers:
        return None
    fee, days, notice = tiers[account_class]
    early = opened is not None and (now - opened).days < days
    return {"fee": fee if early else Decimal("0"), "early_fee_applies": early, "notice_days": notice}


def main(payload):
    now = parse_date(payload.get("now"), "now")
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("accounts must be a list")
    result = {"passed": [], "failed": [], "missing": [], "closure_terms": None}
    verified = payload.get("identity_verified")
    if verified is True:
        add(result, "passed", "identity_verified")
    else:
        add(result, "missing" if verified is None else "failed", "identity_verified")

    savings_request = payload.get("savings_opening", {}).get("requested", False)
    checking_request = payload.get("checking_opening", {}).get("requested", False)
    closure_request = payload.get("closure", {}).get("requested", False)
    open_checking = [a for a in accounts if str(a.get("account_type", "")).lower() == "checking" and is_open(a)]
    savings = [a for a in accounts if str(a.get("account_type", "")).lower() == "savings"]
    checking = [a for a in accounts if str(a.get("account_type", "")).lower() == "checking"]

    if savings_request:
        if open_checking:
            add(result, "passed", "active_checking_exists")
        else:
            add(result, "failed", "active_checking_exists")
        seasoned = []
        for account in open_checking:
            opened = parse_date(account.get("date_opened"), "checking.date_opened")
            if opened is None:
                add(result, "missing", f"checking_open_date:{account.get('account_id', 'unknown')}")
            elif (now - opened).days >= 14:
                seasoned.append(account)
        if seasoned:
            add(result, "passed", "checking_tenure_at_least_14_days")
        else:
            add(result, "failed", "checking_tenure_at_least_14_days")
        if len(savings) < 5:
            add(result, "passed", "fewer_than_5_savings_accounts")
        else:
            add(result, "failed", "fewer_than_5_savings_accounts")
        for account in accounts:
            identifier = account.get("account_id", "unknown")
            if account.get("in_collections") is None:
                add(result, "missing", f"collections_status:{identifier}")
            elif account.get("in_collections"):
                add(result, "failed", f"no_collections:{identifier}")
            try:
                balance = money(account.get("balance"), f"balance:{identifier}")
            except ValueError:
                add(result, "missing", f"balance:{identifier}")
                continue
            if balance < 0:
                add(result, "failed", f"no_negative_balance:{identifier}")
        if not any(item.startswith("no_collections") for item in result["failed"]):
            add(result, "passed", "no_accounts_in_collections")
        if not any(item.startswith("no_negative_balance") for item in result["failed"]):
            add(result, "passed", "no_negative_balances")

    if checking_request:
        age = payload.get("checking_opening", {}).get("customer_age")
        if age is None:
            add(result, "missing", "customer_age")
        elif isinstance(age, int) and age >= 18:
            add(result, "passed", "customer_at_least_18")
        else:
            add(result, "failed", "customer_at_least_18")
        if len(checking) < 4:
            add(result, "passed", "fewer_than_4_checking_accounts")
        else:
            add(result, "failed", "fewer_than_4_checking_accounts")
        cutoff = now.replace(year=now.year - 1) if False else None
        closed_for_cause_unknown = False
        recent_closed_for_cause = False
        for account in checking:
            value = account.get("closed_for_cause_date")
            if value is None:
                closed_for_cause_unknown = True
                continue
            closed_date = parse_date(value, "closed_for_cause_date")
            if (now - closed_date).days < 183:
                recent_closed_for_cause = True
        if recent_closed_for_cause:
            add(result, "failed", "no_checking_closed_for_cause_in_past_6_months")
        elif closed_for_cause_unknown:
            add(result, "missing", "closed_for_cause_history_in_past_6_months")
        else:
            add(result, "passed", "no_checking_closed_for_cause_in_past_6_months")

    if closure_request:
        account_id = payload.get("closure", {}).get("account_id")
        account = next((a for a in accounts if a.get("account_id") == account_id), None)
        if account is None:
            add(result, "missing", "closure_account_record")
        else:
            if is_open(account):
                add(result, "passed", "closure_account_status_open")
            else:
                add(result, "failed", "closure_account_status_open")
            pending = account.get("has_pending_transactions")
            if pending is None:
                add(result, "missing", "closure_pending_transaction_status")
            elif pending:
                add(result, "failed", "closure_has_no_pending_transactions")
            else:
                add(result, "passed", "closure_has_no_pending_transactions")
            opened = parse_date(account.get("date_opened"), "closure.date_opened")
            terms = closure_terms(account.get("account_class"), opened, now)
            if terms is None:
                add(result, "missing", "closure_tier_for_account_class")
            else:
                result["closure_terms"] = {"early_fee_applies": terms["early_fee_applies"], "fee": str(terms["fee"]), "notice_days": terms["notice_days"]}
                balance = money(account.get("balance"), "closure.balance")
                if terms["fee"] > 0 and balance >= terms["fee"]:
                    add(result, "passed", "closure_balance_covers_early_fee")
                elif terms["fee"] > 0:
                    add(result, "failed", "closure_balance_covers_early_fee")
                elif balance == 0:
                    add(result, "passed", "closure_balance_is_zero")
                else:
                    add(result, "failed", "closure_balance_is_zero")
    result["eligible_from_supplied_data"] = not result["failed"] and not result["missing"]
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
