#!/usr/bin/env python3
"""Produce a deterministic eligibility, closure, and Gold APY checklist.

Reads one JSON object from stdin and writes one JSON object to stdout. This script
performs no bank actions and intentionally treats absent facts as unknown.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ACTIVE = {"ACTIVE", "OPEN"}
GOLD_CARD_BONUSES = {
    "Bronze Rewards Card": Decimal("0.15"),
    "Silver Rewards Card": Decimal("0.20"),
    "Gold Rewards Card": Decimal("0.025"),
    "Platinum Rewards Card": Decimal("0.15"),
    "Diamond Elite Card": Decimal("0.30"),
    "EcoCard": Decimal("0.60"),
    "Green Rewards Card": Decimal("0.35"),
    "Crypto-Cash Back Card": Decimal("0"),
}


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def amount(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def state(value, passed_text, failed_text, unknown_text):
    if value is True:
        return {"state": "pass", "detail": passed_text}
    if value is False:
        return {"state": "fail", "detail": failed_text}
    return {"state": "unknown", "detail": unknown_text}


def all_pass(checks):
    return all(item["state"] == "pass" for item in checks.values())


def main(payload):
    as_of = parse_date(payload.get("as_of"))
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        accounts = []

    verified = payload.get("verified")
    age = payload.get("age_years")
    personal_checking = [
        a for a in accounts
        if a.get("account_type") == "checking" and a.get("personal", True) is not False
    ]
    personal_savings = [
        a for a in accounts
        if a.get("account_type") == "savings" and a.get("personal", True) is not False
    ]
    active_checking = [a for a in personal_checking if str(a.get("status", "")).upper() in ACTIVE]

    # Checking opening eligibility
    if isinstance(age, (int, float)):
        adult_value = age >= 18
    else:
        adult_value = None
    checking_count_value = len(personal_checking) <= 4 if accounts else None

    cause_dates = []
    malformed_cause_date = False
    for account in personal_checking:
        raw = account.get("closed_for_cause_date")
        if raw is not None:
            parsed = parse_date(raw)
            if parsed is None:
                malformed_cause_date = True
            else:
                cause_dates.append(parsed)
    if not accounts or malformed_cause_date or as_of is None:
        cause_value = None
    else:
        # A six-month exact calendar calculation is not needed to safely block;
        # dates within the prior 183 days are conservatively treated as recent.
        cause_value = not any((as_of - d).days >= 0 and (as_of - d).days <= 183 for d in cause_dates)

    checking_checks = {
        "identity_verified": state(verified is True if isinstance(verified, bool) else None,
                                   "Customer is verified.", "Customer is not verified.",
                                   "Verification status is missing."),
        "age_18_or_over": state(adult_value, "Customer is at least 18.",
                                  "Customer is younger than 18.", "Age is missing."),
        "personal_checking_limit": state(checking_count_value,
                                          "Customer has no more than four personal checking accounts.",
                                          "Customer exceeds the four personal checking-account limit.",
                                          "Personal checking accounts have not been supplied."),
        "no_recent_closure_for_cause": state(cause_value,
                                              "No supplied checking closure for cause is within the prior six months.",
                                              "A checking account was closed for cause within the prior six months.",
                                              "Need as-of date and valid closure-for-cause history."),
    }

    # Savings opening eligibility
    if accounts:
        good_standing = True
        for account in accounts:
            if str(account.get("status", "")).upper() == "COLLECTIONS":
                good_standing = False
            bal = amount(account.get("balance"))
            if bal is None:
                good_standing = None
                break
            if bal < 0:
                good_standing = False
        savings_limit_value = len(personal_savings) < 5
    else:
        good_standing = None
        savings_limit_value = None

    tenure_values = []
    bad_open_date = False
    for account in active_checking:
        opened = parse_date(account.get("date_opened"))
        if opened is None:
            bad_open_date = True
        elif as_of is not None:
            tenure_values.append((as_of - opened).days >= 14)
    if not accounts or not active_checking or as_of is None or bad_open_date:
        tenure_value = None
    else:
        tenure_value = any(tenure_values)

    savings_checks = {
        "identity_verified": checking_checks["identity_verified"],
        "active_checking_exists": state(bool(active_checking) if accounts else None,
                                         "At least one active/open personal checking account exists.",
                                         "No active/open personal checking account exists.",
                                         "Account inventory is missing."),
        "fewer_than_five_personal_savings": state(savings_limit_value,
                                                    "Customer has fewer than five personal savings accounts.",
                                                    "Customer already has five or more personal savings accounts.",
                                                    "Personal savings accounts have not been supplied."),
        "no_collections_or_negative_balances": state(good_standing,
                                                       "No supplied account is in collections or has a negative balance.",
                                                       "An account is in collections or has a negative balance.",
                                                       "Account status or balance is missing."),
        "checking_tenure_at_least_14_days": state(tenure_value,
                                                    "An active checking account has been held at least 14 days.",
                                                    "No active checking account has reached 14 days of tenure.",
                                                    "Need active checking opening date and as-of date."),
    }

    # Light Blue closure evaluation. For other classes, return unknown because no
    # generalized closure schedule is in this packaged method.
    target_id = payload.get("closure_account_id")
    target = next((a for a in accounts if a.get("account_id") == target_id), None)
    if target is None:
        closure_checks = {"target_account": state(None, "", "", "Closure target record is missing.")}
        fee = None
    elif target.get("account_class") != "Light Blue Account":
        closure_checks = {"target_account": state(None, "", "", "This script only evaluates Light Blue Account closure fees.")}
        fee = None
    else:
        target_status = str(target.get("status", "")).upper()
        opened = parse_date(target.get("date_opened"))
        bal = amount(target.get("balance"))
        pending = target.get("pending_transactions")
        if opened is None or as_of is None:
            fee = None
            balance_ok = None
        else:
            fee = Decimal("15.00") if (as_of - opened).days < 30 else Decimal("0.00")
            balance_ok = None if bal is None else (bal >= fee if fee > 0 else bal == 0)
        closure_checks = {
            "account_is_open": state(target_status == "OPEN" if target_status else None,
                                      "Closure target status is OPEN.", "Closure target is not OPEN.", "Target status is missing."),
            "no_pending_transactions": state(pending is False if isinstance(pending, bool) else None,
                                              "No pending transactions are reported.", "Pending transactions exist.",
                                              "Pending-transaction status is missing."),
            "balance_meets_closure_rule": state(balance_ok,
                                                 "Balance meets the applicable Light Blue closure rule.",
                                                 "Balance does not meet the applicable Light Blue closure rule.",
                                                 "Need current balance, opening date, and as-of date."),
        }

    apy_input = payload.get("gold_apy", {})
    if not isinstance(apy_input, dict):
        apy_input = {}
    cards = apy_input.get("active_card_classes", [])
    cards = cards if isinstance(cards, list) else []
    recognized = [c for c in cards if c in GOLD_CARD_BONUSES]
    unsupported = [c for c in cards if c not in GOLD_CARD_BONUSES]
    card_bonus = max((GOLD_CARD_BONUSES[c] for c in recognized), default=Decimal("0"))
    winners = [c for c in recognized if GOLD_CARD_BONUSES[c] == card_bonus]
    candidates = apy_input.get("checking_boost_candidates", [])
    candidates = candidates if isinstance(candidates, list) else []
    parsed_boosts = []
    bad_boost = False
    for candidate in candidates:
        if not isinstance(candidate, dict):
            bad_boost = True
            continue
        value = amount(candidate.get("percent"))
        if value is None or value < 0:
            bad_boost = True
        else:
            parsed_boosts.append((str(candidate.get("source", "documented checking boost")), value))
    checking_bonus = max((value for _, value in parsed_boosts), default=Decimal("0"))
    boost_winners = [source for source, value in parsed_boosts if value == checking_bonus]
    total = Decimal("5.5") + card_bonus + checking_bonus

    unknown = []
    if as_of is None:
        unknown.append("A valid as_of date is required for tenure and closure-fee checks.")
    if not accounts:
        unknown.append("Account inventory is required for opening and closure eligibility.")
    for group_name, group in (("checking_opening", checking_checks), ("savings_opening", savings_checks), ("closure", closure_checks)):
        for check_name, check in group.items():
            if check["state"] == "unknown":
                unknown.append(group_name + "." + check_name + ": " + check["detail"])
    if unsupported:
        unknown.append("Gold APY includes unsupported card classes: " + ", ".join(unsupported))
    if bad_boost:
        unknown.append("One or more checking APY boost candidates are invalid.")

    return {
        "checking_opening": {"eligible": all_pass(checking_checks), "checks": checking_checks},
        "savings_opening": {"eligible": all_pass(savings_checks), "checks": savings_checks},
        "closure": {
            "eligible": all_pass(closure_checks),
            "light_blue_early_closure_fee_usd": None if fee is None else format(fee, ".2f"),
            "checks": closure_checks,
        },
        "gold_apy": {
            "base_percent": "5.5",
            "highest_card_bonus_percent": format(card_bonus, "f"),
            "selected_card_classes": winners,
            "highest_documented_checking_boost_percent": format(checking_bonus, "f"),
            "selected_checking_boost_sources": boost_winners,
            "total_percent_if_all_inputs_apply": format(total, "f"),
            "unsupported_cards": unsupported,
            "note": "Credit-card bonuses and checking boosts each use only their highest applicable value; the two categories may be additive.",
        },
        "unknown_or_missing": unknown,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
