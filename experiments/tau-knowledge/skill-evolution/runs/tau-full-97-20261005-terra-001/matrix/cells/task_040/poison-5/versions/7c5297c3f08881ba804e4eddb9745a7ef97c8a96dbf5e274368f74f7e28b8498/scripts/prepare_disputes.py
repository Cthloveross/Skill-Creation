#!/usr/bin/env python3
"""Validate dispute records and create filing-tool argument objects.

Reads the JSON schema documented in SKILL.md from stdin. Writes:
{
  "as_of_date": "MM/DD/YYYY",
  "prior_disputes_in_last_12_months": 0,
  "ready_submissions": [{...file_credit_card_transaction_dispute_4829 args...}],
  "blocked": [{"index": 0, "transaction_id": "...", "errors": [...],
               "eligibility": {"eligible": false, "reasons": [...]}}],
  "errors": [...]
}
No banking action is performed by this script.
"""
import json
import sys
from datetime import datetime, date, timedelta
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
TIER_LIMITS = {
    "Bronze Rewards Card": Decimal("2500"),
    "EcoCard": Decimal("2500"),
    "Business Bronze Rewards Card": Decimal("2500"),
    "Crypto-Cash Back Card": Decimal("2500"),
    "Silver Rewards Card": Decimal("5000"),
    "Business Silver Rewards Card": Decimal("5000"),
    "Green Rewards Card": Decimal("5000"),
    "Silver Zoom Card": Decimal("5000"),
    "Gold Rewards Card": Decimal("10000"),
    "Business Gold Rewards Card": Decimal("10000"),
    "Platinum Rewards Card": Decimal("15000"),
    "Business Platinum Rewards Card": Decimal("15000"),
    "Diamond Elite Card": Decimal("25000"),
}
ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}


