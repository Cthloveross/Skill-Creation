---
name: stolen-wallet-card-security
description: Handle a verified customer's stolen or lost wallet report, including debit-card freezes, later debit-card unfreezes when a found card is eligible, and credit-card replacement protection.
---

# Stolen Wallet Card Security

Use this Skill for a customer reporting that a wallet or cards were lost or stolen, including when they later find a card, confirm a card was stolen, or change their requested action.

## Verification and audit

Before any state-changing card action:

1. Locate exactly one customer profile using a customer-provided name or email.
2. Verify at least two of these retrieved profile fields against information supplied by the customer: date of birth, email, phone number, and address. A profile lookup by itself is not verification.
3. Get a current timestamp with `get_current_time` and call `log_verification` after successful verification. Supply the canonical profile values for every required log field, including `user_id` and `time_verified`.
4. If the profile is ambiguous or fewer than two fields match, request the missing information. Do not retrieve card details for action or take a card action.

Previously obtained observations may be reused only when they establish an unambiguous customer and two customer-supplied matching fields. The verification audit log is still required before the first state-changing action.

## Debit-card freeze workflow

A freeze is temporary. It is appropriate when the verified owner requests temporary security, including after a theft report, but a confirmed stolen debit card should also be offered permanent closure as the safer option. Do not replace a customer's explicit request to freeze with closure.

Before a freeze, disclose that:

- New transactions and recurring payments/subscriptions will be declined.
- Already-authorized pending transactions can still process.
- The card can later be unfrozen through customer service or the mobile app.
- Freezing does not itself block ATM access for someone who has the PIN; ATM Block must be enabled separately in the mobile app.

Then:

1. Call `get_all_user_accounts_by_user_id_3847(user_id)` and identify only requested checking accounts. Match customer-provided account names to returned labels/classes; if ambiguous, ask for selection rather than guessing.
2. For each selected checking account, call `get_debit_cards_by_account_id_7823(account_id)`.
3. Confirm ownership by matching `card.user_id` to the verified user. Freeze only a selected card whose status is exactly `ACTIVE`.
4. Use `freeze_debit_card_3892(card_id)` once for each eligible card. If this is exposed as a discoverable agent tool, unlock it first and then call it through the runtime's normal discoverable-tool mechanism.
5. Confirm only successful tool results. Preserve other completed freezes if an individual lookup or action fails and truthfully explain/escalate the unresolved security concern.

Do not call a freeze tool for `PENDING`, `FROZEN`, or `CLOSED` cards.

## Later found-card unfreeze workflow

A later customer statement that a specific card has been found and a request to remove its temporary freeze is a new action request; it supersedes the prior temporary-freeze request for that card only. Do not refer the customer to another channel instead of performing the documented unfreeze workflow when its requirements are met.

For each requested unfreeze:

1. Reuse the valid verified-owner context or reverify if it is no longer established.
2. Identify the exact debit card from the prior lookup/action record, or retrieve its linked checking account and debit-card records again if needed. Confirm the card belongs to the verified user.
3. Confirm that the card status is `FROZEN` and its linked checking account status is `OPEN`. If either condition is not met, do not unfreeze; explain the observed condition and take only supported next steps.
4. Invoke `unfreeze_debit_card_3893(card_id)` using the normal direct or unlocked discoverable-tool mechanism.
5. Treat the card as active and ready for immediate use only after a successful result. Confirm the successful unfreeze to the customer. If the call fails, do not claim it was unfrozen; maintain the existing protection and escalate the execution failure.

Never describe `unfreeze_debit_card_3893` as unsupported when the documented requirements are satisfied.

## Debit-card closure after a theft confirmation

Permanent debit-card closure is documented through `close_debit_card_4721(card_id, reason)` and requires verified ownership, an `ACTIVE` or `PENDING` card, no pending/processing transactions, no unresolved pending refunds (unless the documented written acknowledgement route is satisfied), and normally a 14-day card age. `lost`, `stolen`, and `fraud_suspected` bypass the minimum-age requirement only.

If the customer later confirms a card is stolen:

1. Explain that permanent closure is documented and irreversible, and ask whether they want replacement if applicable.
2. Recheck all closure eligibility using current records before calling the closure tool.
3. If a prior temporary freeze leaves the card `FROZEN`, do not falsely claim closure is undocumented and do not unfreeze merely to try to satisfy closure status requirements. Keep the protective freeze, explain that the current status blocks the documented closure call, and make a truthful security handoff/escalation if closure cannot be directly completed.
4. If all documented eligibility conditions are met, call `close_debit_card_4721` with the exact supported reason, confirm success, and explain that recurring payments need updating and the closed card cannot be reopened.

## Credit-card protection

The supplied procedures document credit-card replacement, not an agent-side credit-card freeze. Never claim a credit card is frozen or invent a lock action.

For a verified customer reporting a lost or stolen debit card:

1. Call `get_credit_card_accounts_by_user(user_id)` and identify active requested credit cards by returned type and last four digits.
2. Proactively offer replacement protection and ask whether each credit card was in the lost/stolen wallet.
3. Do not submit a replacement until the customer explicitly agrees and all prerequisites are complete: identity verified, account identified, shipping address confirmed (including unit/suite if applicable), exactly one allowed reason recorded, shipping speed selected, required expedited-fee consent obtained, and eligibility confirmed (including no pending replacement and applicable replacement limit).
4. For a completed request, unlock and call `order_replacement_credit_card_7291` with the account/card identifier, reason, confirmed address, shipping speed, applicable expedited-fee acknowledgement, and relevant notes. Submission automatically cancels the old card.
5. For stolen or suspected-fraud cards, recommend expedited delivery and review of recent transactions. Do not label ordinary transactions fraudulent without the customer's report.

Shipping is standard (7–10 business days, free) or expedited (2–3 business days). Expedited fees are $15 for entry tier, $10 for mid tier, and free for premium tier and above. If immediate credit-card protection is requested but no documented direct action is available, use the normal human-transfer process for a fraud/security concern without delaying independent eligible debit-card actions.

## Failure handling and customer completion

- Use only documented tool names and runtime-supported argument schemas. Unlocking a discoverable tool is not a card action.
- Never guess a card ID, account ID, account match, ownership, or successful result.
- Complete independent eligible card actions even if another requested card is ambiguous or fails.
- Do not say all cards are secured unless every requested card has a confirmed supported outcome.
- Summarize separately: successful debit freezes, successful unfreezes, cards still frozen and why, closures or closure blockers, credit-card replacement offers/orders, pending-transaction effects, recurring-payment effects, ATM Block limitation, and any escalation.

## Optional deterministic planning helper

`scripts/plan_debit_freezes.py` converts structured account and debit-card lookup records into a conservative freeze plan. It performs no banking action and does not parse unstructured tool prose.

Run:

```text
python3 scripts/plan_debit_freezes.py < request.json
```

Input JSON schema:

```json
{
  "verified_user_id": "string",
  "requested_debit_account_labels": ["string"],
  "accounts": [{"account_id":"string", "account_type":"CHECKING", "account_class":"string", "status":"string"}],
  "debit_cards": [{"card_id":"string", "account_id":"string", "user_id":"string", "status":"ACTIVE", "card_number_last_4":"string"}]
}
```

`account_name`, `display_name`, or `name` may be used instead of `account_class`. The JSON result has `freeze_card_ids`, `selected_cards`, and `blockers`. Use returned IDs only after verification, required disclosure, and the audit log. Resolve or communicate every blocker; never override one by guessing.
