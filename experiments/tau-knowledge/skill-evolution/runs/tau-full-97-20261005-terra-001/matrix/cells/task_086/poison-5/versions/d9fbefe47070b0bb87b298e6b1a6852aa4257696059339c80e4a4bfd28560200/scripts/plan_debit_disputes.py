#!/usr/bin/env python3
"""Plan debit-card dispute filings without performing banking actions.

Input JSON schema:
{
  "as_of_date": "MM/DD/YYYY", "identity_verified": bool, "user_id": str,
  "accounts": [{"account_id": str, "account_type": str, "account_class": str,
                "status": str, "date_opened": "MM/DD/YYYY"|null,
                "has_holds_or_restrictions": bool}],
  "cards": [{"card_id": str, "account_id": str, "user_id": str, "status": str}],
  "transactions": [{"transaction_id": str, "account_id": str, "date": "MM/DD/YYYY",
                    "amount": number, "type": str, "status": str}],
  "existing_disputes": [{"account_id": str, "status": str}],
  "claims": [{"transaction_id": str, "account_id": str, "card_id": str,
              "dispute_category": str, "transaction_type": str,
              "discovery_date": "MM/DD/YYYY", "disputed_amount": number,
              "card_in_possession": bool, "pin_compromised": str,
              "contacted_merchant": bool, "police_report_filed": bool,
              "written_statement_provided": bool,
              "statement_date": "MM/DD/YYYY"|null,
              "duplicate_group": str|null, "fraud_suspected": bool|null,
              "atm_owner": "rho_bank"|"third_party"|null}]
}

Output JSON contains one plan per eligible-for-review claim, skipped duplicate claims,
and card-level post-filing action recommendations. The program never invokes tools.
"""
import json
import sys
from datetime import datetime, date

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
         "atm_deposit", "recurring_payment", "person_to_person"}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
