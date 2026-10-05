#!/usr/bin/env python3
"""Create a deterministic, non-executing debit-card-dispute plan.

Input and output schemas are documented in SKILL.md. The script reads one JSON
object from stdin, writes one JSON object to stdout, and never invokes tools.
"""
import json
import sys
from datetime import date, datetime

LIMITS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
OPEN_DISPUTE_STATUSES = {
    "OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"
}
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
UNAUTHORIZED_ACTIVITY = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud"
}
FRAUD = {"card_present_fraud", "card_not_present_fraud"}
TIMINGS = {"within_2_business_days", "within_60_days", "after_60_days"}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}
MERCHANT_CLAIMS = {
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation",
}


def parse_date(value):
    if not value:
        return None
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value).strip(), pattern).date()
        except ValueError:
            pass
    return None


def format_date(value):
    parsed = parse_date(value)
    return parsed.strftime("%m/%d/%Y") if parsed else None


def absolute_amount(value):
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def tier_for(account_class):
    text = str(account_class or "").upper()
    return next((tier for tier in LIMITS if tier in text), None)


def unresolved_count(disputes, account_id):
    return sum(
        1 for dispute in disputes
        if dispute.get("account_id") == account_id
        and str(dispute.get("status", "")).upper() in OPEN_DISPUTE_STATUSES
    )


def find_card(cards, account_id, claim):
    candidates = [card for card in cards if card.get("account_id") == account_id]
    if claim.get("card_id"):
        candidates = [card for card in candidates if card.get("card_id") == claim["card_id"]]
    elif claim.get("card_last4") is not None:
        wanted = str(claim["card_last4"])
        candidates = [card for card in candidates if str(card.get("card_number_last_4")) == wanted]
    return candidates[0] if len(candidates) == 1 else None


def select_transaction(claim, transaction_by_id, source_positions):
    """Return the target transaction, retaining reverse-chronological tie rules.

    Duplicate IDs are expected in the exact source-history order. For equal dates,
    the later record in reverse chronological history is the earliest available
    posting and therefore wins.
    """
    selected_id = claim.get("transaction_id")
    note = None
    duplicate_ids = claim.get("duplicate_transaction_ids")
    if claim.get("category") == "duplicate_charge" and duplicate_ids:
        candidates = []
        for supplied_position, transaction_id in enumerate(duplicate_ids):
            transaction = transaction_by_id.get(transaction_id)
            if transaction:
                source_position = source_positions.get(transaction_id, supplied_position)
                candidates.append((parse_date(transaction.get("date")) or date.max,
                                   -source_position, transaction))
        if not candidates:
            return None, None, "None of the supplied duplicate transaction IDs were found."
        candidates.sort(key=lambda row: (row[0], row[1]))
        selected_id = candidates[0][2].get("transaction_id")
        note = "Duplicate rule applied: selected one earliest matching transaction."
    return selected_id, transaction_by_id.get(selected_id), note


def liability_notice(timing):
    if timing == "within_2_business_days":
        return "Before filing, disclose the applicable Regulation E maximum liability of $50."
    if timing == "within_60_days":
        return "Before filing, disclose the applicable Regulation E maximum liability of $500."
    if timing == "after_60_days":
        return "Before filing, disclose potentially unlimited liability after 60 days and possible non-recovery."
    return "Determine and communicate Regulation E reporting timing before this unauthorized-activity claim; do not invent a statement date."


