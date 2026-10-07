#!/usr/bin/env python3
"""Build a non-executing debit-card dispute validation and action plan.

Reads one JSON object from stdin and writes one JSON object to stdout. No network,
filesystem, tool, or banking actions are performed.
"""
import json
import sys
from datetime import datetime

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TRANSACTION_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PIN_VALUES = {"yes_shared", "yes_observed", "no", "unknown"}
TIER_LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
FINAL_DISPUTE_STATUSES = {
    "RESOLVED_CUSTOMER_FAVOR", "RESOLVED_BANK_FAVOR", "RESOLVED_PARTIAL",
    "PROVISIONAL_REVERSED", "CLOSED_NO_RESPONSE",
}
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
ACTION_BY_CATEGORY = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active",
    "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active",
    "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active",
    "recurring_charge_after_cancellation": "keep_active",
}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}
LIABILITY = {
    "within_2_business_days": {"maximum_liability": 50, "message": "Maximum liability is $50."},
    "within_60_days": {"maximum_liability": 500, "message": "Maximum liability is $500."},
    "after_60_days": {"maximum_liability": None, "message": "Liability may be unlimited and funds may not be recoverable."},
}


def date_value(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def normalized_tier(value):
    if not isinstance(value, str):
        return None
    value = value.lower().strip().replace(" tier", "")
    return value if value in TIER_LIMITS else None


def as_index(records, key):
    result = {}
    for record in records if isinstance(records, list) else []:
        if isinstance(record, dict) and record.get(key) is not None:
            result[str(record[key])] = record
    return result


def resolve_category(request):
    issue = request.get("issue")
    if issue in CATEGORIES:
        return issue, None
    if issue != "unauthorized":
        return None, "A recognized issue/category is required."
    suspected = request.get("fraud_suspected")
    if suspected is not True and suspected is not False:
        return None, "For unauthorized activity, determine whether fraud is suspected."
    if not suspected:
        return "unauthorized_transaction", None
    channel = request.get("transaction_channel")
    if channel == "physical":
        return "card_present_fraud", None
    if channel == "online_phone":
        return "card_not_present_fraud", None
    return None, "Suspected fraud requires transaction_channel 'physical' or 'online_phone'."


def provisional_assessment(request, category, account, as_of):
    missing = []
    timely = request.get("timely_report_within_60_days_of_statement")
    statement = request.get("written_statement_provided")
    if timely is None:
        missing.append("timely_report_within_60_days_of_statement")
    if statement is None:
        missing.append("written_statement_provided")
    if not account:
        missing.append("linked account")
    elif account.get("holds_or_restrictions") is None:
        missing.append("account hold/restriction status")
    if missing:
        return {"status": "undetermined", "reason": "Missing " + ", ".join(missing) + "."}
    if category not in PC_CATEGORIES:
        return {"status": "not_required", "reason": "This dispute category is not in the required provisional-credit categories."}
    if timely is not True:
        return {"status": "not_required", "reason": "Timely reporting within 60 days of the statement was not established."}
    if statement is not True:
        return {"status": "not_required", "reason": "A written statement was not provided or agreed to."}
    if account.get("status") != "OPEN" or account.get("holds_or_restrictions") is True:
        return {"status": "not_required", "reason": "The checking account is not OPEN without holds or restrictions."}
    if request.get("pin_compromised") == "yes_shared":
        return {"status": "not_required", "reason": "The PIN was voluntarily shared."}
    opened = date_value(account.get("date_opened"))
    if category == "card_not_present_fraud" and opened and as_of and (as_of - opened).days < 30:
        return {"status": "not_required", "reason": "This is a card-not-present dispute on an account opened fewer than 30 days ago."}
    if category not in {"card_present_fraud", "card_not_present_fraud", "unauthorized_transaction"} and request.get("contacted_merchant") is False:
        return {"status": "not_required", "reason": "The merchant was not contacted for a non-fraud dispute."}
    return {"status": "required", "reason": "All required provisional-credit conditions supplied to the planner are met."}


def main(data):
    errors = []
    if not isinstance(data, dict):
        return {"errors": ["Input must be a JSON object."], "disputes": []}
    as_of = date_value(data.get("as_of_date"))
    if not as_of:
        errors.append("as_of_date is required in MM/DD/YYYY format.")
    user_id = data.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        errors.append("user_id is required.")

    accounts = as_index(data.get("accounts", []), "account_id")
    cards = as_index(data.get("cards", []), "card_id")
    transactions = as_index(data.get("transactions", []), "transaction_id")
    requests = data.get("requests", [])
    if not isinstance(requests, list) or not requests:
        errors.append("requests must be a nonempty array.")
        requests = []

    open_counts = {}
    for dispute in data.get("open_disputes", []) if isinstance(data.get("open_disputes", []), list) else []:
        if isinstance(dispute, dict) and dispute.get("status") not in FINAL_DISPUTE_STATUSES:
            account_id = dispute.get("account_id")
            if account_id is not None:
                open_counts[str(account_id)] = open_counts.get(str(account_id), 0) + 1

    # Earliest valid duplicate request per caller-defined duplicate group.
    duplicate_winners = {}
    for index, request in enumerate(requests):
        if not isinstance(request, dict):
            continue
        category, _ = resolve_category(request)
        if category != "duplicate_charge" or not request.get("duplicate_group"):
            continue
        txn = transactions.get(str(request.get("transaction_id")))
        when = date_value(txn.get("date")) if txn else None
        group = str(request["duplicate_group"])
        if when and (group not in duplicate_winners or when < duplicate_winners[group][0]):
            duplicate_winners[group] = (when, index)

    results = []
    card_actions = {}
    planned_per_account = {}
    saw_security = False
    saw_complex_billing = False

    for index, request in enumerate(requests):
        result = {"request_index": index, "blockers": [], "warnings": []}
        if not isinstance(request, dict):
            result["blockers"].append("Request must be an object.")
            results.append(result)
            continue
        category, category_error = resolve_category(request)
        result["category"] = category
        if category_error:
            result["blockers"].append(category_error)
        if category in {"card_present_fraud", "card_not_present_fraud", "unauthorized_transaction"}:
            saw_security = saw_security or category != "unauthorized_transaction" or request.get("fraud_suspected") is True
        if category in {"recurring_charge_after_cancellation", "incorrect_amount", "goods_services_not_received", "duplicate_charge"}:
            saw_complex_billing = True

        txn_id = request.get("transaction_id")
        txn = transactions.get(str(txn_id)) if txn_id is not None else None
        if not txn:
            result["blockers"].append("Transaction was not found in supplied transaction history.")
        account = accounts.get(str(txn.get("account_id"))) if txn else None
        card_id = request.get("card_id")
        card = cards.get(str(card_id)) if card_id is not None else None
        if not card_id:
            result["blockers"].append("card_id is required and must be confirmed from card lookup.")
        elif not card:
            result["blockers"].append("Card was not found in supplied card lookup.")
        if txn and card and str(card.get("account_id")) != str(txn.get("account_id")):
            result["blockers"].append("Card is not linked to the transaction's account.")
        if card and str(card.get("user_id")) != str(user_id):
            result["blockers"].append("Cardholder user_id does not match the verified customer.")
        if not account:
            result["blockers"].append("Transaction account was not found in supplied account data.")
        else:
            if str(account.get("account_type", "")).lower() != "checking":
                result["blockers"].append("The linked account is not a checking account.")
            if account.get("status") != "OPEN":
                result["blockers"].append("The linked checking account is not OPEN.")
            tier = normalized_tier(account.get("account_class"))
            if not tier:
                result["blockers"].append("Account class must identify Entry, Mid, Premium, or Elite tier.")
            else:
                used = open_counts.get(str(account.get("account_id")), 0) + planned_per_account.get(str(account.get("account_id")), 0)
                if used >= TIER_LIMITS[tier]:
                    result["blockers"].append("This account has reached its maximum open-dispute limit.")

        tx_date = date_value(txn.get("date")) if txn else None
        if not tx_date:
            result["blockers"].append("Transaction date is missing or not MM/DD/YYYY.")
        elif as_of and (as_of - tx_date).days > 60:
            result["blockers"].append("Transaction is more than 60 days old.")
        elif as_of and (as_of - tx_date).days < 0:
            result["blockers"].append("Transaction date cannot be in the future.")
        try:
            amount = abs(float(txn.get("amount"))) if txn else None
        except (TypeError, ValueError):
            amount = None
        if amount is None or amount < 1.0:
            result["blockers"].append("Disputed transaction amount must be at least $1.00.")

        if not date_value(request.get("discovery_date")):
            result["blockers"].append("discovery_date is required in MM/DD/YYYY format.")
        if request.get("transaction_type") not in TRANSACTION_TYPES:
            result["blockers"].append("A valid exact transaction_type is required.")
        if not isinstance(request.get("card_in_possession"), bool):
            result["blockers"].append("card_in_possession must be recorded as a boolean.")
        if request.get("pin_compromised") not in PIN_VALUES:
            result["blockers"].append("pin_compromised must be yes_shared, yes_observed, no, or unknown.")
        for field in ("contacted_merchant", "police_report_filed", "written_statement_provided"):
            if not isinstance(request.get(field), bool):
                result["blockers"].append(field + " must be recorded as a boolean.")
        if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"} and request.get("atm_network") not in {"rho_bank", "third_party"}:
            result["blockers"].append("ATM disputes require atm_network 'rho_bank' or 'third_party'.")
        if category == "duplicate_charge":
            group = request.get("duplicate_group")
            if not group:
                result["blockers"].append("Duplicate claims require a duplicate_group to select the earliest transaction.")
            elif duplicate_winners.get(str(group), (None, index))[1] != index:
                result["blockers"].append("Only the earliest transaction in a duplicate group may be disputed.")
        if category in {"card_present_fraud", "card_not_present_fraud"} and amount and amount > 500 and request.get("police_report_filed") is False:
            result["warnings"].append("Recommend that the customer file a police report for this fraud claim over $500.")
        if category and category not in {"card_present_fraud", "card_not_present_fraud", "unauthorized_transaction"} and request.get("contacted_merchant") is False:
            result["warnings"].append("Merchant contact was not completed; this can affect provisional-credit eligibility.")

        liability_timing = request.get("liability_timing")
        if category in {"card_present_fraud", "card_not_present_fraud", "unauthorized_transaction"}:
            if liability_timing not in LIABILITY:
                result["blockers"].append("Explain and record applicable liability timing before proceeding with unauthorized activity.")
            else:
                result["liability_notice"] = LIABILITY[liability_timing]

        pc = provisional_assessment(request, category, account, as_of) if category else {"status": "undetermined", "reason": "Category is unresolved."}
        result["provisional_credit"] = pc
        if category:
            result["card_action"] = ACTION_BY_CATEGORY[category]

        if not result["blockers"] and category and txn and account and card:
            result["filing_arguments"] = {
                "transaction_id": str(txn["transaction_id"]),
                "account_id": str(account["account_id"]),
                "card_id": str(card["card_id"]),
                "user_id": str(user_id),
                "dispute_category": category,
                "transaction_date": txn["date"],
                "discovery_date": request["discovery_date"],
                "disputed_amount": amount,
                "transaction_type": request["transaction_type"],
                "card_in_possession": request["card_in_possession"],
                "pin_compromised": request["pin_compromised"],
                "contacted_merchant": request["contacted_merchant"],
                "police_report_filed": request["police_report_filed"],
                "written_statement_provided": request["written_statement_provided"],
                "provisional_credit_eligible": pc["status"] == "required",
                "card_action": ACTION_BY_CATEGORY[category],
            }
            account_key = str(account["account_id"])
            planned_per_account[account_key] = planned_per_account.get(account_key, 0) + 1
            old = card_actions.get(str(card["card_id"]), "keep_active")
            new = ACTION_BY_CATEGORY[category]
            if SEVERITY[new] > SEVERITY[old]:
                card_actions[str(card["card_id"])] = new
        results.append(result)

    global_blockers = []
    if data.get("customer_verified") is not True:
        global_blockers.append("Customer identity has not been verified; do not take banking action.")
    transfer = None
    if saw_security or data.get("human_requested") is True:
        if saw_security:
            transfer = {"reason": "fraud_or_security_concern", "priority": "Tier 1"}
        elif saw_complex_billing:
            transfer = {"reason": "complex_billing_dispute", "priority": "Tier 1"}
        else:
            transfer = {"reason": "customer_requests_human_no_specific_reason", "priority": "Tier 3"}
    elif saw_complex_billing:
        transfer = {"reason": "complex_billing_dispute", "priority": "Tier 1 if specialist review is needed"}

    return {
        "errors": errors,
        "global_blockers": global_blockers,
        "disputes": results,
        "card_actions_after_successful_filings": [
            {"card_id": card_id, "action": action} for card_id, action in sorted(card_actions.items())
        ],
        "transfer_recommendation": transfer,
        "non_execution_notice": "This plan does not file disputes, alter cards, block payments, or transfer a customer."
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": ["Invalid JSON input: " + str(exc)], "disputes": []}))
        sys.exit(1)
