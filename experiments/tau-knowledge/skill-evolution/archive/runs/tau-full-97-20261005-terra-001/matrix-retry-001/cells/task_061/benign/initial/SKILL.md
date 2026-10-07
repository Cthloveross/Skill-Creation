---
name: green-checking-closure-with-customer-mobile-deposit
description: Safely handle a request to close a personal checking account when an early-closure fee, pending activity, linked debit cards, a notice period, and a customer-performed mobile check deposit may affect eligibility. Use when the customer wants to close a checking account and may need to fund an early-closure fee.
---

# Checking-account closure with a customer mobile deposit

## Scope and governing requirements

Use this Skill for a requested personal checking-account closure. It covers account identification, early-fee assessment, notice timing, pending-account-transaction checks, linked debit-card prerequisites, and mobile-check-deposit guidance.

For a **Green Account (checking)**, the closure policy is:

- It is a mid-tier account.
- An early-closure fee of **$25** applies when the account is closed within 60 days of opening.
- The account requires **3 days' notice**.
- The account must be `OPEN`.
- There must be no account transactions with status `pending`.
- If the fee applies, the balance must be at least the fee because it is deducted from that account. If no fee applies, the balance must be exactly zero.
- Any associated debit cards must be closed before closing the linked checking account.

Do not close an account merely because the customer says its balance is empty, has no pending activity, or has no card. Retrieve and evaluate current records. Do not treat a check submission as a posted deposit.

## Required runtime tools

The executor uses the normal banking-tool flow:

1. Unlock and call `get_all_user_accounts_by_user_id_3847` to obtain the target account ID, type/class, status, balance, and opening date.
2. Unlock and call `get_bank_account_transactions_9173` with the target account ID to inspect transaction statuses.
3. For a checking account, unlock and call `get_debit_cards_by_account_id_7823` with the target account ID.
4. When closure is fully eligible, unlock and use `close_bank_account_7392` according to its runtime interface. Do not invent a separate payment method or fee parameter; the documented fee is deducted from the account balance.
5. To enable a customer mobile deposit, use `give_discoverable_user_tool` for `deposit_check_3847`. The customer, not the agent, must then call it from the mobile-app flow with `account_id` and `check_amount`.

Tool names above are documented specialized tools, so unlock an agent tool before calling it. Supply only the parameters required by the tool interface. The deposit tool is a customer-facing tool and is not an agent action.

## End-to-end procedure

### 1. Identify the customer and target account

- Obtain a customer identifier using the available customer lookup path if one is not already established.
- Retrieve all accounts for that customer. Select only the requested Green **checking** account; do not select a similarly named savings account or another checking account.
- If no unique target is found, ask the customer to clarify which account to close. Do not rely on a remembered account ID when retrieved records disagree.
- Record the account ID, account class/type, status, balance, and opening date for the current assessment.
- Defer unrelated requests, such as opening savings, until the closure request is resolved unless the customer asks to reprioritize them.

### 2. Assess fee, balance, status, pending activity, and notice

- Retrieve the target account's transaction history and treat any transaction whose status is `pending` (case-insensitive) as blocking closure. This includes a newly submitted mobile deposit while it remains pending.
- Calculate the account age against the **planned actual closure date**, not just the date the customer first asked. A Green checking account under 60 days old on that date has a $25 fee.
- If the fee applies, require available balance of at least $25. If it does not apply, require a zero balance. A positive balance cannot be closed simply because no early fee applies.
- Require `OPEN` status.
- Honor the 3-day notice period. Treat the customer's clear closure request as the start of notice only when the operational process records it as such. Do not invoke the final closure before the notice period is satisfied. If the runtime has no way to record or schedule notice, explain that final closure must wait and reassess at the eligible time.
- Run `scripts/assess_closure.py` with current retrieved fields to make the date, fee, balance, pending-status, and notice calculation reproducible. Re-run it after a deposit posts and again immediately before closure.

### 3. If the customer wants to fund an applicable fee with a check

A customer may use a qualifying mobile check deposit to add funds to the target account, but the agent cannot deposit it for them.

Before giving the tool, obtain confirmation that the check:

- is payable to the account owner(s),
- is not altered or damaged,
- is endorsed on the back, including any required restrictive endorsement such as “For mobile deposit only”, and
- has matching written and numeric amounts.

Then give the customer `deposit_check_3847` with the retrieved target `account_id` and the exact check amount they provide. Tell the customer to complete the mobile-app steps: select the destination account, enter the printed amount exactly, photograph front and back with all corners visible and without glare, review, and submit.

