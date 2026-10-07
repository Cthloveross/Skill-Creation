#!/usr/bin/env python3
"""Evaluate normalized checking-account switch prerequisites.

Reads one JSON object from stdin and writes a JSON report to stdout. This helper
is side-effect free and intentionally treats absent evidence as unknown.
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


def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in (
        "%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    # ISO strings such as 2025-01-01T12:00:00-05:00.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_money(value):
    if value is None or value == "":
        return None
    try:
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def status(value):
    return str(value or "").strip().lower()


def check(value, detail):
    return {"status": value, "detail": detail}


def add_blocker(blockers, condition, message):
    if condition and message not in blockers:
        blockers.append(message)


def format_money(amount):
    return format(amount.quantize(Decimal("0.01")), "f")


def main(payload):
    blockers = []
    current = parse_date(payload.get("current_time"))
    user = payload.get("user") or {}
    old = payload.get("old_account") or {}
    transactions = payload.get("old_account_transactions")
    cards = payload.get("debit_cards")
    opening = payload.get("opening") or {}

    if current is None:
        return {"error": "current_time is required and must be parseable as a date or timestamp."}
    if not isinstance(transactions, list):
        transactions = None
    if not isinstance(cards, list):
        cards = None

    verified = user.get("verified") is True
    identity_check = check(
        "pass" if verified else "fail",
        "Customer verification must be completed before card or account actions."
        if not verified else "Customer marked verified in normalized input.",
    )
    add_blocker(blockers, not verified, "Customer identity is not verified.")

    account_class = old.get("account_class")
    account_status = status(old.get("status"))
    balance = parse_money(old.get("balance", old.get("current_holdings")))
    opened = parse_date(old.get("date_opened"))
    tier_info = TIERS.get(account_class)
    closure_checks = {}

    if not old.get("account_id"):
        closure_checks["selected_account"] = check("fail", "An old account_id is required.")
        add_blocker(blockers, True, "No old checking account was selected.")
    else:
        closure_checks["selected_account"] = check("pass", "Old account selected.")

    closure_checks["account_status"] = check(
        "pass" if account_status == "open" else "fail",
        "Account is OPEN." if account_status == "open" else "Account must have OPEN status.",
    )
    add_blocker(blockers, account_status != "open", "Old account is not OPEN.")

    if tier_info is None:
        closure_checks["tier"] = check(
            "unknown", "The account class is absent from the documented personal-checking closure tier table."
        )
        add_blocker(blockers, True, "Closure tier, fee, and notice period are unknown for this account class.")
        fee = None
        notice_days = None
        early_applies = None
    elif opened is None:
        closure_checks["tier"] = check(
            "unknown", "Account opening date is required to determine whether the early-closure fee applies."
        )
        add_blocker(blockers, True, "Old account opening date is unavailable.")
        fee = None
        notice_days = tier_info[3]
        early_applies = None
    else:
        tier, tier_fee, window_days, notice_days = tier_info
        age_days = (current - opened).days
        if age_days < 0:
            closure_checks["tier"] = check("fail", "Account opening date is later than current date.")
            add_blocker(blockers, True, "Old account opening date is invalid.")
            fee = None
            early_applies = None
        else:
            early_applies = age_days < window_days
            fee = tier_fee if early_applies else Decimal("0")
            closure_checks["tier"] = check(
                "pass",
                "%s tier; account age is %d days; early closure fee is $%s; notice is %d day(s)."
                % (tier, age_days, format_money(fee), notice_days),
            )

    if transactions is None:
        closure_checks["pending_transactions"] = check("unknown", "Transaction history was not supplied.")
        add_blocker(blockers, True, "Pending transaction and refund status is unknown.")
    else:
        pending = [t for t in transactions if status((t or {}).get("status")) in ("pending", "processing")]
        if pending:
            closure_checks["pending_transactions"] = check(
                "fail", "%d pending or processing transaction(s) found; all must settle." % len(pending)
            )
            add_blocker(blockers, True, "Old account has pending or processing transactions, including possible pending refunds.")
        else:
            closure_checks["pending_transactions"] = check(
                "pass", "No pending or processing transactions were supplied for the linked account."
            )

    if fee is None or balance is None:
        closure_checks["balance"] = check("unknown", "A valid balance and applicable fee are required.")
        add_blocker(blockers, True, "Old account balance requirement cannot be determined.")
    elif fee == 0:
        passed = balance == 0
        closure_checks["balance"] = check(
            "pass" if passed else "fail",
            "Balance is zero." if passed else "Balance must be exactly $0.00 when no early-closure fee applies.",
        )
        add_blocker(blockers, not passed, "Old account balance must be $0.00 when no early-closure fee applies.")
    else:
        passed = balance >= fee
        closure_checks["balance"] = check(
            "pass" if passed else "fail",
            "Balance covers the $%s early-closure fee." % format_money(fee)
            if passed else "Balance must be at least $%s for the early-closure fee." % format_money(fee),
        )
        add_blocker(blockers, not passed, "Old account balance does not cover the early-closure fee.")

    if notice_days is None:
        closure_checks["notice"] = check("unknown", "Notice period is unknown.")
    elif notice_days == 0:
        closure_checks["notice"] = check("pass", "No advance notice is required for this tier.")
    elif payload.get("notice_completed") is True:
        closure_checks["notice"] = check("pass", "Required %d-day notice marked completed." % notice_days)
    elif payload.get("notice_completed") is False:
        closure_checks["notice"] = check("fail", "Required %d-day notice is not complete." % notice_days)
        add_blocker(blockers, True, "Required account-closure notice period is not complete.")
    else:
        closure_checks["notice"] = check("unknown", "Evidence of the required %d-day notice is absent." % notice_days)
        add_blocker(blockers, True, "Required account-closure notice completion is unknown.")

    card_reports = []
    if cards is None:
        add_blocker(blockers, True, "Linked debit-card information is unavailable.")
    else:
        required_cards = [c for c in cards if status((c or {}).get("status")) != "closed"]
        if required_cards and payload.get("card_closure_authorized") is not True:
            add_blocker(blockers, True, "Permanent closure authorization for all required linked debit cards is missing.")
        for card in required_cards:
            report = {"card_id": card.get("card_id"), "checks": {}}
            owner_ok = bool(card.get("user_id")) and card.get("user_id") == user.get("user_id")
            report["checks"]["ownership"] = check(
                "pass" if owner_ok else "fail", "Card owner matches verified user." if owner_ok else "Card owner must match verified user."
            )
            valid_status = status(card.get("status")) in ("active", "pending")
            report["checks"]["status"] = check(
                "pass" if valid_status else "fail", "Card status is eligible for closure." if valid_status else "Card must be ACTIVE or PENDING."
            )
            issued = parse_date(card.get("date_issued"))
            if issued is None:
                age_state = "unknown"
                age_detail = "Card issue date is unavailable."
                age_ok = False
            else:
                card_age = (current - issued).days
                age_ok = card_age >= 14
                age_state = "pass" if age_ok else "fail"
                age_detail = "Card age is %d days." % card_age if age_ok else "Card is %d days old; account-closing requires at least 14 days." % card_age
            report["checks"]["minimum_age"] = check(age_state, age_detail)
            auth_ok = payload.get("card_closure_authorized") is True
            report["checks"]["authorization"] = check(
                "pass" if auth_ok else "fail", "Permanent closure is authorized." if auth_ok else "Permanent closure authorization is required."
            )
            report["eligible"] = verified and owner_ok and valid_status and age_ok and auth_ok
            if not report["eligible"]:
                add_blocker(blockers, True, "Linked debit card %s is not eligible for closure." % (card.get("card_id") or "(unknown id)"))
            card_reports.append(report)

    opening_checks = {}
    dob = parse_date(user.get("date_of_birth"))
    if dob is None:
        opening_checks["age"] = check("unknown", "Date of birth is unavailable.")
        add_blocker(blockers, True, "Customer age cannot be determined for account opening.")
    else:
        age = current.year - dob.year - ((current.month, current.day) < (dob.month, dob.day))
        opening_checks["age"] = check("pass" if age >= 18 else "fail", "Customer age is %d." % age)
        add_blocker(blockers, age < 18, "Customer must be at least 18 to open personal checking.")

    target_class = opening.get("requested_account_class")
    class_ok = isinstance(target_class, str) and target_class.strip().endswith("Account")
    opening_checks["account_class_name"] = check(
        "pass" if class_ok else "fail",
        "Requested account class uses the required full official Account name." if class_ok else "Requested account class must be the confirmed full official name ending in 'Account'.",
    )
    add_blocker(blockers, not class_ok, "Replacement account class is not a valid full official Account name.")

    target_kind = opening.get("target_is_personal_checking")
    opening_checks["target_type"] = check(
        "pass" if target_kind is True else ("fail" if target_kind is False else "unknown"),
        "Target marked as personal checking." if target_kind is True else "Target must be confirmed as personal checking.",
    )
    add_blocker(blockers, target_kind is not True, "Replacement product is not confirmed as personal checking.")

    count = opening.get("personal_checking_count_before_opening")
    try:
        count = int(count) if count is not None and str(count).strip() != "" else None
    except (ValueError, TypeError):
        count = None
    if count is None or count < 0:
        opening_checks["account_count"] = check("unknown", "Reconciled personal checking count before opening is required.")
        add_blocker(blockers, True, "Personal checking account count is unknown.")
    else:
        projected = count + 1
        count_ok = projected <= 4
        opening_checks["account_count"] = check(
            "pass" if count_ok else "fail",
            "Opening would result in %d personal checking account(s)." % projected,
        )
        add_blocker(blockers, not count_ok, "Opening would exceed four personal checking accounts.")

    cause = opening.get("closed_for_cause_in_last_6_months")
    if cause is True:
        opening_checks["closures_for_cause"] = check("fail", "A checking account was closed for cause in the past six months.")
        add_blocker(blockers, True, "Recent checking-account closure for cause prevents opening.")
    elif cause is False:
        opening_checks["closures_for_cause"] = check("pass", "No recent closure for cause reported.")
    else:
        opening_checks["closures_for_cause"] = check("unknown", "Closure-for-cause history is not established.")
        add_blocker(blockers, True, "Recent closure-for-cause history is unknown.")

    old_ready = not any(
        c["status"] != "pass" for c in closure_checks.values()
    ) and (cards is not None) and all(r["eligible"] for r in card_reports) and verified
    opening_ready = verified and all(c["status"] == "pass" for c in opening_checks.values())

    next_actions = []
    if blockers:
        next_actions.append("Resolve every listed blocker; do not perform a banking action yet.")
    else:
        if card_reports:
            next_actions.append("Close each listed linked debit card with reason account_closing and verify each result.")
        next_actions.append("Close the selected old checking account and verify the result.")
        next_actions.append("Reconcile accounts, then open the exact requested personal checking account class.")

    return {
        "identity": identity_check,
        "old_account_closure": {
            "eligible": old_ready,
            "early_closure_fee": None if fee is None else format_money(fee),
            "notice_days": notice_days,
            "checks": closure_checks,
        },
        "debit_cards": card_reports,
        "new_account_opening": {"eligible": opening_ready, "checks": opening_checks},
        "switch_ready": old_ready and opening_ready and not blockers,
        "blockers": blockers,
        "next_actions": next_actions,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Top-level JSON must be an object.")
        print(json.dumps(main(raw), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
