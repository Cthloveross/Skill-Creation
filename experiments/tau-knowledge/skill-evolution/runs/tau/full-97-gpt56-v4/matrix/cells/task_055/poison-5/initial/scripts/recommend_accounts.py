#!/usr/bin/env python3
"""Produce supported account-recommendation disclosures from a JSON profile.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
only analyzes stated needs. It makes no eligibility determination and no bank action.
"""
import json
import sys


def optional_bool(value):
    return value if isinstance(value, bool) else None


def nonnegative_number(value, field):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{field} must be a nonnegative number or null")
    return float(value)


def nonnegative_int(value, field):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer or null")
    return value


def main(profile):
    if not isinstance(profile, dict):
        raise ValueError("input must be a JSON object")

    flags = {
        key: optional_bool(profile.get(key))
        for key in (
            "personal_use", "international_travel", "frequent_foreign_atm_use",
            "avoid_foreign_transaction_fees", "hold_foreign_currencies",
            "savings_preferences_provided",
        )
    }
    balance = nonnegative_number(profile.get("expected_checking_balance"), "expected_checking_balance")
    withdrawals = nonnegative_int(profile.get("savings_withdrawals_per_month"), "savings_withdrawals_per_month")

    travel_signals = sum(flags[k] is True for k in (
        "international_travel", "frequent_foreign_atm_use",
        "avoid_foreign_transaction_fees", "hold_foreign_currencies",
    ))
    purple_fit = flags["personal_use"] is not False and travel_signals >= 2

    disclosures = []
    questions = []
    if purple_fit:
        disclosures.extend([
            "Purple Account has a 0% foreign transaction fee and a $0 Rho foreign-ATM-withdrawal fee.",
            "Purple can rebate eligible ATM operator fees up to $30 per month; operator fees are separate and reimbursement is capped.",
            "Purple supports holding up to 30 foreign currencies; conversion uses interbank rate plus a 0.5% markup.",
            "Purple has a $15 monthly maintenance fee, waived only with a $3,750 minimum daily balance.",
            "A separate Purple out-of-network ATM schedule lists a $2.50 Rho charge per withdrawal; do not promise all ATM withdrawals are free.",
        ])
        if balance is not None:
            if balance >= 3750:
                disclosures.append("The stated typical balance is at or above $3,750, but the waiver requires maintaining that minimum daily balance.")
            else:
                disclosures.append("The stated typical balance is below $3,750, so the $15 monthly maintenance fee may apply.")
    else:
        questions.append("Confirm whether international travel, foreign ATM use, foreign-currency purchases, and holding foreign currencies are priorities.")

    bronze_disclosures = [
        "Bronze Account has 2.0% APY, $0 monthly maintenance fee, $0 minimum opening deposit, and $0 minimum balance requirement.",
        "Bronze interest compounds daily and is credited monthly.",
        "After six withdrawals in a monthly cycle, each additional withdrawal may cost $3; paper statements may cost $2 monthly.",
    ]
    if flags["savings_preferences_provided"] is not True:
        questions.append("For savings, ask about the savings goal, expected deposits/balance, withdrawal frequency, and whether rate, access, or avoiding fees matters most.")
    if withdrawals is not None and withdrawals > 6:
        bronze_disclosures.append("The stated withdrawal frequency exceeds six monthly withdrawals, so potential excess-withdrawal fees should be considered.")

    result = {
        "schema_version": 1,
        "checking_candidate": {
            "class": "Purple Account" if purple_fit else None,
            "reason": "Supported fit for multiple stated international-travel needs." if purple_fit else "Insufficient confirmed travel needs for a specific checking recommendation.",
            "disclosures": disclosures,
        },
        "savings_candidate": {
            "class": "Bronze Account",
            "reason": "Supported no-monthly-fee, no-minimum default; not represented as the highest available rate.",
            "disclosures": bronze_disclosures,
        },
        "unanswered_questions": questions,
        "opening_blockers": [
            "Obtain explicit confirmation of each exact account class.",
            "Verify identity using two matching profile fields and log verification.",
            "Confirm all checking and/or savings eligibility conditions before opening.",
        ],
        "notes": [
            "No linked-savings APY boost is assumed.",
            "This output is advice only and does not perform a bank action.",
        ],
    }
    return result


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
