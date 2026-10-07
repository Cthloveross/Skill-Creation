"""Local validation and provisional-credit eligibility helper.

Read one JSON object from stdin and emit one JSON object to stdout.
Modes: eligibility, validate_payload.
"""
import datetime as dt
import json
import sys
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
CARD_ACTIONS = {"keep_active", "cancel_and_reissue"}
TIER_LIMITS = {
    "Bronze Rewards Card": Decimal("2500.00"),
    "EcoCard": Decimal("2500.00"),
    "Business Bronze Rewards Card": Decimal("2500.00"),
    "Crypto-Cash Back Card": Decimal("2500.00"),
    "Silver Rewards Card": Decimal("5000.00"),
    "Business Silver Rewards Card": Decimal("5000.00"),
    "Green Rewards Card": Decimal("5000.00"),
    "Silver Zoom Card": Decimal("5000.00"),
    "Gold Rewards Card": Decimal("10000.00"),
    "Business Gold Rewards Card": Decimal("10000.00"),
    "Platinum Rewards Card": Decimal("15000.00"),
    "Business Platinum Rewards Card": Decimal("15000.00"),
    "Diamond Elite Card": Decimal("25000.00"),
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use MM/DD/YYYY or YYYY-MM-DD")


def parse_amount(value):
    if isinstance(value, bool):
        raise ValueError("amount must be numeric")
    try:
        text = str(value).strip().replace("$", "").replace(",", "")
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("amount must be numeric")
    if not amount.is_finite():
        raise ValueError("amount must be finite")
    return amount


def eligibility(data):
    required = [
        "current_date", "account_open_date", "card_type", "transaction_amount",
        "purchase_date", "dispute_reason", "contacted_merchant",
        "disputes_past_12_months",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        return {"error": "missing required fields", "missing": missing}
    try:
        current = parse_date(data["current_date"])
        opened = parse_date(data["account_open_date"])
        purchase = parse_date(data["purchase_date"])
        amount = parse_amount(data["transaction_amount"])
        prior_count = int(data["disputes_past_12_months"])
    except (ValueError, TypeError) as exc:
        return {"error": str(exc)}
    if isinstance(data["disputes_past_12_months"], bool) or prior_count < 0:
        return {"error": "disputes_past_12_months must be a nonnegative integer"}
    if not isinstance(data["contacted_merchant"], bool):
        return {"error": "contacted_merchant must be a boolean"}

    reason = data["dispute_reason"]
    limit = TIER_LIMITS.get(data["card_type"])
    account_age = (current - opened).days
    purchase_age = (current - purchase).days
    failures = []
    if account_age < 60:
        failures.append("account_open_less_than_60_days")
    if reason not in REASONS:
        failures.append("invalid_dispute_reason")
    elif reason not in {
        "unauthorized_fraudulent_charge",
        "duplicate_charge",
        "goods_services_not_received",
    }:
        failures.append("reason_not_provisionally_eligible")
    elif reason == "goods_services_not_received" and purchase_age <= 30:
        failures.append("goods_not_received_purchase_not_more_than_30_days_old")
    if amount < Decimal("25.00"):
        failures.append("amount_below_25")
    if limit is None:
        failures.append("unrecognized_card_tier")
    elif amount > limit:
        failures.append("amount_exceeds_card_tier_limit")
    if prior_count > 2:
        failures.append("more_than_two_prior_disputes_in_12_months")
    if reason != "unauthorized_fraudulent_charge" and not data["contacted_merchant"]:
        failures.append("non_fraud_merchant_not_contacted")

    result = {
        "eligible_for_provisional_credit": not failures,
        "reasons": failures,
        "account_age_days": account_age,
        "purchase_age_days": purchase_age,
    }
    if limit is not None:
        result["maximum_amount"] = float(limit)
    return result


def validate_payload(data):
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["payload must be an object"]}
    errors = []
    required = [
        "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
        "phone", "email", "address", "contacted_merchant", "purchase_date",
        "issue_noticed_date", "dispute_reason", "resolution_requested",
        "eligible_for_provisional_credit",
    ]
    for key in required:
        if key not in payload:
            errors.append("missing_" + key)
        elif key not in {"contacted_merchant", "eligible_for_provisional_credit"} and (
            not isinstance(payload[key], str) or not payload[key].strip()
        ):
            errors.append("invalid_" + key)
    if payload.get("card_action") not in CARD_ACTIONS:
        errors.append("invalid_card_action")
    if payload.get("dispute_reason") not in REASONS:
        errors.append("invalid_dispute_reason")
    resolution = payload.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("invalid_resolution_requested")
    for key in ("contacted_merchant", "eligible_for_provisional_credit"):
        if key in payload and not isinstance(payload[key], bool):
            errors.append("invalid_" + key + "_boolean")
    for key in ("purchase_date", "issue_noticed_date"):
        if key in payload:
            try:
                # Filing requires the first accepted format, rather than ISO input.
                dt.datetime.strptime(payload[key], "%m/%d/%Y")
            except (TypeError, ValueError):
                errors.append("invalid_" + key + "_format")
    last4 = payload.get("card_last_4_digits")
    if isinstance(last4, str) and (len(last4) != 4 or not last4.isdigit()):
        errors.append("invalid_card_last_4_digits")
    has_partial = "partial_refund_amount" in payload
    if resolution == "partial_refund":
        if not has_partial:
            errors.append("missing_partial_refund_amount")
        else:
            try:
                if parse_amount(payload["partial_refund_amount"]) <= 0:
                    errors.append("invalid_partial_refund_amount")
            except ValueError:
                errors.append("invalid_partial_refund_amount")
    elif has_partial:
        errors.append("partial_refund_amount_not_allowed_for_resolution")
    return {"valid": not errors, "errors": errors}


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        mode = request.get("mode")
        if mode == "eligibility":
            output = eligibility(request)
        elif mode == "validate_payload":
            output = validate_payload(request)
        else:
            output = {"error": "mode must be eligibility or validate_payload"}
        print(json.dumps(output, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        sys.exit(2)


if __name__ == "__main__":
    main()
