#!/usr/bin/env python3
"""Create a deterministic, non-executing debit-card dispute filing plan.
Input: JSON described in SKILL.md. Output: {"plans": [...], "card_actions": [...]}.
No banking tools are called by this helper.
"""
import json
import sys
from datetime import datetime, date

OPEN_DISPUTE_STATUSES = {
    "OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"
}
FINAL_DISPUTE_STATUSES = {
    "RESOLVED_CUSTOMER_FAVOR", "RESOLVED_BANK_FAVOR", "RESOLVED_PARTIAL",
    "PROVISIONAL_REVERSED", "CLOSED_NO_RESPONSE"
}
LIMITS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
CARD_ACTIONS = {
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
VALID_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person"
}
PROVISIONAL_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge"
}
NON_PROVISIONAL_CATEGORIES = {
    "goods_services_not_received", "recurring_charge_after_cancellation",
    "atm_deposit_not_credited", "incorrect_amount"
}
FRAUD_CATEGORIES = {"card_present_fraud", "card_not_present_fraud"}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def mmddyyyy(value):
    d = parse_date(value)
    return d.strftime("%m/%d/%Y") if d else None


def money(value):
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return None


def tier(value):
    text = str(value or "").upper().strip()
    for key in LIMITS:
        if key in text:
            return key
    return None


def open_count(existing, account_id):
    return sum(1 for item in existing if item.get("account_id") == account_id
               and str(item.get("status", "")).upper() in OPEN_DISPUTE_STATUSES)


def liability_timing(claim, as_of):
    supplied = claim.get("reporting_timing")
    if supplied in {"within_2_business_days", "within_60_days", "after_60_days"}:
        return supplied
    statement = parse_date(claim.get("statement_date"))
    if not statement:
        return None
    report = parse_date(claim.get("report_date")) or as_of
    if not report:
        return None
    days = (report - statement).days
    if days < 0:
        return "within_2_business_days"
    # This is calendar-day approximation only. Callers needing a precise 2-business-day
    # result must supply reporting_timing after applying their business-day calendar.
    if days <= 2:
        return "within_2_business_days"
    if days <= 60:
        return "within_60_days"
    return "after_60_days"


