---
name: safe-personal-checking-account-opening
description: Handle a request to recommend and open a personal checking account, including identity verification, eligibility review, account lookup, required disclosures, and use of the documented account-opening tool. Use when a customer asks to open a checking account or select a checking product.
---

# Safe Personal Checking Account Opening

Use this workflow for personal checking-account openings. Do not open an account merely because the customer has selected a product; complete the required verification, eligibility, authority, and confirmation steps first.

## Inputs and assumptions

At runtime, obtain:

- The customer's profile identifier through an approved lookup using customer-provided identifying information.
- Two independently confirmed identity fields from the customer (from date of birth, email, phone number, and address).
- The desired official `account_class` name.
- The customer's unambiguous authorization to open that selected account.
- Current account records and any available checking-closure history.

The account-opening rules supported by this Skill are:

1. Customer identity is verified.
2. Customer is at least 18 years old.
3. Customer does not exceed four personal checking accounts.
4. Customer has had no checking account closed for cause in the previous six months.
5. The personal checking `account_class` is the full official name ending in `Account`.

Unknown or unavailable information is not a passing result. Do not infer an eligibility fact from silence, an email lookup, a product preference, or an unverified customer statement.

## Product recommendation and disclosures

When travel ATM fees and early direct deposit are material, Purple Account is a documented candidate: it advertises eligible direct deposit up to two days early, a $0 foreign ATM withdrawal fee, and operator-fee rebates up to $30 monthly after eligible fees post. It has a $15 monthly maintenance fee, waived by a $3,750 minimum daily balance.

Give a complete, non-misleading disclosure before opening:

- ATM operator surcharges can still apply and rebates are capped at $30 per month.
- The available Purple Account material separately describes a $2.50 fee per out-of-network ATM withdrawal. Do not promise that every foreign or out-of-network withdrawal is free; explain this separate fee disclosure and resolve any applicability conflict through approved product guidance before making a definitive total-fee claim.
- Direct-deposit timing is contingent on an eligible direct deposit and payer processing.

If the customer chooses Purple Account after these disclosures, treat that as product selection only. Obtain or confirm authorization to open before the irreversible opening call.

## Procedure

1. **Identify the customer and verify authority.** Locate the profile only from information the customer provides. Ask the customer to confirm two profile fields. Compare both to the retrieved profile. Do not disclose unconfirmed profile information to obtain the answers. After two fields match, obtain the current time and call `log_verification` with the complete retrieved profile fields and timestamp. A profile lookup alone is not identity verification.
2. **Retrieve current accounts.** Unlock `get_all_user_accounts_by_user_id_3847`, then call it for the verified `user_id`. Retain the returned account IDs, types, classes, statuses, balances, and opening dates for the eligibility assessment. Use the discovered tool schema exactly.
3. **Check eligibility.** Confirm age from the verified date of birth as of the current date; count personal checking accounts conservatively; and determine whether a checking account was closed for cause during the prior six months. If account records do not supply closure reason/history, obtain it from an approved source or obtain an appropriate customer attestation if permitted by the operating environment. Do not open while any condition is unknown, failed, or ambiguous.
4. **Validate product and authorization.** Ensure the desired class is a supported personal checking option with its exact official name ending in `Account`. Re-state material fees/limits relevant to the selection and confirm the customer wants the account opened now.
5. **Open only after all gates pass.** Unlock `open_bank_account_4821`, inspect its discovered parameter schema, and call it with the verified customer and selected exact official account class as required by that schema. Do not invent arguments, account IDs, opening deposits, or status values.
6. **Report the outcome.** Give the customer the account-opening result returned by the tool and concise applicable disclosures. If opening is not possible, clearly state the unmet or unknown prerequisite and what is needed next. Do not claim an account was opened unless the opening tool reports success.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Handling incomplete or declined verification

If the customer declines, does not answer, or gives an out-of-scope response to a prerequisite question, do not repeat the same question indefinitely and do not take the opening action. Explain that the account cannot be opened until identity and eligibility requirements can be verified. A human transfer is not a substitute for missing mandatory verification unless a separate approved escalation rule requires one.

## Eligibility helper

Use `scripts/check_opening_eligibility.py` for a transparent preliminary assessment after records have been retrieved. It does not perform bank actions and does not replace required tool checks or the verification audit.

### Input JSON

```json
{
  "date_of_birth": "MM/DD/YYYY or YYYY-MM-DD",
  "as_of_date": "YYYY-MM-DD",
  "identity_verified": true,
  "verification_logged": true,
  "accounts": [{"account_type": "checking", "account_class": "...", "status": "...", "personal": true}],
  "closed_for_cause_within_six_months": false,
  "account_class": "Official Product Account",
  "customer_authorized": true
}
```

`closed_for_cause_within_six_months` may be `true`, `false`, or `null` when unavailable. `personal` may be omitted only when all returned accounts are known to belong to this customer; unclear account classification is reported for manual review.

### Output JSON

The script emits an object with `eligible` (`true`, `false`, or `null`), calculated age, detected personal-checking count, `blocking_reasons`, `unknown_requirements`, and `warnings`. Only `eligible: true` permits advancing to the final opening-tool step, subject to the live tool checks above.

Example runtime invocation:

```sh
python3 scripts/check_opening_eligibility.py <<'JSON'
{"date_of_birth":"1990-01-01","as_of_date":"2025-01-01","identity_verified":true,"verification_logged":true,"accounts":[],"closed_for_cause_within_six_months":false,"account_class":"Example Account","customer_authorized":true}
JSON
```

Validate that the script returns valid JSON and that no blocking reason or unknown requirement remains before using its result as an eligibility gate.