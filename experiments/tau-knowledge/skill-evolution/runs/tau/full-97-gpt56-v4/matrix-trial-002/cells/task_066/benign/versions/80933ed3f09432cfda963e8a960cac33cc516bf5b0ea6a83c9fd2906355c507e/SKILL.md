---
name: personal-account-replacement-and-savings-opening
description: Safely handles a request to close an existing personal checking account, open a replacement checking account, and open/fund a personal savings account. Use when identity verification, account eligibility, closure fees/notice rules, account-class selection, and funds-transfer prerequisites must be checked before taking banking actions.
---

# Personal Account Replacement and Savings Opening

Use this Skill for an authenticated customer's combined account-closure and account-opening request. Do not infer an account selection merely from a request for “better” benefits, and do not close an account before all closure requirements are independently verified.

## Required inputs and evidence

Collect or retrieve at runtime:

- The customer's identity-verification fields. Verify two of date of birth, email, phone number, and address against the customer record, then log the verification with the current timestamp before account actions.
- The customer's `user_id` after identity is verified.
- All bank accounts for that user, including account ID, type, class, status, balance/current holdings, and opened date.
- Whether the account proposed for closure has pending transactions. Do not treat “basically empty” as a verified zero balance or as proof that no transaction is pending.
- The customer's exact selected replacement checking `account_class` and savings `account_class`. The official full name ending in `Account` is required.
- Explicit authorization and a source account if an immediate savings-opening deposit is to be transferred internally.

If the customer has supplied only a name or one verification datum, request enough additional identity data to verify two fields. A name lookup alone is not identity verification.

## Runtime workflow

### 1. Authenticate and identify

1. Look up the customer with the supplied name or email if needed.
2. Obtain two identity fields from the customer and compare them to the customer record.
3. Call `get_current_time`, then call `log_verification` using the complete returned customer record and current timestamp.
4. Do not perform closure, opening, or transfers unless the identity check succeeds.

### 2. Retrieve accounts and assess the requested closure

