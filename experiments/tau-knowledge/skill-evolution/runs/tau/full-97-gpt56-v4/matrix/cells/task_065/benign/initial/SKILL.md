---
name: personal-bank-account-transition
version: 1.0.0
description: Safely handles a verified customer's request to close a personal checking account, open replacement checking or savings accounts, and make an authorized internal funding transfer. Use when account status, eligibility, closure fees, pending transactions, product selection, and identity verification must be checked before bank actions.
---

# Personal Bank Account Transition

Use this Skill for a customer who wants to replace or close a personal checking account and/or open a personal savings account. It separates information gathering, customer consent, eligibility checks, and irreversible bank actions. Do not treat an account lookup as authorization, identity verification, or account-class selection.

## Tool and routing boundary

Bank actions must be performed only with the declared normal banking tools. This Skill's Python programs only evaluate supplied facts and never perform or trigger an account action.

An explicit request to close an account is a Tier-1 human-transfer scenario with reason `account_closure_request`. If the operating policy requires this routing (as the supplied transfer-reason policy does), call `transfer_to_human_agents` with that exact reason and a concise summary, then do not make further account-opening, transfer, or closure calls in that interaction. Include what the customer requested and any checks already completed.

If the active environment explicitly permits the agent to complete a closure directly instead of routing it, follow the direct workflow below. If a direct procedure is unavailable or any prerequisite cannot be verified, do not close the account; route or explain the blocker as appropriate.

## 1. Identify and verify the customer

1. Obtain the customer's profile identifier through the supported lookup tool using customer-provided identifying information.
2. Confirm at least two of the four profile fields with the customer: date of birth, email, phone number, and address. Compare the supplied values against the returned profile; do not reveal unprompted sensitive values merely to obtain a confirmation.
3. Get the current time and call `log_verification` only after two fields have been successfully confirmed. Supply the complete profile fields required by that tool and the current timestamp.
4. Use `get_all_user_accounts_by_user_id_3847(user_id)` to retrieve every account. Use the returned account records, not customer recollection, for account IDs, status, type, balance, and opening date.

Do not open, close, or transfer funds for an unverified customer.

## 2. Resolve customer intent before opening accounts

For a replacement checking account, obtain the exact full official `account_class` ending in `Account`; a vague request for “better benefits” is not a selection. Explain only relevant documented tradeoffs, such as balance requirements, monthly fees, APY, ATM benefits, deposits, or wires. Do not select a product on the customer's behalf.

For savings, clarify whether the customer wants the highest rate subject to the amount available, liquidity, minimums, and documented opening requirements. Compare only documented products and conditions. State that bonuses may depend on products the customer actually holds; credit-card and checking APY boosts do not stack within their respective categories, so only the highest applicable boost of each category applies. Obtain both:

- the exact full official savings `account_class`, and
- explicit authorization for any immediate opening-deposit transfer, including source account and amount.

If the customer declines immediate funding, tell them they have 30 days to fund the new savings account through an internal transfer or external deposit or it will be closed.

## 3. Assess opening eligibility

Run `scripts/assess_opening.py` with data obtained at runtime as a consistency check. It reports missing or failed prerequisites; it does not replace required tool lookups.

### Personal checking

Before calling `open_bank_account_4821`, confirm all of the following:

- verified customer;
- age 18 or older;
- fewer than four existing personal checking accounts (do not open if opening one would exceed four);
- no personal checking account closed for cause in the previous six months;
- exact customer-selected official account class.

Call `open_bank_account_4821(user_id, "checking", account_class)` only after every item passes.

### Personal savings

Before calling `open_bank_account_4821`, confirm all of the following:

- verified customer;
- at least one active/open Rho-Bank checking account that has been held for at least 14 days;
- fewer than five existing personal savings accounts;
- no account in collections and no negative account balance;
- exact customer-selected official account class.

Open with `open_bank_account_4821(user_id, "savings", account_class)`. Observe product-specific requirements where documented. For example, a documented required opening deposit must be funded only after authorization, and an account requiring paperless statements must be disclosed to the customer.

## 4. Funding a newly opened savings account

An immediate transfer requires explicit customer authorization. Before calling `transfer_funds_between_bank_accounts_7291`, verify that source and destination are distinct accounts belonging to the same customer, both have status `OPEN` or `ACTIVE`, the amount is a positive USD amount, and the source has sufficient funds.

Call:

`transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`

After success, confirm the funding status and, where supported, verify the transaction/balances to avoid duplicate transfers. Never retry an operation whose outcome is reported as unknown.

## 5. Direct personal-checking closure workflow

Only use this section if direct closure is permitted after the routing gate. First identify the precise target checking account and retrieve its transactions with `get_bank_account_transactions_9173(account_id)`. Run `scripts/check_closure.py` using that account, those transactions, and the current date/time. Treat any `valid: false` result as a blocker.

Required checks are:

- account status is exactly `OPEN`;
- no transaction has `status: "pending"`;
- the account is a supported personal checking tier;
- if an early fee applies, the balance is at least that fee; otherwise the balance/current holdings must be exactly $0.

Closure tiers are:

| Account class | Early-fee window and fee | Notice period |
|---|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | under 30 days: $15 | 0 days |
| Blue Account, Green Account (checking) | under 60 days: $25 | 3 days |
| Evergreen Account | under 90 days: $50 | 7 days |
| Bluest Account | under 180 days: $100 | 14 days |

A fee is deducted from the account balance; there is no alternate payment method. Do not use another account to pay it. Observe the applicable notice period before closure if the environment supplies a notice mechanism; do not claim closure is complete before that requirement is met.

Once all direct-closure conditions and any notice requirement are satisfied, unlock and call `close_bank_account_7392` with the target account according to its declared signature. Confirm only the result actually returned by the tool.

## 6. Customer-facing completion

Summarize only completed operations, new account details returned by tools, funding status or deadline, blockers, and any needed next decision. Do not state that a product has been opened, funds have moved, or an account has closed until the relevant tool reports success.

## Scripts

Both scripts read one JSON object from standard input and write one JSON object to standard output. They use only standard-library Python and can be run without network access.

### `scripts/assess_opening.py`

Input schema:

```json
{
  "now": "current timestamp or date",
  "date_of_birth": "MM/DD/YYYY",
  "identity_verified": true,
  "checking_closed_for_cause_within_6_months": false,
  "accounts": [
    {"account_type": "checking", "status": "OPEN", "balance": "0.00", "date_opened": "MM/DD/YYYY"}
  ]
}
```

Output includes `checking_eligible`, `savings_eligible`, per-requirement booleans, and `blockers`. Use it after account lookup; provide a known Boolean for the closure-for-cause history rather than assuming false when history is unavailable.

Example invocation:

```sh
python3 scripts/assess_opening.py <<'JSON'
{"now":"2025-01-01","date_of_birth":"1990-01-01","identity_verified":true,"checking_closed_for_cause_within_6_months":false,"accounts":[]}
JSON
```

### `scripts/check_closure.py`

Input schema:

```json
{
  "now": "current timestamp or date",
  "account": {
    "account_id": "runtime account id",
    "account_type": "checking",
    "account_class": "Light Blue Account",
    "status": "OPEN",
    "balance": "0.00",
    "date_opened": "MM/DD/YYYY"
  },
  "transactions": [{"status": "posted"}]
}
```

Output contains `valid`, `fee`, `early_fee_applies`, `notice_days`, `checks`, and human-readable `blockers`. Validate the output against the live account and transaction-tool results immediately before a closure call.
