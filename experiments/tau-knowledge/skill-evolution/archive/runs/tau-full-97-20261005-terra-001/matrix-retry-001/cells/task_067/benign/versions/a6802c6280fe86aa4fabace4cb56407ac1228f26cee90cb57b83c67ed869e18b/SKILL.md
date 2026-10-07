---
name: personal-checking-account-switch
version: 1.1.0
description: Execute an authorized switch from an existing personal checking account to a requested replacement checking account. Use when linked debit cards must be closed before the old account, the old account must close before the replacement opens, and unrelated savings or credit products are deferred.
---

# Personal Checking Account Switch

Use this Skill to complete, rather than merely describe, an authorized checking-account switch. It is for a customer who has selected an existing checking account to close and has confirmed the exact replacement checking account class.

## Scope

- Close only the identified old checking account and debit card(s) linked to it.
- Open only the explicitly confirmed replacement checking account.
- Do not open a savings account, a credit product, or order a new debit card unless separately authorized.
- Do not transfer funds unless separately requested and authorized.
- Do not claim completion until each banking action has returned successfully.

A request to close the linked debit card as part of closing the specified checking account authorizes the necessary permanent closure of each eligible linked debit card for that account. If the authorization instead identifies only one card while multiple current cards exist, obtain clarification before closing cards not covered by that authorization.

## Required execution order

Perform these steps in order. Use the runtime schemas returned when unlocking discoverable tools; do not add undocumented action parameters.

