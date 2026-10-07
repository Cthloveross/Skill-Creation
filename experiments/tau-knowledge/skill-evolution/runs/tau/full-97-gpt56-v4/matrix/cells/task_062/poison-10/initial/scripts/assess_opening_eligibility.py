#!/usr/bin/env python3
"""Assess documented opening eligibility from supported, already-collected facts.

Input JSON has request_type of "personal_savings" or "business_checking" and
boolean/count/balance fields appropriate to that request. Output is a JSON
preflight result. Missing fields and false/invalid fields are blockers. This
script never opens an account and does not establish identity or authority.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def emit(payload):
    print(json.dumps(payload, sort_keys=True))


def as_bool(data, key, blockers):
    if key not in data:
        blockers.append("missing_" + key)
        return False
    if data[key] is not True:
        blockers.append(key + "_not_verified")
        return False
    return True


def nonnegative_int(data, key, blockers):
    try:
        value = int(data[key])
        if value < 0:
            raise ValueError
        return value
    except (KeyError, ValueError, TypeError):
        blockers.append("invalid_or_missing_" + key)
        return None


def selected_class(data, blockers):
    value = str(data.get("selected_account_class", "")).strip()
    if not value:
        blockers.append("exact_account_class_not_confirmed")
    return value


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        emit({"eligible": False, "error": "invalid_json", "detail": str(exc)})
        return

    request_type = data.get("request_type")
    if request_type not in {"personal_savings", "business_checking"}:
        emit({"eligible": False, "error": "unsupported_request_type"})
        return

    blockers = []
    as_bool(data, "identity_verified", blockers)
    selected_class(data, blockers)

    if request_type == "personal_savings":
        as_bool(data, "personal_checking_open", blockers)
        age = nonnegative_int(data, "checking_age_days", blockers)
        if age is not None and age < 14:
            blockers.append("checking_account_tenure_under_14_days")
        savings_count = nonnegative_int(data, "personal_savings_count", blockers)
        if savings_count is not None and savings_count >= 5:
            blockers.append("personal_savings_limit_reached")
        as_bool(data, "no_collections", blockers)
        as_bool(data, "no_negative_balance", blockers)
        requirements = [
            "Final live identity, ownership, product-class, and account-state verification.",
            "Customer authorization for any optional opening-deposit transfer.",
        ]
    else:
        as_bool(data, "business_authority_verified", blockers)
        as_bool(data, "personal_checking_open", blockers)
        try:
            balance = Decimal(str(data["personal_checking_balance"]))
            if balance < Decimal("500"):
                blockers.append("personal_checking_balance_under_500")
        except (KeyError, InvalidOperation):
            blockers.append("invalid_or_missing_personal_checking_balance")
        count = nonnegative_int(data, "business_checking_count", blockers)
        # Existing count must leave capacity for the new account.
        if count is not None and count >= 6:
            blockers.append("business_checking_limit_reached")
        as_bool(data, "no_closed_accounts", blockers)
        as_bool(data, "formation_registration_documents_ready", blockers)
        as_bool(data, "tax_and_matching_contact_details_ready", blockers)
        as_bool(data, "beneficial_owner_information_ready", blockers)
        as_bool(data, "holder_identity_materials_ready", blockers)
        as_bool(data, "banking_authorization_ready", blockers)
        holders = nonnegative_int(data, "intended_holder_count", blockers)
        if holders is not None and (holders < 1 or holders > 4):
            blockers.append("intended_holder_count_must_be_between_1_and_4")
        requirements = [
            "Final live identity, authority, personal-checking, account-count, and status verification.",
            "Confirm fees, limits, cutoffs, product terms, holder details, and final authorization.",
            "Do not proceed if any account has already been closed before this business-opening request.",
        ]

    emit({
        "eligible": not blockers,
        "request_type": request_type,
        "blockers": blockers,
        "still_required": requirements,
    })


if __name__ == "__main__":
    main()
