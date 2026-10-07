---
name: business-checking-recommendation-and-opening
version: 1.0.0
description: Recommend a documented business checking account from stated customer requirements, apply time-bounded account-priority promotions only among qualifying accounts, and safely prepare an account-opening workflow.
---

# Business Checking Recommendation and Opening

Use this Skill when a customer asks which business checking account fits their needs, or asks to open a recommended business checking account.

## Principles

1. Turn the customer's explicit statements into mandatory requirements. Do not infer that an unstated preference (for example, a low balance requirement) is mandatory.
2. Treat a requirement as satisfied only when the account's terms document it. Missing product information is not evidence that the account qualifies.
3. A promotion may rank qualifying accounts, but can never make an account qualify or override a mandatory requirement.
4. Do not open an account merely because the customer requested advice. Obtain confirmation of the exact account class after the recommendation.
5. Never characterize a $0 overdraft fee as a guarantee that all overdrawn transactions will be paid. Explain any documented decline, return, or balance-related conditions separately.

## Recommendation workflow

1. Identify the hard requirements, requested enhancements, and useful-but-unstated tradeoffs. Ask a focused follow-up only if it would change the recommendation or the customer has not supplied a decision-critical constraint.
2. Consult `references/business_checking_terms.md`. Build a candidate list using only products whose relevant terms are documented.
3. If a promotion is active as of the supplied current date, include its ordered account classes as a promotion policy. Run `scripts/evaluate_business_checking.py` or apply the same rules manually.
4. Explain:
   - the recommended account and why it meets each stated hard requirement;
   - material fees, thresholds, limits, or cash-flow implications that the customer should understand;
   - why any promotion affects the ordering, if applicable; and
   - any unknown product terms that prevent an account from being treated as a match.
5. Give a concise comparison when it materially helps. Do not claim that an existing account lacks a feature unless that is documented.

### Handling incomplete requirements

When only one hard requirement is known, recommend the highest-ranked documented qualifying account if the customer has asked for a direct recommendation, while clearly disclosing material tradeoffs. Invite the customer to provide balance, transaction-volume, payments, or service needs if they want the decision refined. If the available facts cannot establish that any account meets a hard requirement, say so and ask for the missing information rather than guessing.

### Current-prompt application pattern

For a customer whose only non-negotiable requirement is a $0 overdraft fee and who wants a more-featured account:

- Compare the documented $0-overdraft-fee products, not merely the customer's existing product.
- During the documented November 2025 promotion, do not assume Sky Blue qualifies when no Sky Blue terms establish the $0 fee requirement.
- Lime Green is a documented qualifying promotional option and has documented dedicated-manager support, 1.5% APY, and a $100,000 daily transaction limit. Its $25 monthly fee, $15,000 waiver threshold, and $5,000 end-of-day balance condition for benefits are material for a customer with variable cash flow and must be disclosed.
- This is a recommendation, not authority to open. Ask the customer to confirm the exact account class before starting the opening procedure.

## Opening workflow

Only proceed after the customer confirms the account class they want.

1. Verify identity under the available verification policy. Where the provided banking tools require it, confirm two of the four identity fields (date of birth, email, phone number, address), retrieve information using an approved lookup method, obtain the current timestamp, and call `log_verification` with the complete required audit record.
2. Check every documented business-checking eligibility condition:
   - customer is verified;
   - at least one existing personal checking account has status `OPEN`;
   - no more than six business checking accounts;
   - no account has status `CLOSED`; and
   - the existing checking account balance is at least $500.
3. Confirm the precise `account_class` aloud with the customer; do not substitute a similarly named account.
4. Only after all checks pass, use the normal banking-tool discovery and execution workflow for the documented account-opening tool. Use the tool's actual schema after it is unlocked; do not invent parameters.
5. If verification or eligibility fails, explain the unmet condition without exposing unnecessary account information. Do not attempt the opening action. If the customer requests a human after an unavailable-offer refusal, use the appropriate available transfer path.

## Evaluator script

`scripts/evaluate_business_checking.py` makes a transparent eligibility-and-promotion ranking from runtime-supplied data. It does not open accounts.

### Input JSON schema

```json
{
  "as_of": "YYYY-MM-DD",
  "requirements": {
    "zero_overdraft_fee": true,
    "max_overdraft_fee": 0,
    "features_all": ["dedicated_account_manager"],
    "min_daily_transaction_limit": 100000,
    "min_apy": 1.5,
    "max_monthly_maintenance_fee": 25,
    "max_waiver_balance": 15000,
    "exact_attributes": {"optional_key": "required value"}
  },
  "candidates": [
    {
      "account_class": "Account class displayed to the customer",
      "overdraft_fee": 0,
      "features": ["dedicated_account_manager"],
      "daily_transaction_limit": 100000,
      "apy": 1.5,
      "monthly_maintenance_fee": 25,
      "waiver_balance": 15000,
      "attributes": {"optional_key": "required value"}
    }
  ],
  "promotions": [
    {
      "start": "YYYY-MM-DD",
      "end": "YYYY-MM-DD",
      "priority": ["First qualifying account", "Second qualifying account"]
    }
  ]
}
```

All requirement fields are optional. A supplied requirement is mandatory. A candidate missing a value needed to test a supplied requirement is excluded, rather than assumed to satisfy it. Amounts may be JSON numbers or strings such as `"$0.00"`. `features_all` values are normalized case-insensitively.

### Output JSON schema and interpretation

The script emits `{"status":"ok", ...}` with `qualifying`, `excluded`, `ranking`, `active_promotions`, and `recommendation`. `recommendation` is the first qualifying account after active-promotion ordering; without an active promotion, it is the first qualifying candidate in supplied order. This is deliberate: the executor must supply a defensible non-promotion ordering rather than treating an arbitrary script score as product advice. An empty `ranking` means no documented candidate met all hard requirements. Invalid input emits `{"status":"error","errors":[...]}`.

Example invocation through the package runtime:

```json
{"relative_path":"scripts/evaluate_business_checking.py","input_json":{"as_of":"2025-11-14","requirements":{"zero_overdraft_fee":true},"candidates":[...],"promotions":[...]}}
```

Validate the result before relying on it: confirm `status` is `ok`, inspect every `excluded` reason, ensure the recommendation appears in `qualifying`, and verify that every claimed product term against the reference is represented in the candidate object.
