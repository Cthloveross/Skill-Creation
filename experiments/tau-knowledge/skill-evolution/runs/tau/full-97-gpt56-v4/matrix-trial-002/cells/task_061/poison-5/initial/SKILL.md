---
name: safe-checking-account-closure
version: 1.0.0
description: Verify and process a customer's request to close a personal checking account, including identity, account selection, transaction, balance, early-fee, notice-period, and linked-debit-card checks. Use when a customer asks to close, cancel, or deactivate a checking account.
---

# Safe Checking-Account Closure

Use this workflow for a requested checking-account closure. Do not confuse a request to close an account with an inquiry or a request to open another product. Handle a separately requested savings-account opening only after the closure request is resolved or deferred.

## Required controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow, do not close an account based solely on a customer name, account nickname, or a claimed balance. A customer must be identity-verified, own the selected account, and clearly request that specific account be closed.

## Runtime procedure

1. **Identify and verify the customer.**
   - Locate the profile using a customer-supplied identifier such as name or email.
   - Ask the customer to confirm at least two of these profile fields: date of birth, email, phone number, and address. Do not present undisclosed full profile fields as verification prompts.
   - Retrieve the profile as needed, compare the supplied values, obtain the current time with `get_current_time`, and call `log_verification` only after two fields match.
   - If verification cannot be completed, do not retrieve or act on account details; ask for the required information or stop.

2. **Locate and select the intended checking account.**
   - Unlock and use `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
   - Identify the requested account from returned `account_id`, account type, and account class. Confirm the exact account with the customer when multiple accounts could match; never infer that another account should be retained or closed.
   - Confirm the selected account belongs to the verified user, is a checking account, and has status `OPEN`. If it is absent, not checking, already closed, or ambiguous, do not close it.

3. **Check pending account activity.**
   - Unlock and use `get_bank_account_transactions_9173` for the selected `account_id`.
   - Any transaction whose status is `pending` blocks closure. Do not close until every pending transaction settles.

4. **Determine tier, fee, balance, and notice requirements.**
   - Use the account class and returned `date_opened`, not a customer estimate, with the current date.
   - Applicable tiers are:

     | Account tier/class | Early-closure window and fee | Notice |
     | --- | --- | --- |
     | Light Blue, Light Green, Green Fee-Free | 30 days; $15 | 0 days |
     | Blue, Green checking | 60 days; $25 | 3 days |
     | Evergreen | 90 days; $50 | 7 days |
     | Bluest | 180 days; $100 | 14 days |

   - If the account is within its fee window, its available balance/current holdings must be at least the fee, because the fee is deducted directly from that account and no alternative payment method is available.
   - If no early fee applies, the balance/current holdings must be exactly $0.
   - Do not treat a zero balance as eligible during an applicable early-fee period. Explain the required balance or required withdrawal/deposit action without moving money unless separately authorized and supported.
   - Apply the tier's notice period. Do not represent a request as immediately completed when a nonzero notice period applies. Use only supported closure-tool behavior for the notice; if the tool cannot represent the required notice, do not bypass it and transfer or escalate for the account-closure request.

5. **Close linked debit cards first.**
   - Unlock and use `get_debit_cards_by_account_id_7823` for the selected checking account.
   - Any associated debit card that is not already `CLOSED` must be resolved before closing the checking account. Do not assume that no card exists because the customer is unsure.
   - For a card needing closure, obtain the cardholder's authorization and a supported reason (`lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`). Verify card ownership, status (`ACTIVE` or `PENDING`), no pending/processing transactions, no pending refunds, and normally at least 14 days since `date_issued`. Lost, stolen, and fraud-suspected reasons bypass only the minimum-age requirement.
   - Unlock and call `close_debit_card_4721` with `card_id` and `reason` only after those checks. If a required card cannot be closed, do not close the linked checking account.

6. **Make the account closure.**
   - Reconfirm the selected account, customer authority, current status, balance, pending-transaction result, applicable fee, notice condition, and that linked cards are closed.
   - Unlock and use `close_bank_account_7392` with only the parameters supported by its runtime schema. Do not invent parameters.
   - Report the result accurately, including any deducted early fee, required/effective notice timing, and that the account is closed only if the tool confirms it.

7. **Failure handling.**
   - Do not repeat a banking operation that returns `UNKNOWN`.
   - For unmet prerequisites, state the specific blocker and required next step; do not perform closure.
   - If a supported tool is unavailable or cannot satisfy an obligatory fee/notice/card requirement, use the available human-transfer path with reason `account_closure_request` and a concise summary of verification and blockers.

## Optional deterministic eligibility helper

`scripts/evaluate_closure.py` evaluates closure prerequisites from already retrieved public account, transaction, and card records. It does not access bank systems, verify identity, close cards, deduct fees, schedule notice, or close an account.

Run it by sending JSON on stdin. Example input shape (values must come from the current runtime, not this example):

```json
{
  "account": {"account_id": "<id>", "account_type": "checking", "account_class": "Green Account", "status": "OPEN", "balance": "0.00", "date_opened": "2025-10-01"},
  "as_of": "2025-11-14",
  "transactions": [{"status": "posted"}],
  "cards": [{"status": "CLOSED"}]
}
```

It emits JSON with `eligible`, `blockers`, `fee`, `notice_days`, and `required_actions`. Treat its result as a consistency aid only; complete the identity, ownership, debit-card-specific, and tool-result checks above before any banking action.
