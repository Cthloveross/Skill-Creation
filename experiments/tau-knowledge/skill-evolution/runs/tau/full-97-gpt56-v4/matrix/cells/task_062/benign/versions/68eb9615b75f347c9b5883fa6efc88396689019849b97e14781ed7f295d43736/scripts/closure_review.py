#!/usr/bin/env python3
"""Review documented personal-account closure prerequisites.

Input JSON:
{
  "now": ISO-8601 date/time or YYYY-MM-DD,
  "accounts": [{"account_id": str, "account_class": str, "status": str,
                "balance": number|string, "date_opened": ISO or MM/DD/YYYY}],
  "transactions_by_account": {account_id: [{"status": str}, ...]},
  "closure_account_ids": [str, ...]
}
Output JSON: {"reviews": [review, ...]}.  This is an advisory calculation only.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

TIERS = {
    "Bronze Account": (60, Decimal("20"), 1, False),
    "Silver Account": (90, Decimal("35"), 5, False),
    "Silver Plus Account": (90, Decimal("35"), 5, False),
    "Gold Account": (180, Decimal("75"), 10, False),
    "Gold Plus Account": (180, Decimal("75"), 10, False),
    "Gold Years Account": (180, Decimal("75"), 10, False),
    "Platinum Account": (270, Decimal("150"), 21, True),
    "Platinum Plus Account": (270, Decimal("150"), 21, True),
    "Diamond Elite Account": (270, Decimal("150"), 21, True),
    "Light Blue Account": (30, Decimal("15"), 0, False),
    "Light Green Account": (30, Decimal("15"), 0, False),
    "Green Fee-Free Account": (30, Decimal("15"), 0, False),
    "Blue Account": (60, Decimal("25"), 3, False),
    "Green Account (checking)": (60, Decimal("25"), 3, False),
    "Evergreen Account": (90, Decimal("50"), 7, False),
    "Bluest Account": (180, Decimal("100"), 14, False),
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("unparseable date")


def money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid balance")
    if not amount.is_finite():
        raise ValueError("invalid balance")
    return amount


def review(account, transactions, today):
    blockers = []
    account_id = account.get("account_id")
    account_class = account.get("account_class")
    result = {
        "account_id": account_id,
        "account_class": account_class,
        "eligible_to_close_now": False,
        "blockers": blockers,
    }
    tier = TIERS.get(account_class)
    if tier is None:
        blockers.append("unrecognized account class; determine documented closure terms")
        return result
    window_days, fee, notice_days, manager_approval = tier
    result.update({
        "early_closure_window_days": window_days,
        "early_closure_fee": format(fee, ".2f"),
        "notice_days": notice_days,
        "manager_approval_required": manager_approval,
        "notice_satisfied": notice_days == 0,
        "earliest_close_date_if_notice_starts_today": (today + timedelta(days=notice_days)).isoformat(),
    })
    if str(account.get("status", "")).upper() != "OPEN":
        blockers.append("account status is not OPEN")
    if any(str(tx.get("status", "")).lower() == "pending" for tx in transactions if isinstance(tx, dict)):
        blockers.append("pending transactions exist")
    try:
        opened = parse_date(account.get("date_opened"))
        age_days = (today - opened).days
        if age_days < 0:
            raise ValueError("opening date is in the future")
        early = age_days < window_days
        result["account_age_days"] = age_days
        result["early_closure_fee_applies"] = early
    except ValueError as exc:
        blockers.append("cannot determine early-fee applicability: " + str(exc))
        early = None
    try:
        balance = money(account.get("balance"))
        result["balance"] = format(balance, ".2f")
        if early is True and balance < fee:
            blockers.append("balance is below applicable early-closure fee")
        elif early is False and balance != Decimal("0"):
            blockers.append("balance must be zero when no early-closure fee applies")
    except ValueError as exc:
        blockers.append(str(exc))
    if manager_approval:
        blockers.append("manager approval must be obtained and recorded")
    if notice_days:
        blockers.append("required closure notice has not yet been shown as elapsed")
    result["eligible_to_close_now"] = not blockers
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        today = parse_date(payload["now"])
        accounts = payload.get("accounts")
        wanted = payload.get("closure_account_ids")
        tx_by_id = payload.get("transactions_by_account", {})
        if not isinstance(accounts, list) or not isinstance(wanted, list) or not isinstance(tx_by_id, dict):
            raise ValueError("accounts, closure_account_ids, and transactions_by_account have invalid types")
        index = {a.get("account_id"): a for a in accounts if isinstance(a, dict) and a.get("account_id") is not None}
        reviews = []
        for account_id in wanted:
            account = index.get(account_id)
            if account is None:
                reviews.append({"account_id": account_id, "eligible_to_close_now": False,
                                "blockers": ["target account is missing from live account snapshot"]})
                continue
            transactions = tx_by_id.get(account_id)
            if not isinstance(transactions, list):
                transactions = [{"status": "unknown"}]
                base = review(account, transactions, today)
                base["blockers"].append("transaction history missing or invalid; pending status cannot be verified")
                base["eligible_to_close_now"] = False
                reviews.append(base)
            else:
                reviews.append(review(account, transactions, today))
        print(json.dumps({"reviews": reviews}, sort_keys=True))
    except (KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"error": "invalid input: " + str(exc)}))


if __name__ == "__main__":
    main()
