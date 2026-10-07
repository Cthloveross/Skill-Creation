---
name: close-personal-checking-account
version: 1.1.0
description: Evaluate and, only when every requirement is met, close a requested personal checking account. Applies to checking-account closure requests requiring account lookup, transaction and debit-card review, tier-based early-fee and notice evaluation, and a confirmed closure action.
---

# Close Personal Checking Account

## Scope and customer intent

Use this Skill only for the specifically requested personal checking account. Identify the requested account from the account lookup; do not infer that another similarly named account is the target.

Respect explicitly retained accounts and deferred requests. In particular, do not close, transfer from, alter, or otherwise mutate a checking account that the customer said to keep. Do not open a savings account when the customer has deferred that request.

## Closure policy

Before a checking account can be closed, all of the following must be true:

1. The account status is `OPEN`.
2. There are no `pending` transactions for that account.
3. Every linked debit card is confirmed `CLOSED`.
4. The account has met its tier's required notice period.
5. If an early-closure fee applies, the account balance is at least that fee. The fee is deducted directly from that same account; there is no alternative payment method.
6. If no early-closure fee applies, the balance is exactly `$0.00`.

| Account level | Tier | Early closure fee | Fee window | Notice period |
|---|---|---:|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | Entry | $15 | within 30 days | 0 days |
| Blue Account, Green Account (checking) | Mid | $25 | within 60 days | 3 days |
| Evergreen Account | Premium | $50 | within 90 days | 7 days |
| Bluest Account | Elite | $100 | within 180 days | 14 days |

Use the current date and the account's `date_opened` to determine whether the fee applies. A nonzero notice period is not satisfied merely because the customer asks for closure today. Do not claim that notice has elapsed unless a supported record establishes a notice date and enough time has passed.

## Required workflow

1. Resolve the customer's `user_id`. Use already available, customer-provided identifying information and an available user lookup where necessary.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` with the resolved `user_id`.
3. Select only the requested checking account. Confirm its identifier, checking type, account level/class, `OPEN` status, balance/current holdings, and opening date.
   - Some account lookups label the product as `level` and the account kind as `class`; normalize these into the evaluator's `account_class` and `account_type` fields.
   - If no unique requested checking account is found, explain the issue and do not mutate any account.
4. Unlock and call `get_bank_account_transactions_9173` with the selected account ID. Treat any transaction with status `pending` as a closure blocker. An empty returned list means no transactions were returned, but still retain the tool result as the review evidence.
5. Unlock and call `get_debit_cards_by_account_id_7823` with the same selected account ID. An empty returned list satisfies the linked-card review; otherwise every linked card must be `CLOSED` before account closure.
6. Normalize the lookup records and use `scripts/evaluate_closure.py` to evaluate the deterministic account, fee, balance, transaction, card, and notice checks.
7. If linked cards remain open, do not close the account yet. For an `ACTIVE` or `PENDING` linked card, first verify the customer by confirmation of at least two identity fields (date of birth, email, phone number, address), obtain the current time, and call `log_verification` with the complete returned identity record and timestamp. The card must have no pending activity and be at least 14 days old for an `account_closing` closure reason. Unlock and use `close_debit_card_4721` only when its exposed requirements are met. Re-fetch cards after each card closure.
   - Do not mischaracterize an account-closure request as lost, stolen, or fraud to bypass the card-age rule.
   - A `FROZEN`, unknown, malformed, or otherwise unsupported card status is a blocker. Do not close the bank account.
8. Re-run the evaluator after any card closure, change in transactions, balance, account status, or recorded notice date.
9. Only if `closure_ready` is true, unlock and call `close_bank_account_7392` using the account identifier required by that tool's exposed schema. Never send undocumented fee, balance, or notice override fields.
10. Confirm the close-tool result before stating that the account is closed. Do not describe a blocked or future closure as completed.

Use normal banking tools for all banking actions. The evaluator only analyzes supplied data and never performs an action.

## Notice handling and escalation

A required notice period must be recorded through a supported case or notice mechanism before it can elapse. If there is no supported mechanism available to record the customer's notice, explain that closure cannot be completed yet and transfer to a human agent using `transfer_to_human_agents` with the applicable `account_closure_request` reason. Do not pretend a transfer, notice record, or account closure happened unless its tool result confirms it.

When the required notice date is known, the earliest closure date is the notice date plus the tier's notice days. Review the account again at that time: it must still be `OPEN`, have the required balance, have no pending transactions, and have no linked card that remains open.

## Required customer explanations for blockers

State every currently applicable blocker in plain language. For a Mid-tier Green Account when the $25 fee applies and funding is insufficient, use wording equivalent to this complete explanation:

> I can't close the Green Account yet. The $25.00 early-closure fee must be deducted from the Green Account, so at least $25 must be available in that account. Its 3-day notice period must also be recorded and satisfied before closure.

The product name may be replaced with the actual requested account name, but retain all of these facts: the fee amount, that it is deducted from that account, the minimum amount that must be available there, and the `3-day notice period`.

If the customer asks whether a check deposit can fund the fee, explain that it can be considered only once at least the fee amount is available in the requested account and the notice requirement is satisfied. Do not promise that an unposted or unavailable deposit will fund the fee. At the closure review, re-check for pending transactions before proceeding.

For other blockers, explain the corresponding corrective action:

- **Pending transaction:** wait for every pending transaction to post or otherwise resolve, then re-check.
- **Fee applies but balance is insufficient:** funds must be available in the target account because the fee can only be deducted from that account.
- **No fee but nonzero balance:** bring the target balance to exactly `$0.00` through supported customer processes.
- **Linked card is not closed:** close eligible linked debit cards first and re-check the complete card list.
- **Card is too new:** wait until the evaluator's earliest normal card-closure date unless the customer independently reports a qualifying security event.
- **Account is not open or its class is unsupported:** do not invoke the account-close tool.

## Evaluator

Run the evaluator through the packaged-script runtime, for example:

```text
run_skill_script(relative_path="scripts/evaluate_closure.py", input_json=<normalized-review-data>)
```

The script reads one JSON object from stdin and writes one JSON object to stdout. It accepts:

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
  "transactions": [{"transaction_id": "string", "status": "posted or pending"}],
  "cards": [{"card_id": "string", "status": "CLOSED", "date_issued": "YYYY-MM-DD"}]
}
```

`transactions` and `cards` must be complete lists returned for the selected target account. The output contains `blocking_reasons`, `required_next_actions`, fee and notice calculations, per-card instructions, and `closure_ready`.

Before calling the account-close tool, validate that the output `account_id` matches the selected account, `supported_account_class` is true, the source lists were complete, and `closure_ready` is true. If the evaluator returns `ok: false`, correct or re-fetch the malformed source data; do not close the account.