PROVISIONAL_CATEGORIES = {"unauthorized_transaction", "card_present_fraud",
                          "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def business_days_between(start, end):
    """Weekdays elapsed after start through end; holidays are not modeled."""
    if not start or not end or end < start:
        return None
    total = 0
    cursor = start
    while cursor < end:
        cursor = date.fromordinal(cursor.toordinal() + 1)
        if cursor.weekday() < 5:
            total += 1
    return total


def norm(value):
    return str(value or "").strip().lower()


def add_once(items, message):
    if message not in items:
        items.append(message)


def main(data):
    as_of = parse_date(data.get("as_of_date"))
    accounts = {x.get("account_id"): x for x in data.get("accounts", []) if x.get("account_id")}
    cards = {x.get("card_id"): x for x in data.get("cards", []) if x.get("card_id")}
    transactions = {x.get("transaction_id"): x for x in data.get("transactions", []) if x.get("transaction_id")}
    user_id = data.get("user_id")
    existing = data.get("existing_disputes", [])
    open_count = {}
    for dispute in existing:
        if str(dispute.get("status", "")).upper() in OPEN_STATUSES:
            account_id = dispute.get("account_id")
            open_count[account_id] = open_count.get(account_id, 0) + 1

    claims = list(data.get("claims", []))
    # A duplicate group is explicitly provided by the executor after comparing transactions.
    earliest_by_group = {}
    for index, claim in enumerate(claims):
        group = claim.get("duplicate_group")
        if claim.get("dispute_category") != "duplicate_charge" or not group:
            continue
        tx = transactions.get(claim.get("transaction_id"), {})
        tx_date = parse_date(tx.get("date"))
        old = earliest_by_group.get(group)
        if old is None or (tx_date is not None and (old[0] is None or tx_date < old[0])):
            earliest_by_group[group] = (tx_date, index)

    plans, skipped, card_actions = [], [], {}
    planned_per_account = {}
    for index, claim in enumerate(claims):
        group = claim.get("duplicate_group")
        if group and claim.get("dispute_category") == "duplicate_charge":
            chosen = earliest_by_group[group][1]
            if index != chosen:
                skipped.append({"claim_index": index, "transaction_id": claim.get("transaction_id"),
                                "reason": "Later duplicate transaction; only the earliest transaction may be disputed."})
                continue

        blocking, warnings, followups = [], [], []
        transaction = transactions.get(claim.get("transaction_id"))
        account = accounts.get(claim.get("account_id"))
        card = cards.get(claim.get("card_id"))
        category = claim.get("dispute_category")
        tx_type = claim.get("transaction_type")
        tx_date = parse_date(transaction.get("date")) if transaction else None
        discovery = parse_date(claim.get("discovery_date"))
        statement_date = parse_date(claim.get("statement_date"))

        if not data.get("identity_verified"):
            add_once(blocking, "Customer identity has not been verified and logged.")
        if not user_id:
            add_once(blocking, "Missing verified user_id.")
        if not transaction:
            add_once(blocking, "Transaction ID was not found in the supplied account transactions.")
        if not account:
            add_once(blocking, "Selected checking account was not supplied.")
        if not card:
            add_once(blocking, "Selected debit card was not supplied.")
        if transaction and transaction.get("account_id") != claim.get("account_id"):
            add_once(blocking, "Transaction does not belong to the selected account.")
        if norm(account.get("account_type")) != "checking" if account else False:
            add_once(blocking, "Debit card disputes require a checking account.")
        if account and str(account.get("status", "")).upper() != "OPEN":
            add_once(blocking, "Linked checking account is not OPEN.")
        if card and (card.get("account_id") != claim.get("account_id") or card.get("user_id") != user_id):
            add_once(blocking, "Card is not linked to the selected account and verified user.")
        if category not in CATEGORIES:
            add_once(blocking, "Invalid or missing dispute category.")
        if tx_type not in TYPES:
            add_once(blocking, "Invalid or missing transaction type.")
        if claim.get("pin_compromised") not in PINS:
            add_once(blocking, "pin_compromised must be yes_shared, yes_observed, no, or unknown.")
        if not isinstance(claim.get("card_in_possession"), bool):
            add_once(blocking, "card_in_possession must be collected as a boolean.")
        if not isinstance(claim.get("written_statement_provided"), bool):
            add_once(blocking, "Written-statement consent is missing.")
        if not isinstance(claim.get("contacted_merchant"), bool):
            add_once(blocking, "Merchant-contact answer is missing.")
        try:
            amount = float(claim.get("disputed_amount"))
        except (TypeError, ValueError):
            amount = None
        if amount is None or amount < 1:
            add_once(blocking, "Disputed amount must be at least $1.00.")
        if transaction and amount is not None and abs(float(transaction.get("amount", 0))) + 1e-9 < amount:
            add_once(blocking, "Disputed amount exceeds the transaction amount; confirm the claimed amount.")
        if not tx_date:
            add_once(blocking, "Transaction date is missing or invalid.")
        if not as_of:
            add_once(blocking, "as_of_date is required in MM/DD/YYYY format to check the 60-day filing window.")
        elif tx_date and (as_of - tx_date).days > 60:
            add_once(blocking, "Transaction is more than 60 calendar days old.")
        elif tx_date and (as_of - tx_date).days < 0:
            add_once(blocking, "Transaction date is in the future.")
        if not discovery:
            add_once(blocking, "Discovery date is missing or invalid.")

        is_fraud = category in {"card_present_fraud", "card_not_present_fraud"}
        non_fraud = category not in {"card_present_fraud", "card_not_present_fraud"}
        if non_fraud and claim.get("contacted_merchant") is not True:
            add_once(blocking, "Non-fraud dispute requires attempted merchant contact.")
        stated_fraud = claim.get("fraud_suspected")
        if category == "unauthorized_transaction" and stated_fraud is True:
            add_once(blocking, "Suspected fraud must use a card-present or card-not-present fraud category, not unauthorized_transaction.")
        if category == "card_not_present_fraud" and tx_type != "online_purchase":
            add_once(warnings, "Confirm this was online/phone/card-not-present; transaction type does not indicate online purchase.")
        if category == "card_present_fraud" and tx_type == "online_purchase":
            add_once(blocking, "Online purchase suspected fraud must use card_not_present_fraud.")

        tier = norm(account.get("account_class")) if account else ""
        maximum = LIMITS.get(tier)
        if maximum is None:
            add_once(blocking, "Unknown checking account tier; cannot determine the per-account open-dispute limit.")
        else:
            projected = open_count.get(claim.get("account_id"), 0) + planned_per_account.get(claim.get("account_id"), 0)
            if projected >= maximum:
                add_once(blocking, "Account has reached its maximum number of open disputes.")

        action = ACTIONS.get(category, "keep_active")
        # Liability is computed only when a statement date is supplied; it is informational.
        report_basis = discovery
        liability = None
        if statement_date and report_basis:
            elapsed = business_days_between(statement_date, report_basis)
            if elapsed is not None:
                liability = 50 if elapsed <= 2 else (500 if elapsed <= 60 else None)
                if elapsed > 60:
                    add_once(warnings, "Reported more than 60 business days after statement date; recovery may be unavailable.")
        elif category in {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud"}:
            add_once(warnings, "Statement date is needed to explain and assess Regulation E reporting liability and timeliness.")

        account_new = False
        opened = parse_date(account.get("date_opened")) if account else None
        if as_of and opened:
            account_new = (as_of - opened).days < 30
        timely = bool(statement_date and discovery and (discovery - statement_date).days <= 60 and (discovery - statement_date).days >= 0)
        unrestricted = bool(account and str(account.get("status", "")).upper() == "OPEN" and not account.get("has_holds_or_restrictions", False))
        provisional = (category in PROVISIONAL_CATEGORIES and timely and
                       claim.get("written_statement_provided") is True and unrestricted and
                       claim.get("pin_compromised") != "yes_shared" and
                       not (account_new and category == "card_not_present_fraud"))
        if category in PROVISIONAL_CATEGORIES and not statement_date:
            add_once(warnings, "Cannot establish required provisional-credit timeliness without the statement date.")
        if category in {"goods_services_not_received", "recurring_charge_after_cancellation", "atm_deposit_not_credited", "incorrect_amount"}:
            add_once(warnings, "This category does not require provisional credit.")
        if is_fraud and amount is not None and amount > 500 and claim.get("police_report_filed") is not True:
            add_once(followups, "Ask about a police report and recommend filing one for suspected fraud over $500.")
        if category == "atm_cash_discrepancy":
            owner = claim.get("atm_owner")
            if owner not in {"rho_bank", "third_party"}:
                add_once(blocking, "Identify whether the ATM is Rho-Bank owned or third-party.")
            elif owner == "third_party":
                add_once(followups, "Submit the third-party ATM chargeback/network process; investigation may take up to 90 days.")
                if amount is not None and amount > 200:
                    add_once(followups, "Send Electronic Fund Transfer Error Resolution Affidavit; it must be returned within 10 business days.")
            else:
                add_once(followups, "Review Rho-Bank ATM journal evidence; confirmed cash discrepancies receive immediate provisional credit.")

        plan = {
            "claim_index": index,
            "transaction_id": claim.get("transaction_id"),
            "eligible_to_file": not blocking,
            "blocking_reasons": blocking,
            "warnings": warnings,
            "required_followups": followups,
            "liability_maximum": liability,
            "provisional_credit_eligible": provisional,
            "provisional_credit_timing_business_days": 20 if account_new else 10,
            "card_action": action,
            "tool_arguments": {
                "transaction_id": claim.get("transaction_id"), "account_id": claim.get("account_id"),
                "card_id": claim.get("card_id"), "user_id": user_id, "dispute_category": category,
                "transaction_date": transaction.get("date") if transaction else None,
                "discovery_date": claim.get("discovery_date"), "disputed_amount": amount,
                "transaction_type": tx_type, "card_in_possession": claim.get("card_in_possession"),
                "pin_compromised": claim.get("pin_compromised"), "contacted_merchant": claim.get("contacted_merchant"),
                "police_report_filed": claim.get("police_report_filed"),
                "written_statement_provided": claim.get("written_statement_provided"),
                "provisional_credit_eligible": provisional, "card_action": action,
            },
        }
        plans.append(plan)
        if not blocking:
            planned_per_account[claim.get("account_id")] = planned_per_account.get(claim.get("account_id"), 0) + 1
            prior = card_actions.get(claim.get("card_id"), "keep_active")
            if SEVERITY[action] > SEVERITY[prior]:
                card_actions[claim.get("card_id")] = action

    return {"plans": plans, "skipped_duplicate_claims": skipped,
            "post_filing_card_actions": [{"card_id": card_id, "action": action}
                                          for card_id, action in card_actions.items()]}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        sys.exit(1)
