#!/usr/bin/env python3
"""Conservative, read-only preflight assessment for a banking account overhaul.

Reads one JSON object from stdin and writes one JSON report to stdout.  This helper
never calls bank tools and intentionally marks missing facts as blockers.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for parser in (
        lambda: datetime.fromisoformat(text.replace("Z", "+00:00")).date(),
        lambda: datetime.strptime(text, "%m/%d/%Y").date(),
        lambda: datetime.strptime(text, "%Y-%m-%d").date(),
    ):
        try:
            return parser()
        except ValueError:
            pass
    return None


def money(value):
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def status_open(account):
    return str(account.get("status", "")).upper() in {"OPEN", "ACTIVE"}


def balance(account):
    return money(account.get("balance", account.get("current_holdings")))


def pending_state(value):
    """Return True/False when known; None when the supplied record is unusable."""
    if isinstance(value, bool):
        return value
    if isinstance(value, list):
        return any(str(item.get("status", "")).lower() == "pending"
                   for item in value if isinstance(item, dict))
    return None


def closure_terms(kind, account_class):
    savings = {
        "Bronze Account": (60, Decimal("20"), 1, False),
        "Silver Account": (90, Decimal("35"), 5, False),
        "Silver Plus Account": (90, Decimal("35"), 5, False),
        "Gold Account": (180, Decimal("75"), 10, False),
        "Gold Plus Account": (180, Decimal("75"), 10, False),
        "Gold Years Account": (180, Decimal("75"), 10, False),
        "Platinum Account": (270, Decimal("150"), 21, True),
        "Platinum Plus Account": (270, Decimal("150"), 21, True),
        "Diamond Elite Account": (270, Decimal("150"), 21, True),
    }
    checking = {
        "Light Blue Account": (30, Decimal("15"), 0, False),
        "Light Green Account": (30, Decimal("15"), 0, False),
        "Green Fee-Free Account": (30, Decimal("15"), 0, False),
        "Blue Account": (60, Decimal("25"), 3, False),
        "Green Account (checking)": (60, Decimal("25"), 3, False),
        "Evergreen Account": (90, Decimal("50"), 7, False),
        "Bluest Account": (180, Decimal("100"), 14, False),
    }
    return (savings if kind == "savings" else checking).get(account_class)


def add_check(report, name, passed, detail):
    report["checks"].append({"name": name, "passed": passed, "detail": detail})
    if not passed:
        report["errors"].append(detail)


def review_closure(report, account, kind, now, pending):
    item = {
        "account_id": account.get("account_id"),
        "account_class": account.get("account_class"),
        "kind": kind,
        "eligible": False,
        "blockers": [],
    }
    if not status_open(account):
        item["blockers"].append("Account status must be OPEN before closure.")
    state = pending_state(pending)
    if state is None:
        item["blockers"].append("Pending-transaction status must be retrieved before closure.")
    elif state:
        item["blockers"].append("Pending transactions must clear before closure.")
    opened = parse_date(account.get("date_opened"))
    terms = closure_terms(kind, account.get("account_class"))
    if not opened or not now:
        item["blockers"].append("A valid current date and account opening date are required to calculate closure terms.")
    elif not terms:
        item["blockers"].append("Closure terms for this account class are not available in this helper.")
    else:
        age = max(0, (now - opened).days)
        window, fee, notice, approval = terms
        early = age < window
        applicable_fee = fee if early else Decimal("0")
        item.update({"age_days": age, "early_closure_fee": str(applicable_fee),
                     "notice_days": notice, "manager_approval_required": approval})
        current_balance = balance(account)
        if current_balance is None:
            item["blockers"].append("Current account balance is required.")
        elif early and current_balance < fee:
            item["blockers"].append("Balance must be at least the applicable early-closure fee.")
        elif not early and current_balance != 0:
            item["blockers"].append("Balance must be zero when no early-closure fee applies.")
        if approval:
            item["blockers"].append("Elite savings closure requires manager approval.")
    item["eligible"] = not item["blockers"]
    report["closure_reviews"].append(item)


def main(payload):
    report = {"errors": [], "checks": [], "closure_reviews": []}
    accounts = payload.get("accounts")
    requests = payload.get("requests", {})
    pending = payload.get("pending_by_account", {})
    now = parse_date(payload.get("now"))
    if not isinstance(accounts, list):
        report["errors"].append("accounts must be a list.")
        return report
    if not isinstance(requests, dict) or not isinstance(pending, dict):
        report["errors"].append("requests and pending_by_account must be objects.")
        return report
    if not now:
        report["errors"].append("now must be a valid ISO or MM/DD/YYYY date.")

    by_id = {str(a.get("account_id")): a for a in accounts if isinstance(a, dict) and a.get("account_id")}
    verified = payload.get("user_verified") is True

    personal_checking = [a for a in accounts if isinstance(a, dict)
                         and str(a.get("account_type", "")).lower() == "checking"
                         and a.get("is_business") is not True]
    active_personal_checking = [a for a in personal_checking if status_open(a)]
    personal_savings = [a for a in accounts if isinstance(a, dict)
                        and str(a.get("account_type", "")).lower() == "savings"
                        and a.get("is_business") is not True]
    business_checking = [a for a in accounts if isinstance(a, dict)
                         and str(a.get("account_type", "")).lower() == "checking"
                         and a.get("is_business") is True]

    savings_class = requests.get("personal_savings_class")
    if savings_class is not None:
        add_check(report, "personal_savings_identity", verified,
                  "Customer identity must be verified before opening personal savings.")
        tenure_ok = any((now and parse_date(a.get("date_opened")) and
                         (now - parse_date(a.get("date_opened"))).days >= 14)
                        for a in active_personal_checking)
        add_check(report, "personal_savings_checking_and_tenure", bool(tenure_ok),
                  "An OPEN/ACTIVE personal checking account held at least 14 days is required.")
        add_check(report, "personal_savings_limit", len(personal_savings) < 5,
                  "Customer must hold fewer than five personal savings accounts.")
        standing_known = all(balance(a) is not None for a in accounts)
        standing_ok = standing_known and all(balance(a) >= 0 and str(a.get("status", "")).upper() != "COLLECTIONS" for a in accounts)
        add_check(report, "personal_savings_good_standing", standing_ok,
                  "All account balances and statuses must show no negative balance or collections.")
        class_ok = isinstance(savings_class, str) and savings_class.endswith("Account")
        add_check(report, "personal_savings_class", class_ok,
                  "Personal savings account class must be the exact official name ending in 'Account'.")

    business_class = requests.get("business_checking_class")
    if business_class is not None:
        add_check(report, "business_checking_identity", verified,
                  "Customer identity must be verified before opening business checking.")
        add_check(report, "business_authority", requests.get("business_authority_verified") is True,
                  "Business authority and authorized-signer status must be verified.")
        qualifying = [a for a in personal_checking if str(a.get("status", "")).upper() == "OPEN" and balance(a) is not None and balance(a) >= Decimal("500")]
        add_check(report, "business_personal_checking", bool(qualifying),
                  "An existing personal checking account with status OPEN and balance at least $500 is required.")
        add_check(report, "business_checking_limit", len(business_checking) <= 6,
                  "Customer must not exceed six business checking accounts.")
        no_closed = all(str(a.get("status", "")).upper() != "CLOSED" for a in accounts)
        add_check(report, "business_no_closed_accounts", no_closed,
                  "Customer must have no account with status CLOSED.")
        add_check(report, "business_class_present", isinstance(business_class, str) and bool(business_class.strip()),
                  "A supported exact business checking account class is required.")

    for key, kind in (("close_savings_id", "savings"), ("close_checking_id", "checking")):
        target = requests.get(key)
        if target is not None:
            account = by_id.get(str(target))
            if not account:
                report["closure_reviews"].append({"account_id": target, "kind": kind, "eligible": False,
                                                   "blockers": ["Requested account was not found in supplied account data."]})
            else:
                review_closure(report, account, kind, now, pending.get(str(target)))
    return report


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True, default=str))
    except Exception as exc:
        print(json.dumps({"errors": ["Invalid helper input: " + str(exc)], "checks": [], "closure_reviews": []}))
