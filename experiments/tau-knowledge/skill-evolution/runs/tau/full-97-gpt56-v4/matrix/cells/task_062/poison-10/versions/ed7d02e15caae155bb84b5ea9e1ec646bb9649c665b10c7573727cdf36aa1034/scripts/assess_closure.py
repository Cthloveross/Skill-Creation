#!/usr/bin/env python3
"""Assess documented personal account-closure preconditions.

Input JSON:
  account_type: "checking" or "savings"
  account_class: official class, with or without the word "Account"
  opened_on: ISO date or datetime
  as_of: ISO date or datetime (the current supported date)
  status: account status string
  pending_transactions: boolean
  current_holdings: decimal number or string

Output JSON includes tier, fee/notice terms, blockers, and eligible. It is only a
preflight calculation; ownership, identity, authority, notices, and approvals
must be verified separately in live banking tools.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

TIERS = {
    "checking": [
        ("entry", {"light blue", "light green", "green fee-free"}, 30, "15.00", 0, False),
        ("mid", {"blue", "green"}, 60, "25.00", 3, False),
        ("premium", {"evergreen"}, 90, "50.00", 7, False),
        ("elite", {"bluest"}, 180, "100.00", 14, False),
    ],
    "savings": [
        ("entry", {"bronze"}, 60, "20.00", 1, False),
        ("mid", {"silver", "silver plus"}, 90, "35.00", 5, False),
        ("premium", {"gold", "gold plus", "gold years"}, 180, "75.00", 10, False),
        ("elite", {"platinum", "platinum plus", "diamond elite"}, 270, "150.00", 21, True),
    ],
}


def normalise_class(value):
    text = str(value).strip().lower()
    if text.endswith(" account"):
        text = text[:-8].strip()
    return " ".join(text.split())


def parse_date(value):
    return date.fromisoformat(str(value).strip()[:10])


def emit(payload):
    print(json.dumps(payload, sort_keys=True))


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        emit({"eligible": False, "error": "invalid_json", "detail": str(exc)})
        return

    required = ["account_type", "account_class", "opened_on", "as_of", "status", "pending_transactions", "current_holdings"]
    missing = [key for key in required if key not in data]
    if missing:
        emit({"eligible": False, "error": "missing_fields", "missing_fields": missing})
        return

    account_type = str(data["account_type"]).strip().lower()
    if account_type not in TIERS:
        emit({"eligible": False, "error": "unsupported_account_type"})
        return

    product = normalise_class(data["account_class"])
    matching = None
    for row in TIERS[account_type]:
        if product in row[1]:
            matching = row
            break
    if matching is None:
        emit({"eligible": False, "error": "unsupported_account_class", "account_type": account_type})
        return

    try:
        opened = parse_date(data["opened_on"])
        as_of = parse_date(data["as_of"])
        holdings = Decimal(str(data["current_holdings"]))
    except (ValueError, InvalidOperation) as exc:
        emit({"eligible": False, "error": "invalid_date_or_holdings", "detail": str(exc)})
        return

    tier, _, fee_window, fee_text, notice_days, manager_approval = matching
    age_days = (as_of - opened).days
    if age_days < 0:
        emit({"eligible": False, "error": "opened_on_after_as_of"})
        return

    fee = Decimal(fee_text)
    # Conservative: on the stated day boundary, retain the fee requirement.
    early_fee_applies = age_days <= fee_window
    required_holdings = fee if early_fee_applies else Decimal("0.00")
    blockers = []
    if str(data["status"]).strip().upper() != "OPEN":
        blockers.append("account_status_is_not_OPEN")
    if data["pending_transactions"] is not False:
        blockers.append("pending_transactions_must_be_false")
    if holdings < required_holdings:
        blockers.append("insufficient_current_holdings_for_closure_rule")
    if manager_approval:
        blockers.append("manager_approval_must_be_verified_separately")

    emit({
        "eligible": not blockers,
        "account_type": account_type,
        "tier": tier,
        "account_age_days": age_days,
        "early_closure_fee_applies": early_fee_applies,
        "early_closure_fee": format(fee if early_fee_applies else Decimal("0.00"), ".2f"),
        "notice_days": notice_days,
        "manager_approval_required": manager_approval,
        "required_minimum_current_holdings": format(required_holdings, ".2f"),
        "blockers": blockers,
        "still_required": [
            "Verify customer identity, authority, and account ownership in live tools.",
            "Verify any required notice and final confirmation immediately before closing.",
        ],
    })


if __name__ == "__main__":
    main()
