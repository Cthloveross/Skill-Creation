---
name: open-eligible-personal-checking
version: 1.0.0
description: Verify a customer, assess documented eligibility, accurately answer Green Fee-Free Account foreign-ATM and maintenance-fee questions, and open a selected personal checking account only after all required checks pass. Use for requests to open a personal checking account, especially when foreign/out-of-network ATM costs affect the product choice.
---

# Open an eligible personal checking account

## Scope and governing requirements

Use this Skill for personal checking openings. The documented prerequisites are:

1. The customer is verified.
2. The customer is at least 18.
3. The customer does not exceed four personal checking accounts.
4. The customer has no checking account closed for cause in the preceding six months.
5. The customer has confirmed an official `account_class` whose complete name ends in `Account`.

The retrieval tool for account eligibility is `get_all_user_accounts_by_user_id_3847`. The required opening tool is `open_bank_account_4821`; both are agent-discoverable tools and must be unlocked before use. Do not open an account based solely on a product discussion or a customer name.

## Responding to the Green Fee-Free Account question

When the customer has selected **Green Fee-Free Account**, state the following product-specific facts accurately:

- Rho charges **$0.00** for out-of-network ATM withdrawals and **$0.00** for foreign ATM withdrawals on this account.
- An ATM owner/operator can separately charge a surcharge; that is not a Rho fee.
- The monthly maintenance fee is **$22.50**. It is waived for a statement cycle when the customer maintains a **minimum daily balance of at least $150** during that cycle.

Do not apply fees documented for similarly named but different account classes (for example, `Green Account (checking)`) to `Green Fee-Free Account`. Do not characterize the $150 condition as merely having a one-time balance of $150. If the customer asks about total trip cost, distinguish Rho ATM fees, third-party operator surcharges, and the monthly maintenance fee.

After answering, obtain or reconfirm the customer’s explicit intent to open the exact official class. `Green Fee-Free Account` is an official-form selection ending in `Account`; preserve that full string when opening it.

## Required execution workflow

1. **Identify the customer safely.** Use a supplied full name or email with the applicable profile lookup tool. If zero or multiple records are returned, request a unique profile identifier; do not guess.
2. **Verify identity.** Ask the customer to provide any two of date of birth, email address, phone number, and street address. Do not lead the customer by disclosing profile values. Compare the two supplied values with the retrieved profile. When two fields match, retrieve the current timestamp with `get_current_time` and call `log_verification` with the complete profile fields and timestamp. Set `identity_verified` only after that log succeeds.
3. **Retrieve accounts.** Unlock `get_all_user_accounts_by_user_id_3847`, then retrieve accounts using the verified `user_id`. Retain the returned account records, including account type, class, status, and any closure reason/date data.
4. **Assess eligibility.** Canonicalize the profile and retrieved accounts and run `scripts/assess_opening.py`. The script is a decision aid, not a replacement for the retrieval and verification tools. It treats incomplete data on a closed account as a review condition rather than assuming eligibility.
5. **Resolve blockers before opening.** If the output is not eligible, do not call the opening tool. For an unmet requirement, explain the applicable requirement without exposing unnecessary internal data. For missing closure information or an unrecognized account classification, obtain an authoritative eligibility review through the available approved process; do not waive the check.
6. **Open only after a pass.** Confirm the selected full account class one final time if there was any ambiguity or the discussion occurred before identity verification. Unlock `open_bank_account_4821`, inspect the unlocked tool's required argument schema, and call it with only its supported fields and the verified customer identity plus the exact confirmed `account_class`. Do not invent an initial deposit, balance, account subtype, or any unsupported parameter.
7. **Report the outcome.** On success, tell the customer that the requested account was opened and provide only the account information returned by the tool. Restate relevant fee conditions when useful. If the opening tool fails, report that it could not be completed and do not imply that an account exists.

## Eligibility helper

`scripts/assess_opening.py` accepts one JSON object on stdin and emits one JSON object on stdout.

### Input schema

```json
{
  "as_of": "YYYY-MM-DD or timestamp",
  "profile": {"date_of_birth": "MM/DD/YYYY or ISO date"},
  "identity_verified": true,
  "selection": "full official account class",
  "official_account_classes": ["full official account class"],
  "accounts": [
    {
      "account_id": "optional identifier",
      "account_type": "checking",
      "account_class": "optional class",
      "status": "open or closed status",
      "is_personal_checking": true,
      "closed_for_cause": false,
      "closure_reason": "optional reason",
      "date_closed": "optional closure date"
    }
  ],
  "policy": {
    "minimum_age": 18,
    "max_personal_checking_accounts": 4,
    "closure_lookback_months": 6
  }
}
```

Use the actual current date as `as_of`. Supply `is_personal_checking` when the returned record or approved classification clearly establishes it. If it is absent, the helper conservatively treats a checking record as personal unless the record explicitly identifies it as business. Preserve closure fields exactly when available. `official_account_classes` must be the approved choices available for this opening, not a customer-invented label.

### Output schema and interpretation

```json
{
  "eligible": false,
  "age": 0,
  "personal_checking_count": 0,
  "reasons": ["machine-readable reason"],
  "review_required": false,
  "cutoff_date": "YYYY-MM-DD"
}
```

Open only when `eligible` is `true`. `reasons` explains failed checks. `review_required: true` means a record indicates a closure but its cause or date cannot establish compliance; it is not a pass.

### Runnable executor call example

```json
{"relative_path":"scripts/assess_opening.py","input_json":{"as_of":"2025-01-15","profile":{"date_of_birth":"1990-01-01"},"identity_verified":true,"selection":"Example Checking Account","official_account_classes":["Example Checking Account"],"accounts":[],"policy":{"minimum_age":18,"max_personal_checking_accounts":4,"closure_lookback_months":6}}}
```

Before relying on the output, validate that it contains all six output keys, that `age` reflects the date of birth as of `as_of`, that every retrieved checking account was represented, and that every closed checking record has an evaluated reason and closure date. The example is structural only and is not a product recommendation or an account-opening instruction.