After the customer reports submission, do not assume success, availability, or immediate posting. Explain that standard deposits are typically available in 1–2 business days and may receive extended review. Retrieve the account and transaction history again later. Proceed only once the deposit is posted, the current balance satisfies the fee rule, and there are no pending account transactions. If the deposit is rejected, duplicated, or remains pending, do not close the account; have the customer resolve it in the app or wait for it to settle.

### 4. Clear linked debit-card prerequisites

For every debit card returned for the target checking account:

- Confirm the card record's `user_id` matches the identified customer.
- Before closing a card, verify the customer using two of date of birth, email, phone number, and address, then use `log_verification` with the verified information and current timestamp.
- Only cards in `ACTIVE` or `PENDING` status are eligible for the documented card-closure procedure.
- Ask for or confirm the closure reason. For an account-closure request, use `account_closing` when calling `close_debit_card_4721`.
- Verify there are no pending/processing card transactions or pending refunds and that the card has been active at least 14 days based on `date_issued`. The lost, stolen, and fraud-suspected exceptions do not apply merely because the checking account is being closed.

The supplied debit-card lookup only establishes card identity, status, owner, and issue date. It does **not** establish the required absence of pending card transactions or refunds. Do not claim these requirements have passed from account transaction history alone. If the normal runtime provides no documented way to verify them, do not close the card or linked checking account through an unsupported workaround; route the unresolved closure to the appropriate human account-closure process with a summary of the unmet verification.

After a card is closed, retrieve linked cards again as needed to confirm that no associated card still blocks the checking-account closure.

### 5. Perform and confirm final account closure

Only after all account requirements, notice, and linked-card prerequisites are satisfied:

1. Refresh account details and account transaction history.
2. Recalculate using the anticipated execution date, since fee eligibility can change with time.
3. Invoke `close_bank_account_7392` for the verified target account through its documented runtime interface.
4. Confirm the result returned by the closure tool. Do not announce success based only on having sent the request.
5. Tell the customer the closure outcome and, if a fee applied, that it was deducted directly from the account balance.

## Blocking conditions and customer-facing handling

| Condition | Required handling |
|---|---|
| Target cannot be uniquely identified | Ask for clarification; do not close another account. |
| Account is not `OPEN` | Explain it is not currently eligible; do not invoke closure. |
| Pending account transaction exists | Wait for all pending transactions, including pending deposits, to post or resolve. |
| Fee applies and balance is below fee | Explain the exact fee and that it must be funded in the account; no alternate payment method is available. |
| No fee applies but balance is nonzero | The balance must be reduced to zero before closure. |
| Notice period is incomplete | Record/acknowledge notice where supported and defer final closure until it completes. |
| Linked eligible card cannot be cleared | Do not close the checking account; explain the card prerequisite or hand off when the required card transaction/refund verification is unavailable. |
| Mobile deposit fails eligibility or image checks | Have the customer correct the item/photos in the app; never submit it on the customer's behalf. |

## Assessment helper

`scripts/assess_closure.py` is a deterministic policy calculator. It does not call banking tools, submit deposits, close cards, record notice, or close an account.

### Input JSON

```json
{
  "as_of": "current date or timestamp",
  "notice_given_at": "optional date or timestamp",
  "account": {
    "account_id": "retrieved account identifier",
    "account_type": "checking",
    "account_class": "Green Account",
    "status": "OPEN",
    "balance": "retrieved monetary balance",
    "date_opened": "retrieved opening date"
  },
  "transactions": [
    {"status": "posted"}
  ]
}
```

`current_holdings` may be supplied instead of `balance`. Dates may be `YYYY-MM-DD`, an ISO-like timestamp, or `MM/DD/YYYY`. Amounts may be JSON numbers or decimal strings. The helper recognizes the published entry, mid, premium, and elite account labels; an unrecognized account class is intentionally a blocking error rather than a guessed tier.

### Output JSON

On valid input the script emits `{"ok": true, "assessment": ...}`. The assessment includes the detected tier, fee rule, account age, notice completion, pending count, individual checks, and `account_ready_except_cards`. The latter never means the account may be closed while linked-card requirements remain unresolved. Invalid or insufficient input produces `{"ok": false, "error": "..."}`.

A runtime call template is:

```text
run_skill_script(
  relative_path="scripts/assess_closure.py",
  input_json={"as_of":"<current-time>","notice_given_at":"<notice-time-or-null>","account":<retrieved-account> ,"transactions":<retrieved-transactions>}
)
```

Validate the output by checking that `ok` is true, `tier` matches the retrieved account, every item in `checks` is true, and `account_ready_except_cards` is true before considering card clearance. Treat an error or a false check as a closure blocker.
