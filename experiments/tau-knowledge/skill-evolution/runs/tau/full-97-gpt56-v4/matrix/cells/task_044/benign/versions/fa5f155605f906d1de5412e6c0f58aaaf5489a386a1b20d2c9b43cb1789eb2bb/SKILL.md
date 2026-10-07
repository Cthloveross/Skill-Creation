---
name: credit-card-closure-retention
version: 1.1.0
description: Handle a verified customer's request to close a credit-card account, including eligibility checks, required reason-history and retention workflow, and compliant closure or next-step communication. Use when a customer requests card closure or asks about closing a credit card.
---

# Credit Card Closure and Retention Workflow

Use this Skill for a customer-requested credit-card closure. Do not close an account merely because the customer has asked for information or has not made a final decision after a retention offer.

## Required facts and policy

Closure can proceed only when all of the following are true:

- The authenticated customer owns the selected account.
- The outstanding balance is exactly `$0.00`.
- The account has been open for at least 60 days.
- There are no active or pending credit-card disputes for the customer that apply to the account.
- There are no unresolved replacement-card orders for the account. An order is only non-blocking when every returned order is clearly `delivered` or `cancelled`.

When closure proceeds, tell the customer that remaining rewards are redeemable for 45 days after the closure request and are forfeited afterward. Tell them a full annual-fee refund may apply only when closure is within 37 days of that fee posting. Explain, if appropriate, that closing can reduce available credit and affect utilization/credit score.

For Gold Rewards Card product questions: it has a 0% foreign transaction fee. Its backend `points` represent cash back at `$0.01` per point when redeemed as a statement credit or checking-account credit. Do not make claims about a competitor's rewards, fee, or bonus unless independently supported.

## Runtime inputs and state to maintain

Obtain values at runtime; never rely on identifiers or balances from a prior case:

- `user_id`, customer identity fields, and selected `credit_card_account_id`
- account open date, balance, card type, rewards balance, and retention tier
- verification timestamp
- dispute-history result, replacement-order result, closure-reason-history result
- customer reason, whether it was successfully logged, any retention offer, and the customer's final response

Treat missing, malformed, ambiguous, or failed checks as blocking. Do not close an account on incomplete evidence.

## Procedure

### 1. Identify the account and verify identity