def main(data):
    as_of = parse_date(data.get("as_of"))
    accounts = {x.get("account_id"): x for x in data.get("accounts", [])}
    cards = list(data.get("cards", []))
    txs = {x.get("transaction_id"): x for x in data.get("transactions", [])}
    existing = list(data.get("existing_disputes", []))
    plans = []

    for claim in data.get("claims", []):
        blocks, needs, notices, post = [], [], [], []
        category = claim.get("category")
        account_id = claim.get("account_id")
        account = accounts.get(account_id)
        if not data.get("identity_verified"):
            blocks.append("Customer identity has not been verified and logged.")
        if not account:
            blocks.append("Claim account was not found in supplied account data.")
        else:
            if str(account.get("account_type", "")).lower() != "checking":
                blocks.append("Debit-card disputes require a checking account.")
            if str(account.get("status", "")).upper() != "OPEN":
                blocks.append("Linked checking account is not OPEN.")

        matching_cards = [c for c in cards if c.get("account_id") == account_id]
        card_id = claim.get("card_id")
        if card_id:
            matching_cards = [c for c in matching_cards if c.get("card_id") == card_id]
        elif claim.get("card_last4") is not None:
            wanted = str(claim.get("card_last4"))
            matching_cards = [c for c in matching_cards if str(c.get("card_number_last_4")) == wanted]
        if len(matching_cards) != 1:
            blocks.append("Could not uniquely identify the debit card for this account and last four/card ID.")
            card = None
        else:
            card = matching_cards[0]
            card_id = card.get("card_id")
            if card.get("user_id") != data.get("user_id"):
                blocks.append("Matched card is not owned by the verified user.")

        selected_id = claim.get("transaction_id")
        if category == "duplicate_charge" and claim.get("duplicate_transaction_ids"):
            candidates = [txs.get(x) for x in claim["duplicate_transaction_ids"] if txs.get(x)]
            if candidates:
                candidates.sort(key=lambda x: parse_date(x.get("date")) or date.max)
                selected_id = candidates[0].get("transaction_id")
                if len(candidates) > 1:
                    notices.append("Duplicate rule applied: earliest supplied matching transaction selected first.")
            else:
                blocks.append("None of the supplied duplicate transaction IDs were found.")
        tx = txs.get(selected_id)
        if not tx:
            blocks.append("Transaction ID was not found; retrieve and match account transactions before filing.")
        else:
            if tx.get("account_id") != account_id:
                blocks.append("Transaction does not belong to the claim account.")
            if str(tx.get("status", "")).lower() not in {"posted", "pending"}:
                blocks.append("Transaction status is not recognized as posted or pending.")
            tdate = parse_date(tx.get("date"))
            if not tdate or not as_of:
                needs.append("A valid transaction date and filing date are required for the 60-day check.")
            elif (as_of - tdate).days > 60:
                blocks.append("Transaction is more than 60 days old on filing date.")
            elif (as_of - tdate).days < 0:
                blocks.append("Transaction date is after filing date.")
            disputed = money(claim.get("disputed_amount"))
            posted = money(tx.get("amount"))
            if disputed is None:
                blocks.append("Disputed amount is missing or invalid.")
            else:
                if disputed < 1:
                    blocks.append("Disputed amount must be at least $1.00.")
                if posted is not None and disputed > posted + 1e-9:
                    blocks.append("Disputed amount cannot exceed the posted transaction amount.")

        if category not in CARD_ACTIONS:
            blocks.append("Dispute category is missing or unsupported.")
        if claim.get("transaction_type") not in VALID_TYPES:
            blocks.append("Transaction type is missing or unsupported.")
        if not parse_date(claim.get("discovery_date")):
            needs.append("Discovery date is required in YYYY-MM-DD or MM/DD/YYYY format.")
        for key in ("card_in_possession", "contacted_merchant", "written_statement_provided"):
            if not isinstance(claim.get(key), bool):
                needs.append(f"{key} must be explicitly true or false.")
        if claim.get("pin_compromised") not in {"yes_shared", "yes_observed", "no", "unknown"}:
            needs.append("PIN compromise answer must be yes_shared, yes_observed, no, or unknown.")
        if category not in FRAUD_CATEGORIES and claim.get("contacted_merchant") is not True:
            blocks.append("Non-fraud disputes require an attempted merchant resolution before filing.")
        if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
            if claim.get("atm_owner") not in {"rho_bank", "third_party"}:
                needs.append("ATM owner must be rho_bank or third_party.")
            elif claim.get("atm_owner") == "third_party":
                post.append("Submit chargeback request to the third-party ATM owner/network; 90-day investigation timeline applies.")
                if category == "atm_cash_discrepancy" and (money(claim.get("disputed_amount")) or 0) > 200:
                    notices.append("Electronic Fund Transfer Error Resolution Affidavit is required: email it to the registered address; it must be signed and returned within 10 business days. Failure may result in denial; false signing is a federal offense.")
            elif claim.get("atm_owner") == "rho_bank":
                if category == "atm_cash_discrepancy":
                    post.append("Review Rho-Bank ATM journal records; if discrepancy is confirmed, issue provisional credit immediately.")
                else:
                    post.append("Retrieve ATM deposit images and compare them with the claimed deposit.")

        if account:
            account_tier = tier(account.get("account_class"))
            if not account_tier:
                needs.append("Account class must map to Entry, Mid, Premium, or Elite to validate dispute limit.")
            else:
                current_open = open_count(existing, account_id)
                if current_open >= LIMITS[account_tier]:
                    blocks.append(f"Account has reached its {LIMITS[account_tier]} open-dispute limit for {account_tier.title()} tier.")
        duplicate_existing = [d for d in existing if d.get("transaction_id") == selected_id]
        if duplicate_existing:
            blocks.append("A dispute already exists for this transaction ID; do not file a duplicate claim.")

        timing = liability_timing(claim, as_of)
        if not timing:
            needs.append("Statement date or authoritative reporting_timing is required for liability and provisional-credit determination.")
            liability = None
        elif timing == "within_2_business_days":
            liability = 50.0
            notices.append("Disclose maximum unauthorized-activity liability of $50 for reporting within 2 business days.")
        elif timing == "within_60_days":
            liability = 500.0
            notices.append("Disclose maximum unauthorized-activity liability of $500 for reporting within 60 days of the statement.")
        else:
            liability = None
            notices.append("Disclose potentially unlimited liability after 60 days of the statement; recovery may not be available.")

        account_clear = bool(account and str(account.get("status", "")).upper() == "OPEN"
                             and not account.get("has_holds", False)
                             and not account.get("has_restrictions", False))
        age_days = None
        if account and parse_date(account.get("date_opened")) and as_of:
            age_days = (as_of - parse_date(account.get("date_opened"))).days
        category_ok = category in PROVISIONAL_CATEGORIES
        excluded = []
        if category in NON_PROVISIONAL_CATEGORIES:
            excluded.append("category is not required for provisional credit")
        if category not in FRAUD_CATEGORIES and claim.get("contacted_merchant") is not True:
            excluded.append("merchant was not contacted for non-fraud claim")
        if claim.get("pin_compromised") == "yes_shared":
            excluded.append("PIN was voluntarily shared")
        if category == "card_not_present_fraud" and age_days is not None and age_days < 30:
            excluded.append("new account card-not-present exclusion")
        if category == "card_not_present_fraud" and age_days is None:
            needs.append("Account opening date is needed for new-account card-not-present provisional-credit rule.")
        provisional = bool(timing in {"within_2_business_days", "within_60_days"} and category_ok
                           and claim.get("written_statement_provided") is True and account_clear and not excluded)
        amount = money(claim.get("disputed_amount")) or 0.0
        provisional_amount = max(0.0, amount - (liability or 0.0)) if provisional else 0.0
        if provisional:
            deadline = 20 if age_days is not None and age_days < 30 else 10
            post.append(f"Required provisional credit: ${provisional_amount:.2f} within {deadline} business days.")
        elif excluded:
            notices.append("Provisional credit is not required because " + "; ".join(excluded) + ".")

        if category in FRAUD_CATEGORIES and amount > 500:
            if not isinstance(claim.get("police_report_filed"), bool):
                needs.append("Ask whether a police report was filed for fraud over $500.")
            elif not claim.get("police_report_filed"):
                notices.append("Recommend filing a police report for fraud over $500.")

        action = CARD_ACTIONS.get(category)
        filing = None
        if tx and card and category in CARD_ACTIONS and claim.get("transaction_type") in VALID_TYPES and not needs and not blocks:
            filing = {
                "transaction_id": selected_id, "account_id": account_id, "card_id": card_id,
                "user_id": data.get("user_id"), "dispute_category": category,
                "transaction_date": mmddyyyy(tx.get("date")), "discovery_date": mmddyyyy(claim.get("discovery_date")),
                "disputed_amount": amount, "transaction_type": claim.get("transaction_type"),
                "card_in_possession": claim.get("card_in_possession"), "pin_compromised": claim.get("pin_compromised"),
                "contacted_merchant": claim.get("contacted_merchant"),
                "police_report_filed": bool(claim.get("police_report_filed", False)),
                "written_statement_provided": claim.get("written_statement_provided"),
                "provisional_credit_eligible": provisional, "card_action": action,
            }
        plans.append({
            "claim_reference": claim.get("claim_reference"), "selected_transaction_id": selected_id,
            "blocking_reasons": blocks, "needs_information": needs, "notices": notices,
            "provisional_credit_eligible": provisional, "provisional_credit_amount": provisional_amount,
            "filing_arguments": filing, "post_filing": post, "card_id": card_id,
            "individual_card_action": action,
        })

    card_actions = []
    for cid in sorted({p["card_id"] for p in plans if p.get("card_id")}):
        successful = [p for p in plans if p.get("card_id") == cid and p.get("filing_arguments")]
        if not successful:
            continue
        chosen = max((p["individual_card_action"] for p in successful), key=lambda x: SEVERITY[x])
        card_actions.append({"card_id": cid, "after_successful_filings": chosen,
                             "individual_actions": [p["individual_card_action"] for p in successful]})
    return {"plans": plans, "card_actions": card_actions}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON input must be an object.")
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
