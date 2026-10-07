#!/usr/bin/env python3
"""Deterministically preflight debit-card dispute payloads.

Input JSON schema:
{
  "current_date": "MM/DD/YYYY",
  "user_id": "...",
  "identity_verified": true,
  "open_dispute_limits_checked": true,
  "accounts": [{"account_id":"...", "account_type":"checking", "account_class":"Entry Tier|Mid Tier|Premium Tier|Elite Tier", "status":"OPEN", "has_holds_or_restrictions":false, "open_dispute_count":0, "date_opened":"MM/DD/YYYY"}],
  "cards": [{"card_id":"...", "account_id":"...", "user_id":"...", "status":"ACTIVE"}],
  "claims": [{
    "transaction_id":"...", "account_id":"...", "card_id":"...",
    "transaction_date":"MM/DD/YYYY", "transaction_amount":123.45,
    "disputed_amount":123.45, "discovery_date":"MM/DD/YYYY",
    "dispute_category":"...", "transaction_type":"...",
    "card_in_possession":true, "pin_compromised":"no",
    "contacted_merchant":true, "police_report_filed":false,
    "written_statement_provided":true,
    "timely_reported_within_60_days_of_statement":true,
    "duplicate_group":"optional shared identifier"
  }]
}

The script makes no external calls. Unknown/missing prerequisite values block a claim rather
than being guessed. `open_dispute_limits_checked` represents a completed, external account
limit check; when true, `open_dispute_count` is compared to the tier maximum.
"""
import datetime as dt
import json
import sys
from collections import defaultdict

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal", "atm_deposit", "recurring_payment", "person_to_person"}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
ACTIONS = {
    "card_present_fraud": "close_and_reissue", "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active", "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active", "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active", "recurring_charge_after_cancellation": "keep_active",
}
LIMITS = {"Entry Tier": 2, "Mid Tier": 3, "Premium Tier": 4, "Elite Tier": 5}
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def date(value, field, errors):
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        errors.append(f"{field} must be MM/DD/YYYY")
        return None


def boolean(claim, field, errors):
    value = claim.get(field)
    if not isinstance(value, bool):
        errors.append(f"{field} must be a boolean")
        return False
    return value


