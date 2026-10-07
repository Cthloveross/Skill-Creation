#!/usr/bin/env python3
"""Preflight debit-card dispute filings without making banking calls.

Read one JSON object from stdin and emit one JSON result object on stdout.

Input schema (all dates are MM/DD/YYYY):
{
 "current_date":"...", "user_id":"...", "identity_verified":true,
 "open_dispute_limits_checked":true,
 "accounts":[{"account_id":"...", "account_type":"checking", "status":"OPEN",
   "account_tier":"Entry Tier", "open_dispute_count":0,
   "has_holds_or_restrictions":false, "date_opened":"..."}],
 "cards":[{"card_id":"...", "account_id":"...", "user_id":"...", "status":"ACTIVE"}],
 "transactions":[{"transaction_id":"...", "account_id":"...", "date":"...",
   "amount":-12.34, "status":"posted", "lookup_position":0}],
 "claims":[{"transaction_id":"...", "account_id":"...", "card_id":"...",
   "transaction_date":"...", "disputed_amount":12.34, "discovery_date":"...",
   "dispute_category":"...", "transaction_type":"...", "card_in_possession":true,
   "pin_compromised":"no", "contacted_merchant":true, "police_report_filed":false,
   "written_statement_provided":true,
   "timely_reported_within_60_days_of_statement":true,
   "liability_window":"within_2_business_days|within_60_days|after_60_days",
   "duplicate_group":"optional id"}]
}

`transactions` must be copied from the account lookup. Its `lookup_position` is the
zero-based position in that lookup, which is reverse chronological; for same-date
duplicates the greatest position is treated as the earliest listed transaction.
`account_type` may instead be named `class` when that is how the account lookup labels
checking/savings. `account_tier` must come from a supported tier/limit source; never
infer it from a product marketing name. A result's payload is suitable for the filing
tool only when `ready` is true.
"""
import datetime as dt
import json
import sys
from collections import defaultdict

CATEGORIES = {"unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited", "duplicate_charge", "incorrect_amount", "goods_services_not_received", "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud"}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal", "atm_deposit", "recurring_payment", "person_to_person"}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
LIMITS = {"Entry Tier": 2, "Mid Tier": 3, "Premium Tier": 4, "Elite Tier": 5}
ACTIONS = {"card_present_fraud":"close_and_reissue", "card_not_present_fraud":"close_and_reissue", "unauthorized_transaction":"freeze_pending_investigation", "atm_cash_discrepancy":"keep_active", "atm_deposit_not_credited":"keep_active", "duplicate_charge":"keep_active", "incorrect_amount":"keep_active", "goods_services_not_received":"keep_active", "recurring_charge_after_cancellation":"keep_active"}
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}
SEVERITY = {"keep_active":0, "freeze_pending_investigation":1, "close_and_reissue":2}
LIABILITY = {"within_2_business_days":50.0, "within_60_days":500.0, "after_60_days":None}


def parse_date(value, label, errors):
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        errors.append(f"{label} must be MM/DD/YYYY")
        return None


def require_bool(obj, key, errors):
    value = obj.get(key)
    if not isinstance(value, bool):
        errors.append(f"{key} must be a boolean")
    return value


def account_type(account):
    return account.get("account_type", account.get("class"))


