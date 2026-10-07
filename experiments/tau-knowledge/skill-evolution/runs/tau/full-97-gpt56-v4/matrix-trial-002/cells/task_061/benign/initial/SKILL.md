---
name: close-personal-checking-account
version: 1.0.0
description: Safely handles a verified customer's request to close a personal checking account, including identity verification, account/card/transaction eligibility checks, Green Account mid-tier fee and notice rules, and use of the normal banking closure tools. Use when a customer asks to close, cancel, or deactivate a checking account.
---

# Close a Personal Checking Account

Use this Skill for a customer-directed closure of a personal checking account. Treat account closure and debit-card closure as irreversible actions. Do not close a different account merely because it has a similar product name, and do not open or recommend a savings account unless the customer asks to resume that separate request.

## Inputs to collect

Obtain from the conversation:

- A customer identifier (name or email).
- The intended checking product/account, stated clearly enough to distinguish it from the customer's other accounts.
- Two independently confirmed identity fields out of date of birth, email, phone number, and address.
- The customer's affirmative closure request. A request to close the checking account covers the required closure of cards linked to that account; explain that linked cards must be permanently closed first.

A name is useful for lookup but is **not** one of the two required verification factors.

## Required banking-tool workflow

### 1. Identify and verify the customer

1. Look up the customer by the supplied name or email using the corresponding normal lookup tool.
2. If zero or multiple plausible customer records result, ask for a more specific identifier. Do not guess.
3. Compare two user-provided verification factors against the retrieved record. Do not count information merely retrieved from the bank record as customer confirmation.
4. After two factors match, call `get_current_time` and then `log_verification` with the complete retrieved user record and that timestamp. Do not take closure actions before this verification audit is logged.
5. If a factor does not match, do not disclose further account information or proceed. Ask for a correct factor or follow the applicable secure-support process.

### 2. Locate only the requested account

Unlock and call `get_all_user_accounts_by_user_id_3847` using the verified `user_id`.

From its results, select an account only when all of the following are true:

- it is a checking account;
- its product/class matches the customer's requested product; and
- it is not another account the customer asked to retain.

If the result does not uniquely identify the requested account, ask the customer to disambiguate with non-sensitive account details. Record the target's account ID, class, status, balance/current holdings, and opening date. Do not act on a savings account or the retained checking account.

### 3. Determine the tier, fee, and notice requirements

Use the account class and opening date with the current date. For **Green Account (checking)**:

- It is a mid-tier checking account.
- A $25 early-closure fee applies when closure is within 60 days after opening.
- Its notice period is 3 days.

Calculate tenure using calendar dates and preserve the result used for the decision. If closure is within the 60-day window, the current holdings must be at least $25; the fee is deducted directly from that account, with no alternative payment method. If no early fee applies, current holdings must be exactly $0.

Honor the three-day notice period. If a supported closure tool offers an explicit scheduling/notice mechanism, use only the parameters documented by that tool and schedule no earlier than the eligible date. If the normal workflow has no supported way to record or schedule notice, explain the earliest closure date and do not represent the account as closed before that date. Never invent tool arguments or bypass the notice period.

For a different personal checking product, apply the documented tier rules instead:

| Tier | Products | Early fee/window | Notice |
|---|---|---:|---:|
| Entry | Light Blue, Light Green, Green Fee-Free | $15 / 30 days | 0 days |
| Mid | Blue, Green Account (checking) | $25 / 60 days | 3 days |
| Premium | Evergreen | $50 / 90 days | 7 days |
| Elite | Bluest | $100 / 180 days | 14 days |

### 4. Check account activity and linked debit cards

Unlock and call `get_bank_account_transactions_9173` for the target account. Any transaction whose status is `pending` blocks closure, regardless of type. Tell the customer that the transactions must settle; do not close the account.

Unlock and call `get_debit_cards_by_account_id_7823` for the target checking account. All cards associated with a checking account must be closed before the account can be closed, including a card history entry that is still `ACTIVE` or `PENDING`.

For each card that needs closure:

1. Confirm its `user_id` is the verified customer's ID and its status is `ACTIVE` or `PENDING`.
2. Verify that it has no pending/processing card transactions and no pending refunds using the supported normal banking data available in the live environment. The account transaction list may help identify pending account activity, but do not claim it proves card-specific refund status when it does not identify the card/refund.
3. Check that the card has been active at least 14 days from `date_issued`. The lost, stolen, and fraud-suspected reasons bypass only this age rule; `account_closing` does not.
4. If any card prerequisite is not met, explain the blocker and earliest eligible date where applicable. Do not close the account.
5. When eligible, unlock `close_debit_card_4721` and call it with the documented parameters, including that card's ID and reason `account_closing`.
6. Confirm the result, then re-fetch debit cards if necessary to ensure no linked card remains active or pending.

If the live environment lacks a supported way to check a mandatory card prerequisite, do not fabricate a check or close the card. Escalate using `transfer_to_human_agents` with reason `account_closure_request` and a concise summary of the verified customer, intended account, and missing prerequisite check.

### 5. Revalidate immediately before account closure

Immediately before the final account action, re-read the target account and its transactions/cards as needed. Confirm all of these are still true:

- Account status is `OPEN`.
- No account transaction is pending.
- No linked debit card remains `ACTIVE` or `PENDING`.
- The applicable balance rule is met ($0 if no early fee; at least the fee if one applies).
- All required notice has elapsed or the tool has validly scheduled it.

If a recheck reveals a changed balance, pending activity, changed status, or an unclosed card, stop and explain the new blocker.

### 6. Close and report accurately

Once every prerequisite is satisfied, unlock `close_bank_account_7392` and invoke it using the target account ID and only the parameter schema exposed by the normal tool. Do not make a separate payment for an early closure fee; it is deducted from the account balance by the closure process.

Report only what the tool result confirms:

- the intended account/product was closed or scheduled for closure;
- any applicable early-closure fee and its amount; and
- that associated debit cards were permanently closed, if applicable.

If the close operation fails or returns an unclear/unknown result, do not retry blindly and do not tell the customer it succeeded. Explain that completion could not be confirmed and transfer with reason `technical_system_error` (or `account_closure_request` when the issue is an unmet closure condition).

## Customer communication

Be concise and transparent. If closure is blocked, name the specific condition—pending transaction, linked card, insufficient fee balance, nonzero balance, insufficient card age, or remaining notice period—and the next action or earliest date. If the customer deferred savings, acknowledge that it can be handled later without reopening the topic during the closure workflow.

## Completion checklist

Before claiming success, ensure the execution record shows: two-factor verification plus `log_verification`; the correct account lookup; transaction and debit-card checks; closure of every required eligible linked card; final revalidation; and a successful/scheduled `close_bank_account_7392` result. If any item is absent, do not claim the checking account is closed.