def plan_one(payload, claim, accounts, cards, transaction_by_id, source_positions, disputes, as_of):
    blocks, needs, notices, post = [], [], [], []
    account_id = claim.get("account_id")
    category = claim.get("category")
    account = accounts.get(account_id)

    if not payload.get("identity_verified"):
        blocks.append("Customer identity has not been verified and logged.")
    if not account:
        blocks.append("Claim account was not found in live account data.")
    else:
        if str(account.get("account_type", "")).lower() != "checking":
            blocks.append("Debit-card dispute claims require a checking account.")
        if str(account.get("status", "")).upper() != "OPEN":
            blocks.append("Linked checking account is not OPEN.")
        tier = tier_for(account.get("account_class"))
        if not tier:
            needs.append("Account class is needed to determine the dispute limit.")
        elif unresolved_count(disputes, account_id) >= LIMITS[tier]:
            blocks.append("The account has reached its open-dispute limit.")

    card = find_card(cards, account_id, claim)
    if not card:
        blocks.append("Could not uniquely match a customer debit card to this claim.")
    elif card.get("user_id") != payload.get("user_id"):
        blocks.append("Matched card is not owned by the verified user.")

    selected_id, transaction, selection_error = select_transaction(
        claim, transaction_by_id, source_positions
    )
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
        disputed = absolute_amount(claim.get("disputed_amount"))
        posted = absolute_amount(transaction.get("amount"))
        if disputed is None:
            blocks.append("Disputed amount is missing or invalid.")
        elif disputed < 1:
            blocks.append("Disputed amount must be at least $1.00.")
        elif posted is not None and disputed > posted + 1e-9:
            blocks.append("Disputed amount cannot exceed the posted transaction amount.")

    if any(item.get("transaction_id") == selected_id for item in disputes):
        blocks.append("A dispute already exists for this transaction; do not refile it.")
    if category not in ACTIONS:
        blocks.append("Dispute category is missing or unsupported.")
    if claim.get("transaction_type") not in VALID_TYPES:
        blocks.append("Transaction type is missing or unsupported.")
    if not parse_date(claim.get("discovery_date")):
        blocks.append("A specific, valid discovery date is required before filing.")
    for field in ("card_in_possession", "contacted_merchant", "written_statement_provided"):
        if not isinstance(claim.get(field), bool):
            blocks.append(f"{field} must be an explicit Boolean.")
    if claim.get("pin_compromised") not in {"yes_shared", "yes_observed", "no", "unknown"}:
        blocks.append("PIN-compromise value is missing or unsupported.")

    if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
        owner = claim.get("atm_owner")
        if owner not in {"rho_bank", "third_party"}:
            blocks.append("ATM owner must be identified as rho_bank or third_party.")
        elif owner == "third_party":
            post.append("Submit a chargeback request to the third-party ATM owner/network; investigation may take up to 90 days.")
            if category == "atm_cash_discrepancy" and (absolute_amount(claim.get("disputed_amount")) or 0) > 200:
                notices.append("Send the EFT Error Resolution Affidavit to the registered email; it is due within 10 business days, non-return may lead to denial, and false signing is a federal offense.")
        elif category == "atm_cash_discrepancy":
            post.append("Review the Rho-Bank ATM journal; a confirmed discrepancy receives immediate provisional credit.")
        else:
            post.append("Retrieve and compare Rho-Bank ATM deposit images.")

    timing = claim.get("reporting_timing")
    if category in UNAUTHORIZED_ACTIVITY:
        notices.append(liability_notice(timing))
    elif timing is not None and timing not in TIMINGS:
        notices.append("Reporting timing value is unsupported; use a documented timing value when known.")

    account_age = None
    if account and parse_date(account.get("date_opened")) and as_of:
        account_age = (as_of - parse_date(account.get("date_opened"))).days
    account_clear = bool(
        account and str(account.get("status", "")).upper() == "OPEN"
        and not account.get("has_holds", False)
        and not account.get("has_restrictions", False)
    )
    exclusions = []
    if category not in QUALIFYING_PROVISIONAL:
        exclusions.append("category is not eligible for required provisional credit")
    if category in MERCHANT_CLAIMS and claim.get("contacted_merchant") is False:
        exclusions.append("merchant was not contacted")
    if claim.get("pin_compromised") == "yes_shared":
        exclusions.append("PIN was voluntarily shared")
    if category == "card_not_present_fraud" and account_age is not None and account_age < 30:
        exclusions.append("card-not-present claim is on a new account")
    if category == "card_not_present_fraud" and account_age is None:
        notices.append("Account age is needed to fully assess the new-account card-not-present credit rule.")

    timely = timing in {"within_2_business_days", "within_60_days"}
    provisional = bool(
        timely and category in QUALIFYING_PROVISIONAL
        and claim.get("written_statement_provided") is True
        and account_clear and not exclusions
    )
    disputed = absolute_amount(claim.get("disputed_amount")) or 0.0
    if provisional:
        deadline = 20 if account_age is not None and account_age < 30 else 10
        post.append(f"Required provisional credit of up to ${disputed:.2f} is due within {deadline} business days, subject to any liability offset.")
    elif exclusions:
        notices.append("Required provisional credit does not apply because " + "; ".join(exclusions) + ".")
    elif category in QUALIFYING_PROVISIONAL and timing not in TIMINGS:
        notices.append("Timely-reporting status is needed to determine whether provisional credit is required.")

    if category in FRAUD and disputed > 500:
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
            "user_id": payload.get("user_id"),
            "dispute_category": category,
            "transaction_date": format_date(transaction.get("date")),
            "discovery_date": format_date(claim.get("discovery_date")),
            "disputed_amount": disputed,
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
        "selection_note": "Duplicate rule applied: selected one earliest matching transaction." if category == "duplicate_charge" and selected_id else None,
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
    accounts = {item.get("account_id"): item for item in payload.get("accounts", [])}
    cards = list(payload.get("cards", []))
    transactions = list(payload.get("transactions", []))
    transaction_by_id = {item.get("transaction_id"): item for item in transactions}
    source_positions = {
        item.get("transaction_id"): position for position, item in enumerate(transactions)
    }
    disputes = list(payload.get("existing_disputes", []))
    plans = [
        plan_one(payload, claim, accounts, cards, transaction_by_id, source_positions, disputes, as_of)
        for claim in payload.get("claims", [])
    ]

    card_actions = []
    for card_id in sorted({plan["card_id"] for plan in plans if plan.get("card_id")}):
        successful = [
            plan for plan in plans
            if plan.get("card_id") == card_id and plan.get("filing_arguments")
        ]
        if successful:
            action = max(
                (plan["individual_card_action"] for plan in successful),
                key=lambda value: SEVERITY[value],
            )
            card_actions.append({
                "card_id": card_id,
                "after_successful_filings": action,
                "individual_actions": [plan["individual_card_action"] for plan in successful],
            })
    return {"plans": plans, "card_actions": card_actions}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("Top-level input must be a JSON object.")
        print(json.dumps(main(request), sort_keys=True, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
