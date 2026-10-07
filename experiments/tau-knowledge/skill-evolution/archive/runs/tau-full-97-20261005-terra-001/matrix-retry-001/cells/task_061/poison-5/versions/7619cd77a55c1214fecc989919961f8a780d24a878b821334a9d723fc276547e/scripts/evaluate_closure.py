#!/usr/bin/env python3
"""Deterministic preflight evaluator for personal checking-account closure.

Input is one JSON object on stdin. Output is one JSON object on stdout. This
program does not call banking tools and never performs a banking action.
"""
import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

TIERS = {
    "light blue account": ("ENTRY", "15.00", 30, 0),
    "light green account": ("ENTRY", "15.00", 30, 0),
    "green fee-free account": ("ENTRY", "15.00", 30, 0),
    "blue account": ("MID", "25.00", 60, 3),
    "green account": ("MID", "25.00", 60, 3),
    "evergreen account": ("PREMIUM", "50.00", 90, 7),
    "bluest account": ("ELITE", "100.00", 180, 14),
}
SECURITY_REASONS = {"lost", "stolen", "fraud_suspected"}
CLOSABLE_CARD_STATUSES = {"ACTIVE", "PENDING"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    candidates = [value, value[:10]]
    for item in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(item, fmt).date()
            except ValueError:
                pass
    return None


def normalized_class(value):
    if not isinstance(value, str):
        return ""
    # Returned checking classes may include a parenthetical type annotation.
    return value.lower().split("(", 1)[0].strip()


def decimal_value(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            return None
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def check_for(card_checks, card_id):
    if isinstance(card_checks, dict):
        item = card_checks.get(str(card_id), {})
        return item if isinstance(item, dict) else {}
    if isinstance(card_checks, list):
        for item in card_checks:
            if isinstance(item, dict) and str(item.get("card_id")) == str(card_id):
                return item
    return {}


def main(payload):
    blockers = []
    ready_card_actions = []
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    cards = payload.get("cards")
    transactions = payload.get("transactions")
    card_checks = payload.get("card_checks", {})

    as_of = parse_date(payload.get("as_of"))
    if as_of is None:
        blockers.append("A valid as_of date is required for fee, notice, and card-age calculations.")

    for flag, label in (
        ("identity_verified", "Customer identity has not been verified."),
        ("authority_confirmed", "Customer authority to request closure has not been confirmed."),
        ("ownership_verified", "Ownership of the selected account has not been verified."),
        ("closure_confirmed", "Explicit confirmation to close the selected account is missing."),
    ):
        if payload.get(flag) is not True:
            blockers.append(label)

    if not account.get("account_id"):
        blockers.append("No verified target account_id was supplied.")
    if str(account.get("account_type", "")).lower() != "checking":
        blockers.append("The target account is not verified as a checking account.")
    if str(account.get("status", "")).upper() != "OPEN":
        blockers.append("The target account status is not OPEN.")

    account_class = normalized_class(account.get("account_class"))
    tier_data = TIERS.get(account_class)
    opened = parse_date(account.get("date_opened"))
    fee_info = {
        "tier": None,
        "amount": None,
        "window_days": None,
        "applies": None,
        "window_ends_on": None,
    }
    notice_info = {"days_required": None, "given_on": None, "eligible_on": None, "elapsed": None}

    if tier_data is None:
        blockers.append("The returned checking account class has no supported closure-tier mapping.")
    else:
        tier, fee_text, window_days, notice_days = tier_data
        fee_info.update({"tier": tier, "amount": fee_text, "window_days": window_days})
        notice_info["days_required"] = notice_days
        if opened is None or as_of is None:
            blockers.append("A valid account opening date is required to determine the early-closure fee.")
        else:
            window_end = opened + timedelta(days=window_days)
            applies = as_of < window_end
            fee_info["applies"] = applies
            fee_info["window_ends_on"] = window_end.isoformat()

        notice_given = parse_date(payload.get("notice_given_on"))
        if notice_given is not None:
            notice_info["given_on"] = notice_given.isoformat()
        if notice_days == 0:
            notice_info["elapsed"] = True
        elif notice_given is None or as_of is None:
            notice_info["elapsed"] = False
            blockers.append("The required closure-notice start date is missing or invalid.")
        else:
            eligible_on = notice_given + timedelta(days=notice_days)
            notice_info["eligible_on"] = eligible_on.isoformat()
            notice_info["elapsed"] = as_of >= eligible_on
            if not notice_info["elapsed"]:
                blockers.append("The required closure notice period has not elapsed.")

    balance = decimal_value(account.get("balance"))
    if payload.get("balance_verified") is not True:
        blockers.append("Current account balance has not been verified.")
    elif balance is None:
        blockers.append("Current account balance is missing or invalid.")
    elif fee_info["applies"] is True:
        required = Decimal(fee_info["amount"])
        if balance < required:
            blockers.append("Current balance is below the applicable early-closure fee.")
    elif fee_info["applies"] is False and balance != Decimal("0.00"):
        blockers.append("No early fee applies, so the current balance must be exactly zero.")

    if payload.get("transactions_verified") is not True:
        blockers.append("Current account transactions have not been verified.")
    elif not isinstance(transactions, list):
        blockers.append("Transactions must be supplied as a list after retrieval.")
    else:
        pending = [t for t in transactions if isinstance(t, dict) and str(t.get("status", "")).lower() == "pending"]
        if pending:
            blockers.append("The account has pending transactions.")

    if not isinstance(cards, list):
        blockers.append("Linked debit cards have not been retrieved as a list.")
        cards = []

    for card in cards:
        if not isinstance(card, dict):
            blockers.append("A linked debit-card record is malformed.")
            continue
        card_id = card.get("card_id")
        status = str(card.get("status", "")).upper()
        if status == "CLOSED":
            continue
        if not card_id:
            blockers.append("A non-closed linked debit card has no card_id.")
            continue
        checks = check_for(card_checks, card_id)
        if status not in CLOSABLE_CARD_STATUSES:
            blockers.append("Linked debit card %s is %s and cannot be closed with the documented card-closure tool." % (card_id, status or "of unknown status"))
            continue
        reasons = []
        if checks.get("ownership_verified") is not True:
            reasons.append("card ownership is not verified")
        if checks.get("pending_transactions_verified") is not True or checks.get("has_pending_transactions") is not False:
            reasons.append("no-pending-card-transactions check is incomplete or failed")
        if checks.get("pending_refunds_verified") is not True or checks.get("has_pending_refunds") is not False:
            reasons.append("no-pending-refunds check is incomplete or failed")
        reason = str(checks.get("closure_reason", "account_closing")).lower()
        issued = parse_date(card.get("date_issued") or checks.get("date_issued"))
        security_bypass = reason in SECURITY_REASONS and checks.get("security_reason_confirmed") is True
        if not security_bypass:
            if issued is None or as_of is None:
                reasons.append("card issue date is missing for the 14-day age check")
            elif as_of < issued + timedelta(days=14):
                reasons.append("card has not met the 14-day minimum age")
        if reasons:
            blockers.append("Linked debit card %s must be resolved before account closure: %s." % (card_id, "; ".join(reasons)))
        else:
            ready_card_actions.append({"card_id": card_id, "reason": reason})
            blockers.append("Linked debit card %s remains open and must be closed before account closure." % card_id)

    result = {
        "account_id": account.get("account_id"),
        "account_class": account.get("account_class"),
        "as_of": as_of.isoformat() if as_of else None,
        "fee": fee_info,
        "notice": notice_info,
        "card_actions_ready": ready_card_actions,
        "blocking_reasons": blockers,
        "eligible_to_call_close_bank_account": len(blockers) == 0,
    }
    return result


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(raw), sort_keys=True))
    except Exception as exc:
        print(json.dumps({
            "eligible_to_call_close_bank_account": False,
            "blocking_reasons": ["Invalid evaluator input: %s" % exc],
            "card_actions_ready": [],
        }, sort_keys=True))
