#!/usr/bin/env python3
"""Validate dispute inputs and construct per-transaction filing payloads.

Input: one JSON object on stdin, as described in SKILL.md.
Output: JSON with ready, filings, eligibility, validation_errors, and prior_dispute_count.
This program is deterministic and has no banking-tool side effects.
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "incorrect_amount",
    "goods_services_not_received",
    "goods_services_not_as_described",
    "canceled_subscription_still_charging",
    "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}


def add_error(errors, index, field, message):
    errors.append({"transaction_index": index, "field": field, "message": message})


def parse_date(value):
    """Accept exact MM/DD/YYYY plus ISO-like history timestamps; return date or None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def strict_mmddyyyy(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def money(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        text = str(value).strip().replace("$", "").replace(",", "")
        result = Decimal(text)
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def tier_limit(card_type):
    """Return the documented tier and maximum provisional credit, or (None, None)."""
    if not isinstance(card_type, str):
        return None, None
    c = " ".join(card_type.casefold().replace("card", "").split())
    # Specific business names precede shared personal-name matching.
    if c in {"bronze rewards", "ecocard", "business bronze rewards", "crypto-cash back"}:
        return "entry", Decimal("2500.00")
    if c in {"silver rewards", "business silver rewards", "green rewards", "silver zoom"}:
        return "mid", Decimal("5000.00")
    if c in {"gold rewards", "business gold rewards"}:
        return "premium", Decimal("10000.00")
    if c in {"platinum rewards", "business platinum rewards"}:
        return "elite", Decimal("15000.00")
    if c == "diamond elite":
        return "invitation", Decimal("25000.00")
    return None, None


def year_ago(d):
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # February 29
        return d.replace(year=d.year - 1, day=28)


def history_count(data, as_of, errors):
    """Return count of disputes in the preceding 12 months, or None if unknowable."""
    if "prior_disputes_past_12_months" in data:
        count = data["prior_disputes_past_12_months"]
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            return count
        add_error(errors, None, "prior_disputes_past_12_months", "must be a non-negative integer")
        return None
    if "prior_disputes" not in data or not isinstance(data["prior_disputes"], list):
        add_error(errors, None, "prior_disputes", "dispute-history result is required to determine provisional credit")
        return None
    cutoff = year_ago(as_of)
    count = 0
    for item in data["prior_disputes"]:
        raw = item.get("dispute_date") if isinstance(item, dict) else item
        d = parse_date(raw)
        if d is None:
            add_error(errors, None, "prior_disputes", "each history record needs a parseable dispute_date")
            return None
        if cutoff <= d <= as_of:
            count += 1
    return count


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def main(data):
    errors = []
    filings = []
    eligibility = []

    as_of = strict_mmddyyyy(data.get("as_of_date"))
    if as_of is None:
        add_error(errors, None, "as_of_date", "must be the filing date in MM/DD/YYYY format")
        # A placeholder prevents date arithmetic; outputs remain not ready.
        as_of = date.min

    if data.get("identity_verified") is not True:
        add_error(errors, None, "identity_verified", "must be true only after two identity fields were confirmed and verification was logged")

    user = data.get("user")
    if not isinstance(user, dict):
        user = {}
        add_error(errors, None, "user", "registered user profile is required")
    user_fields = {
        "full_name": "full_name", "user_id": "user_id", "phone": "phone",
        "email": "email", "address": "address",
    }
    for source, destination in user_fields.items():
        if not nonempty(user.get(source)):
            add_error(errors, None, "user." + source, "registered value is required")

    prior_count = history_count(data, as_of, errors) if as_of != date.min else None
    transactions = data.get("transactions")
    if not isinstance(transactions, list) or not transactions:
        add_error(errors, None, "transactions", "provide at least one matched transaction")
        transactions = []

    for i, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            add_error(errors, i, "transaction", "must be an object")
            continue
        invalid = False
        def require(condition, field, message):
            nonlocal invalid
            if not condition:
                add_error(errors, i, field, message)
                invalid = True

        txid = tx.get("transaction_id")
        card_type = tx.get("card_type")
        last4 = tx.get("card_last_4_digits")
        amount = money(tx.get("amount"))
        opened = strict_mmddyyyy(tx.get("account_open_date"))
        purchase = strict_mmddyyyy(tx.get("purchase_date"))
        noticed = strict_mmddyyyy(tx.get("issue_noticed_date"))
        reason = tx.get("dispute_reason")
        resolution = tx.get("resolution_requested")
        action = tx.get("card_action")
        contacted = tx.get("contacted_merchant")

        require(nonempty(txid), "transaction_id", "matched transaction ID is required")
        require(nonempty(card_type), "card_type", "card type is required for the tier check")
        require(isinstance(last4, str) and re.fullmatch(r"\d{4}", last4) is not None,
                "card_last_4_digits", "must be exactly four digits from the card account")
        require(amount is not None and amount >= 0, "amount", "must be a non-negative transaction amount")
        require(opened is not None, "account_open_date", "must be MM/DD/YYYY")
        require(purchase is not None, "purchase_date", "must be MM/DD/YYYY")
        require(noticed is not None, "issue_noticed_date", "must be MM/DD/YYYY")
        require(reason in REASONS, "dispute_reason", "must be an allowed dispute reason code")
        require(resolution in RESOLUTIONS, "resolution_requested", "must be an allowed resolution code")
        require(action in ACTIONS, "card_action", "must be keep_active or cancel_and_reissue")
        require(type(contacted) is bool, "contacted_merchant", "must be boolean")

        partial = None
        if resolution == "partial_refund":
            partial = money(tx.get("partial_refund_amount"))
            require(partial is not None and partial > 0, "partial_refund_amount", "must be a positive dollar amount")
            if partial is not None and amount is not None:
                require(partial <= amount, "partial_refund_amount", "cannot exceed the disputed transaction amount")

        is_business = isinstance(card_type, str) and "business" in card_type.casefold()
        if is_business and data.get("business_authorization_confirmed") is not True:
            require(False, "business_authorization_confirmed",
                    "business authority must be confirmed before filing a business-card dispute")

        tier, limit = tier_limit(card_type)
        if tier is None:
            require(False, "card_type", "card tier is unknown; cannot determine provisional-credit eligibility")

        eligible = False
        reasons_not_eligible = []
        prerequisites_known = all(v is not None for v in (amount, opened, purchase)) and prior_count is not None and limit is not None
        if prerequisites_known:
            if (as_of - opened).days < 60:
                reasons_not_eligible.append("account_open_less_than_60_days")
            if reason not in ELIGIBLE_REASONS:
                reasons_not_eligible.append("reason_not_eligible")
            elif reason == "goods_services_not_received" and not (purchase < as_of - timedelta(days=30)):
                reasons_not_eligible.append("goods_not_received_purchase_not_more_than_30_days_old")
            if amount < Decimal("25.00"):
                reasons_not_eligible.append("amount_under_25")
            elif amount > limit:
                reasons_not_eligible.append("amount_exceeds_card_tier_limit")
            if prior_count > 2:
                reasons_not_eligible.append("more_than_two_prior_disputes_in_12_months")
            if reason != "unauthorized_fraudulent_charge" and contacted is not True:
                reasons_not_eligible.append("merchant_not_contacted_for_nonfraud_dispute")
            eligible = not reasons_not_eligible
        else:
            reasons_not_eligible.append("eligibility_prerequisite_unavailable")

        eligibility.append({
            "transaction_id": txid,
            "card_tier": tier,
            "tier_limit": float(limit) if limit is not None else None,
            "eligible_for_provisional_credit": eligible,
            "not_eligible_reasons": reasons_not_eligible,
        })

        if not invalid and prior_count is not None and as_of != date.min:
            payload = {
                "transaction_id": txid,
                "card_action": action,
                "card_last_4_digits": last4,
                "full_name": user.get("full_name"),
                "user_id": user.get("user_id"),
                "phone": user.get("phone"),
                "email": user.get("email"),
                "address": user.get("address"),
                "contacted_merchant": contacted,
                "purchase_date": tx.get("purchase_date"),
                "issue_noticed_date": tx.get("issue_noticed_date"),
                "dispute_reason": reason,
                "resolution_requested": resolution,
                "eligible_for_provisional_credit": eligible,
            }
            if resolution == "partial_refund":
                payload["partial_refund_amount"] = float(partial)
            filings.append(payload)

    # Any global error makes the collection unsafe to submit, even if a local payload exists.
    return {
        "ready": len(errors) == 0,
        "prior_dispute_count": prior_count,
        "filings": filings if len(errors) == 0 else [],
        "eligibility": eligibility,
        "validation_errors": errors,
    }


if __name__ == "__main__":
    try:
        supplied = json.load(sys.stdin)
        if not isinstance(supplied, dict):
            raise ValueError("top-level input must be a JSON object")
        print(json.dumps(main(supplied), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ready": False, "filings": [], "eligibility": [], "validation_errors": [
            {"transaction_index": None, "field": "input", "message": str(exc)}
        ]}, separators=(",", ":"), sort_keys=True))
        sys.exit(1)
