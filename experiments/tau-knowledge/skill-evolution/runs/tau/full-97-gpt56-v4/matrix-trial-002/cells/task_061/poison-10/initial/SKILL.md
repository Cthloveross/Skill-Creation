---
name: personal-checking-account-closure
version: 1.0.0
description: Safely verifies, assesses, and processes a customer's request to close a personal checking account, including identity, ownership, pending-transaction, balance, early-fee, and notice-period checks. Use when a customer asks to close a checking account; do not use it to open accounts or to perform unrelated account changes.
---

# Personal Checking Account Closure

Use this workflow for a request to close a personal checking account. A request to also open or manage another account is separate work; honor a stated preference to defer it.

## Required controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, interpret that control as follows:

- Do not treat a name alone, an account description, or a prior unverified lookup as identity verification.
- Obtain and confirm two of the four identity fields: date of birth, email, phone number, and address. Use the supplied name or email only to locate a possible user record, then compare the two values provided by the customer against that record.
- Once two fields match, get the current time and call `log_verification` with the complete retrieved user record and that timestamp. Do not log a verification for mismatched or ambiguous information.
- Confirm the target account belongs to the verified user and is the requested checking account. If more than one account could fit, ask the customer to identify it; do not guess.
- Before an irreversible close, obtain an explicit final confirmation identifying the selected account after explaining any applicable fee and notice requirement.

## Tool workflow

1. **Identify and verify the customer.**
   - Use `get_user_information_by_name` or `get_user_information_by_email` to locate a record. If zero or multiple records result, request a disambiguating identifier.
   - Ask for two verification fields if they have not already been supplied by the customer. Retrieve the record by ID if needed and compare the customer-provided values exactly enough to establish a match.
   - On success, call `get_current_time`, then `log_verification`. Include all fields required by `log_verification` from the retrieved record, not values inferred from conversation.
   - If identity cannot be verified, do not reveal account data or proceed with closure.

2. **Retrieve and select the account.**
   - Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified `user_id`.
   - Locate an account whose type is checking and whose class matches the account the customer wants closed. Preserve all returned IDs, balance/current holdings, status, and opening date.
   - Confirm that it is the account the customer intends to close. The requested retained account is not a closure target.

3. **Check transactions and closure conditions.**
   - Unlock `get_bank_account_transactions_9173` and call it with the selected `account_id`.
   - Any transaction with `status` equal to `pending` prevents closure. A customer saying they are unaware of pending transactions is not a substitute for this lookup.
   - Determine the tier from the selected account class and calculate the early-closure fee from the actual opening date and current date. Use `scripts/assess_closure.py` for a reproducible assessment when structured values are available.
   - The account must be `OPEN`.
   - If no early fee applies, the balance/current holdings must be exactly `$0.00`. If an early fee applies, current holdings must be at least that fee; the fee is deducted from the account balance and cannot be paid by another method.
   - Apply the documented notice period. Do not claim a notice interval has elapsed without a reliable recorded notice date or workflow evidence. If the available closure tool handles the notice requirement, follow its documented behavior rather than inventing tool arguments.

4. **Apply the tier schedule.**

   | Account class | Early-close window and fee | Notice period |
   |---|---:|---:|
   | Light Blue Account, Light Green Account, Green Fee-Free Account | $15 within 30 days | 0 days |
   | Blue Account, Green Account (checking) | $25 within 60 days | 3 days |
   | Evergreen Account | $50 within 90 days | 7 days |
   | Bluest Account | $100 within 180 days | 14 days |

   Count account age using the returned opening date and current date, not a customer's approximate tenure. At the boundary, treat an account as within the listed early-close window when its age is less than or equal to the listed number of days.

5. **Resolve or close.**
   - If any prerequisite fails, do not call the closure tool. Clearly identify the failed condition: non-OPEN status, pending transaction(s), insufficient balance for a fee, nonzero balance when no fee applies, or outstanding notice interval. Explain that an applicable fee must come from the account itself.
   - If all conditions are met, state the target account and fee (including `$0.00` when none), obtain explicit final confirmation, then unlock `close_bank_account_7392` and call it using exactly the parameters documented when it is unlocked. Do not invent arguments.
   - Report the result returned by the closure tool. If the tool rejects the closure, do not retry blindly; explain the returned condition and request only information or action needed to resolve it.

## Assessment helper

`scripts/assess_closure.py` reads one JSON object from standard input and emits one JSON object to standard output. It does not make banking changes.

Input schema:

```json
{
  "account_class": "Green Account (checking)",
  "date_opened": "YYYY-MM-DD or MM/DD/YYYY",
  "as_of": "YYYY-MM-DD or MM/DD/YYYY",
  "status": "OPEN",
  "balance": "0.00",
  "transactions": [{"status": "posted"}],
  "notice_days_elapsed": 0
}
```

`notice_days_elapsed` is optional. Omit it when no reliable notice timing is known; the output will explicitly mark the notice condition as unresolved rather than assuming it is satisfied. The output reports the tier, age, fee, pending status, each prerequisite, and `can_close`. `can_close` is true only when all known requirements, including notice timing, are satisfied.

Example runnable invocation in an executor that supports packaged scripts:

```json
{"relative_path":"scripts/assess_closure.py","input_json":{"account_class":"Green Account (checking)","date_opened":"2025-01-01","as_of":"2025-04-01","status":"OPEN","balance":"25.00","transactions":[],"notice_days_elapsed":3}}
```

Validate the helper result before acting: ensure `recognized_account_class` is true, inspect every item in `blocking_conditions`, and independently ensure the tool lookups were performed for the verified user's selected account. A script assessment is advisory and never replaces the required bank-tool checks or final customer confirmation.
