---
name: close-personal-checking-account
version: 1.0.0
description: Safely evaluate and process a requested closure of a personal checking account, including tier-based fee and notice rules, pending-transaction checks, and required closure of linked debit cards. Use when a customer identifies a checking account to close; do not use it to close savings accounts or debit cards independently.
---

# Close Personal Checking Account

## Scope and guardrails

Use this Skill for a customer's requested personal checking-account closure. Work only on the uniquely identified requested account. Do not close another checking account, open a savings account, or act on a deferred request merely because it was mentioned in the conversation.

The account closure requirements are:

- The account must be `OPEN`.
- It must have no `pending` bank-account transactions.
- If an early-closure fee applies, its balance must be at least that fee. The fee is deducted from the account; do not suggest or attempt another payment method.
- If no fee applies, the balance must be exactly zero.
- Every linked debit card must be closed before closing the checking account.
- Honor the account tier's notice period before invoking the account-close action.

Tier rules:

| Account class | Tier | Early fee/window | Notice |
|---|---|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | Entry | $15 within 30 days | 0 days |
| Blue Account, Green Account (checking) | Mid | $25 within 60 days | 3 days |
| Evergreen Account | Premium | $50 within 90 days | 7 days |
| Bluest Account | Elite | $100 within 180 days | 14 days |

“Within” is evaluated as fewer than the stated number of calendar days since `date_opened`. The closure date is the date on which closure would actually occur.

## Runtime inputs and identity

1. Use an already resolved customer `user_id`, or locate it from customer-provided identifying information using an available user-lookup tool.
2. Before closing any linked debit card, verify the customer by having them confirm at least two of date of birth, email, phone number, and address. Do not count values returned by a lookup as confirmation unless the customer has supplied or confirmed them.
3. Obtain the current timestamp with `get_current_time` and call `log_verification` with all returned user identity fields and that timestamp after successful two-field confirmation.
4. The user's explicit request to close the identified account may serve as the start of the account's required notice period. Record the request date only through supported case/system mechanisms. If the system does not establish a notice date, do not claim that a nonzero notice period has elapsed.

## Tool workflow

Use the normal discoverable-agent-tool flow: unlock each named tool before calling it, then call it using its exposed schema. Never manufacture tool results or parameters.

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the resolved `user_id`.
2. Select the requested account only when exactly one record matches the requested checking-account class. Check `account_type`, `account_class`, `status`, `balance`, and `date_opened`.
   - If no matching checking account exists, explain that it could not be located and do not close anything.
   - If more than one account plausibly matches, ask the customer to distinguish it using a safe identifier such as the account type/class or a permitted account identifier.
   - Do not infer that a similarly named or other-tier account is the target.
3. Unlock and call `get_bank_account_transactions_9173` for the target `account_id`. Treat any transaction whose `status` is `pending` as a closure blocker. This all-account transaction check also supplies the available evidence for pending card refunds.
4. Unlock and call `get_debit_cards_by_account_id_7823` for the target checking `account_id`. Any card not `CLOSED` prevents immediate account closure.
5. Normalize those records and run `scripts/evaluate_closure.py` to make the tier, date, balance, transaction, card, and notice checks reproducible. See the script schema below.
6. If a linked card is `ACTIVE` or `PENDING`, use the verified customer and no-pending-transaction evidence to evaluate debit-card eligibility:
   - It must be at least 14 days old based on `date_issued`.
   - Use reason `account_closing` because the card is being closed for its linked account closure.
   - Unlock and call `close_debit_card_4721` only if its exposed tool requirements are met.
   - A lost, stolen, or fraud reason can bypass the age rule for an independently reported security event, but do not mislabel an account-closure request as one of those reasons to bypass the rule.
   - A `FROZEN`, unknown, or otherwise unsupported non-closed card cannot be closed using the documented debit-card closure procedure. Explain the blocker and use an approved escalation path if available; do not close the account.
   - Re-fetch debit-card information after each closure and continue only after all linked cards are confirmed `CLOSED`.
7. If all prerequisites pass and the notice period has elapsed, unlock and call `close_bank_account_7392` for the selected target account, using the tool's exposed required account identifier argument. Do not pass undocumented fee, notice, or balance override parameters.
8. Confirm the tool result before telling the customer that the account is closed. State the fee only if one was applicable and successfully processed. Confirm that the non-target account remains untouched.

## Notice and blocked cases

Do not invoke `close_bank_account_7392` before a nonzero notice period expires. Tell the customer the earliest closure date, calculated from the recorded closure request/notice date. A request made today does not make a 3-, 7-, or 14-day notice period immediately satisfied.

If the evaluator reports a blocker, explain the specific corrective action:

- pending transaction: wait for it to post or otherwise resolve;
- fee applies and balance is too low: sufficient funds must be in the account because the fee can only be deducted there;
- no fee and nonzero balance: reduce or move the balance to exactly zero using supported customer processes;
- card too new: wait until its earliest card-closure date, unless the customer independently reports a qualifying security reason;
- cards still open: close them first;
- account not open or unsupported class: do not attempt account closure.

Do not suggest an alternative payment method for an early fee and do not represent a future closure as already completed.

## Evaluator script

`scripts/evaluate_closure.py` accepts JSON on stdin and emits one JSON object on stdout. It performs no banking actions.

Input schema:

```json
{
  "account": {
    "account_id": "string",
    "account_type": "checking",
    "account_class": "Green Account",
    "status": "OPEN",
    "balance": "0.00",
    "date_opened": "MM/DD/YYYY or YYYY-MM-DD"
  },
  "as_of": "YYYY-MM-DD or timestamp",
  "notice_given_date": "optional YYYY-MM-DD or timestamp",
  "transactions": [{"status": "posted"}],
  "cards": [
    {"card_id": "string", "status": "CLOSED", "date_issued": "YYYY-MM-DD"}
  ]
}
```

`transactions` and `cards` must be the complete lists returned for the target account. The script reports `blocking_reasons`, `required_next_actions`, card-level closure instructions, the fee calculation, and `closure_ready`. Its `closure_ready` value is a policy decision aid; an executor must still perform the required tool actions and confirm their results.

Example invocation by the Skill runtime:

```text
run_skill_script(relative_path="scripts/evaluate_closure.py", input_json=<normalized tool records>)
```

Validate that the emitted `account_id` is the selected target, `supported_account_class` is true, every source list is complete, and `closure_ready` is true before calling the bank-account close tool. Re-run the evaluator after debit-card closures or any material change to balance, transactions, status, or notice date.
