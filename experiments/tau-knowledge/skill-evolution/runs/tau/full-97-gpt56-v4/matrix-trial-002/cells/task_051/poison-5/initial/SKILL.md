---
name: credit-limit-increase-processing
description: Process a credit-limit-increase (CLI) request for a credit-card customer. Use when a customer requests a CLI or asks whether a requested increase is eligible; validates tier caps, submits a valid request before the prescribed eligibility review, then records an approval or a single specific denial.
---

# Credit Limit Increase Processing

## Scope and prerequisites

Use this Skill for credit-card CLI requests. Do not treat a request for a card payment or an internal transfer as a CLI action: those require a known source account and an applicable banking/payment tool. Never invent a payment, transfer, account identifier, tool, or tool result.

Before disclosing account-specific details or taking an account-changing action, verify the customer under the normal identity-verification process. Obtain confirmation of two of date of birth, email, phone number, and address; retrieve the user record; then call `log_verification` with all required record fields and the current timestamp from `get_current_time`. A name alone identifies a possible record but is not sufficient verification.

Identify the account using the verified `user_id` and `get_credit_card_accounts_by_user`. Confirm the relevant account, its current limit, balance, opening date, status, and past-due amount. If there is more than one plausible card, ask the customer to identify the card.

## Tier rules

Map the card tier to the following policy. Bronze/entry products must be treated as Entry-tier only when the product information establishes that mapping; do not infer a tier from color or marketing name without support.

| Tier | Minimum age | Cooldown after a prior **approved** CLI | Utilization requirement | On-time-payment months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | strictly below 70% | 6 consecutive | 25% of current limit |
| Mid-tier | 90 days | 90 days | strictly below 80% | 3 consecutive | 50% of current limit |
| Premium-tier | 60 days | 60 days | strictly below 90% | 3 consecutive | 50% of current limit |

Utilization is `current_balance / current_credit_limit * 100`. Equality with the utilization threshold fails. A limit request at exactly the tier cap is permitted. The requested increase must be a concrete dollar amount and the new total limit is `current limit + requested increase`.

Use `scripts/cli_rules.py` for repeatable date, utilization, and cap calculations. It evaluates supplied facts only; it does not establish account facts or make banking actions.

## Required workflow and ordering

1. **Obtain a definite, permitted request before submission.** Ask for a dollar increase if the customer provided only a percentage, range, or a desired total that cannot be unambiguously converted. Calculate the tier maximum from the current limit. If the requested increase exceeds it, tell the customer the maximum dollar amount and ask whether they want that amount or another valid amount. Do **not** submit an over-limit request. If the customer declines or does not provide a valid revised amount, end the CLI workflow without submitting or denying a request.

2. **Submit the valid request first.** After the customer confirms a valid dollar amount, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`. This formal submission must occur before the eligibility review. Record the result. Do not submit a duplicate if the result is unknown or the tool reports that a request was created; instead resolve the status through the normal supported path.

3. **Perform every eligibility check after submission.** Unlock each specialized tool before calling it.
   - Calculate account age as full elapsed calendar days from the account-open date to the current date/time. It must meet the tier minimum.
   - Unlock and call `get_credit_limit_increase_history_4829` with the credit-card account ID. Inspect prior request dates and outcomes. Only an earlier **approved** request starts the tier cooldown; denied requests do not. A customer qualifies only after the required number of full days has elapsed since that earlier submission. Do not mistakenly treat the request just submitted in step 2 as a prior approved request.
   - Unlock and call `get_user_dispute_history_7291` with `user_id`. Any active/non-final dispute fails the no-pending-disputes requirement. Closed/final disputes alone do not.
   - Unlock and call `get_pending_replacement_orders_5765` with the credit-card account ID. An empty list passes. If any order is not clearly delivered or cancelled (for example pending or shipped), fail this check.
   - Check that the account is current and has no past-due balance. An inactive or otherwise non-current account must not be treated as good standing; if a required policy reason is unavailable, use `other` rather than falsely claiming a supported reason.
   - Calculate current utilization from the balance and current limit. It must be strictly below the tier threshold at review time.
   - Unlock and call `get_payment_history_6183` with the credit-card account ID and exactly the tier-required number of months. Confirm every required consecutive month is on time. Missing, late, ambiguous, or insufficient history fails this check.

4. **Record one decision.** If and only if every check passes, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit` equal to the current limit plus the confirmed increase. Otherwise unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the most applicable allowed denial reason:
   - account age: `insufficient_account_age`
   - approved-request cooldown: `cooldown_period_active`
   - active dispute: `pending_disputes`
   - non-final replacement order: `pending_replacement_card`
   - past-due/non-current balance: `past_due_balance`
   - utilization at or above the threshold: `high_utilization`
   - payment-history failure: `insufficient_payment_history`
   - a request that somehow reached decision while above its cap: `requested_amount_exceeds_limit`
   - unsupported/ambiguous failure: `other`

   Complete all checks for the audit record even when an earlier failure is found. Make exactly one terminal approval or denial for the submitted request. Do not approve based only on a customer statement that they intend to pay down a balance.

5. **Communicate clearly.** For approval, confirm the approved increase and new total credit limit. For denial, explain the applicable reason and an actionable next step. For utilization, state that it must be *below* the applicable percentage, and distinguish a potential later application from the already-recorded denial. For cooldown, provide the reapplication date only when the prior approved-request date is known.

## Payments and transfer requests during a CLI conversation

A customer may ask to pay the card balance from checking in order to lower utilization. That is a separate request. Require an identified source checking account and confirm it is open, in good standing, and has sufficient funds. Internal transfers are free and can be completed through the customer’s digital banking or the appropriate supported payment/transfer workflow. Do not use a CLI tool to move money and do not infer which checking account to debit. If the customer does not provide a usable source account or the requested payment is out of scope, explain that no payment was made and that the CLI eligibility review uses the balance currently on record. A later payment does not retroactively change an already submitted CLI decision.

## Script interface

Run `scripts/cli_rules.py` by passing one JSON object on stdin. Required keys are `tier`, `current_limit`, `current_balance`, and `requested_increase`; optional keys are `account_open_date`, `as_of`, and `prior_approved_request_date`. Dates accept `YYYY-MM-DD`, `MM/DD/YYYY`, or an ISO-like timestamp beginning with one of those dates. The script emits JSON containing the selected rules, requested amount validation, utilization, and available date-based checks. A successful calculation is not an eligibility decision: tool-based dispute, replacement, standing, payment-history, and request-history evidence remains required.

Example runtime input (illustrative only):
```json
{"tier":"Entry-tier","current_limit":4000,"current_balance":1200,"requested_increase":800,"account_open_date":"2024-01-01","as_of":"2024-06-01"}
```

Validate the script result before relying on it: `requested_within_cap` must be true before submission, `utilization_below_threshold` must be true for that criterion, and a non-null `account_age_days` must meet `minimum_account_age_days`. Reject malformed values rather than silently rounding them.
