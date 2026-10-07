#!/usr/bin/env python3
"""Evaluate account-opening prerequisites supplied by the caller.

The program is deliberately side-effect free: it does not retrieve customer data,
open an account, or move funds. All results are JSON on stdout.
"""

import json
import sys


def as_object(value, label, required=True):
    if value is None and not required:
        return {}
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    return value


def as_nonnegative_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(field + " must be a nonnegative number")
    return value


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        requested = as_object(payload.get("requested"), "requested")
        customer = as_object(payload.get("customer"), "customer")
        policy = as_object(payload.get("policy"), "policy")
        funding = as_object(payload.get("funding"), "funding", required=False)

        blockers = []
        unknowns = []

        def known_boolean(obj, key, required_value, label):
            if key not in obj or obj[key] is None:
                unknowns.append(label)
                return
            if obj[key] is not required_value:
                blockers.append(label)

        account_type = requested.get("account_type")
        account_class = requested.get("account_class")
        if account_type not in ("checking", "savings"):
            blockers.append("requested account_type must be checking or savings")
        if not isinstance(account_class, str) or not account_class.strip():
            blockers.append("official account_class is missing")
        suffix = policy.get("account_class_suffix")
        if suffix is not None:
            if not isinstance(suffix, str) or not suffix:
                raise ValueError("account_class_suffix must be a nonempty string")
            elif isinstance(account_class, str) and not account_class.endswith(suffix):
                blockers.append("account_class does not use the required official suffix")

        known_boolean(requested, "selection_confirmed", True, "exact account selection has not been confirmed")
        known_boolean(requested, "opening_authorized", True, "opening authorization has not been confirmed")

        if policy.get("require_verified") is True:
            known_boolean(customer, "verified", True, "customer identity is not verified")

        if "minimum_age" in policy:
            minimum_age = as_nonnegative_number(policy["minimum_age"], "minimum_age")
            age = customer.get("age")
            if age is None:
                unknowns.append("customer age")
            elif isinstance(age, bool) or not isinstance(age, (int, float)):
                blockers.append("customer age is invalid")
            elif age < minimum_age:
                blockers.append("customer does not meet the minimum age")

        count_key = "existing_personal_checking_count" if account_type == "checking" else "existing_personal_savings_count"
        limit_key = "max_existing_checking_accounts" if account_type == "checking" else "max_existing_savings_accounts"
        if limit_key in policy:
            limit = as_nonnegative_number(policy[limit_key], limit_key)
            count = customer.get(count_key)
            if count is None:
                unknowns.append(count_key)
            elif isinstance(count, bool) or not isinstance(count, (int, float)) or count < 0:
                blockers.append(count_key + " is invalid")
            elif count > limit:
                blockers.append("existing account count exceeds the permitted limit")

        if policy.get("disallow_closed_for_cause_within_months") is not None:
            months = as_nonnegative_number(policy["disallow_closed_for_cause_within_months"], "disallow_closed_for_cause_within_months")
            value = customer.get("checking_closed_for_cause_within_policy_window")
            if value is None:
                unknowns.append("checking closure-for-cause history for the policy window")
            elif value is not False:
                blockers.append("checking account was closed for cause within the policy window")

        if policy.get("require_active_checking") is True:
            known_boolean(customer, "has_active_checking", True, "no active checking account is confirmed")

        if "minimum_checking_tenure_days" in policy:
            required_days = as_nonnegative_number(policy["minimum_checking_tenure_days"], "minimum_checking_tenure_days")
            tenure = customer.get("checking_tenure_days")
            if tenure is None:
                unknowns.append("checking tenure")
            elif isinstance(tenure, bool) or not isinstance(tenure, (int, float)) or tenure < 0:
                blockers.append("checking tenure is invalid")
            elif tenure < required_days:
                blockers.append("checking tenure is below the required minimum")

        if policy.get("disallow_collections") is True:
            known_boolean(customer, "has_accounts_in_collections", False, "accounts in collections are present")
        if policy.get("disallow_negative_balances") is True:
            known_boolean(customer, "has_negative_balance", False, "negative account balance is present")

        user_id = customer.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            unknowns.append("authenticated user_id")

        ready = not blockers and not unknowns
        output = {
            "ready": ready,
            "blockers": blockers,
            "unknowns": unknowns,
            "open_action": None,
            "post_open_funding_plan": None,
        }
        if ready:
            output["open_action"] = {
                "tool": "open_bank_account_4821",
                "arguments": {
                    "user_id": user_id,
                    "account_type": account_type,
                    "account_class": account_class,
                },
                "execute_only_after_gate": True,
            }

        # Funding is intentionally post-open because the new destination account ID is
        # unknown until the opening tool succeeds.
        if account_type == "savings":
            required_deposit = funding.get("required_opening_deposit")
            immediate = funding.get("immediate_transfer_authorized")
            deadline_days = funding.get("deferred_funding_deadline_days")
            if immediate is True:
                source_id = funding.get("source_checking_account_id")
                if required_deposit is None or not isinstance(source_id, str) or not source_id:
                    output["post_open_funding_plan"] = {
                        "status": "needs_required_deposit_or_source_account",
                        "instruction": "Do not transfer until the required deposit and source checking account are confirmed.",
                    }
                else:
                    output["post_open_funding_plan"] = {
                        "status": "authorized_after_successful_open",
                        "tool": "transfer_funds_between_bank_accounts_7291",
                        "arguments": {
                            "source_account_id": source_id,
                            "destination_account_id": "NEW_ACCOUNT_ID_FROM_OPEN_RESULT",
                            "amount": required_deposit,
                        },
                    }
            elif immediate is False:
                plan = {"status": "customer_deferred_funding"}
                if deadline_days is not None:
                    plan["funding_deadline_days"] = deadline_days
                output["post_open_funding_plan"] = plan
            else:
                output["post_open_funding_plan"] = {
                    "status": "ask_customer_about_opening_deposit_funding",
                    "instruction": "Ask whether the customer authorizes an immediate internal transfer after the account opens.",
                }

        print(json.dumps(output, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}, sort_keys=True))
        sys.exit(2)


if __name__ == "__main__":
    main()
