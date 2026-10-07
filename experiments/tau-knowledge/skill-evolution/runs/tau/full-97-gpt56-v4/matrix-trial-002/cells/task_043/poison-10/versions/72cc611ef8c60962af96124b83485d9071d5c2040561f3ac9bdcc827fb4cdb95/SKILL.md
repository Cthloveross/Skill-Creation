---
name: credit-card-closure-retention
version: 1.0.0
description: Handle a verified customer's request to close a credit card by performing required closure eligibility checks, preventing repeat-retention abuse, logging an approved closure reason, making permitted retention offers, applying an accepted annual-fee waiver, or processing closure.
---

# Credit-card closure and retention

Use this Skill when a customer asks to close a specific Rho-Bank credit card. Treat each card account separately. Do not use an account ID inferred from transaction-card labels when the account record can be obtained directly.

## Guardrails

- Authenticate the customer and ensure the target account belongs to that customer before any account action.
- Before a payment, annual-fee waiver, or closure, verify **two of these four** profile fields with the customer: date of birth, email, phone number, and address. Retrieve the profile with `get_user_information_by_id`, compare the customer-provided values, obtain the current time using `get_current_time`, then call `log_verification` with every required field exactly as held in the profile plus that timestamp.
- Never disclose profile values merely to prompt verification. Ask the customer to provide them.
- Do not make a retention offer until every closure-eligibility requirement is satisfied. A request to pay a balance is not confirmation that the balance is now zero.
- Only use the normal declared banking tools. If a needed payment or account-information capability is absent, explain that it cannot be completed in the current session; do not claim payment or eligibility succeeded.
- Do not retry or repeat an action whose result is `UNKNOWN`. Explain the uncertainty and escalate if needed.

## Runtime tool preparation

The following are discoverable agent tools described by the procedure. Before calling each one, unlock it with `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool` using a JSON-string `arguments` value:

- `get_pending_replacement_orders_5765`
- `get_closure_reason_history_8293`
- `log_credit_card_closure_reason_4521`
- `apply_credit_card_account_flag_6147`
- `close_credit_card_account_7834`

Unlock only tools needed for the selected path. The discoverable tool call result, not a successful unlock, is the action outcome.

## Procedure

### 1. Locate and authenticate

1. Obtain a customer lookup value and use the appropriate lookup tool. Retrieve their card accounts using `get_credit_card_accounts_by_user`.
2. Ask the customer which listed card they mean if the request is ambiguous. Select exactly one matching account and retain its `credit_card_account_id` / `account_id` and its owner `user_id`.
3. Collect and verify two profile fields, then create the required `log_verification` audit record before taking any consequential action. If verification fails or cannot be completed, do not pay, waive, or close the card.

### 2. Check closure eligibility in this order

Perform all applicable checks against the selected account. If any check is blocked or ambiguous, tell the customer exactly what must be resolved and stop; do not log a retention reason or make an offer.

1. **Disputes:** call `get_user_dispute_history_7291` with `user_id`. Review records for active/pending/non-final disputes associated with the selected card where association is available. Any active or pending dispute blocks closure. If card association cannot be determined from the result, do not assume the selected account is clear; obtain clarification or escalate.
2. **Replacement cards:** call the unlocked `get_pending_replacement_orders_5765` with `{"credit_card_account_id":"..."}`. An empty list is clear. If any order is pending, shipped, or otherwise non-final, closure is blocked. Only delivered and cancelled orders are final.
3. **Account age:** compare `date_of_account_open` to the current date. The account must be at least 60 calendar days old.
4. **Balance:** the current account balance must be exactly $0.00. Pending transactions must also be allowed to post. If the customer wants to pay using another account, first perform identity verification and use only a declared, authorized payment workflow. Re-query the credit-card account after a reported successful payment before treating the balance as zero.

### 3. Prevent repeated retention attempts

For an eligible account, unlock and call `get_closure_reason_history_8293` with only:

```json
{"credit_card_account_id":"<selected account id>"}
```

If it returns a closure-reason record within the past year, make no retention offer. Say that you will proceed with the requested closure, then follow the closure path below. If it has no such record, continue.

### 4. Capture and log the reason

Ask why the customer wants to close if the reason is not already clear. Map the customer’s stated reason to exactly one accepted value:

`annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

Confirm an unclear mapping with the customer. Unlock and call `log_credit_card_closure_reason_4521` using **only** these arguments:

```json
{
  "credit_card_account_id":"<selected account id>",
  "user_id":"<authenticated user id>",
  "closure_reason":"<allowed value>"
}
```

Do not add notes, timestamps, or any other keys.

### 5. Address the reason and retain where accepted

Tailor the response:

- **annual_fee:** if account tenure is at least two years, offer a one-year annual-fee waiver as a loyalty benefit. If less than two years, offer a permanent downgrade to a no-annual-fee card while preserving account history, but only if a supported downgrade workflow is available.
- **not_using_card:** remind the customer of applicable benefits and suggest a recurring subscription to keep it active.
- **found_better_card:** ask which features matter and offer help applying for a comparable Rho-Bank card if one is known to be available.
- **unhappy_with_rewards:** review available bonus-category enrollment and suggest reward optimization based on spending patterns.
- **negative_experience:** apologize, gather details, and escalate to a supervisor if warranted. A goodwill credit may be considered only through an explicitly supported service-complaint workflow.

For a qualifying annual-fee customer who explicitly accepts the waiver, calculate the expiration date as one calendar year after the runtime current date in `MM/DD/YYYY` format. Use `scripts/waiver_expiration.py` rather than manual arithmetic. Then unlock and call `apply_credit_card_account_flag_6147` with:

```json
{
  "credit_card_account_id":"<selected account id>",
  "user_id":"<authenticated user id>",
  "flag_type":"annual_fee_waived",
  "expiration_date":"<script result expiration_date>",
  "reason":"loyalty_benefit"
}
```

Report success only after the tool reports success. An accepted tailored waiver retains the customer; do not add a second points/statement-credit offer.

If the customer still wants closure after addressing the concern, make exactly one tier-based retention offer: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium and above: 5,000 points or $50 statement credit. Do not apply any offer without explicit acceptance and a declared tool/workflow that supports it.

### 6. Close when requested

If prior retention history required skipping offers, or the customer declines the applicable offer and still requests closure, remind them:

- remaining rewards may be redeemed for 45 days after submitting the closure request, then are forfeited;
- a full annual-fee refund may be available if closure occurs within 37 days of the fee posting.

Then unlock and call `close_credit_card_account_7834` with:

```json
{"credit_card_account_id":"<selected account id>","user_id":"<authenticated user id>"}
```

Confirm closure only on a successful tool result. State that the customer will receive a confirmation email and final statement within several business days. If the customer is blocked by eligibility, do not call the closure tool.

## Helper script

`scripts/waiver_expiration.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{"current_time":"YYYY-MM-DD HH:MM:SS TZ"}
```

`current_time` may also be an ISO-like date/time beginning with `YYYY-MM-DD`. Output schema:

```json
{"expiration_date":"MM/DD/YYYY"}
```

It uses a calendar-year addition and converts February 29 to February 28 in a non-leap expiration year. Example runnable call:

```sh
printf '%s\n' '{"current_time":"2025-11-14 03:40:00 EST"}' | python3 scripts/waiver_expiration.py
```

Validate that the output contains a string matching `^\d{2}/\d{2}/\d{4}$` before placing it in the waiver call.
