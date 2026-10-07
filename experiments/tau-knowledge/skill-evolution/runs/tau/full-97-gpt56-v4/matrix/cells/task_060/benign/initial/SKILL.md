---
name: close-checking-account-safely
description: Verify, prepare, and close a personal checking account while enforcing account-tier fees, notice periods, pending-transaction checks, and linked debit-card closure requirements. Use when a verified customer asks to close a checking account, including when they have multiple accounts and must retain a different one.
---

# Safe Checking-Account Closure

Use this Skill for a customer-requested closure of a personal checking account. Treat account closure and any request to open or compare another product as separate requests. Do not close an account merely because the customer says it is empty, and do not act on similarly named accounts without retrieving the customer's accounts and identifying the requested product.

## Required information and tool access

The normal banking tools named by the applicable procedures are:

- `get_all_user_accounts_by_user_id_3847(user_id)`
- `get_bank_account_transactions_9173(account_id)`
- `get_debit_cards_by_account_id_7823(account_id)`
- `close_debit_card_4721(card_id, reason)`
- `close_bank_account_7392(...)`

These are agent-discoverable tools. Unlock a named tool before calling it, and inspect its exposed parameter schema. Supply only documented/required parameters; do not invent fields or assume an unsupported scheduling capability.

For a closure action, verify the customer's identity under the normal verification procedure first. Confirm two of the available identity fields with the customer, retrieve the matching record, obtain the current time, and log the successful verification with `log_verification`. Do not treat a name alone, an account ID, or data visible in a prior tool result as the customer's confirmation of two identity fields.

## End-to-end procedure

1. **Confirm scope and preserve other accounts.**
   - Restate the requested account by product/class (for example, the customer's Green checking account), and explicitly preserve any account the customer says they want to keep.
   - A request to close an account is authorization to pursue closure of that specifically identified account, not authorization to open a savings account or alter a separate checking account. Defer product-selection discussion if the customer asks to handle closure first.

2. **Identify the account from bank records.**
   - After identity verification, retrieve all accounts using the verified `user_id`.
   - Select only an account whose type and class unambiguously match the requested checking product. If none, or more than one, matches, explain the ambiguity and ask the customer to identify the correct account. Never guess from balance, account ordering, or a partial product name.
   - Record from the returned account data: account ID, account type/class, status, balance, and date opened.

3. **Determine the tier, fee window, and notice period.**
   - Entry tier — Light Blue Account, Light Green Account, Green Fee-Free Account: $15 if closed within 30 days; 0 days' notice.
   - Mid tier — Blue Account, Green Account (checking): $25 if closed within 60 days; 3 days' notice.
   - Premium tier — Evergreen Account: $50 if closed within 90 days; 7 days' notice.
   - Elite tier — Bluest Account: $100 if closed within 180 days; 14 days' notice.
   - Calculate account age from the bank's current time and the account's `date_opened`. Use `scripts/closure_eligibility.py` for a repeatable advisory calculation when dates are available in supported formats.
   - If a notice period applies, do not represent the account as eligible for immediate closure until the required notice has elapsed. If the system exposes a supported way to record or schedule notice, use only that documented capability. Otherwise, explain the applicable notice period and earliest closure date; do not call the close tool prematurely.

4. **Verify account closure prerequisites.**
   - Account status must be `OPEN`.
   - Retrieve account transactions by account ID. There must be no transaction with status `pending` (case-insensitive comparison is appropriate when parsing textual tool output).
   - If no early-closure fee applies, current holdings/balance must be exactly $0.
   - If an early-closure fee applies, balance must be at least the applicable fee. The fee is deducted from this account; do not propose a card, transfer, cash payment, or another account as an alternative payment method.
   - If a prerequisite is not met, do not close the account. State the specific blocker and, when possible, the concrete condition that must be met.

5. **Close linked debit cards before the checking account.**
   - Retrieve all debit cards associated with the selected checking account, including historical cards.
   - Every associated card that is currently `ACTIVE` or `PENDING` must be addressed before closing the linked checking account. Closed historical cards need no further action.
   - For each card to be closed, enforce the debit-card closure requirements: the verified customer must own the card; no pending/processing card transactions; no pending refunds unless the customer gives the required written acknowledgement that the refund will credit to the linked checking account; and at least 14 days since `date_issued`.
   - The account-closing reason is `account_closing`. Lost, stolen, and fraud-suspected reasons bypass only the card-age requirement; do not substitute one of those reasons merely to accelerate an account closure.
   - If a card is ineligible, do not close it and do not close the checking account. Explain the blocker. If a card is eligible, call `close_debit_card_4721` using its discovered schema and the `account_closing` reason, then confirm success from the tool result before proceeding.
   - If the available runtime lacks a documented normal-banking method to inspect required card transactions or refunds, do not claim those checks passed and do not close the card or account. Explain that the required review cannot be completed through the available channel and follow the normal escalation process if applicable.

6. **Execute and confirm account closure.**
   - Only after notice, account, transaction, balance/fee, and debit-card requirements pass, unlock and call `close_bank_account_7392` with the exact schema exposed by the tool.
   - Treat an error, timeout, malformed result, or ambiguous result as a non-confirmation. Do not retry an operation whose outcome is reported as unknown.
   - On confirmed success, tell the customer the specifically identified account is closed. If an early fee applied, state the fee and that it was deducted from that account balance. Confirm that the retained account was not changed.

## Customer communication rules

- Be concise but state blockers plainly: pending account transactions, insufficient balance for an applicable fee, nonzero balance when no fee applies, non-OPEN status, unmet notice, or a linked debit-card issue.
- Do not claim the checking account is closed until the bank closure tool confirms it.
- Do not expose full card numbers or unrelated account details.
- If the customer still wants savings help after closure is complete or deferred, handle that as a new product-selection/opening flow and collect the requirements for that separate request.

## Eligibility helper

Run the helper by passing JSON on standard input:

```json
{
  "account_class": "Green Account (checking)",
  "date_opened": "2025-10-01",
  "current_time": "2025-11-14 03:40:00 EST",
  "balance": "0.00",
  "status": "OPEN",
  "pending_transaction_count": 0,
  "notice_given_at": "2025-11-11 03:40:00 EST"
}
```

It emits JSON containing the recognized tier, early-fee determination, earliest closure time if notice is known, and a list of deterministic account-level blockers. It is advisory only: retrieve authoritative account, transaction, card, and closure results from the banking tools. A result with `input_errors` means correct the supplied data rather than infer eligibility.
