---
name: credit-card-closure-with-retention
description: Safely process a verified customer's credit-card closure request, including closure eligibility, replacement-card and dispute checks, abuse-safe retention handling, and final closure communication. Use when an authenticated customer asks to close a credit card account.
---

# Credit Card Closure With Retention

## Scope and safety rules

Use this Skill only after identifying the requested credit-card account and its owner. A closure must not be submitted until all of the following are true:

- Identity is verified and a successful verification audit record has been logged.
- The account balance is exactly $0.00.
- There are no active or pending disputes.
- The account has been open for at least 60 days.
- There are no pending replacement-card orders. An order blocks closure unless every returned order is `delivered` or `cancelled`.
- The customer has either declined the applicable retention offer, or retention is skipped because the account has a closure-reason record in the prior year.

Do not infer an eligibility result from missing, malformed, stale, or ambiguous tool output. Resolve the data or explain that closure cannot yet be completed. Do not close a different card than the one the customer selected.

The executor, not this package, performs banking-tool calls. Discoverable-tool recommendations in this Skill never perform account changes automatically.

## Runtime inputs to collect

Obtain at runtime:

- The customer's selected card/account and the owning `user_id`.
- At least two customer-confirmed identity fields out of date of birth, email, phone number, and mailing address, matched against the customer profile.
- Current account date opened and balance.
- Current dispute-history response for the user.
- Current replacement-order response for the account.
- Closure-reason history for the account.
- The customer's reason, their response to concern handling, and their acceptance or decline of any retention option.
- Current date/time for verification logging and date-sensitive checks.

Never substitute identifiers, profile values, dates, balances, or tool results from an earlier case. If a transcript already contains two matching customer-confirmed identity fields, it may satisfy the confirmation portion; still create the verification audit record before continuing.

## End-to-end procedure

### 1. Identify the customer, account, and verify identity

1. Locate the user using an available profile lookup, then retrieve that user's credit-card accounts. Confirm that the selected account belongs to that user and matches the requested card.
2. Compare customer-provided identity responses against the profile. Require at least two matching fields among date of birth, email, phone number, and address. A profile lookup alone is not customer confirmation.
3. Get the current time and log the successful verification before account-processing actions:
   - Call `log_verification` with `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`.
   - Populate all profile fields in that audit record from the verified profile, using the timestamp returned by the current-time tool.
4. If two fields cannot be verified, do not disclose additional account information or continue with closure. Ask for another supported field or route the identity-verification failure to a human using the highest applicable transfer reason, normally `account_ownership_dispute` when specialist identity handling is required.

### 2. Perform closure eligibility checks before retention

Unlock and call the following internal tools as needed:

- `get_user_dispute_history_7291` with `{"user_id":"<user_id>"}`.
- `get_pending_replacement_orders_5765` with `{"credit_card_account_id":"<account_id>"}`.

Use the account record for opening date and current balance. The packaged helper may be used to calculate the deterministic result from normalized tool data:

```json
{
  "account_open_date": "<date from account record>",
  "as_of": "<current date or timestamp>",
  "current_balance": "<current balance>",
  "disputes": ["<dispute records from the dispute tool>"],
  "replacement_orders": ["<replacement-order records from the replacement tool>"]
}
```

Call `scripts/closure_preflight.py` through the runtime's script runner with actual structured values in place of the placeholders. It emits JSON containing `eligible`, `blockers`, the account age, and a correctly formatted one-year waiver expiration date. Treat `eligible: null` or a nonempty `errors` array as insufficient evidence, not as approval.

Interpret dispute results conservatively: an empty list passes; only clearly resolved/closed disputes pass. An `open`, `pending`, `under_review`, unknown, or omitted status blocks closure until clarified. Interpret replacement results conservatively: an empty list passes; all orders must be clearly `delivered` or `cancelled`.

If any check fails, explain the specific prerequisite that must be resolved and stop. Do **not** make retention offers for an ineligible account.

### 3. Check retention-attempt history

After eligibility passes, unlock and call:

- `get_closure_reason_history_8293` with exactly `{"credit_card_account_id":"<account_id>"}`.

Determine whether this account has a closure-reason record within the prior year. If one does, skip reason logging and all retention activity; thank the customer and move to final pre-closure validation. This prevents repeated-offer abuse. If records are ambiguous or dates cannot be assessed, do not make a retention offer; proceed only when the customer has clearly requested closure and all closure prerequisites are met.

### 4. Log and address the reason when retention is allowed

Ask why the customer wants to close if it is not already clear from the conversation. Normalize the answer to exactly one permitted value:

`annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

Unlock and call `log_credit_card_closure_reason_4521` using **only** these arguments; do not add metadata or explanatory fields:

```json
{
  "credit_card_account_id": "<account_id>",
  "user_id": "<user_id>",
  "closure_reason": "<allowed_reason>"
}
```

Address the stated concern without making unsupported promises:

- **annual_fee:** For a customer of at least two years, offer a one-year annual-fee waiver as a loyalty benefit. Only after acceptance, unlock and call `apply_credit_card_account_flag_6147` with `credit_card_account_id`, `user_id`, `flag_type: "annual_fee_waived"`, `expiration_date` set to one calendar year from the current date in `MM/DD/YYYY`, and `reason: "loyalty_benefit"`. For less than two years, offer a same-category no-annual-fee downgrade. Explain preserved history and credit line plus changed benefits. After the customer agrees, call `downgrade_credit_card_3847` with `credit_card_account_id`, `user_id`, and the correct same-category target: `Bronze Rewards Card` for personal or `Business Bronze Rewards Card` for business.
- **not_using_card:** Describe relevant known benefits and suggest a recurring subscription only as an option.
- **found_better_card:** Ask which features the alternative card provides. Offer help with a comparable Rho-Bank card only if available product information supports that comparison; never invent benefits or availability.
- **unhappy_with_rewards:** Review applicable bonus-category enrollment and legitimate ways to maximize rewards. Explain representation accurately: stored points for cash-back cards redeem at $0.01 per point as statement or checking-account credit.
- **negative_experience:** Apologize, collect details, and escalate service complaints when warranted. Do not grant a goodwill credit unless an authorized tool and policy are available.
- **simplifying_finances** or **other:** Acknowledge the reason and continue respectfully.

### 5. Make one retention offer and respect the decision

If the customer still wants closure after concern handling, make one offer based on the documented card tier:

- Entry tier: 500 bonus points or a $5 statement credit.
- Mid tier: 2,000 bonus points or a $20 statement credit.
- Premium and above: 5,000 bonus points or a $50 statement credit.

Use product documentation to establish a tier; do not guess based only on a card name. If the customer accepts a retention alternative, do not close the account. Apply only a retention action whose tool and policy are available, and otherwise obtain authorized assistance rather than claiming the reward was applied.

If the customer declines, or retention was skipped for prior attempts, thank them and proceed without pressure.

### 6. Revalidate immediately before closure and close

Immediately before submitting the closure, repeat the replacement-order check with `get_pending_replacement_orders_5765`. If any returned order is not clearly delivered or cancelled, stop and explain that closure must wait. Refresh account/dispute information as appropriate if prior data may have changed; all four eligibility conditions must still be evidenced.

Unlock and call `close_credit_card_account_7834` only after all checks and the customer decision are complete. Its arguments are exactly:

```json
{
  "credit_card_account_id": "<account_id>",
  "user_id": "<user_id>"
}
```

If a required tool errors or a system outage prevents closure, do not state that it was closed. Capture the completed checks and transfer using `technical_system_error`. If human handling is otherwise required for the explicit closure request, use `account_closure_request`, the highest applicable transfer reason.

### 7. Required post-closure communication

After a successful closure response, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; afterward they are forfeited.
- A full annual-fee refund may be available if the account is closed within 37 days of the annual-fee charge.
- Closing a card can affect credit utilization and potentially the credit score, especially for an older or high-limit account.

For cash-back cards whose rewards are represented as points, state monetary value only when relevant and use $0.01 per point. Do not imply rewards are already redeemed or an annual-fee refund is guaranteed.

## Validation checklist

Before calling the closure tool, verify all of the following are documented in the live workflow:

1. Correct user and requested account were matched.
2. Two customer-confirmed identity fields matched and `log_verification` succeeded.
3. Balance is exactly zero and account age is at least 60 days.
4. Dispute history has no unresolved or ambiguous disputes.
5. The final, immediately preceding replacement check has no non-final order.
6. Closure-history handling was completed, and either retention was skipped for a recent record or the customer declined after one appropriate offer.
7. The close call uses only the account ID and matching user ID.
8. Success is communicated only after a successful close-tool response.

## Helper interface

`scripts/closure_preflight.py` reads one JSON object from standard input and writes one JSON object to standard output. Required keys are `account_open_date`, `as_of`, `current_balance`, `disputes`, and `replacement_orders`. Dates may be `YYYY-MM-DD`, `MM/DD/YYYY`, or a timestamp beginning with one of those dates. `disputes` and `replacement_orders` must be arrays of objects. See the script docstring for exact output fields and validation behavior.
