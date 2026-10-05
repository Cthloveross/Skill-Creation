---
name: personal-checking-account-switch
version: 1.0.0
description: Safely switch a verified customer from an existing personal checking account to a requested new personal checking account. Use when closure must occur before opening, especially when linked debit cards must be closed first. It performs the documented eligibility, transaction, balance, card-age, fee, notice, and account-opening checks without opening deferred products.
---

# Personal Checking Account Switch

Use this Skill for a customer who wants to close an existing personal checking account and then open a replacement checking account. It is designed for cases where the old account's linked debit card(s) must be permanently closed before the account can be closed.

## Scope and ordering

1. Verify the customer's identity before any account or card action.
2. Close every closable linked debit card required for the old checking account.
3. Close the old checking account only after all required debit cards are closed.
4. Open the requested new checking account only after the old-account closure succeeds.
5. Do **not** open a savings account, transfer money, or order a replacement debit card unless the customer separately authorizes that product or action.

This order matters. Never close an account while a linked debit card that must be closed remains active or pending, and do not treat a requested new account as already open.

## Identity and authorization

- Obtain confirmation of at least two of the four identity fields: date of birth, email, phone number, and address. Do not disclose the values while asking.
- Retrieve the customer profile as needed, call `get_current_time`, then call `log_verification` with the customer record and current timestamp after the two-field verification succeeds.
- A profile lookup, name, account number, or prior clarification alone is not identity verification.
- Confirm the requested old account when more than one candidate exists. Confirm the replacement account class using its full official name.
- For debit-card closure, obtain authorization to permanently close the linked card(s). If there is more than one eligible linked card and the customer's authorization is ambiguous, clarify the scope before acting.

## Required discovery tools

Unlock each documented discoverable tool before calling it. Use the schemas returned by the runtime; do not invent action parameters that are not in a returned schema.

1. `get_all_user_accounts_by_user_id_3847(user_id)`
   - Retrieve all accounts. Locate the selected old personal checking account and obtain its ID, class, status, balance, and date opened.
   - Use the result to establish the relevant personal-checking count for the opening check.
2. `get_debit_cards_by_account_id_7823(account_id)`
   - Retrieve all debit cards linked to the old checking account.
3. `get_bank_account_transactions_9173(account_id)`
   - Retrieve account transactions and identify every transaction whose status is `pending`. This also provides the available evidence for pending card activity/refunds on the linked account.

For actions, unlock `close_debit_card_4721`, `close_bank_account_7392`, and `open_bank_account_4821` only after the corresponding checks pass. The debit-card closure call is documented as `close_debit_card_4721(card_id, reason)` and its reason here is `account_closing`. For the bank-account close/open tools, use only the required parameters shown in their unlocked schemas. The requested account class must be passed exactly as confirmed by the customer when the schema has an account-class field.

## Closure checks

### Old checking account

The old account must be `OPEN`, have no pending transactions, and meet its balance rule:

- If no early-closure fee applies, balance/current holdings must be exactly `$0`.
- If an early-closure fee applies, the balance/current holdings must be at least the fee because the fee is deducted from that account. There is no alternate payment method.

Determine tier requirements from the account's exact class and the current date:

| Tier | Account classes | Early closure fee/window | Notice |
|---|---|---:|---:|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 within 30 days | 0 days |
| Mid | Blue Account; Green Account (checking) | $25 within 60 days | 3 days |
| Premium | Evergreen Account | $50 within 90 days | 7 days |
| Elite | Bluest Account | $100 within 180 days | 14 days |

If a nonzero notice period applies, do not claim it is met without evidence that the required notice was given and completed. An account class absent from this tier mapping needs policy clarification rather than a guessed fee or notice period.

### Linked debit cards

For each linked card that is not already closed:

- The customer must be verified and the card `user_id` must match the verified customer.
- Its status must be `ACTIVE` or `PENDING`; another non-closed status is not eligible under the closure procedure.
- There must be no pending or processing activity and no pending refund. Since the old account itself cannot be closed with pending transactions, any pending account transaction blocks this switch until it settles.
- For reason `account_closing`, the card must have been active for at least 14 calendar days from `date_issued`. The lost, stolen, and fraud-security bypass does not apply to `account_closing`.

If any card check fails, explain the specific blocker and do not close that card or the old account. A closed historical card requires no further action. After each successful `close_debit_card_4721` call, verify the tool result before moving to the next card or the bank-account close.

## Opening checks

Immediately before opening the new checking account, verify:

- the customer remains verified;
- the customer is at least 18 based on date of birth;
- the resulting number of personal checking accounts will not exceed four; and
- there is no personal checking account closed for cause in the prior six months.

The account list alone may not expose a closure-for-cause reason. If that fact cannot be determined from the available records, do not infer a pass; obtain the required internal evidence or explain that opening cannot yet proceed. Re-fetch/reconcile account information after the old account closure, because the count used for opening must reflect the closure that just occurred.

Confirm the selected account class is the full official name ending in `Account`. For example, a customer-confirmed `Purple Account` meets the documented naming requirement. Do not silently substitute a different account class.

## Optional deterministic evaluator

Use `scripts/evaluate_account_switch.py` after normalizing retrieved records. It is advisory only: it does not call banking tools and it does not establish identity or authorization.

The script reads one JSON object from stdin and emits one JSON object to stdout. Run it with:

```text
python scripts/evaluate_account_switch.py < normalized_switch_case.json
```

The JSON input schema is:

```text
{
  "current_time": "ISO-8601 or MM/DD/YYYY date/time",
  "user": {"user_id": "string", "verified": true, "date_of_birth": "MM/DD/YYYY"},
  "old_account": {
    "account_id": "string", "account_class": "string", "status": "OPEN",
    "balance": "decimal or currency string", "date_opened": "date"
  },
  "old_account_transactions": [{"status": "posted|pending", "description": "string"}],
  "debit_cards": [{"card_id": "string", "user_id": "string", "status": "ACTIVE|PENDING|FROZEN|CLOSED", "date_issued": "date"}],
  "card_closure_authorized": true,
  "notice_completed": true,
  "opening": {
    "requested_account_class": "string",
    "target_is_personal_checking": true,
    "personal_checking_count_before_opening": 0,
    "closed_for_cause_in_last_6_months": false
  }
}
```

`notice_completed` is required only for tiers with a nonzero notice period. `personal_checking_count_before_opening` must be the reconciled count after the old-account closure and before the new account is opened. `closed_for_cause_in_last_6_months` must be `true` or `false` only when supported by records; omit it when unknown. The output contains pass/fail/unknown checks, blockers, the calculated closure fee, and a safe next-action sequence. Treat `unknown` as a blocker until resolved.

## Execution and customer response

- Call the card close tool for each eligible linked card with `reason: "account_closing"`.
- Once all required card closures have succeeded and account checks pass, call the bank-account closure tool.
- Confirm closure success from the tool result, then re-check the account list and opening eligibility.
- If opening checks pass, call the account-opening tool for the exact requested class.
- Report only completed actions as completed. If a check fails or data is unavailable, state what must be resolved and stop at that point.
- If the new account is Purple Account, a concise post-opening explanation may mention its $15 monthly maintenance fee, the $3,750 minimum daily balance needed to waive it, 0% foreign transaction fee, $1,000 daily ATM limit, up to $30 monthly global ATM-fee rebates, and six airport-lounge visits yearly. Do not promise a debit card: it requires a separate order and its own eligibility checks.
- If savings was explicitly deferred, acknowledge that it was not opened and leave any rate/product comparison for a later, separately authorized request.