def liability_amount(category, disputed, window, errors):
    # Liability is relevant to unauthorized/fraud categories. Other covered error
    # categories have no customer-liability offset for this payload field.
    if category not in {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud"}:
        return 0.0
    if window not in LIABILITY:
        errors.append("liability_window is required for unauthorized/fraud claims")
        return None
    ceiling = LIABILITY[window]
    return -1 if ceiling is None else min(disputed, ceiling)


def main(data):
    accounts = {x.get("account_id"): x for x in data.get("accounts", []) if x.get("account_id")}
    cards = {x.get("card_id"): x for x in data.get("cards", []) if x.get("card_id")}
    transactions = {x.get("transaction_id"): x for x in data.get("transactions", []) if x.get("transaction_id")}
    global_errors = []
    today = parse_date(data.get("current_date"), "current_date", global_errors)
    user_id = data.get("user_id")
    grouped = defaultdict(list)
    for i, claim in enumerate(data.get("claims", [])):
        if claim.get("dispute_category") == "duplicate_charge" and claim.get("duplicate_group"):
            tx = transactions.get(claim.get("transaction_id"), {})
            e = []
            d = parse_date(tx.get("date", claim.get("transaction_date")), f"claims[{i}].transaction_date", e)
            try:
                position = int(tx.get("lookup_position"))
            except (TypeError, ValueError):
                position = -1
            # Oldest date wins; for identical dates, reverse-chronological lookup's
            # larger index is earlier.
            grouped[claim["duplicate_group"]].append((d or dt.date.max, -position, i))
    selected_duplicates = {min(rows)[2] for rows in grouped.values()}

    results, actions_by_card = [], defaultdict(list)
    for i, claim in enumerate(data.get("claims", [])):
        errors = list(global_errors)
        category, tx_type = claim.get("dispute_category"), claim.get("transaction_type")
        account_id, card_id, tx_id = claim.get("account_id"), claim.get("card_id"), claim.get("transaction_id")
        account, card, tx = accounts.get(account_id), cards.get(card_id), transactions.get(tx_id)
        tx_date = parse_date(claim.get("transaction_date"), f"claims[{i}].transaction_date", errors)
        discovery = parse_date(claim.get("discovery_date"), f"claims[{i}].discovery_date", errors)
        if data.get("identity_verified") is not True: errors.append("identity_verified must be true after logged two-field verification")
        if not user_id: errors.append("user_id is required")
        if category not in CATEGORIES: errors.append("dispute_category is invalid")
        if tx_type not in TYPES: errors.append("transaction_type is invalid")
        if claim.get("pin_compromised") not in PINS: errors.append("pin_compromised is invalid")
        for key in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
            require_bool(claim, key, errors)
        try:
            disputed = float(claim.get("disputed_amount"))
            if disputed < 1: errors.append("disputed_amount must be at least $1.00")
        except (TypeError, ValueError):
            disputed = 0.0; errors.append("disputed_amount must be numeric")
        if tx is None:
            errors.append("transaction_id was not found in supplied transaction lookup")
            tx_amount = None
        else:
            try: tx_amount = abs(float(tx.get("amount")))
            except (TypeError, ValueError): tx_amount = None; errors.append("lookup transaction amount must be numeric")
            lookup_date = tx.get("date")
            if tx.get("account_id") != account_id: errors.append("transaction is not linked to account_id")
            if tx.get("status") != "posted": errors.append("transaction must be posted")
            if lookup_date != claim.get("transaction_date"): errors.append("transaction_date does not match transaction lookup")
            if tx_amount is not None and disputed > tx_amount: errors.append("disputed_amount cannot exceed transaction amount")
        if tx_date and today:
            if tx_date > today: errors.append("transaction_date cannot be in the future")
            elif (today - tx_date).days > 60: errors.append("transaction is more than 60 days old")
        if discovery and tx_date and discovery < tx_date: errors.append("discovery_date cannot precede transaction_date")
        if account is None: errors.append("account_id was not found in supplied account lookup")
        else:
            if account_type(account) != "checking": errors.append("linked account must be checking")
            if account.get("status") != "OPEN": errors.append("linked checking account must be OPEN")
            tier = account.get("account_tier")
            if tier not in LIMITS: errors.append("account_tier is required from a supported tier/limit source")
            elif data.get("open_dispute_limits_checked") is not True: errors.append("open dispute limit has not been established")
            else:
                try:
                    if int(account.get("open_dispute_count")) >= LIMITS[tier]: errors.append("account has reached its maximum open disputes")
                except (TypeError, ValueError): errors.append("open_dispute_count is required after limit check")
            if account.get("has_holds_or_restrictions") not in (True, False): errors.append("account hold/restriction status is required")
        if card is None: errors.append("card_id was not found in supplied card lookup")
        else:
            if card.get("account_id") != account_id: errors.append("card is not linked to account_id")
            if card.get("user_id") != user_id: errors.append("card does not belong to user_id")
        if category == "atm_cash_discrepancy" and tx_type != "atm_withdrawal": errors.append("ATM cash discrepancy requires atm_withdrawal")
        if category == "atm_deposit_not_credited" and tx_type != "atm_deposit": errors.append("ATM deposit dispute requires atm_deposit")
        if category == "card_present_fraud" and tx_type not in {"pin_purchase", "signature_purchase"}: errors.append("card-present fraud requires a physical purchase type")
        if category == "card_not_present_fraud" and tx_type != "online_purchase": errors.append("card-not-present fraud requires online_purchase")
        if category == "recurring_charge_after_cancellation" and tx_type != "recurring_payment": errors.append("recurring cancellation dispute requires recurring_payment")
        if category == "duplicate_charge" and claim.get("duplicate_group") and i not in selected_duplicates: errors.append("not earliest transaction in duplicate group")
        account_new = False
        if account and today:
            opened = parse_date(account.get("date_opened"), "account.date_opened", [])
            account_new = bool(opened and 0 <= (today - opened).days < 30)
        timely = claim.get("timely_reported_within_60_days_of_statement")
        if timely not in (True, False): errors.append("statement-timeliness determination is required")
        eligible = (category in PC_CATEGORIES and timely is True and claim.get("written_statement_provided") is True and account is not None and account.get("status") == "OPEN" and account.get("has_holds_or_restrictions") is False and not (category not in {"card_present_fraud", "card_not_present_fraud"} and claim.get("contacted_merchant") is False) and claim.get("pin_compromised") != "yes_shared" and not (account_new and category == "card_not_present_fraud"))
        liability = liability_amount(category, disputed, claim.get("liability_window"), errors)
        action = ACTIONS.get(category)
        payload = {"transaction_id":tx_id, "account_id":account_id, "card_id":card_id, "user_id":user_id, "dispute_category":category, "transaction_date":claim.get("transaction_date"), "discovery_date":claim.get("discovery_date"), "disputed_amount":disputed, "transaction_type":tx_type, "card_in_possession":claim.get("card_in_possession"), "pin_compromised":claim.get("pin_compromised"), "contacted_merchant":claim.get("contacted_merchant"), "police_report_filed":claim.get("police_report_filed"), "written_statement_provided":claim.get("written_statement_provided"), "provisional_credit_eligible":eligible, "customer_max_liability_amount":liability, "card_action":action}
        results.append({"claim_index":i, "ready":not errors, "errors":errors, "payload":payload, "account_is_new":account_new})

    # The tier maximum applies to all open claims on an account, including the
    # claims being prepared in this batch. Do not let individually valid claims
    # collectively overrun the remaining capacity. There is no safe implied
    # priority among claims, so block the affected ready batch for clarification
    # or supported escalation rather than silently filing only some of it.
    ready_by_account = defaultdict(list)
    for result in results:
        if result["ready"]:
            ready_by_account[result["payload"]["account_id"]].append(result)
    for account_id, account_results in ready_by_account.items():
        account = accounts.get(account_id, {})
        tier = account.get("account_tier")
        try:
            existing = int(account.get("open_dispute_count"))
        except (TypeError, ValueError):
            existing = None
        if tier in LIMITS and existing is not None and existing + len(account_results) > LIMITS[tier]:
            for result in account_results:
                result["errors"].append("batch would exceed the account's maximum open disputes")
                result["ready"] = False

    actions_by_card = defaultdict(list)
    for result in results:
        if result["ready"] and result["payload"]["card_action"]:
            actions_by_card[result["payload"]["card_id"]].append(result["payload"]["card_action"])
    return {"claims":results, "card_actions":{card:max(v, key=lambda x:SEVERITY[x]) for card,v in actions_by_card.items()}}

if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error":f"invalid input: {exc}"}, separators=(",", ":"))); sys.exit(1)