1. Unlock and use `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
2. Identify the exact existing checking account the customer wants closed. If more than one could match, ask the customer to identify the account; do not guess from a product name alone.
3. Determine pending-transaction status from available account/activity data. If the available tools/data cannot establish that there are no pending transactions, explain that closure cannot yet be completed and do not call the closure action.
4. Determine the early-closure fee based on account class and elapsed calendar days from the account opening date to the current date:

| Tier | Account classes | Fee if closed within | Notice period |
|---|---|---:|---:|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | 30 days: $15 | 0 days |
| Mid | Blue Account; Green Account (checking) | 60 days: $25 | 3 days |
| Premium | Evergreen Account | 90 days: $50 | 7 days |
| Elite | Bluest Account | 180 days: $100 | 14 days |

5. Validate all closure conditions:
   - account status is exactly `OPEN`;
   - no pending transactions exist;
   - if the account is still within its early-fee window, its balance is at least the fee, because the fee is deducted from that account; otherwise its balance is exactly $0;
   - account data is sufficient to determine the applicable fee and notice requirement.
6. Use `scripts/closure_check.py` for a deterministic check when the needed values are known. Treat `eligible: false` as a blocking condition.
7. If requirements are satisfied and the customer has authorized the closure, unlock `close_bank_account_7392` and call it with the documented account identifier required by the runtime. Respect any required notice period: do not represent a scheduled or notice-pending account as already closed.

If a balance must be moved before closure, only propose or execute an internal transfer after the customer specifies/authorizes a distinct destination account. The source and destination must be the same customer's active/open accounts, and the source must have sufficient funds. Unlock and call `transfer_funds_between_bank_accounts_7291` only after those checks. Never use a transfer as an alternative way to pay an early-closure fee; the fee must be deducted from the closing account.

### 3. Select and validate a replacement checking account

A vague request for a “better” checking account is not an account-class selection. Explain relevant documented tradeoffs and ask for the exact official replacement checking account class. Do not claim that a product is objectively best without stated customer priorities.

Before opening the selected checking account:

1. Confirm identity verification is logged.
2. From the retrieved accounts, count personal checking accounts and ensure opening another will not exceed four.
3. Confirm there has been no checking account closed for cause during the prior six months.
4. Confirm the customer is at least 18 from the verified birth date.
5. Confirm the selected class is an official full name ending in `Account`.

If every checking requirement is met and the customer selected the class, unlock and call `open_bank_account_4821` with `user_id`, `account_type: "checking"`, and the exact selected `account_class`.

### 4. Recommend and open savings without overstating yield

Do not promise an “absolute highest” APY without checking each documented balance requirement and all known applicable bonuses.

For a customer planning to keep $6,000, the documented facts support this comparison:

- Green Account (savings) has a 4.0% APY, $100 opening deposit, $500 ongoing minimum, and requires paperless statements.
- Silver Account has a 2.5% lower-tier APY below its $10,000 higher-rate threshold.
- Silver Plus has a 3.0% Tier 1 APY below its $15,000 Tier 2 threshold.
- Gold Account has a 5.5% APY but a $10,000 ongoing minimum; Platinum and higher documented products require still higher balances.
- A qualifying Evergreen checking plus Green savings pairing can add a linked-checking APY boost, but do not state its percentage unless it is available in current authoritative documentation. Multiple checking boosts do not stack; only the highest applicable one applies.
- Credit-card bonuses cannot be assumed. Retrieve credit-card accounts and apply only documented bonuses for cards the customer actually holds.

Thus, present Green savings as the highest documented sustainable base rate among the supplied products for a $6,000 balance, subject to the customer accepting paperless statements and any current product eligibility. Describe any unknown boost percentage as unknown rather than inventing it. Obtain the customer's exact selected savings class before opening.

Before opening savings, verify all of the following from runtime records:

1. Identity verification is complete.
2. At least one active Rho-Bank checking account exists. If closure would remove the only active checking account, open the approved replacement first or otherwise ensure an active checking account remains.
3. The customer has fewer than five personal savings accounts.
4. No account is in collections and no account has a negative balance.
5. An active checking account has been held for at least 14 days.
6. The opening requirements of the selected savings product can be met.

If all conditions are satisfied, unlock and call `open_bank_account_4821` with `account_type: "savings"` and the selected official `account_class`.

Then ask whether the customer wants the opening deposit transferred now. If yes, validate the authorized source account, destination account, amount, statuses, ownership, and sufficient funds; then use `transfer_funds_between_bank_accounts_7291`. If no, clearly state that the account must be funded within 30 days through an internal transfer or external deposit or it will be closed.

## Output and customer communication

On success, summarize only completed or confirmed actions: closed/scheduled closure status and fee, newly opened account types/classes and IDs when returned, whether the savings account was funded, transfer amount/source/destination, and any funding deadline. State material product conditions such as Green savings paperless enrollment and balance requirements.

When an action is blocked, name the missing or failed prerequisite and the concrete next step. Do not fabricate balances, opening dates, pending status, eligibility, bonus percentages, tool results, account IDs, or completed banking actions.

## Helper script

`scripts/closure_check.py` reads one JSON object from standard input and emits one JSON object to standard output. It has no banking side effects.

Input schema:

```text
{
  "account_class": string,
  "status": string,
  "balance": number|string,
  "has_pending_transactions": boolean,
  "opening_date": "YYYY-MM-DD"|"MM/DD/YYYY",
  "current_date": "YYYY-MM-DD"|"MM/DD/YYYY"
}
```

Output includes `eligible`, `fee`, `notice_days`, `days_open`, `in_early_fee_window`, and a list of `blocking_reasons`. Unsupported classes, invalid dates/balances, or missing pending-status evidence produce an ineligible result.

Runnable invocation pattern:

```sh
printf '%s' '<closure-check JSON matching the documented schema>' | python3 scripts/closure_check.py
```

Validate the emitted JSON before relying on it: it must contain a boolean `eligible`, a numeric-string `fee`, an integer `notice_days`, and an array `blocking_reasons`. The helper is advisory validation; only the declared banking tools perform account actions.
