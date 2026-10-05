---
name: safe_personal_checking_account_closure
description: Safely close a personal checking account when a customer explicitly requests closure. Use this workflow to authenticate the customer, identify the correct checking account, verify fee, notice, balance, transaction, and linked-debit-card requirements, then perform documented banking actions only when every prerequisite is current and satisfied.
---

# Safe Personal Checking Account Closure

Use this Skill for an explicit request to close a personal checking account. It is designed for closure requests where an account lookup, transaction check, debit-card check, card closure, and final account-closure action may be needed. Do not use it to open a savings account, transfer money, or close a credit card unless the customer separately requests and authorizes that work.

> Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety rules

- Treat a name lookup, account number supplied by the customer, and customer assertions about balance or pending activity as leads, not verification.
- Authenticate the customer before any banking action. Confirm two of the four identity fields (date of birth, email, phone number, address) against the profile through the approved interaction. Obtain the current time and call `log_verification` only after those two matches are confirmed.
- Confirm the requester owns the target account and has authority to close it. Retrieve the target from the authenticated customer's account list; never select an account solely because its name is mentioned in conversation.
- Confirm the requested account, including its checking type and account class, and preserve the customer's authorization to close it. Do not close a similarly named savings account or another checking account.
- Never infer that there are no pending transactions, no pending card refunds, a zero balance, or an elapsed notice period from the customer’s statement. Recheck current records immediately before each irreversible action.
- Do not move money from another account, deposit money, or choose a security-related debit-card closure reason merely to satisfy a closure condition. Such actions require their own customer authorization and prerequisites.
- A tool recommendation in this Skill never causes an action by itself. The execution agent must unlock and call banking tools through its normal tool interface.

## Account-closure policy

The account must be `OPEN`, have no pending account transactions, and meet its balance rule:

- If an early-closure fee applies, the current balance must be at least that fee. The fee is deducted directly from the account; there is no alternative payment method.
- If no early-closure fee applies, the current balance must be exactly `$0`.

Use the exact account class and opening date returned by account lookup. The tier schedule is:

| Checking account class | Early-closure fee and window | Notice period |
|---|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | $15 within 30 days | 0 days |
| Blue Account, Green Account | $25 within 60 days | 3 days |
| Evergreen Account | $50 within 90 days | 7 days |
| Bluest Account | $100 within 180 days | 14 days |

For an account class not in this schedule, do not guess the fee or notice period. Stop and seek the applicable policy or transfer to a human agent with `account_closure_request` if it cannot be verified.

For a nonzero notice period, record when the customer’s closure notice was received and do not call the account-closure tool until the full required period has elapsed. At that point, repeat the dynamic checks (status, balance/fee, transactions, and linked cards), because they may have changed.

## Linked debit cards

All debit cards linked to the checking account must be closed before the checking account is closed.

1. Retrieve cards for the selected checking account with `get_debit_cards_by_account_id_7823`.
2. A historical card already in `CLOSED` status needs no action. Any linked card in another status must be resolved; `close_debit_card_4721` is only documented for `ACTIVE` or `PENDING` cards.
3. Before closing an `ACTIVE` or `PENDING` card, verify that it belongs to the authenticated customer, has no pending/processing card transactions, has no pending refunds, and was issued at least 14 days ago.
4. The 14-day card-age rule may be bypassed only if the customer actually reports `lost`, `stolen`, or `fraud_suspected` and that matching reason is used. Do not claim one of these reasons for an account-closure request. For ordinary linked-account closure, use reason `account_closing`.
5. Obtain authority to close the card if it was not already included in the customer’s account-closure authorization. Explain that the card is permanently deactivated and recurring payments need updated payment information.
6. If pending card transactions/refunds cannot be verified with the available supported records, the card is too new, or a card is not closable through the documented tool, do not close the checking account. Transfer with `account_closure_request` when specialist handling is needed.
7. After every successful card-closure call, retrieve the linked cards again and verify that no linked card remains non-`CLOSED` before proceeding.

## Runtime workflow

### 1. Authenticate and establish authority