def main(data):
    accounts = {a.get("account_id"): a for a in data.get("accounts", []) if a.get("account_id")}
    cards = {c.get("card_id"): c for c in data.get("cards", []) if c.get("card_id")}
    current_errors = []
    today = date(data.get("current_date"), "current_date", current_errors)
    user_id = data.get("user_id")
    identity_verified = data.get("identity_verified") is True
    limits_checked = data.get("open_dispute_limits_checked") is True
    claims = data.get("claims", [])

    # Earliest transaction is the only selected item in an explicit duplicate group.
    grouped = defaultdict(list)
    for index, claim in enumerate(claims):
        if claim.get("dispute_category") == "duplicate_charge" and claim.get("duplicate_group"):
            group_errors = []
            d = date(claim.get("transaction_date"), f"claims[{index}].transaction_date", group_errors)
            grouped[claim["duplicate_group"]].append((d or dt.date.max, str(claim.get("transaction_id", "")), index))
    chosen_duplicates = {min(rows)[2] for rows in grouped.values()}

    output_claims = []
    by_card = defaultdict(list)
    for i, claim in enumerate(claims):
        errors = list(current_errors)
        category = claim.get("dispute_category")
        tx_type = claim.get("transaction_type")
        account_id, card_id, tx_id = claim.get("account_id"), claim.get("card_id"), claim.get("transaction_id")
        account, card = accounts.get(account_id), cards.get(card_id)
        tx_date = date(claim.get("transaction_date"), f"claims[{i}].transaction_date", errors)
        discovery = date(claim.get("discovery_date"), f"claims[{i}].discovery_date", errors)

        if not identity_verified:
            errors.append("identity_verified must be true after logged two-field verification")
        if not user_id:
            errors.append("user_id is required")
        if not tx_id:
            errors.append("transaction_id is required from transaction lookup")
        if category not in CATEGORIES:
            errors.append("dispute_category is invalid")
        if tx_type not in TYPES:
            errors.append("transaction_type is invalid")
        if claim.get("pin_compromised") not in PINS:
            errors.append("pin_compromised is invalid")
        for field in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
            boolean(claim, field, errors)
        try:
            disputed = float(claim.get("disputed_amount"))
            transaction_amount = abs(float(claim.get("transaction_amount")))
            if disputed < 1:
                errors.append("disputed_amount must be at least $1.00")
            if disputed > transaction_amount:
                errors.append("disputed_amount cannot exceed transaction amount")
        except (TypeError, ValueError):
            disputed = 0.0
            errors.append("disputed_amount and transaction_amount must be numeric")
        if tx_date and today:
            if tx_date > today:
                errors.append("transaction_date cannot be in the future")
            elif (today - tx_date).days > 60:
                errors.append("transaction is more than 60 days old")
        if discovery and tx_date and discovery < tx_date:
            errors.append("discovery_date cannot precede transaction_date")
        if account is None:
            errors.append("account_id was not found in supplied account lookup")
        else:
            if account.get("account_type") != "checking":
                errors.append("linked account must be checking")
            if account.get("status") != "OPEN":
                errors.append("linked checking account must be OPEN")
            tier = account.get("account_class")
            if tier not in LIMITS:
                errors.append("account_class is missing or unsupported for dispute limit")
            elif not limits_checked:
                errors.append("open dispute limit has not been established")
            else:
                try:
                    if int(account.get("open_dispute_count")) >= LIMITS[tier]:
                        errors.append("account has reached its maximum open disputes")
                except (TypeError, ValueError):
                    errors.append("open_dispute_count is required after limit check")
        if card is None:
            errors.append("card_id was not found in supplied card lookup")
        else:
            if card.get("account_id") != account_id:
                errors.append("card is not linked to account_id")
            if card.get("user_id") != user_id:
                errors.append("card does not belong to user_id")

        if category == "atm_cash_discrepancy" and tx_type != "atm_withdrawal":
            errors.append("ATM cash discrepancy requires atm_withdrawal")
        if category == "atm_deposit_not_credited" and tx_type != "atm_deposit":
            errors.append("ATM deposit dispute requires atm_deposit")
        if category == "card_not_present_fraud" and tx_type != "online_purchase":
            errors.append("card-not-present fraud requires online_purchase")
        if category == "recurring_charge_after_cancellation" and tx_type != "recurring_payment":
            errors.append("recurring cancellation dispute requires recurring_payment")
        if category == "duplicate_charge" and claim.get("duplicate_group") and i not in chosen_duplicates:
            errors.append("not earliest transaction in duplicate group")

        account_new = False
        if account and today:
            opened = date(account.get("date_opened"), "account.date_opened", [])
            account_new = bool(opened and 0 <= (today - opened).days < 30)
        provisionally_eligible = (
            category in PC_CATEGORIES
            and claim.get("timely_reported_within_60_days_of_statement") is True
            and claim.get("written_statement_provided") is True
            and account is not None and account.get("status") == "OPEN"
            and account.get("has_holds_or_restrictions") is False
            and not (category not in {"card_present_fraud", "card_not_present_fraud"} and claim.get("contacted_merchant") is False)
            and claim.get("pin_compromised") != "yes_shared"
            and not (account_new and category == "card_not_present_fraud")
        )
        # Unknown standing/timeliness is not eligibility, but is separately surfaced.
        if account and account.get("has_holds_or_restrictions") not in (True, False):
            errors.append("account hold/restriction status is required")
        if claim.get("timely_reported_within_60_days_of_statement") not in (True, False):
            errors.append("statement-timeliness determination is required")

        action = ACTIONS.get(category)
        result = {
            "claim_index": i, "ready": not errors, "errors": errors,
            "payload": {
                "transaction_id": tx_id, "account_id": account_id, "card_id": card_id, "user_id": user_id,
                "dispute_category": category, "transaction_date": claim.get("transaction_date"),
                "discovery_date": claim.get("discovery_date"), "disputed_amount": disputed,
                "transaction_type": tx_type, "card_in_possession": claim.get("card_in_possession"),
                "pin_compromised": claim.get("pin_compromised"), "contacted_merchant": claim.get("contacted_merchant"),
                "police_report_filed": claim.get("police_report_filed"),
                "written_statement_provided": claim.get("written_statement_provided"),
                "provisional_credit_eligible": provisionally_eligible, "card_action": action,
            },
            "account_is_new": account_new,
        }
        output_claims.append(result)
        if action and not errors:
            by_card[card_id].append(action)

    card_actions = {}
    for card_id, actions in by_card.items():
        strongest = max(actions, key=lambda item: SEVERITY[item])
        card_actions[card_id] = strongest
    return {"claims": output_claims, "card_actions": card_actions}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        print(json.dumps(main(request), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": f"invalid input: {exc}"}, separators=(",", ":")))
        sys.exit(1)