1. Ask for a profile lookup value if needed (such as email or full name), then retrieve the customer record and their credit-card accounts using the ordinary account lookup tools.
2. Have the customer confirm **two of the four** identity fields: date of birth, email, phone number, or address. Compare their supplied answers with the customer record; do not reveal a full value in order to solicit confirmation.
3. Once two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` with all required stored customer fields (`name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`).
4. Identify the specific account the customer wants to close. If multiple cards could match, ask the customer to select one without exposing unnecessary account details. Confirm that the selected account belongs to the verified user.

If verification fails or the user cannot identify the account, do not disclose account data or make account changes.

### 2. Check closure eligibility before retention

Review the selected account's balance and opening date. Calculate age from the current date; the account must be at least 60 calendar days old.

Unlock and call the following internal tools with their documented exact arguments:

1. `get_user_dispute_history_7291` with `{"user_id":"<user_id>"}`. Review returned disputes. Any `open`, `under_review`, pending, active, or otherwise unresolved dispute blocks closure. If account association is not clear from the response, treat it as unresolved rather than assuming it belongs to another card.
2. `get_pending_replacement_orders_5765` with `{"credit_card_account_id":"<account_id>"}`. Empty results pass. Any order other than clearly `delivered` or `cancelled` blocks closure.

If any eligibility condition fails, explain the specific prerequisite (pay the balance, wait until the account is 60 days old, resolve dispute, or complete/cancel replacement). Do **not** log a retention reason, make a retention offer, or invoke closure. Invite the customer to return once it is resolved.

### 3. Prevent repeated retention attempts

For an eligible account, unlock and call `get_closure_reason_history_8293` with exactly:

```json
{"credit_card_account_id":"<account_id>"}
```

If it returns any closure-reason record within the past year, do not make another retention offer. Say that you will honor the closure request, then proceed to Step 6 only if the customer has clearly confirmed closure.

### 4. Capture and log the closure reason

If there is no qualifying prior reason record, ask why the customer wishes to close if it is not already clear. Map the answer to exactly one allowed value:

- `annual_fee`
- `not_using_card`
- `found_better_card`
- `unhappy_with_rewards`
- `simplifying_finances`
- `negative_experience`
- `other`

Unlock and call `log_credit_card_closure_reason_4521` using **only**:

```json
{"credit_card_account_id":"<account_id>","user_id":"<user_id>","closure_reason":"<allowed_value>"}
```

Do not add notes, timestamps, or any other parameters. If logging fails, do not proceed to a retention offer or closure until the failure is resolved.

### 5. Address the reason and make one offer

Address the reason briefly and accurately. For `found_better_card`, ask which features matter and review only supported comparable benefits. For example, explain that the Gold Rewards Card already has no foreign transaction fee, where applicable; do not claim that it matches an outside issuer's cash-back rate or sign-up bonus. If the customer asks whether a different Rho-Bank card has better rewards but no supported product comparison is available, say you cannot confirm a comparable product rather than speculating. That uncertainty does not prevent making the documented retention offer for the current eligible account or honoring a final closure decision.

Then make exactly one retention offer based on the account's retention tier:

- entry tier: 500 bonus points **or** a `$5` statement credit
- mid tier: 2,000 bonus points **or** a `$20` statement credit
- premium or above: 5,000 bonus points **or** a `$50` statement credit

Use an explicit tier returned by the account source when it is available. For the named **Gold Rewards Card**, use the mid-tier retention offer (2,000 bonus points or a $20 statement credit); this is the applicable retention classification for this workflow. Do not reclassify other product names from a guessed marketing hierarchy. If neither an explicit tier nor a documented named-card classification is available, do not quote an offer; route for specialized assistance.

State the applicable alternatives and ask whether the customer accepts either alternative or wants to continue with closure.

For an annual-fee reason, separately follow the documented tenure rule: customers of 2+ years may be offered a one-year annual-fee waiver using `apply_credit_card_account_flag_6147` with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from today in `MM/DD/YYYY`; customers under two years may be offered a permanent downgrade to a no-annual-fee card preserving history. Do not apply a waiver unless the customer accepts it.

If the customer says the answer depends on hearing the offer, provide the applicable offer and wait for an explicit accept or decline. That is not a closure confirmation.

If the customer accepts a retention option, perform only the documented accepted option through its authorized process/tool, confirm the account remains open, and do not close it. If they decline or again clearly ask to close, proceed without pressure.

### 6. Close only after a final closure decision

Immediately before closing, ensure the successful eligibility evidence is still current; in particular, repeat the replacement-order check if material time has passed. Unlock and call `close_credit_card_account_7834` with:

```json
{"credit_card_account_id":"<account_id>","user_id":"<user_id>"}
```

Use no guessed parameters. Report success only if the tool confirms it. On success, tell the customer a confirmation email and final statement will arrive within several business days, and give the 45-day rewards and 37-day annual-fee timing notices.

If the closure tool fails, do not claim the account was closed and do not retry an ambiguous/unknown action. Explain that closure could not be confirmed and route to a human agent when needed using `account_closure_request` with a concise summary of completed verification and eligibility checks.

## Tool sequencing and safety

Discoverable tools must be unlocked before being called. Bank actions occur only through the declared banking tools; scripts in this package only evaluate supplied dates/statuses and never perform bank actions. Never reveal a customer's full sensitive identity data in customer-facing wording. Do not pressure a customer after a decision to close.

## Optional local eligibility evaluator

`scripts/evaluate_closure_eligibility.py` accepts a JSON object on stdin and emits a JSON eligibility decision on stdout. It is useful for deterministic date and replacement-status evaluation, but the executor must still obtain live tool evidence and use banking tools for all actions.

Example:

```json
{
  "current_date":"2025-11-14",
  "account_open_date":"2023-03-20",
  "balance":"0.00",
  "dispute_statuses":["closed"],
  "replacement_statuses":["delivered"]
}
```

A valid result has `eligible: true` only when all four conditions pass. Validate `blockers` before advancing to history, logging, retention, or closure.
