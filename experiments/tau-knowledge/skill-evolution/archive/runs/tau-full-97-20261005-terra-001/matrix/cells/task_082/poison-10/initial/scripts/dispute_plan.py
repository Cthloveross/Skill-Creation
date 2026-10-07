#!/usr/bin/env python3
"""Validate debit-card dispute filing inputs and produce filing arguments.

Input JSON schema:
{
 "filing_date":"MM/DD/YYYY",
 "customer":{"user_id":"...","verified":true},
 "accounts":[{"account_id":"...","status":"OPEN","tier":"Entry Tier|Mid Tier|Premium Tier|Elite Tier","date_opened":"MM/DD/YYYY","has_holds_or_restrictions":false}],
 "cards":[{"card_id":"...","account_id":"...","user_id":"..."}],
 "open_disputes_by_account":{"account-id":0},
 "disputes":[{
   "transaction_id":"...", "account_id":"...", "card_id":"...", "transaction_date":"MM/DD/YYYY",
   "discovery_date":"MM/DD/YYYY", "disputed_amount":1.0,
   "dispute_category":"...", "transaction_type":"...", "fraud_suspected":true,
   "card_in_possession":true, "pin_compromised":"no", "contacted_merchant":false,
   "police_report_filed":false, "written_statement_provided":true,
   "statement_timely_reported":true, "liability_band":"within_2_business_days|within_60_days|after_60_days",
   "atm_operator":"rho_bank|third_party", "duplicate_group":"optional-group-id"
 }]
}

It emits no actions. `tool_args` are returned only for ready items.
"""
import datetime as dt
import json
import sys
from collections import Counter, defaultdict

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal", "atm_deposit", "recurring_payment", "person_to_person"}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
LIMITS = {"Entry Tier": 2, "Mid Tier": 3, "Premium Tier": 4, "Elite Tier": 5}
ACTIONS = {
    "card_present_fraud": "close_and_reissue", "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}
ELIGIBLE_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}


def date(value, field, errors):
    if not isinstance(value, str):
        errors.append(field + " must be MM/DD/YYYY.")
        return None
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(field + " must be MM/DD/YYYY.")
        return None


def bool_field(obj, key, errors):
    value = obj.get(key)
    if not isinstance(value, bool):
        errors.append(key + " must be boolean.")
        return None
    return value


