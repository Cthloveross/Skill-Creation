#!/usr/bin/env python3
"""Produce a deterministic, non-executing debit-card dispute plan.

Reads the JSON schema documented in SKILL.md from stdin and writes:
{"plans": [...], "card_actions": [...]}.
The helper does not invoke banking tools or make banking changes.
"""
import json
import sys
from datetime import datetime, date

LIMITS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
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
VALID_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
QUALIFYING_PROVISIONAL = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
FRAUD = {"card_present_fraud", "card_not_present_fraud"}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}
TIMINGS = {"within_2_business_days", "within_60_days", "after_60_days"}


def parse_date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def fmt_date(value):
    parsed = parse_date(value)
    return parsed.strftime("%m/%d/%Y") if parsed else None


def amount(value):
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def account_tier(value):
    text = str(value or "").upper()
    return next((key for key in LIMITS if key in text), None)


def unresolved_count(disputes, account_id):
    return sum(
        1 for dispute in disputes
        if dispute.get("account_id") == account_id
        and str(dispute.get("status", "")).upper() in OPEN_STATUSES
    )


def find_card(cards, account_id, claim):
    candidates = [card for card in cards if card.get("account_id") == account_id]
    if claim.get("card_id"):
        candidates = [card for card in candidates if card.get("card_id") == claim["card_id"]]
    elif claim.get("card_last4") is not None:
        wanted = str(claim["card_last4"])
        candidates = [card for card in candidates if str(card.get("card_number_last_4")) == wanted]
    return candidates[0] if len(candidates) == 1 else None


def select_transaction(claim, transactions):
    selected_id = claim.get("transaction_id")
    note = None
    if claim.get("category") == "duplicate_charge" and claim.get("duplicate_transaction_ids"):
        indexed = []
        for position, transaction_id in enumerate(claim["duplicate_transaction_ids"]):
            transaction = transactions.get(transaction_id)
            if transaction:
                indexed.append((parse_date(transaction.get("date")) or date.max, position, transaction))
        if not indexed:
            return None, None, "None of the supplied duplicate transaction IDs were found."
        # The caller must give candidates in earliest-first order for same-date records.
        indexed.sort(key=lambda row: (row[0], row[1]))
        selected_id = indexed[0][2].get("transaction_id")
        note = "Duplicate rule applied: one earliest matching transaction was selected."
    return selected_id, transactions.get(selected_id), note


