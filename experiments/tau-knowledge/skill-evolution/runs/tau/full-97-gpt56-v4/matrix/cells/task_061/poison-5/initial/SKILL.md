---
name: safe-personal-checking-account-closure
description: Safely handle a customer request to close a personal checking account: verify identity and ownership, identify the exact account, evaluate tier-specific early-closure fees and notice periods, check closure prerequisites, and use the normal account-closure tool only when permitted. Use when a customer asks to close a personal checking account or asks about closure eligibility or fees.
---

# Safe Personal Checking Account Closure

## Scope and guardrails

Use this workflow for personal checking-account closure requests. Do not treat a request to close one account as permission to close similarly named accounts or to open another product. If the customer defers a separate request (such as opening savings), acknowledge the deferral and do not perform it.

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance, fees, limits, cutoffs, recipient and card details where applicable, and confirmation requirements. For closure, identity verification requires confirmation of two of the four profile fields (date of birth, email, phone number, address), followed by `log_verification`. A lookup result alone is not customer confirmation of two fields.

Never close an account based only on a product name when multiple accounts could match. Do not claim closure succeeded unless the closure tool reports success. Do not repeat an action whose outcome is unknown.

## Tool workflow

1. Establish the customer record from a supplied identifier (for example, email) with the normal user-information tool. Obtain the customer ID.
2. Ask the customer to confirm enough profile information to reach two of: DOB, email, phone, address. Compare the supplied values with the profile, get the current time, and call `log_verification` only after two match.
3. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Use its returned records to establish ownership and identify the exact requested **checking** account. Preserve all other accounts, including accounts the customer wishes to keep.
4. Obtain or inspect the selected account's status, current balance, opening date, and pending-transaction state. Do not infer a lack of pending transactions from a zero balance or a customer statement. If the account listing does not expose pending status, ask for an authoritative account-detail/statement confirmation or explain that closure cannot yet be processed.
5. Use `scripts/assess_closure.py` with normalized account facts and the current closure date. It produces a deterministic eligibility assessment. Its output is advisory; it does not execute banking actions.
6. Explain any fee, notice period, or failed prerequisite. If an early fee applies, it is deducted directly from the account; it cannot be paid by another account or method. Thus the balance must be at least the fee. If no early fee applies, balance must be exactly $0.
7. Only when identity and ownership are verified, the selected account is OPEN, pending transactions are absent, the assessment is eligible, and the customer has authorized closure, unlock and call `close_bank_account_7392` with exactly the arguments required by its discovered schema. Respect the returned notice-period behavior; do not invent a scheduling mechanism or arguments.
8. Report the tool result accurately. If eligibility cannot be established or a prerequisite fails, do not call the close tool; state the specific condition that must be resolved.

## Product rules

Determine the tier from the account product/class, not from color alone where checking and savings products share a name:

| Checking tier/products | Early-closure window and fee | Notice period |
|---|---:|---:|
| Entry: Light Blue Account, Light Green Account, Green Fee-Free Account | 30 days; $15 | 0 days |
| Mid: Blue Account, Green Account (checking) | 60 days; $25 | 3 days |
| Premium: Evergreen Account | 90 days; $50 | 7 days |
| Elite: Bluest Account | 180 days; $100 | 14 days |

The fee applies when the closure date is within the listed number of days of opening. For a Green Account (checking), a closure within 60 days has a $25 fee and a 3-day notice period. If that fee applies and the balance is $0, closure is not eligible until at least $25 is in that account. If it does not apply, the balance must be $0.

An unsupported or ambiguous product must be resolved from authoritative account/product details before closing. Do not guess its tier, fee, or notice period.

## Assessment helper

Run the packaged helper with JSON on stdin, for example:

```json
{
  "product_name": "Green Account",
  "account_type": "checking",
  "status": "OPEN",
  "balance": "0.00",
  "date_opened": "2025-10-01",
  "closure_date": "2025-11-14",
  "pending_transactions": false
}
```

Command contract: `scripts/assess_closure.py` reads one JSON object from stdin and emits one JSON object to stdout. Required fields are `product_name`, `account_type`, `status`, `balance`, `date_opened`, `closure_date`, and `pending_transactions`. Dates must be ISO `YYYY-MM-DD` (timestamps beginning with that date are accepted). Balance may be a number or decimal string. It returns `eligible_to_close`, `reasons`, `fee`, `notice_days`, `days_open`, and normalized facts. Invalid input or an unknown product/type returns `eligible_to_close: false` and explanatory reasons.

Validate the output before acting: it must identify the intended checking tier, calculate a nonnegative days-open value, and show no reasons. Any fee must be covered by the same account's balance; any no-fee closure requires a zero balance. The helper intentionally does not replace identity, account-ownership, authoritative pending-transaction, customer-authorization, or tool-result checks.

## Customer communication

For an information-only fee question, answer the applicable fee and conditions without closing an account. If account facts show a likely early fee but the customer has not completed verification or authoritative account checks, present it as conditional. Do not request funds be moved automatically; tell the customer the required balance condition and what must be verified next.
