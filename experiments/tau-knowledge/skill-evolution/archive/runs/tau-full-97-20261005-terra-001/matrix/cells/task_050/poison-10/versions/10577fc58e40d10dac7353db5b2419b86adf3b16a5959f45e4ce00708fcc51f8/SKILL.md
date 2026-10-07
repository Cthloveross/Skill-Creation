---
name: credit-limit-increase-processing
description: Process a verified cardholder's credit-limit increase (CLI) request using the required submission-first eligibility workflow, tier thresholds, required updated-income collection for Gold Rewards, discoverable banking tools, and an auditable approval or denial. Use for Entry-tier, Mid-tier, and Premium-tier CLI requests when account data and the customer request are available.
---

# Credit Limit Increase Processing

## Scope and prerequisites

Use this Skill only for the account owner or an authorized account manager. Before accessing or changing account information, verify the claimant using two customer-confirmed identity fields out of date of birth, email, phone number, and address. Do not treat values returned by an account lookup as customer confirmation. After two fields match, call `log_verification` with all required fields and the current timestamp.

Obtain and confirm:

- the requested **dollar increase** (a positive integer) and the reason for it;
- the account and user identifiers for the requested card;
- the card tier and current credit limit; and
- updated income information when the card's terms require it.

For a **Gold Rewards Card**, updated income information is required for CLI review. Ask the customer for their current/updated income information before the final CLI decision, even if another eligibility issue may lead to denial. Record only the information necessary for review; do not invent an income value. If the customer does not provide it, explain that the review cannot be completed without updated income information and treat the income-review requirement as unresolved. Do not state that the customer has a confirmed policy failure merely because the information is unavailable.

If identity is not verified or the request amount is not clear, do not submit or decide the CLI. Ask only for the missing information. Do not expose profile values in order to obtain confirmation. Gold Rewards Card is Premium-tier. For another card type, determine its tier from applicable account/card information; do not guess a tier.

## Policy constants

| Tier | Minimum age | Cooldown | Utilization must be below | Consecutive on-time months | Max increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | 90% | 3 | 50% of current limit |

“Below” is strict: utilization equal to the threshold fails. A cooldown is measured from the submission date of the most recent **approved** CLI request; denied requests do not start a cooldown. The customer is eligible on the date the required age or cooldown is fully reached.

## Required execution workflow

1. **Verify and collect.** Complete identity verification and obtain the account, tier, current limit, requested increase, and reason. Use `get_current_time` for the verification/audit time and decision calculations. For Gold Rewards, request updated income information as part of the review collection. If it is not initially supplied, ask for it before any final decision.
2. **Validate the amount before submitting.** Compute the maximum increase from the current limit and tier. If the requested integer dollar amount exceeds the maximum, do **not** submit a CLI request and do not create an approval/denial decision. Tell the customer the maximum permitted increase and ask whether they want to request that amount or a lower amount. A valid amount may proceed.
3. **Submit first.** For a valid amount, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and `requested_increase_amount`. Record its result. All following eligibility checks occur after this submission.
4. **Run every eligibility check, even if an earlier one fails.** Unlock and call:
   - `get_credit_limit_increase_history_4829` with the account ID; inspect the most recent approved request for cooldown.
   - `get_user_dispute_history_7291` with the user ID; any non-final dispute (such as `open` or `under_review`) is active. Treat an unfamiliar or ambiguous status as unresolved until clarified.
   - `get_pending_replacement_orders_5765` with the account ID; a replacement blocks processing if any order is not clearly `delivered` or `cancelled`.
   - `get_payment_history_6183` with the account ID and the required tier-specific number of months; require all requested months to be consecutive and on time.

   Also inspect reliable account data for account-open date, current balance/credit limit, and account standing/past-due balance. Calculate utilization as `current_balance / credit_limit * 100`. A zero current balance alone does not prove that the account is current; obtain or inspect an explicit current-standing or past-due field when available.

   Do not approve on missing, contradictory, or unparseable required evidence. For Gold Rewards, confirm updated income information has been provided; if it has not, ask for it before deciding. If required evidence remains unavailable after it is requested, record the unresolved check and use `other` for a post-submission denial rather than inventing a result.
5. **Record exactly one final decision for a submitted request.** If every check, including required updated-income review, passes, unlock and call `approve_credit_limit_increase_5847` with account ID, user ID, and `new_credit_limit = current_credit_limit + requested_increase_amount` as a numeric value. If any check fails, unlock and call `deny_credit_limit_increase_5848` with account ID, user ID, and the applicable enum:
   - account age → `insufficient_account_age`
   - approved-request cooldown → `cooldown_period_active`
   - active dispute → `pending_disputes`
   - non-final replacement order → `pending_replacement_card`
   - confirmed non-current account or confirmed past-due balance → `past_due_balance`
   - utilization at or above threshold → `high_utilization`
   - insufficient/non-consecutive on-time payments → `insufficient_payment_history`
   - missing/ambiguous standing evidence, missing required updated income, or other unresolved required evidence → `other`

   The pre-submission excessive-amount case is `requested_amount_exceeds_limit` conceptually, but must not be submitted or denied until the customer supplies a compliant amount, because the workflow forbids submitting it.
6. **Communicate.** Confirm an approval and the new total limit. For a denial, state the customer-safe reason and useful next step: the eligibility date for age/cooldown, resolve disputes or replacement orders, bring the account current, lower utilization below (not merely to) the threshold, establish the required on-time history, or provide the requested updated income information. For `other`, accurately say that a required review item could not be confirmed or completed; never describe an unavailable account-standing check as a confirmed past-due balance. Do not expose internal-only audit details or other customers' data.

## Using the packaged assessment helper

`scripts/assess_cli.py` is deterministic planning and validation only. It never calls banking tools and does not perform any bank action. Supply normalized facts after required tool calls; it writes one JSON assessment to stdout.

Input schema (all values are JSON):

```json
{
  "current_date": "YYYY-MM-DD or timestamp",
  "card_tier": "entry-tier | mid-tier | premium-tier",
  "current_credit_limit": 1000,
  "requested_increase_amount": 100,
  "account_open_date": "YYYY-MM-DD",
  "current_balance": 0,
  "is_past_due": false,
  "history": [{"submitted_at": "YYYY-MM-DD", "status": "approved"}],
  "disputes": [{"status": "closed"}],
  "replacement_orders": [{"status": "delivered"}],
  "consecutive_on_time_months": 3,
  "income_information_required": true,
  "updated_income_provided": true
}
```

`is_past_due`, the three record collections, `consecutive_on_time_months`, and, when applicable, `updated_income_provided` may be omitted only while evidence is unavailable. The helper reports them as `unknown`, which is not approval-eligible. Set `income_information_required` to `true` for Gold Rewards and any other product whose applicable terms require income review. `history` must contain all returned CLI records relevant to the most recent approved submission. The output includes the pre-submission action, every check result, final decision, denial reason if any, and approved new limit if applicable.

Use the output to validate calculations and document the case, then perform the actual banking-tool calls in the workflow. Meaningful validation includes confirming that an excessive amount yields `request_adjustment`; that every required eligibility check is present after a valid amount; that required-but-unprovided income yields an unresolved `income_information` check and no approval; and that an approved numeric limit equals current limit plus requested increase.