def plan_one(data, claim, accounts, cards, transactions, disputes, as_of):
    blocks, needs, notices, post = [], [], [], []
    account_id = claim.get("account_id")
    category = claim.get("category")
    account = accounts.get(account_id)

    if not data.get("identity_verified"):
        blocks.append("Customer identity has not been verified and logged.")
    if not account:
        blocks.append("Claim account was not found in live account data.")
    else:
        if str(account.get("account_type", "")).lower() != "checking":
            blocks.append("Debit-card dispute claims require a checking account.")
        if str(account.get("status", "")).upper() != "OPEN":
            blocks.append("Linked checking account is not OPEN.")
        tier = account_tier(account.get("account_class"))
        if not tier:
            needs.append("Account class is needed to determine its dispute limit.")
        elif unresolved_count(disputes, account_id) >= LIMITS[tier]:
            blocks.append("The account has reached its open-dispute limit.")

    card = find_card(cards, account_id, claim)
    if not card:
        blocks.append("Could not uniquely match a customer debit card to this claim.")
    elif card.get("user_id") != data.get("user_id"):
        blocks.append("Matched card is not owned by the verified user.")

    selected_id, transaction, selection_error = select_transaction(claim, transactions)
    if selection_error:
        blocks.append(selection_error)
    if not transaction:
        blocks.append("Selected transaction was not found in retrieved transaction data.")
    else:
        if transaction.get("account_id") != account_id:
            blocks.append("Selected transaction does not belong to the claim account.")
        transaction_date = parse_date(transaction.get("date"))
        if not transaction_date or not as_of:
            needs.append("A valid transaction and filing date are needed for the 60-day check.")
        elif (as_of - transaction_date).days > 60:
            blocks.append("Transaction is more than 60 days old at filing.")
        elif (as_of - transaction_date).days < 0:
            blocks.append("Transaction is dated after the filing date.")
        loss = amount(claim.get("disputed_amount"))
        posted = amount(transaction.get("amount"))
        if loss is None:
            blocks.append("Disputed amount is missing or invalid.")
        elif loss < 1:
            blocks.append("Disputed amount must be at least $1.00.")
        elif posted is not None and loss > posted + 1e-9:
            blocks.append("Disputed amount cannot exceed the posted transaction amount.")

    if any(d.get("transaction_id") == selected_id for d in disputes):
        blocks.append("A dispute already exists for this transaction; do not refile it.")
    if category not in ACTIONS:
        blocks.append("Dispute category is missing or unsupported.")
    if claim.get("transaction_type") not in VALID_TYPES:
        blocks.append("Transaction type is missing or unsupported.")
    if not parse_date(claim.get("discovery_date")):
        blocks.append("A specific, valid discovery date is required before filing.")
    for key in ("card_in_possession", "contacted_merchant", "written_statement_provided"):
        if not isinstance(claim.get(key), bool):
            blocks.append(f"{key} must be an explicit Boolean.")
    if claim.get("pin_compromised") not in {"yes_shared", "yes_observed", "no", "unknown"}:
        blocks.append("PIN-compromise value is missing or unsupported.")

    if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
        owner = claim.get("atm_owner")
        if owner not in {"rho_bank", "third_party"}:
            blocks.append("ATM owner must be identified as rho_bank or third_party.")
        elif owner == "third_party":
            post.append("Submit the chargeback request to the third-party ATM owner/network; the investigation may take up to 90 days.")
            if category == "atm_cash_discrepancy" and (amount(claim.get("disputed_amount")) or 0) > 200:
                notices.append("Send the EFT Error Resolution Affidavit to the registered email; it is due within 10 business days, may lead to denial if absent, and false signing is a federal offense.")
        elif category == "atm_cash_discrepancy":
            post.append("Review the Rho-Bank ATM journal; confirmed discrepancy receives immediate provisional credit.")
        else:
            post.append("Retrieve and compare Rho-Bank ATM deposit images.")

    timing = claim.get("reporting_timing")
    if timing not in TIMINGS:
        notices.append("Determine and communicate Regulation E reporting timing before an unauthorized-activity claim; do not invent a statement date.")
        timing = None
    elif timing == "within_2_business_days":
        notices.append("Before filing, disclose the applicable maximum unauthorized-activity liability of $50.")
    elif timing == "within_60_days":
        notices.append("Before filing, disclose the applicable maximum unauthorized-activity liability of $500.")
    else:
        notices.append("Before filing, disclose potentially unlimited liability after 60 days and possible non-recovery.")

    age_days = None
    if account and parse_date(account.get("date_opened")) and as_of:
        age_days = (as_of - parse_date(account.get("date_opened"))).days
    account_clear = bool(account and str(account.get("status", "")).upper() == "OPEN"
                         and not account.get("has_holds", False)
                         and not account.get("has_restrictions", False))
    exclusions = []
    if category not in QUALIFYING_PROVISIONAL:
        exclusions.append("category is not eligible for required provisional credit")
    # A merchant-contact exclusion applies to merchant claims, not an ATM-network error.
    if category in {"duplicate_charge", "incorrect_amount", "goods_services_not_received", "recurring_charge_after_cancellation"} and claim.get("contacted_merchant") is False:
        exclusions.append("merchant was not contacted")
    if claim.get("pin_compromised") == "yes_shared":
        exclusions.append("PIN was voluntarily shared")
    if category == "card_not_present_fraud" and age_days is not None and age_days < 30:
        exclusions.append("card-not-present claim is on a new account")
    if category == "card_not_present_fraud" and age_days is None:
        notices.append("Account age is needed to fully assess the new-account card-not-present provisional rule.")

    provisional = bool(
        timing in {"within_2_business_days", "within_60_days"}
        and category in QUALIFYING_PROVISIONAL
        and claim.get("written_statement_provided") is True
        and account_clear and not exclusions
    )
    loss = amount(claim.get("disputed_amount")) or 0.0
    if provisional:
        deadline = 20 if age_days is not None and age_days < 30 else 10
        post.append(f"Required provisional credit of up to ${loss:.2f} is due within {deadline} business days, subject to any liability offset.")
    elif exclusions:
        notices.append("Required provisional credit does not apply because " + "; ".join(exclusions) + ".")

    if category in FRAUD and loss > 500:
        if not isinstance(claim.get("police_report_filed"), bool):
            blocks.append("Ask whether a police report was filed for suspected fraud over $500.")
        elif not claim["police_report_filed"]:
            notices.append("Recommend a police report for suspected fraud over $500.")

    filing = None
    if not blocks and transaction and card and category in ACTIONS:
        filing = {
            "transaction_id": selected_id,
            "account_id": account_id,
            "card_id": card.get("card_id"),
            "user_id": data.get("user_id"),
            "dispute_category": category,
            "transaction_date": fmt_date(transaction.get("date")),
            "discovery_date": fmt_date(claim.get("discovery_date")),
            "disputed_amount": loss,
            "transaction_type": claim.get("transaction_type"),
            "card_in_possession": claim.get("card_in_possession"),
            "pin_compromised": claim.get("pin_compromised"),
            "contacted_merchant": claim.get("contacted_merchant"),
            "police_report_filed": bool(claim.get("police_report_filed", False)),
            "written_statement_provided": claim.get("written_statement_provided"),
            "provisional_credit_eligible": provisional,
            "card_action": ACTIONS[category],
        }

    return {
        "claim_reference": claim.get("claim_reference"),
        "selected_transaction_id": selected_id,
        "card_id": card.get("card_id") if card else None,
        "blocking_reasons": blocks,
        "needs_information": needs,
        "notices": notices,
        "filing_arguments": filing,
        "individual_card_action": ACTIONS.get(category),
        "provisional_credit_eligible": provisional,
        "post_filing": post,
    }


def main(payload):
    as_of = parse_date(payload.get("as_of"))
    accounts = {a.get("account_id"): a for a in payload.get("accounts", [])}
    cards = list(payload.get("cards", []))
    transactions = {t.get("transaction_id"): t for t in payload.get("transactions", [])}
    disputes = list(payload.get("existing_disputes", []))
    plans = [plan_one(payload, claim, accounts, cards, transactions, disputes, as_of)
             for claim in payload.get("claims", [])]

    card_actions = []
    for card_id in sorted({p["card_id"] for p in plans if p.get("card_id")}):
        successful = [p for p in plans if p.get("card_id") == card_id and p.get("filing_arguments")]
        if successful:
            chosen = max((p["individual_card_action"] for p in successful), key=lambda x: SEVERITY[x])
            card_actions.append({
                "card_id": card_id,
                "after_successful_filings": chosen,
                "individual_actions": [p["individual_card_action"] for p in successful],
            })
    return {"plans": plans, "card_actions": card_actions}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
