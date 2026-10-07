#!/usr/bin/env python3
"""Validate a credit-card dispute/replacement case and prepare tool payloads.
Reads a JSON object from stdin and emits a JSON report on stdout. Uses Python's
standard library only; it performs no banking action.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
CARD_ACTIONS = {"keep_active", "cancel_and_reissue"}
REPLACEMENT_REASONS = {"fraud_suspected", "lost", "stolen", "damaged", "expired", "other"}

# Normalize documented card names and common tier labels to policy tiers.
def tier_for(card_type):
    text = (card_type or "").lower()
    if "diamond elite" in text or "invitation" in text:
        return "invitation"
    if "platinum" in text or "elite" in text:
        return "elite"
    if "gold" in text or "premium" in text:
        return "premium"
    if any(x in text for x in ("silver", "green rewards", "silver zoom", "mid")):
        return "mid"
    if any(x in text for x in ("bronze", "eco", "crypto-cash", "entry")):
        return "entry"
    return None

LIMITS = {"entry": Decimal("2500"), "mid": Decimal("5000"), "premium": Decimal("10000"), "elite": Decimal("15000"), "invitation": Decimal("25000")}
EXPEDITED_FEES = {"entry": Decimal("15"), "mid": Decimal("10"), "premium": Decimal("0"), "elite": Decimal("0"), "invitation": Decimal("0")}
REPLACEMENT_LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 4, "invitation": 4}


def required(obj, key, path, errors):
    value = obj.get(key) if isinstance(obj, dict) else None
    if value is None or value == "":
        errors.append(f"Missing {path}.{key}")
    return value


def parse_date(value, path, errors):
    try:
        return datetime.strptime(str(value), "%m/%d/%Y").date()
    except (TypeError, ValueError):
        errors.append(f"{path} must be MM/DD/YYYY")
        return None


def money(value, path, errors):
    try:
        amount = Decimal(str(value).replace("$", "").replace(",", ""))
        if amount < 0:
            raise InvalidOperation
        return amount
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{path} must be a non-negative number")
        return None


def main(case):
    errors, warnings = [], []
    for key in ("as_of_date", "identity_verified", "user", "account", "prior_disputes_past_12_months", "card_last_4_digits", "disputes", "replacement"):
        required(case, key, "case", errors)

    as_of = parse_date(case.get("as_of_date"), "as_of_date", errors)
    if case.get("identity_verified") is not True:
        errors.append("Identity must be verified and logged before submission")

    user = case.get("user") if isinstance(case.get("user"), dict) else {}
    for key in ("user_id", "full_name", "phone", "email", "address"):
        required(user, key, "user", errors)

    account = case.get("account") if isinstance(case.get("account"), dict) else {}
    for key in ("account_id", "card_type", "opened_date"):
        required(account, key, "account", errors)
    opened = parse_date(account.get("opened_date"), "account.opened_date", errors)
    tier = tier_for(account.get("card_type"))
    if not tier:
        errors.append("Unsupported or unknown account.card_type; determine its policy tier manually")

    prior = case.get("prior_disputes_past_12_months")
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        errors.append("prior_disputes_past_12_months must be a non-negative integer from dispute history")
        prior = None

    last4 = str(case.get("card_last_4_digits") or "")
    if len(last4) != 4 or not last4.isdigit():
        errors.append("card_last_4_digits must be exactly four digits obtained from the card/customer tool")

    disputes = case.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        errors.append("disputes must be a non-empty array")
        disputes = []

    provisional = []
    dispute_payloads = []
    for i, dispute in enumerate(disputes):
        path = f"disputes[{i}]"
        if not isinstance(dispute, dict):
            errors.append(f"{path} must be an object")
            continue
        local_errors = []
        txid = required(dispute, "transaction_id", path, local_errors)
        amount = money(required(dispute, "amount", path, local_errors), f"{path}.amount", local_errors)
        purchase = parse_date(required(dispute, "purchase_date", path, local_errors), f"{path}.purchase_date", local_errors)
        noticed = parse_date(required(dispute, "issue_noticed_date", path, local_errors), f"{path}.issue_noticed_date", local_errors)
        reason = required(dispute, "dispute_reason", path, local_errors)
        contacted = required(dispute, "contacted_merchant", path, local_errors)
        resolution = required(dispute, "resolution_requested", path, local_errors)
        action = required(dispute, "card_action", path, local_errors)
        if reason not in REASONS: local_errors.append(f"{path}.dispute_reason is not an allowed code")
        if resolution not in RESOLUTIONS: local_errors.append(f"{path}.resolution_requested is not an allowed code")
        if action not in CARD_ACTIONS: local_errors.append(f"{path}.card_action is not an allowed code")
        if not isinstance(contacted, bool): local_errors.append(f"{path}.contacted_merchant must be boolean")
        partial = dispute.get("partial_refund_amount")
        if resolution == "partial_refund":
            partial_money = money(partial, f"{path}.partial_refund_amount", local_errors)
            if partial_money is not None and amount is not None and (partial_money <= 0 or partial_money > amount):
                local_errors.append(f"{path}.partial_refund_amount must be greater than zero and no more than the transaction amount")
        elif partial is not None:
            warnings.append(f"{path}.partial_refund_amount is ignored because resolution is not partial_refund")

        eligible = None
        factors = []
        if not local_errors and as_of and opened and amount is not None and purchase and tier and prior is not None:
            account_old_enough = (as_of - opened).days >= 60
            eligible_reason = reason in {"unauthorized_fraudulent_charge", "duplicate_charge"}
            if reason == "goods_services_not_received":
                eligible_reason = (as_of - purchase).days > 30
            eligible = (account_old_enough and eligible_reason and amount >= Decimal("25") and
                        amount <= LIMITS[tier] and prior <= 2 and
                        (reason == "unauthorized_fraudulent_charge" or contacted is True))
            factors = {
                "account_open_at_least_60_days": account_old_enough,
                "reason_and_purchase_age_eligible": eligible_reason,
                "amount_within_tier_limit": amount >= Decimal("25") and amount <= LIMITS[tier],
                "prior_disputes_not_more_than_two": prior <= 2,
                "merchant_contact_requirement_met": reason == "unauthorized_fraudulent_charge" or contacted is True,
            }
        provisional.append({"transaction_id": txid, "eligible_for_provisional_credit": eligible, "factors": factors, "validation_errors": local_errors})
        errors.extend(local_errors)
        if not local_errors:
            payload = {
                "transaction_id": txid, "card_action": action, "card_last_4_digits": last4,
                "full_name": user.get("full_name"), "user_id": user.get("user_id"),
                "phone": user.get("phone"), "email": user.get("email"), "address": user.get("address"),
                "contacted_merchant": contacted, "purchase_date": dispute.get("purchase_date"),
                "issue_noticed_date": dispute.get("issue_noticed_date"), "dispute_reason": reason,
                "resolution_requested": resolution, "eligible_for_provisional_credit": eligible,
            }
            if resolution == "partial_refund": payload["partial_refund_amount"] = partial
            dispute_payloads.append(payload)

    replacement = case.get("replacement") if isinstance(case.get("replacement"), dict) else {}
    replacement_payload = None
    requested = replacement.get("requested")
    if not isinstance(requested, bool):
        errors.append("replacement.requested must be boolean")
    elif requested:
        for key in ("reason", "shipping_address", "shipping_speed", "eligible_confirmed", "no_pending_replacement", "replacements_past_60_days"):
            required(replacement, key, "replacement", errors)
        reason, speed = replacement.get("reason"), replacement.get("shipping_speed")
        if reason not in REPLACEMENT_REASONS: errors.append("replacement.reason is not an allowed code")
        if speed not in {"standard", "expedited"}: errors.append("replacement.shipping_speed must be standard or expedited")
        if replacement.get("eligible_confirmed") is not True: errors.append("Replacement eligibility must be confirmed before unlocking the order tool")
        if replacement.get("no_pending_replacement") is not True: errors.append("A pending or unknown replacement order blocks a new replacement")
        count = replacement.get("replacements_past_60_days")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            errors.append("replacement.replacements_past_60_days must be a non-negative integer")
        elif tier and count >= REPLACEMENT_LIMITS[tier]:
            errors.append("Replacement limit for the card tier has been reached in the 60-day period")
        if speed == "expedited" and tier and EXPEDITED_FEES[tier] > 0 and replacement.get("expedited_fee_acknowledgement") is not True:
            errors.append("Explicit expedited fee acknowledgement is required for this tier")
        if not errors:
            replacement_payload = {
                "account_id": account.get("account_id"), "reason": reason,
                "shipping_address": replacement.get("shipping_address"), "shipping_speed": speed,
                "expedited_fee_acknowledgement": replacement.get("expedited_fee_acknowledgement", False),
                "notes": replacement.get("notes", ""),
            }

    unresolved = any(item["eligible_for_provisional_credit"] is None for item in provisional)
    status = "blocked" if errors else ("needs_review" if unresolved else "ready")
    result = {"status": status, "tier": tier, "errors": errors, "warnings": warnings,
              "provisional_credit": provisional, "tool_payloads": {}}
    if not errors and len(dispute_payloads) == len(disputes): result["tool_payloads"]["disputes"] = dispute_payloads
    if replacement_payload is not None: result["tool_payloads"]["replacement"] = replacement_payload
    return result

if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict): raise ValueError("Top-level JSON must be an object")
        print(json.dumps(main(data), default=str, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status": "blocked", "errors": [f"Invalid input: {exc}"], "warnings": [], "tool_payloads": {}}))
