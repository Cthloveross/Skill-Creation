#!/usr/bin/env python3
"""Assess checking-account closure and replacement-opening prerequisites.
Reads one JSON object from stdin and emits one JSON object to stdout. No banking action occurs.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": ("entry", Decimal("15"), 30, 0),
    "Light Green Account": ("entry", Decimal("15"), 30, 0),
    "Green Fee-Free Account": ("entry", Decimal("15"), 30, 0),
    "Blue Account": ("mid", Decimal("25"), 60, 3),
    "Green Account (checking)": ("mid", Decimal("25"), 60, 3),
    "Evergreen Account": ("premium", Decimal("50"), 90, 7),
    "Bluest Account": ("elite", Decimal("100"), 180, 14),
}
OFFICIAL_CLASSES = set(TIERS)
VALID_REASONS = {
    "lost", "stolen", "fraud_suspected", "damaged", "no_longer_needed", "account_closing"
}
SECURITY_REASONS = {"lost", "stolen", "fraud_suspected"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def fact_is_false(value):
    return value is False


def evaluate_card(card, target_id, user_id, as_of, reason):
    blockers = []
    card_id = card.get("card_id")
    if card.get("account_id") != target_id:
        blockers.append("card account_id does not match the selected account")
    if card.get("user_id") != user_id:
        blockers.append("card ownership is not confirmed for the verified customer")
    status = card.get("status")
    if status not in {"ACTIVE", "PENDING"}:
        blockers.append("card status must be ACTIVE or PENDING before it can be closed")
    if fact_is_false(card.get("pending_transactions")):
        pass
    elif card.get("pending_transactions") is True:
        blockers.append("card has pending or processing transactions")
    else:
        blockers.append("pending/processing card transaction status is unknown")
    if card.get("pending_refunds") is True:
        blockers.append("card has a pending refund; written acknowledgement or settlement is required")
    elif not fact_is_false(card.get("pending_refunds")):
        blockers.append("pending-refund status is unknown")
    if reason not in VALID_REASONS:
        blockers.append("a documented card-closure reason is required")
    issued = parse_date(card.get("date_issued"))
    if issued is None:
        blockers.append("card date_issued is missing or invalid")
        age_days = None
        earliest = None
    else:
        age_days = (as_of - issued).days
        earliest = issued.fromordinal(issued.toordinal() + 14).isoformat()
        if age_days < 0:
            blockers.append("card date_issued is in the future")
        elif age_days < 14 and reason not in SECURITY_REASONS:
            blockers.append("card is younger than 14 days; wait until the eligible date")
    return {
        "card_id": card_id,
        "status": status,
        "reason": reason,
        "age_days": age_days,
        "earliest_eligible_date": earliest,
        "can_close_now": not blockers,
        "blockers": blockers,
    }


def main(payload):
    global_blockers = []
    as_of = parse_date(payload.get("as_of"))
    if as_of is None:
        global_blockers.append("as_of must be a valid ISO date or timestamp")
        as_of = date.today()  # Only prevents arithmetic failure; output remains blocked.

    customer = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
    user_id = customer.get("user_id")
    if not user_id:
        global_blockers.append("verified customer user_id is required")
    if customer.get("identity_verified") is not True:
        global_blockers.append("customer identity has not been verified")

    account = payload.get("target_account") if isinstance(payload.get("target_account"), dict) else {}
    account_blockers = list(global_blockers)
    account_id = account.get("account_id")
    if not account_id:
        account_blockers.append("selected account_id is required")
    if account.get("owner_user_id") != user_id:
        account_blockers.append("selected account ownership is not confirmed for the verified customer")
    if account.get("status") != "OPEN":
        account_blockers.append("account status must be OPEN")
    if account.get("pending_transactions") is True:
        account_blockers.append("account has pending transactions")
    elif not fact_is_false(account.get("pending_transactions")):
        account_blockers.append("pending account transaction status is unknown")

    account_class = account.get("account_class")
    tier_data = TIERS.get(account_class)
    fee = None
    within_fee_window = None
    notice_days = None
    age_days = None
    if tier_data is None:
        account_blockers.append("account class is unsupported for closure-tier assessment")
        tier = None
    else:
        tier, fee, fee_window_days, notice_days = tier_data
        opened = parse_date(account.get("date_opened"))
        if opened is None:
            account_blockers.append("account date_opened is missing or invalid")
        else:
            age_days = (as_of - opened).days
            if age_days < 0:
                account_blockers.append("account date_opened is in the future")
            else:
                within_fee_window = age_days < fee_window_days
        if notice_days:
            given = parse_date(payload.get("notice_given_on"))
            if given is None:
                account_blockers.append("required closure notice has not been recorded")
            else:
                notice_elapsed = (as_of - given).days
                if notice_elapsed < notice_days:
                    account_blockers.append("required closure notice period has not elapsed")

    balance_raw = account.get("current_holdings", account.get("balance"))
    balance = money(balance_raw)
    if balance is None:
        account_blockers.append("account balance/current_holdings is missing or invalid")
    elif balance < 0:
        account_blockers.append("negative balance cannot satisfy the closure balance requirement")
    elif within_fee_window is True and fee is not None and balance < fee:
        account_blockers.append("balance is insufficient for the applicable early-closure fee")
    elif within_fee_window is False and balance != Decimal("0"):
        account_blockers.append("balance/current_holdings must be $0 when no early-closure fee applies")

    raw_cards = payload.get("cards")
    cards = raw_cards if isinstance(raw_cards, list) else []
    if not isinstance(raw_cards, list):
        account_blockers.append("complete debit-card retrieval result is required")
    reasons = payload.get("card_reasons") if isinstance(payload.get("card_reasons"), dict) else {}
    card_results = []
    nonclosed_cards = []
    for card in cards:
        if not isinstance(card, dict):
            account_blockers.append("a debit-card record is invalid")
            continue
        if card.get("account_id") != account_id:
            continue
        if card.get("status") != "CLOSED":
            nonclosed_cards.append(card)
            card_results.append(evaluate_card(card, account_id, user_id, as_of, reasons.get(card.get("card_id"))))
    if nonclosed_cards:
        account_blockers.append("all debit cards associated with the checking account must be CLOSED first")

    opening = payload.get("opening") if isinstance(payload.get("opening"), dict) else None
    opening_result = {"requested": False, "can_open": False, "blockers": ["replacement opening was not requested"]}
    if opening is not None:
        opening_blockers = []
        requested = opening.get("requested") is True
        if not requested:
            opening_blockers.append("replacement opening was not requested")
        if customer.get("identity_verified") is not True:
            opening_blockers.append("customer identity has not been verified")
        requested_class = opening.get("account_class")
        if requested_class not in OFFICIAL_CLASSES:
            opening_blockers.append("account_class must be an exact documented official personal checking class")
        age = opening.get("customer_age")
        if not isinstance(age, int):
            opening_blockers.append("customer age is unknown")
        elif age < 18:
            opening_blockers.append("customer must be at least 18 years old")
        count = opening.get("open_personal_checking_count_after_closure")
        if not isinstance(count, int):
            opening_blockers.append("post-closure personal checking account count is unknown")
        elif count >= 4:
            opening_blockers.append("opening would exceed the four personal checking account limit")
        cause = opening.get("closed_for_cause_last_6_months")
        if cause is not False:
            opening_blockers.append("checking-account closure-for-cause history in the past six months is not cleared")
        opening_result = {
            "requested": requested,
            "account_class": requested_class,
            "can_open": not opening_blockers,
            "blockers": opening_blockers,
        }

    plan = []
    if global_blockers:
        plan.append("complete identity verification, log it, and obtain missing customer facts")
    for result in card_results:
        if result["can_close_now"]:
            plan.append("close eligible debit card " + str(result["card_id"]) + " and confirm it is CLOSED")
        else:
            plan.append("resolve debit-card closure blockers for " + str(result["card_id"]))
    if nonclosed_cards:
        plan.append("retrieve fresh card records after card-closure attempts")
    elif not account_blockers:
        plan.append("close the selected checking account and confirm the result")
    else:
        plan.append("resolve checking-account closure blockers and reassess with fresh records")
    if opening_result["requested"]:
        if opening_result["can_open"]:
            plan.append("after confirmed requested closure, open the selected replacement checking account")
        else:
            plan.append("resolve replacement-account opening blockers before opening")

    return {
        "as_of": as_of.isoformat(),
        "account": {
            "account_id": account_id,
            "account_class": account_class,
            "tier": tier,
            "account_age_days": age_days,
            "early_closure_fee": None if fee is None else format(fee, ".2f"),
            "within_early_fee_window": within_fee_window,
            "notice_days": notice_days,
            "can_close_now": not account_blockers,
            "blockers": account_blockers,
        },
        "cards": card_results,
        "opening": opening_result,
        "next_actions": plan,
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(incoming), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}))
