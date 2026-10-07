#!/usr/bin/env python3
"""Assess documented checking-account closure prerequisites.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
performs no network access and no banking action.
"""

import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

POLICIES = {
    "entry": {"fee": Decimal("15"), "window_days": 30, "notice_days": 0},
    "mid": {"fee": Decimal("25"), "window_days": 60, "notice_days": 3},
    "premium": {"fee": Decimal("50"), "window_days": 90, "notice_days": 7},
    "elite": {"fee": Decimal("100"), "window_days": 180, "notice_days": 14},
}


def norm(value):
    return " ".join(str(value or "").strip().lower().split())


def first_value(mapping, *keys):
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def parse_date(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing " + label)
    text = value.strip()
    for fmt, candidate in (("%Y-%m-%d", text[:10]), ("%m/%d/%Y", text)):
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            pass
    raise ValueError("invalid " + label + "; use YYYY-MM-DD or MM/DD/YYYY")


def product_tier(account):
    product = norm(first_value(account, "product_name", "account_class", "level", "product"))
    account_type = norm(first_value(account, "account_type", "type", "class"))
    if account_type and account_type not in {"checking", "checkings"}:
        return None
    if product in {"light blue account", "light green account", "green fee-free account"}:
        return "entry"
    if product in {"blue account", "green account (checking)"}:
        return "mid"
    if product == "green account" and account_type in {"checking", "checkings"}:
        return "mid"
    if product == "evergreen account":
        return "premium"
    if product == "bluest account":
        return "elite"
    return None


def decimal_balance(account):
    raw = first_value(account, "balance", "current_holdings")
    if raw is None:
        raise ValueError("missing account balance/current_holdings")
    try:
        value = Decimal(str(raw).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("invalid account balance/current_holdings")
    if not value.is_finite():
        raise ValueError("invalid account balance/current_holdings")
    return value


def money(value):
    return format(value.quantize(Decimal("0.01")), "f")


def assess(data):
    for key in ("user_id", "current_time", "account", "transactions", "debit_cards"):
        if key not in data:
            raise ValueError("missing required input: " + key)
    if not isinstance(data["account"], dict):
        raise ValueError("account must be an object")
    if not isinstance(data["transactions"], list):
        raise ValueError("transactions must be a list")
    if not isinstance(data["debit_cards"], list):
        raise ValueError("debit_cards must be a list")

    account = data["account"]
    today = parse_date(data["current_time"], "current_time")
    opened = parse_date(first_value(account, "date_opened", "opened_date"), "account.date_opened")
    if opened > today:
        raise ValueError("account.date_opened is later than current_time")

    issues = []
    tier = product_tier(account)
    age_days = (today - opened).days
    fee_applies = None
    fee = None
    notice_days = None
    balance_ok = False
    notice_satisfied = False

    if tier is None:
        issues.append({
            "code": "unsupported_or_ambiguous_product",
            "message": "Cannot determine a documented checking-account tier from the supplied account.",
        })
    else:
        policy = POLICIES[tier]
        fee_applies = age_days <= policy["window_days"]
        fee = policy["fee"] if fee_applies else Decimal("0")
        balance = decimal_balance(account)
        balance_ok = balance >= fee if fee_applies else balance == Decimal("0")
        notice_days = policy["notice_days"]

        if notice_days == 0:
            notice_satisfied = True
        elif data.get("notice_given_at"):
            notice_date = parse_date(data["notice_given_at"], "notice_given_at")
            notice_satisfied = today >= notice_date + timedelta(days=notice_days)
        else:
            notice_satisfied = False

        if not balance_ok:
            if fee_applies:
                issues.append({
                    "code": "insufficient_balance_for_early_fee",
                    "message": "Balance must be at least the applicable early-closure fee, which is deducted from the account.",
                })
            else:
                issues.append({
                    "code": "nonzero_balance_without_fee",
                    "message": "Balance must be exactly zero when no early-closure fee applies.",
                })
        if not notice_satisfied:
            issues.append({
                "code": "notice_period_not_satisfied",
                "message": "The documented notice period has not elapsed or no notice timestamp was supplied.",
            })

    status_open = norm(account.get("status")) == "open"
    if not status_open:
        issues.append({"code": "account_not_open", "message": "Account status must be OPEN."})

    pending_count = sum(
        1 for transaction in data["transactions"]
        if isinstance(transaction, dict) and norm(transaction.get("status")) == "pending"
    )
    no_pending = pending_count == 0
    if not no_pending:
        issues.append({
            "code": "pending_account_transactions",
            "message": "All account transactions must be posted before closure.",
        })

    nonclosed_cards = []
    ownership_mismatches = []
    for card in data["debit_cards"]:
        if not isinstance(card, dict):
            issues.append({"code": "invalid_card_record", "message": "A debit-card record is not an object."})
            continue
        card_id = card.get("card_id")
        if str(card.get("user_id", "")) != str(data["user_id"]):
            ownership_mismatches.append(card_id)
        if norm(card.get("status")) != "closed":
            nonclosed_cards.append(card_id)

    all_cards_closed = not nonclosed_cards and not ownership_mismatches
    if ownership_mismatches:
        issues.append({
            "code": "linked_card_ownership_mismatch",
            "message": "At least one linked card is not owned by the authenticated customer.",
            "card_ids": ownership_mismatches,
        })
    if nonclosed_cards:
        issues.append({
            "code": "linked_cards_not_closed",
            "message": "All associated debit cards must be closed before checking-account closure.",
            "card_ids": nonclosed_cards,
        })

    account_preconditions_pass = bool(tier) and status_open and no_pending and balance_ok
    ready = account_preconditions_pass and notice_satisfied and all_cards_closed
    return {
        "ok": ready,
        "account_id": account.get("account_id"),
        "tier": tier,
        "account_age_days": age_days,
        "early_closure_fee_applies": fee_applies,
        "early_closure_fee": money(fee) if fee is not None else None,
        "notice_days": notice_days,
        "notice_satisfied": notice_satisfied,
        "account_preconditions_pass": account_preconditions_pass,
        "pending_transaction_count": pending_count,
        "all_cards_closed": all_cards_closed,
        "ready_to_execute": ready,
        "issues": issues,
        "limitations": [
            "This result does not verify customer identity, authority, final confirmation, or debit-card-specific pending transaction, refund, and card-age prerequisites."
        ],
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(assess(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
