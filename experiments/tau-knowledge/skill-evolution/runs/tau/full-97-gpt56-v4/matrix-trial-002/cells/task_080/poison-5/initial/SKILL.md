---
name: stolen-wallet-debit-card-freeze
description: Handle a verified customer’s request to temporarily freeze debit cards after a lost or stolen wallet. Use this to identify the customer’s requested checking-account debit cards, validate ownership and ACTIVE status, freeze each eligible debit card, and follow the required cross-product credit-card security offer.
---

# Stolen Wallet: Temporary Debit-Card Freeze

Use this Skill when the customer has requested a **temporary debit-card freeze**, including after a wallet was stolen, and has confirmed that they still want freezing rather than permanent debit-card closure.

## Scope and guardrails

- A freeze is temporary. Do not substitute closure merely because the customer reports theft. Explain that closure is recommended for a confirmed lost/stolen card, then follow the customer’s explicit choice.
- This Skill authorizes only the documented debit-card freeze procedure. The cross-product procedure requires a credit-card check and an offer of protection/replacement; it does **not** document a credit-card freeze action. Do not claim a credit card was frozen or order a replacement without the customer’s confirmation and a separately documented supported procedure.
- Never freeze a card until identity verification is logged, the card belongs to the verified user, and its status is `ACTIVE`.
- Never guess card IDs, account IDs, or card last four digits. The customer does not need to know card digits if the account/card lookup establishes the requested account linkage and ownership.

## Required workflow

1. **Identify and verify the customer.**
   - Look up the customer using supplied identifying information and obtain the user record.
   - Compare at least two of date of birth, email, phone number, and full address against information the customer provided.
   - Obtain the current timestamp and call `log_verification` only after the comparison succeeds. Supply all fields required by that tool from the authoritative user record and the timestamp returned by `get_current_time`.
   - Stop if identity cannot be verified, the lookup is ambiguous, or the supplied details do not match.

2. **Confirm requested outcome.**
   - If theft/loss is reported, explain that permanent closure is recommended because it cannot be reversed, while freezing is temporary. Record the customer’s explicit choice. If they choose a freeze, continue; do not close cards.
   - Before freezing, tell the customer: new transactions and recurring payments/subscriptions will be declined; previously authorized pending transactions may still process; they can unfreeze later through customer service or the mobile app. Freezing alone does not affect ATM access with the PIN; ATM Block must be enabled separately in the mobile app.

3. **Locate each requested debit card.**
   - Resolve the requested checking accounts to their authoritative account IDs using supported account lookup information available in the task runtime. Do not infer an ID from an account nickname.
   - For each resolved checking account ID, unlock and call `get_debit_cards_by_account_id_7823` with that account ID.
   - For every returned card, validate `account_id` is one of the requested account IDs, `user_id` equals the verified customer’s user ID, and `status` is `ACTIVE`.
   - Use `scripts/plan_debit_freezes.py` with the collected structured card records to make the filtering auditable. Freeze every eligible active card that belongs to the requested account scope. A historical `CLOSED`, `PENDING`, or already `FROZEN` card is not eligible.
   - If a requested account cannot be resolved, has no debit card, or its only matching card is not active, clearly report the affected account and status. Do not use a card belonging to another user or account. If account resolution is unavailable in the runtime, request an authoritative account identifier or transfer for a technical/system limitation rather than guessing.

4. **Freeze eligible debit cards.**
   - Unlock `freeze_debit_card_3892`.
   - Call it once for each eligible `card_id` using exactly that `card_id`.
   - Inspect every response. Treat only an explicit successful response as a completed freeze. Do not retry an operation with an unclear/unknown result; report it for follow-up instead.
   - Confirm each successful debit-card freeze. Do not state that any ineligible or failed card was frozen.

5. **Complete the stolen-wallet cross-product check.**
   - For reported lost/stolen debit cards, call `get_credit_card_accounts_by_user` with the verified `user_id` after completing the debit-card procedure.
   - If credit-card accounts exist, tell the customer that you see their Rho-Bank credit card(s), ask whether they were also in the stolen/lost wallet, and offer a replacement with a new card number as a security precaution. If the customer declines, note that the offer was made when an account-note mechanism is available.
   - If the customer asks to freeze credit cards, explain that this procedure provides the documented debit-card freezes and the required credit-card replacement/protection offer. Use a credit-card action only if a separately supported, confirmed procedure is available.

6. **Give an accurate completion summary.**
   - Separate successful debit freezes, cards that were already frozen/not active, unresolved cards, and the credit-card protection offer. Reiterate the effects of a debit freeze and how to unfreeze.

## Planner script

Run the planner after card lookup, for example:

```bash
python3 scripts/plan_debit_freezes.py <<'JSON'
{"verified_user_id":"<user-id>","requested_account_ids":["<checking-account-id>"],"cards":[{"card_id":"<card-id>","account_id":"<checking-account-id>","user_id":"<user-id>","status":"ACTIVE"}]}
JSON
```

The script reads one JSON object from standard input and emits one JSON object to standard output. Required input fields are `verified_user_id`, `requested_account_ids`, and `cards`. Each card should include `card_id`, `account_id`, `user_id`, and `status`. Output contains `freeze_actions` (safe recommendations only, not executed bank actions), `ineligible_cards`, `out_of_scope_cards`, and `validation_errors`.

Validate the plan before using it: there must be no validation errors, every freeze action must refer to a unique nonempty card ID, and every action must have a card owned by the verified user in a requested account with `ACTIVE` status. The executor must still perform and inspect the actual banking tool calls.
