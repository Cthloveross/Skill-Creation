#!/usr/bin/env python3
"""Deterministically evaluate documented personal checking closure prerequisites.

Reads one JSON object from stdin and writes one JSON object to stdout.  This helper
never calls banking tools and does not perform an account closure.
"""

import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation


TIERS = {
    "light blue account": ("entry", Decimal("15.00"), 30, 0),
    "light green account": ("entry", Decimal("15.00"), 30, 0),
    "green fee-free account": ("entry", Decimal("15.00"), 30, 0),
    "blue account": ("mid", Decimal("25.00"), 60, 3),
    "green account": ("mid", Decimal("25.00"), 60, 3),
    "evergreen account": ("premium", Decimal("50.00"), 90, 7),
    "bluest account": ("elite", Decimal("100.00"), 180, 14),
}


def error(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    return 1


def class_key(value):
    """Normalize account classes, accepting a parenthetical checking qualifier."""
    text = str(value or "").strip().lower()
    text = " ".join(text.split())
    if text.endswith("(checking)"):
        text = text[: -len("(checking)")].strip()
    return text


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s is required and must be a date string" % field)
    raw = value.strip()
    # Account dates may be plain dates or timestamps.  Date-only formats are
    # deliberately handled first to avoid locale-dependent parsing.
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    iso = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        # A display timestamp can contain a timezone abbreviation; its leading
        # ISO date remains unambiguous.
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("%s has unsupported date format: %r" % (field, value))


def money(value):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError("balance must be a valid decimal amount")
    return amount


def add_block(blocks, actions, condition, reason, action):
    if condition:
        blocks.append(reason)
        actions.append(action)


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    account = payload.get("account")
    if not isinstance(account, dict):
        raise ValueError("account must be an object")
    for key in ("account_id", "account_type", "account_class", "status", "balance", "date_opened"):
        if key not in account:
            raise ValueError("account.%s is required" % key)
    transactions = payload.get("transactions")
    cards = payload.get("cards")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be the complete returned list")
    if not isinstance(cards, list):
        raise ValueError("cards must be the complete returned list")

    as_of = parse_date(payload.get("as_of"), "as_of")
    opened = parse_date(account["date_opened"], "account.date_opened")
    if opened > as_of:
        raise ValueError("account.date_opened cannot be after as_of")
    balance = money(account["balance"])
    key = class_key(account["account_class"])
    tier_data = TIERS.get(key)
    account_type = str(account["account_type"]).strip().lower()
    supported = tier_data is not None and account_type == "checking"

    blocks = []
    actions = []
    add_block(blocks, actions, not supported,
              "The target is not a supported personal checking account class.",
              "Do not call the account-close tool; resolve the account class or use the applicable procedure.")
    add_block(blocks, actions, str(account["status"]).strip().upper() != "OPEN",
              "Account status is not OPEN.",
              "Do not close the account unless its status is OPEN.")

    invalid_transaction_statuses = []
    pending_transactions = []
    for tx in transactions:
        if not isinstance(tx, dict) or "status" not in tx:
            invalid_transaction_statuses.append("missing")
            continue
        status = str(tx["status"]).strip().lower()
        if status not in ("posted", "pending"):
            invalid_transaction_statuses.append(status or "blank")
        elif status == "pending":
            pending_transactions.append(tx.get("transaction_id", "unidentified transaction"))
    add_block(blocks, actions, bool(invalid_transaction_statuses),
              "Transaction status data is incomplete or contains unsupported statuses: %s." % ", ".join(invalid_transaction_statuses),
              "Re-fetch and resolve the complete bank-account transaction history before closing.")
    add_block(blocks, actions, bool(pending_transactions),
              "There are pending bank-account transactions.",
              "Wait for every pending transaction to resolve, then re-check the account.")

    card_actions = []
    all_cards_closed = True
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            all_cards_closed = False
            blocks.append("A debit-card record is malformed.")
            actions.append("Re-fetch the complete debit-card list before closing the account.")
            continue
        card_id = card.get("card_id", "card record #%d" % (index + 1))
        status = str(card.get("status", "")).strip().upper()
        instruction = {"card_id": card_id, "status": status}
        if status == "CLOSED":
            instruction["action"] = "none"
            instruction["eligible_to_close_now"] = True
        elif status in ("ACTIVE", "PENDING"):
            all_cards_closed = False
            issued_value = card.get("date_issued")
            if issued_value is None:
                instruction.update({
                    "action": "verify_date_issued",
                    "eligible_to_close_now": False,
                    "reason": "date_issued is required to apply the 14-day debit-card age rule"
                })
            else:
                issued = parse_date(issued_value, "cards[%d].date_issued" % index)
                age = (as_of - issued).days
                if issued > as_of:
                    raise ValueError("cards[%d].date_issued cannot be after as_of" % index)
                instruction["card_age_days"] = age
                instruction["earliest_normal_closure_date"] = (issued + timedelta(days=14)).isoformat()
                if age >= 14 and not pending_transactions and not invalid_transaction_statuses:
                    instruction.update({
                        "action": "close_debit_card",
                        "eligible_to_close_now": True,
                        "reason": "close with reason account_closing after verified identity"
                    })
                elif age < 14:
                    instruction.update({
                        "action": "wait",
                        "eligible_to_close_now": False,
                        "reason": "card is younger than 14 days for an account_closing reason"
                    })
                else:
                    instruction.update({
                        "action": "resolve_pending_activity",
                        "eligible_to_close_now": False,
                        "reason": "pending or unverified bank-account activity prevents debit-card closure"
                    })
        else:
            all_cards_closed = False
            instruction.update({
                "action": "manual_resolution",
                "eligible_to_close_now": False,
                "reason": "only ACTIVE or PENDING cards are eligible for the documented debit-card close tool"
            })
        card_actions.append(instruction)

    add_block(blocks, actions, not all_cards_closed,
              "One or more linked debit cards are not confirmed CLOSED.",
              "Close every eligible linked debit card, re-fetch cards, and confirm all are CLOSED before account closure.")

    result = {
        "ok": True,
        "account_id": account["account_id"],
        "as_of": as_of.isoformat(),
        "supported_account_class": supported,
        "account_class": account["account_class"],
        "pending_transaction_count": len(pending_transactions),
        "all_linked_cards_closed": all_cards_closed,
        "card_actions": card_actions,
        "blocking_reasons": blocks,
        "required_next_actions": actions,
    }

    if supported:
        tier, fee, window, notice_days = tier_data
        age = (as_of - opened).days
        fee_applies = age < window
        result.update({
            "tier": tier,
            "account_age_days": age,
            "early_closure_window_days": window,
            "early_closure_fee": format(fee, ".2f") if fee_applies else "0.00",
            "early_closure_fee_applies": fee_applies,
            "notice_period_days": notice_days,
        })
        if fee_applies:
            add_block(blocks, actions, balance < fee,
                      "Early closure fee of $%s applies, but the balance is below that amount." % format(fee, ".2f"),
                      "The account must contain at least the fee amount; the fee can only be deducted from this account.")
        else:
            add_block(blocks, actions, balance != Decimal("0.00"),
                      "No early closure fee applies, so the account balance must be exactly $0.00.",
                      "Bring the account balance to exactly $0.00, then re-check it.")

        notice_raw = payload.get("notice_given_date")
        if notice_raw is None or notice_raw == "":
            notice_satisfied = notice_days == 0
            earliest = as_of if notice_days == 0 else None
            if notice_days:
                blocks.append("No recorded notice date is available for the required %d-day notice period." % notice_days)
                actions.append("Record or obtain the supported notice date, then wait for the full notice period.")
        else:
            notice_date = parse_date(notice_raw, "notice_given_date")
            if notice_date > as_of:
                raise ValueError("notice_given_date cannot be after as_of")
            earliest = notice_date + timedelta(days=notice_days)
            notice_satisfied = as_of >= earliest
            if not notice_satisfied:
                blocks.append("The %d-day notice period has not elapsed." % notice_days)
                actions.append("Wait until %s before attempting account closure." % earliest.isoformat())
        result["notice_satisfied"] = notice_satisfied
        result["earliest_closure_date"] = earliest.isoformat() if earliest else None
    else:
        result.update({
            "tier": None,
            "early_closure_fee": None,
            "early_closure_fee_applies": None,
            "notice_period_days": None,
            "notice_satisfied": False,
            "earliest_closure_date": None,
        })

    result["closure_ready"] = len(blocks) == 0
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        output = main(payload)
        print(json.dumps(output, sort_keys=True))
    except (ValueError, TypeError, KeyError) as exc:
        sys.exit(error(str(exc)))
    except json.JSONDecodeError as exc:
        sys.exit(error("invalid JSON input: %s" % exc))