def parse_date(value):
    """Accept documented MM/DD/YYYY plus common returned timestamps; return date."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    text = value.strip()
    try:
        return datetime.strptime(text, "%m/%d/%Y").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("invalid date") from exc


def required_date(value, field, errors):
    try:
        parsed = parse_date(value)
        # Required filing fields have a mandated wire format.
        if not isinstance(value, str) or not _is_mmddyyyy(value):
            errors.append(f"{field} must use MM/DD/YYYY format")
        return parsed
    except ValueError:
        errors.append(f"{field} is missing or invalid")
        return None


def _is_mmddyyyy(value):
    try:
        return datetime.strptime(value, "%m/%d/%Y").strftime("%m/%d/%Y") == value
    except (TypeError, ValueError):
        return False


def amount(value, field, errors):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result <= 0:
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be a positive number")
        return None


def year_earlier(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # Feb. 29
        return day.replace(year=day.year - 1, month=2, day=28)


def prior_count(history, as_of, global_errors):
    if not isinstance(history, list):
        global_errors.append("dispute_history must be supplied as a list; an empty list is valid")
        return None
    cutoff = year_earlier(as_of)
    count = 0
    for index, record in enumerate(history):
        if not isinstance(record, dict):
            global_errors.append(f"dispute_history[{index}] is not an object")
            continue
        try:
            filed = parse_date(record.get("dispute_date"))
        except ValueError:
            global_errors.append(f"dispute_history[{index}].dispute_date is missing or invalid")
            continue
        if cutoff <= filed <= as_of:
            count += 1
    return count


def eligibility(dispute, account, as_of, previous_count, txn_amount, purchase_day):
    reasons = []
    if account is None:
        reasons.append("matching account is unavailable")
        return False, reasons
    try:
        open_day = parse_date(account.get("date_of_account_open"))
        if (as_of - open_day).days < 60:
            reasons.append("account has been open fewer than 60 days")
    except ValueError:
        reasons.append("account open date is unavailable or invalid")

    reason = dispute.get("dispute_reason")
    if reason not in ELIGIBLE_REASONS:
        reasons.append("dispute reason is not eligible for provisional credit")
    elif reason == "goods_services_not_received":
        if purchase_day is None:
            reasons.append("purchase date is unavailable for delivery-age rule")
        elif (as_of - purchase_day).days <= 30:
            reasons.append("goods/services-not-received purchase is not more than 30 days old")

    limit = TIER_LIMITS.get(account.get("card_type"))
    if limit is None:
        reasons.append("card tier has no documented provisional-credit limit")
    elif txn_amount is None:
        reasons.append("transaction amount is unavailable")
    elif txn_amount < Decimal("25") or txn_amount > limit:
        reasons.append("transaction amount is outside the card tier provisional-credit range")

    if previous_count is None:
        reasons.append("prior dispute history cannot be determined")
    elif previous_count > 2:
        reasons.append("customer has more than two disputes in the past 12 months")

    if reason != "unauthorized_fraudulent_charge":
        if dispute.get("contacted_merchant") is not True:
            reasons.append("customer did not contact the merchant for a non-fraud dispute")
    return not reasons, reasons


def main(data):
    output = {"as_of_date": None, "prior_disputes_in_last_12_months": None,
              "ready_submissions": [], "blocked": [], "errors": []}
    try:
        as_of = parse_date(data.get("as_of_date"))
        output["as_of_date"] = as_of.strftime("%m/%d/%Y")
    except ValueError:
        output["errors"].append("as_of_date is missing or invalid")
        return output

    customer = data.get("customer")
    if not isinstance(customer, dict):
        output["errors"].append("customer must be an object")
        return output
    for field in ("full_name", "user_id", "phone", "email", "address"):
        if not isinstance(customer.get(field), str) or not customer[field].strip():
            output["errors"].append(f"customer.{field} is required")

    action = data.get("card_action")
    if action not in ACTIONS:
        output["errors"].append("card_action must be keep_active or cancel_and_reissue")

    accounts = data.get("accounts")
    account_by_id = {}
    if not isinstance(accounts, list):
        output["errors"].append("accounts must be a list")
    else:
        for account in accounts:
            if isinstance(account, dict) and isinstance(account.get("account_id"), str):
                account_by_id[account["account_id"]] = account

    previous = prior_count(data.get("dispute_history"), as_of, output["errors"])
    output["prior_disputes_in_last_12_months"] = previous
    disputes = data.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        output["errors"].append("disputes must be a non-empty list")
        return output

    global_block = bool(output["errors"])
    for index, dispute in enumerate(disputes):
        errors = []
        if not isinstance(dispute, dict):
            output["blocked"].append({"index": index, "transaction_id": None,
                                      "errors": ["dispute must be an object"],
                                      "eligibility": {"eligible": False, "reasons": ["invalid dispute record"]}})
            continue
        transaction_id = dispute.get("transaction_id")
        if not isinstance(transaction_id, str) or not transaction_id.strip():
            errors.append("transaction_id is required")
        account = account_by_id.get(dispute.get("account_id"))
        if account is None:
            errors.append("account_id does not match a supplied account")
        else:
            last4 = account.get("card_last_4_digits")
            if not isinstance(last4, str) or len(last4) != 4 or not last4.isdigit():
                errors.append("matched account requires four numeric card_last_4_digits")
            if account.get("card_type") not in TIER_LIMITS:
                errors.append("matched account card_type is not a documented tier")

        txn_amount = amount(dispute.get("transaction_amount"), "transaction_amount", errors)
        purchase_day = required_date(dispute.get("purchase_date"), "purchase_date", errors)
        required_date(dispute.get("issue_noticed_date"), "issue_noticed_date", errors)
        reason = dispute.get("dispute_reason")
        if reason not in REASONS:
            errors.append("dispute_reason is not an allowed value")
        resolution = dispute.get("resolution_requested")
        if resolution not in RESOLUTIONS:
            errors.append("resolution_requested is not an allowed value")
        partial = dispute.get("partial_refund_amount")
        if resolution == "partial_refund":
            partial_value = amount(partial, "partial_refund_amount", errors)
        else:
            partial_value = None
            if partial is not None:
                errors.append("partial_refund_amount may be supplied only for partial_refund")
        if not isinstance(dispute.get("contacted_merchant"), bool):
            errors.append("contacted_merchant must be true or false")

        eligible, eligibility_reasons = eligibility(
            dispute, account, as_of, previous, txn_amount, purchase_day
        )
        if global_block:
            errors.append("global required input is invalid or unavailable")
        if errors:
            output["blocked"].append({
                "index": index, "transaction_id": transaction_id,
                "errors": errors,
                "eligibility": {"eligible": eligible, "reasons": eligibility_reasons},
            })
            continue

        args = {
            "transaction_id": transaction_id,
            "card_action": action,
            "card_last_4_digits": account["card_last_4_digits"],
            "full_name": customer["full_name"],
            "user_id": customer["user_id"],
            "phone": customer["phone"],
            "email": customer["email"],
            "address": customer["address"],
            "contacted_merchant": dispute["contacted_merchant"],
            "purchase_date": dispute["purchase_date"],
            "issue_noticed_date": dispute["issue_noticed_date"],
            "dispute_reason": reason,
            "resolution_requested": resolution,
            "eligible_for_provisional_credit": eligible,
        }
        if resolution == "partial_refund":
            args["partial_refund_amount"] = float(partial_value)
        output["ready_submissions"].append(args)
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ready_submissions": [], "blocked": [], "errors": [str(exc)]}, separators=(",", ":")))