def main(data):
    global_errors = []
    filing = date(data.get("filing_date"), "filing_date", global_errors)
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    user_id = customer.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        global_errors.append("customer.user_id is required.")
    if customer.get("verified") is not True:
        global_errors.append("customer.verified must be true before any filing.")

    accounts = {a.get("account_id"): a for a in data.get("accounts", []) if isinstance(a, dict) and a.get("account_id")}
    cards = {c.get("card_id"): c for c in data.get("cards", []) if isinstance(c, dict) and c.get("card_id")}
    disputes = data.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        global_errors.append("disputes must be a nonempty array.")
        disputes = []
    open_counts = data.get("open_disputes_by_account", {})
    if not isinstance(open_counts, dict):
        global_errors.append("open_disputes_by_account must be an object.")
        open_counts = {}

    requested_by_account = Counter(d.get("account_id") for d in disputes if isinstance(d, dict))
    capacity_errors = defaultdict(list)
    for account_id, requested in requested_by_account.items():
        account = accounts.get(account_id)
        if not account:
            continue
        tier = account.get("tier")
        existing = open_counts.get(account_id)
        if tier not in LIMITS:
            capacity_errors[account_id].append("Account tier is missing or unsupported; dispute limit cannot be verified.")
        elif not isinstance(existing, int) or existing < 0:
            capacity_errors[account_id].append("Current open-dispute count is missing or invalid.")
        elif existing + requested > LIMITS[tier]:
            capacity_errors[account_id].append("Filing this batch would exceed the " + tier + " limit of " + str(LIMITS[tier]) + " open disputes.")

    earliest_duplicate = {}
    groups = defaultdict(list)
    for index, item in enumerate(disputes):
        if isinstance(item, dict) and item.get("dispute_category") == "duplicate_charge" and item.get("duplicate_group"):
            temp = []
            d = date(item.get("transaction_date"), "transaction_date", temp)
            if d:
                groups[str(item["duplicate_group"])].append((d, index))
    for group, values in groups.items():
        earliest_duplicate[group] = min(values)[1]

    results = []
    by_card_actions = defaultdict(list)
    for index, item in enumerate(disputes):
        errors = list(global_errors)
        missing = []
        if not isinstance(item, dict):
            results.append({"index": index, "ready": False, "errors": errors + ["Dispute must be an object."], "missing_fields": []})
            continue
        for key in ("transaction_id", "account_id", "card_id"):
            if not isinstance(item.get(key), str) or not item.get(key):
                missing.append(key)
        account = accounts.get(item.get("account_id"))
        card = cards.get(item.get("card_id"))
        if not account:
            errors.append("Account was not supplied from an authorized account lookup.")
        else:
            if account.get("status") != "OPEN":
                errors.append("Debit card disputes require an OPEN checking account.")
            errors.extend(capacity_errors.get(item.get("account_id"), []))
        if not card:
            errors.append("Card was not supplied from an authorized card lookup.")
        else:
            if card.get("account_id") != item.get("account_id"):
                errors.append("Card is not linked to the supplied account.")
            if card.get("user_id") != user_id:
                errors.append("Cardholder does not match the verified customer.")

        transaction_date = date(item.get("transaction_date"), "transaction_date", errors)
        discovery_date = date(item.get("discovery_date"), "discovery_date", errors)
        if filing and transaction_date:
            age = (filing - transaction_date).days
            if age < 0:
                errors.append("Transaction date cannot be after filing date.")
            elif age > 60:
                errors.append("Transaction is more than 60 days old.")
        if transaction_date and discovery_date and discovery_date < transaction_date:
            errors.append("Discovery date cannot precede transaction date.")
        amount = item.get("disputed_amount")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
            errors.append("disputed_amount must be a number of at least 1.00.")
        category = item.get("dispute_category")
        ttype = item.get("transaction_type")
        if category not in CATEGORIES:
            errors.append("dispute_category is unsupported.")
        if ttype not in TYPES:
            errors.append("transaction_type is unsupported.")
        fraud = bool_field(item, "fraud_suspected", errors)
        if category == "unauthorized_transaction" and fraud is True:
            errors.append("Use a fraud category when fraud is suspected, not unauthorized_transaction.")
        if category == "card_present_fraud" and ttype not in {"pin_purchase", "signature_purchase"}:
            errors.append("card_present_fraud requires an in-store physical transaction type.")
        if category == "card_not_present_fraud" and ttype not in {"online_purchase", "recurring_payment", "person_to_person"}:
            errors.append("card_not_present_fraud requires a card-not-present transaction type.")
        if item.get("pin_compromised") not in PINS:
            errors.append("pin_compromised is required and unsupported or missing.")
        for key in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided", "statement_timely_reported"):
            bool_field(item, key, errors)
        if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"} and item.get("atm_operator") not in {"rho_bank", "third_party"}:
            errors.append("ATM disputes require atm_operator of rho_bank or third_party.")
        if item.get("liability_band") not in {"within_2_business_days", "within_60_days", "after_60_days"}:
            errors.append("liability_band is required so the required liability disclosure can be made.")
        if category == "duplicate_charge" and item.get("duplicate_group") and earliest_duplicate.get(str(item["duplicate_group"])) != index:
            errors.append("Only the earliest transaction in a duplicate group may be disputed.")

        provisional = None
        if account and filing:
            opened = date(account.get("date_opened"), "account.date_opened", errors)
            new_account = bool(opened and (filing - opened).days < 30)
            timely = item.get("statement_timely_reported") is True
            written = item.get("written_statement_provided") is True
            no_restrictions = account.get("status") == "OPEN" and account.get("has_holds_or_restrictions") is False
            exclusion = (item.get("pin_compromised") == "yes_shared" or
                         (category not in ELIGIBLE_CATEGORIES) or
                         (fraud is False and item.get("contacted_merchant") is False) or
                         (new_account and category == "card_not_present_fraud"))
            provisional = bool(timely and written and no_restrictions and not exclusion)
        action = ACTIONS.get(category, "keep_active")
        ready = not errors and not missing and provisional is not None
        result = {"index": index, "ready": ready, "errors": errors, "missing_fields": missing,
                  "provisional_credit_eligible": provisional, "card_action": action}
        if ready:
            result["tool_args"] = {
                "transaction_id": item["transaction_id"], "account_id": item["account_id"], "card_id": item["card_id"],
                "user_id": user_id, "dispute_category": category, "transaction_date": item["transaction_date"],
                "discovery_date": item["discovery_date"], "disputed_amount": float(amount), "transaction_type": ttype,
                "card_in_possession": item["card_in_possession"], "pin_compromised": item["pin_compromised"],
                "contacted_merchant": item["contacted_merchant"], "police_report_filed": item["police_report_filed"],
                "written_statement_provided": item["written_statement_provided"],
                "provisional_credit_eligible": provisional, "card_action": action,
            }
            by_card_actions[item["card_id"]].append(action)
        results.append(result)

    aggregate = {}
    for card_id, actions in by_card_actions.items():
        aggregate[card_id] = max(actions, key=lambda value: SEVERITY[value])
    return {"items": results, "actual_card_action_by_card": aggregate, "global_errors": global_errors}


if __name__ == "__main__":
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(value), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"items": [], "actual_card_action_by_card": {}, "global_errors": [str(exc)]}, separators=(",", ":")))
