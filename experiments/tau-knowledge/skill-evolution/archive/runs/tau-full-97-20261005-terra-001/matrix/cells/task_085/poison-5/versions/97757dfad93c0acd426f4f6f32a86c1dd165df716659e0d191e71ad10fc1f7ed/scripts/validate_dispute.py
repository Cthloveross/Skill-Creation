#!/usr/bin/env python3
"""Validate debit-card dispute data and emit safe filing recommendations.

Reads one JSON object from stdin and writes one JSON object to stdout. This script
never calls banking tools and does not persist any data.
"""
import datetime as dt
import json
import sys

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TRANSACTION_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
ACTIONS = {
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
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
TIER_LIMITS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be MM/DD/YYYY")
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError as exc:
        raise ValueError(f"{field} must be MM/DD/YYYY") from exc


def boolean(value, field, errors):
    if not isinstance(value, bool):
        errors.append(f"{field} must be boolean")
        return False
    return value


def amount(value, field, errors):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be numeric")
        return None
    return float(value)


def liability(days):
    if not isinstance(days, int) or isinstance(days, bool) or days < 0:
        return None
    if days <= 2:
        return 50.0
    if days <= 60:
        return 500.0
    return None  # Unlimited; a calculable offset is not appropriate.


def normalized_tier(value):
    return str(value or "").strip().upper().replace(" TIER", "")


def account_age_days(as_of, opened):
    return (as_of - opened).days


def validate(data):
    global_errors = []
    try:
        as_of = date(data.get("as_of_date"), "as_of_date")
    except ValueError as exc:
        return {"ready": False, "blockers": [str(exc)], "warnings": [], "filings": [], "card_actions": []}

    if data.get("identity_verified") is not True:
        global_errors.append("Customer identity/authority has not been verified and recorded")
    account = data.get("account") or {}
    card = data.get("card") or {}
    if str(account.get("account_type", "")).lower() != "checking":
        global_errors.append("Selected account is not a checking account")
    if str(account.get("status", "")).upper() != "OPEN":
        global_errors.append("Selected checking account is not OPEN")
    if not account.get("account_id"):
        global_errors.append("account.account_id is required")
    if not card.get("card_id") or not card.get("user_id"):
        global_errors.append("card.card_id and card.user_id are required")
    if card.get("account_id") != account.get("account_id"):
        global_errors.append("Selected card is not linked to selected account")
    tier = normalized_tier(account.get("account_class"))
    if tier not in TIER_LIMITS:
        global_errors.append("account.account_class must identify Entry, Mid, Premium, or Elite tier")
    try:
        opened = date(account.get("date_opened"), "account.date_opened")
        if opened > as_of:
            global_errors.append("account.date_opened cannot be in the future")
    except ValueError as exc:
        opened = None
        global_errors.append(str(exc))

    open_disputes = sum(
        1 for item in (data.get("existing_disputes") or [])
        if item.get("account_id") == account.get("account_id")
        and str(item.get("status", "")).upper() in OPEN_STATUSES
    )
    limit = TIER_LIMITS.get(tier, 0)
    transaction_by_id = {x.get("transaction_id"): x for x in (data.get("transactions") or []) if x.get("transaction_id")}
    filings, all_blockers, all_warnings = [], list(global_errors), []
    pending_per_account = 0

    for index, claim in enumerate(data.get("claims") or [], start=1):
        errors, warnings = [], []
        prefix = f"claim {index}: "
        txid = claim.get("transaction_id")
        tx = transaction_by_id.get(txid)
        if not tx:
            errors.append("transaction_id does not match a supplied account transaction")
        else:
            if tx.get("account_id") != account.get("account_id"):
                errors.append("transaction belongs to a different account")
            try:
                tx_date = date(tx.get("date"), "transaction.date")
                age = (as_of - tx_date).days
                if age < 0:
                    errors.append("transaction date cannot be in the future")
                elif age > 60:
                    errors.append("transaction is more than 60 days old")
            except ValueError as exc:
                errors.append(str(exc))
                tx_date = None
            tx_amount = amount(tx.get("amount"), "transaction.amount", errors)
            if tx_amount is not None and abs(tx_amount) < 1.0:
                errors.append("transaction amount must be at least $1.00")

        category = claim.get("dispute_category")
        if category not in CATEGORIES:
            errors.append("dispute_category is invalid")
        transaction_type = claim.get("transaction_type")
        if transaction_type not in TRANSACTION_TYPES:
            errors.append("transaction_type is invalid")
        disputed = amount(claim.get("disputed_amount"), "disputed_amount", errors)
        if disputed is not None and disputed < 1.0:
            errors.append("disputed_amount must be at least $1.00")
        if tx and disputed is not None and tx_amount is not None and disputed > abs(tx_amount):
            errors.append("disputed_amount cannot exceed transaction amount")
        try:
            discovery = date(claim.get("discovery_date"), "discovery_date")
            if tx and tx_date and discovery < tx_date:
                warnings.append("discovery date precedes transaction date; confirm the customer-provided dates")
        except ValueError as exc:
            errors.append(str(exc))

        card_in_possession = boolean(claim.get("card_in_possession"), "card_in_possession", errors)
        contacted_merchant = boolean(claim.get("contacted_merchant"), "contacted_merchant", errors)
        police_report = boolean(claim.get("police_report_filed"), "police_report_filed", errors)
        written = boolean(claim.get("written_statement_provided"), "written_statement_provided", errors)
        pin = claim.get("pin_compromised")
        if pin not in PINS:
            errors.append("pin_compromised is invalid")
        if category not in {"card_present_fraud", "card_not_present_fraud"} and contacted_merchant is False:
            warnings.append("non-fraud claim has no prior merchant/operator contact; required provisional credit may not apply")
        if category in {"card_present_fraud", "card_not_present_fraud"} and disputed is not None and disputed > 500 and not police_report:
            warnings.append("recommend a police report for suspected fraud above $500")
        if category == "card_present_fraud" and transaction_type not in {"pin_purchase", "signature_purchase"}:
            warnings.append("confirm that suspected fraud was physical card use")
        if category == "card_not_present_fraud" and transaction_type != "online_purchase":
            warnings.append("confirm that suspected fraud was online or phone/card-not-present")

        if category == "duplicate_charge":
            group = claim.get("duplicate_group_transaction_ids")
            if group is not None:
                candidates = [transaction_by_id.get(i) for i in group]
                if not isinstance(group, list) or not candidates or any(x is None for x in candidates):
                    errors.append("duplicate_group_transaction_ids must contain supplied transaction IDs")
                else:
                    try:
                        earliest = min(candidates, key=lambda x: date(x.get("date"), "duplicate transaction.date"))
                        if txid != earliest.get("transaction_id"):
                            errors.append("duplicate disputes must select the earliest transaction first")
                    except ValueError as exc:
                        errors.append(str(exc))
            else:
                warnings.append("verify this is the earliest transaction among duplicates")

        atm_owner = claim.get("atm_owner")
        journal = claim.get("atm_journal_result")
        if category == "atm_cash_discrepancy":
            if atm_owner not in {"RHO_BANK", "THIRD_PARTY"}:
                errors.append("ATM cash discrepancy requires atm_owner RHO_BANK or THIRD_PARTY")
            if atm_owner == "RHO_BANK" and journal not in {"confirmed", "correct_amount", "unavailable"}:
                errors.append("Rho-Bank ATM cash discrepancy requires journal review result")
            if atm_owner == "RHO_BANK" and journal == "correct_amount":
                warnings.append("journal indicates correct dispensing; claim may still be formally filed")
            if atm_owner == "THIRD_PARTY":
                warnings.append("submit a chargeback request to the ATM owner/network; investigation may take up to 90 days")
                if disputed is not None and disputed > 200:
                    warnings.append("Electronic Fund Transfer Error Resolution Affidavit is required")
        if category == "atm_deposit_not_credited" and atm_owner == "RHO_BANK":
            if claim.get("atm_deposit_images_reviewed") is not True:
                warnings.append("retrieve and review Rho-Bank ATM deposit images")

        timely = claim.get("timely_reporting_within_60_days_of_statement")
        if not isinstance(timely, bool):
            errors.append("timely_reporting_within_60_days_of_statement must be boolean")
            timely = False
        new_cnp = opened is not None and account_age_days(as_of, opened) < 30 and category == "card_not_present_fraud"
        unrestricted = account.get("holds_or_restrictions") is False
        pc_eligible = bool(timely and category in PC_CATEGORIES and written and unrestricted and pin != "yes_shared" and not new_cnp)
        if category not in {"card_present_fraud", "card_not_present_fraud"} and contacted_merchant is False:
            pc_eligible = False
        days = claim.get("days_from_statement_discovery")
        offset = liability(days)
        if not isinstance(days, int) or isinstance(days, bool) or days < 0:
            warnings.append("provide days_from_statement_discovery to calculate the applicable liability disclosure/offset")
        elif offset is None:
            warnings.append("reported after 60 days: liability may be unlimited and recovery may not be available")
        pc_amount = None
        if pc_eligible and disputed is not None:
            pc_amount = max(0.0, disputed - (offset or 0.0))
        immediate = bool(pc_eligible and category == "atm_cash_discrepancy" and atm_owner == "RHO_BANK" and journal == "confirmed")

        if open_disputes + pending_per_account >= limit:
            errors.append(f"open-dispute limit reached for {tier.title()} tier account ({limit})")
        if errors or global_errors:
            all_blockers.extend(prefix + message for message in errors)
            all_warnings.extend(prefix + message for message in warnings)
            continue
        pending_per_account += 1
        payload = {
            "transaction_id": txid,
            "account_id": account.get("account_id"),
            "card_id": card.get("card_id"),
            "user_id": card.get("user_id"),
            "dispute_category": category,
            "transaction_date": tx.get("date"),
            "discovery_date": claim.get("discovery_date"),
            "disputed_amount": disputed,
            "transaction_type": transaction_type,
            "card_in_possession": card_in_possession,
            "pin_compromised": pin,
            "contacted_merchant": contacted_merchant,
            "police_report_filed": police_report,
            "written_statement_provided": written,
            "provisional_credit_eligible": pc_eligible,
            "card_action": ACTIONS.get(category),
        }
        filings.append({
            "claim_index": index,
            "payload": payload,
            "provisional_credit_amount": pc_amount,
            "immediate_provisional_credit_recommended": immediate,
            "liability_disclosure_maximum": offset,
            "warnings": warnings,
        })
        all_warnings.extend(prefix + message for message in warnings)

    action_by_card = {}
    for item in filings:
        payload = item["payload"]
        card_id, action = payload["card_id"], payload["card_action"]
        if card_id not in action_by_card or SEVERITY[action] > SEVERITY[action_by_card[card_id]]:
            action_by_card[card_id] = action
    card_actions = [{"card_id": key, "actual_action_after_all_filings": value} for key, value in action_by_card.items()]
    return {
        "ready": not all_blockers and bool(filings),
        "blockers": all_blockers,
        "warnings": all_warnings,
        "filings": filings,
        "card_actions": card_actions,
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(validate(data), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ready": False, "blockers": [str(exc)], "warnings": [], "filings": [], "card_actions": []}, separators=(",", ":")))


if __name__ == "__main__":
    main()