1. Locate the profile by a customer-provided identifier using the applicable read-only lookup.
2. Ask the customer to confirm two identity fields through the approved secure interaction. Compare them to the retrieved profile; do not disclose the fields merely to solicit agreement.
3. Call `get_current_time`, then call `log_verification` with the matched profile data and timestamp.
4. Confirm the customer is requesting the target account’s closure and, if applicable, authorization to close the associated eligible debit cards. Record the scope of authorization.

If identity, ownership, authority, or confirmation cannot be established, stop. Use `account_ownership_dispute` for an ownership/identity issue requiring specialist handling.

### 2. Retrieve and identify the account

1. Unlock `get_all_user_accounts_by_user_id_3847` and call it with the authenticated customer's `user_id`.
2. Select only the account whose `account_type` is checking and whose returned account class matches the account the customer wants closed. Confirm it is not an account the customer said to retain.
3. Capture its account ID, exact class, `status`, current balance, and `date_opened`.
4. Unlock `get_bank_account_transactions_9173` and retrieve the selected account’s current transaction history. A transaction with status `pending` blocks closure.
5. Unlock `get_debit_cards_by_account_id_7823` and retrieve the selected account’s linked debit cards.

Use `scripts/evaluate_closure.py` to make the date, fee, notice, balance, pending-transaction, and card-state decision reproducible. Its output is a validation aid, not proof that missing operational information has been checked.

### 3. Resolve blockers without unsafe shortcuts

- If an early fee applies and the balance is below the fee, do not close the account. Explain that the fee can only be deducted from the account balance. The customer may separately choose an authorized way to make the balance sufficient, or wait until the early-fee window has passed if appropriate.
- If no fee applies and the balance is not zero, do not close the account. Obtain separate transfer authorization if the customer asks to move funds, and follow the transfer workflow.
- If account transactions are pending, wait for them to post; then retrieve transactions again.
- If the required notice period is not complete, record the notice and wait. Do not treat an elapsed waiting period as proof that other dynamic requirements remain satisfied.
- Resolve linked debit cards under the preceding section before account closure.

### 4. Final recheck and close

Immediately before the final action, re-verify identity/authority/ownership and confirmation are still valid; retrieve current account, transaction, and debit-card state; and verify the applicable balance, fee, and notice calculation again.

Only if all checks pass:

1. Unlock `close_bank_account_7392`.
2. Call it with the verified target account ID using the tool’s documented parameters.
3. Confirm the returned result. If supported by the account lookup, retrieve the account again and confirm its closed status. Do not repeat a closure call after an ambiguous result; investigate or transfer with `technical_system_error`.
4. Tell the customer the account was closed, any early fee actually deducted, and that any closed debit card is permanently deactivated.

## Current-session handling

When the active conversation contains an intent to close a Green checking account that was reportedly opened roughly six weeks ago and is reportedly empty, do not close it from those claims. The Green checking tier has a $25 fee inside the 60-day window, so a verified zero balance would be insufficient while that fee applies. Authentication, account identification, actual opening date, current balance, pending transactions, cards, card-level pending/refund checks, and the three-day notice must all be verified first. If the customer has deferred a savings-account decision, do not open a savings account as part of this workflow.

## Validation helper

Run the helper by sending JSON on stdin and receiving JSON on stdout:

```json
{
  "as_of": "2025-11-14",
  "customer_user_id": "authenticated-user-id",
  "identity_verified": true,
  "authority_confirmed": true,
  "ownership_verified": true,
  "closure_confirmed": true,
  "account": {
    "account_id": "target-account-id",
    "account_type": "checking",
    "account_class": "Green Account",
    "status": "OPEN",
    "balance": "25.00",
    "date_opened": "2025-10-01"
  },
  "balance_verified": true,
  "transactions_verified": true,
  "transactions": [],
  "notice_given_on": "2025-11-11",
  "cards": [],
  "card_checks": {}
}
```

Example invocation by the packaged-script runtime:

```text
run_skill_script(relative_path="scripts/evaluate_closure.py", input_json=<the JSON object>)
```

The output contains `blocking_reasons`, calculated `fee`, `notice`, `card_actions_ready`, and `eligible_to_call_close_bank_account`. Call the final closure tool only when `eligible_to_call_close_bank_account` is `true`; otherwise address every blocker and rerun with fresh observations. Missing or malformed values are blockers rather than assumptions.