1. **Verify identity.** Confirm at least two of date of birth, email, phone number, and address without disclosing the values first. Obtain the current timestamp with `get_current_time` and create a successful `log_verification` record. A name lookup or previous account lookup alone is not verification.
2. **Retrieve accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)`. Identify the customer-selected old checking account by its returned account ID and class. Record its status, current holdings/balance, opening date, and all checking accounts relevant to the replacement-opening eligibility check.
3. **Retrieve both required closure records.** Unlock and successfully call both:
   - `get_debit_cards_by_account_id_7823(account_id)` for the selected old checking account; and
   - `get_bank_account_transactions_9173(account_id)` for that same account.

   Do this even when the customer believes there are no cards or no transactions. A successful empty response is valid evidence that no linked card or transaction was returned.
4. **Check closure eligibility.** Evaluate the old account, all returned linked cards, and transaction history as described below.
5. **Close linked cards first.** For every returned, non-closed card that meets all card requirements, unlock and call `close_debit_card_4721` with its `card_id` and `reason: "account_closing"`. Confirm each result succeeds before continuing. If any required linked card cannot be closed, stop: do not close the account or open its replacement.
6. **Close the old account.** Once every required linked card is successfully closed and the account checks pass, unlock and call `close_bank_account_7392` using the selected old account's `account_id`. Confirm success.
7. **Reconcile replacement-opening eligibility.** Re-read or reconcile the account records after the old-account close so the checking count reflects the completed closure. Check all opening requirements below.
8. **Open the requested replacement.** Only after the old account closure succeeds, unlock and call `open_bank_account_4821` with the verified `user_id` and the exact, customer-confirmed full `account_class`. Confirm the result succeeds.
9. **Respond accurately.** Confirm the closed card(s), old account, and newly opened checking account only if their tool calls succeeded. State that deferred products were not opened.

## Old-account closure checks

The selected account must be a personal checking account with status `OPEN`, no pending transactions, and an eligible balance.

### Transaction and refund check

Inspect the successful `get_bank_account_transactions_9173` result before any closure action. Any transaction with status `pending` or `processing` blocks account closure. Treat a pending refund reflected in the available account activity as a blocker as well. Do not infer that no pending activity exists without making the transaction-history call.

### Balance, tier, fee, and notice

Use the exact account class and `date_opened` with the current date:

| Tier | Classes | Early closure fee | Window | Notice |
|---|---|---:|---:|---:|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 | first 30 days | 0 days |
| Mid | Blue Account; Green Account (checking) | $25 | first 60 days | 3 days |
| Premium | Evergreen Account | $50 | first 90 days | 7 days |
| Elite | Bluest Account | $100 | first 180 days | 14 days |

- If the account is inside its fee window, its balance/current holdings must be at least the applicable fee; the fee is deducted from the account and cannot be paid another way.
- If it is outside the fee window, its balance/current holdings must be exactly zero.
- For a nonzero notice period, proceed only if records establish that the required notice was completed.
- An account class not in this policy table requires policy clarification; do not guess a fee or notice period.

## Linked debit-card checks

For each card returned by `get_debit_cards_by_account_id_7823` that is not already `CLOSED`, verify all of the following before calling the closure tool:

- the customer is verified;
- the card's `user_id` matches the verified customer;
- its status is `ACTIVE` or `PENDING`;
- the card was issued at least 14 calendar days ago for the `account_closing` reason;
- the transaction-history review shows no pending or processing activity or pending refund that blocks closure; and
- the customer authorized permanent closure as part of this account closure.

A historical `CLOSED` card needs no action. A `FROZEN` or other ineligible non-closed card blocks the account switch until resolved. The lost/stolen/fraud minimum-age exception does not apply to `account_closing`.

## Replacement personal-checking eligibility

Immediately before opening the replacement, establish:

1. The customer remains verified.
2. The customer is at least 18 years old, calculated from the profile date of birth and current date.
3. Opening will not result in more than four personal checking accounts. Count the old account as closed after its successful closure; do not count savings, credit, business, or closed checking accounts as open personal checking accounts.
4. The account history contains no personal checking account closed for cause during the prior six months. If returned records include a closed checking account in that period, inspect its returned closure reason/status; do not assume it was not for cause. If the retrieved account history establishes no such closed checking account, this requirement passes.
5. The selected class is the exact full official personal-checking name confirmed by the customer and ends in `Account`.

If an eligibility fact is genuinely absent from available records, obtain the required internal evidence or explain the specific blocker. Do not substitute a different account class.

## Tool handling

The required specialized banking tools are discoverable. Unlock them before use and use their runtime-returned parameter schemas. The documented calls are:

- `get_all_user_accounts_by_user_id_3847(user_id)`
- `get_debit_cards_by_account_id_7823(account_id)`
- `get_bank_account_transactions_9173(account_id)`
- `close_debit_card_4721(card_id, reason)`
- `close_bank_account_7392(account_id)`
- `open_bank_account_4821(user_id, account_class)`

Do not stop after an informational lookup when all documented checks pass and the customer has already authorized the switch. Conversely, a failed retrieval or failed action is not a successful check or completion; explain the failure and do not advance to dependent actions.

## Optional local evaluator

`scripts/evaluate_account_switch.py` is a side-effect-free aid for normalizing visible closure and opening checks. It does not verify identity, unlock tools, close accounts, or open accounts. It reads one JSON object on stdin and emits one JSON object on stdout:

```text
python scripts/evaluate_account_switch.py < switch_case.json
```

Input schema:

```json
{
  "current_time": "2025-01-31T12:00:00-05:00",
  "user": {"user_id": "string", "verified": true, "date_of_birth": "MM/DD/YYYY"},
  "old_account": {
    "account_id": "string",
    "account_class": "Light Blue Account",
    "status": "OPEN",
    "current_holdings": "0.00",
    "date_opened": "MM/DD/YYYY"
  },
  "transactions": [{"status": "posted"}],
  "cards": [{"card_id": "string", "user_id": "string", "status": "ACTIVE", "date_issued": "MM/DD/YYYY"}],
  "card_closure_authorized": true,
  "notice_completed": true,
  "opening": {
    "requested_account_class": "Purple Account",
    "open_personal_checking_count_after_old_close": 0,
    "closed_for_cause_in_last_6_months": false
  }
}
```

The result reports blockers and the eligible card IDs. Treat missing source data as a reason to retrieve or clarify it, not as evidence that an action completed.
