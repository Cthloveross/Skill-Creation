---
name: credit-card-account-closure
version: 1.0.0
description: Safely process a verified customer's request to close a credit card account. Use for account identification, mandatory closure eligibility checks, balance-payoff routing, retention handling, closure execution, and required rewards/annual-fee disclosures.
---

# Credit Card Account Closure

## Scope and safety gates

Use this Skill only for a credit-card closure request. Do not close an account, make a retention offer, log a closure reason, or move money until the customer has passed standard identity verification.

Identity verification requires confirmation of **two of four** customer fields: date of birth, email, phone number, and address. A name, a prior lookup, or data visible to the agent is not itself a confirmation. Once two fields are confirmed, call `log_verification` with all required customer profile fields and a current timestamp from `get_current_time`.

Identify the requested account from `get_credit_card_accounts_by_user`. Confirm the selected account is the requested card type. If multiple possible accounts exist, ask the customer to identify the intended account; never select by balance or age alone.

## Required closure eligibility

The target account can be closed only when all of these are currently true:

1. Outstanding balance is exactly `$0.00`.
2. The target account has no active or pending transaction disputes.
3. The account has been open at least 60 days.
4. There are no pending replacement-card orders. An order blocks closure unless it is clearly `delivered` or `cancelled`; `pending`, `shipped`, missing, or ambiguous status blocks closure.

Do not offer retention or call the closure tool when any requirement is false or cannot be confirmed. Explain the specific unresolved item(s) and what must happen first.

Use `scripts/closure_plan.py` to normalize the account facts and produce a deterministic readiness assessment. It is a planning/validation aid only; it does not call banking tools or change accounts.

## Runtime workflow

1. **Verify and identify**
   - Obtain two identity confirmations, retrieve the current time, and log verification.
   - Retrieve the customer’s card accounts and select the specifically requested account.
   - Use only the authenticated customer's `user_id` and the selected account's `account_id` in all subsequent actions.

2. **Assess eligibility before retention**
   - Confirm the current account balance and account-open date from a current account lookup.
   - Check disputes with `get_user_dispute_history_7291` using `user_id`. The result is user-wide: determine whether each active/pending dispute belongs to the target account using reliable account/card context. If the association cannot be determined, treat dispute eligibility as unconfirmed rather than assuming it is clear.
   - Immediately before initiating the closure workflow, call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Proceed only if the result is empty or every returned order is clearly delivered or cancelled.
   - Where the runtime exposes these specialized tools through the discoverable-agent interface, unlock the named tool before calling it and pass only its documented arguments.

3. **If a balance remains**
   - Tell the customer the exact balance must be paid in full and that closure cannot proceed until it posts as `$0.00`.
   - If the customer asks to pay from an eligible Rho-Bank checking account, first verify identity, locate both accounts, confirm sufficient checking funds, confirm the exact payment amount, and obtain transfer authorization.
   - Then unlock and call `pay_credit_card_from_checking_9182` with exactly `user_id`, `checking_account_id`, `credit_card_account_id`, and positive `amount`. The amount may not exceed either checking funds or the card balance.
   - Re-query the credit-card account after payment. Do not continue until the returned balance is exactly zero. If the runtime cannot provide or verify the checking account and its balance, do not fabricate an account ID or execute a payment.

4. **Retention protocol — only after eligibility is confirmed**
   - Call `get_closure_reason_history_8293` with only `credit_card_account_id` to determine whether that account has closure-reason records within the last year.
   - If records exist within the past year, skip retention, tell the customer you will proceed with closure, and continue to step 5.
   - Otherwise, obtain the customer's reason if it is not already clear, map it to exactly one allowed value, and call `log_credit_card_closure_reason_4521` with only `credit_card_account_id`, `user_id`, and `closure_reason`.
   - Allowed reason values are: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.
   - Address the concern. For `found_better_card`, ask which features matter and offer help finding a comparable Rho-Bank card if available. For `not_using_card`, remind the customer of relevant benefits and suggest a recurring subscription if appropriate.
   - For annual-fee concerns only: customers with at least two years' tenure may be offered a one-year fee waiver. Apply it only after acceptance, using `apply_credit_card_account_flag_6147` with exactly `credit_card_account_id`, `user_id`, `flag_type: "annual_fee_waived"`, an `expiration_date` one year from today in `MM/DD/YYYY`, and `reason: "loyalty_benefit"`. Customers with less than two years' tenure may instead be offered a permanent no-annual-fee downgrade preserving account history.
   - If the customer still wishes to close, make one tier-based retention offer: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium and above: 5,000 points or $50 statement credit. Do not pressure the customer. If declined, proceed.

5. **Close the account**
   - Reconfirm the replacement-order result immediately before closure if any elapsed time or intervening operation could have changed it.
   - Unlock `close_credit_card_account_7834` if required by the runtime, then call it with exactly `credit_card_account_id` and `user_id`.
   - Do not add undocumented arguments. Report only the actual tool result as confirmation.

6. **Required post-closure communication**
   - Tell the customer that remaining rewards may be redeemed for **45 days after the closure request** and are forfeited afterward.
   - Explain that a full annual-fee refund may be available only when closure occurs within **37 days of the annual-fee posting**. Do not promise a refund without a confirmed posting date and closure outcome.
   - Inform the customer that a confirmation email and final statement will arrive within several business days.
   - When relevant, explain that closing a card may reduce total available credit and affect utilization, particularly for a high-limit or old account.

## Planning helper

Run the helper with JSON on stdin and read its JSON result from stdout:

```text
python3 scripts/closure_plan.py <<'JSON'
{
  "current_time": "2025-01-01 12:00:00 EST",
  "identity_verified": true,
  "account": {
    "account_id": "runtime-selected-account-id",
    "user_id": "authenticated-user-id",
    "card_type": "card type from current lookup",
    "date_of_account_open": "MM/DD/YYYY",
    "current_balance": "$0.00",
    "reward_points": 0
  },
  "dispute_check": {"performed": true, "active_for_target": false},
  "replacement_check": {"performed": true, "orders": []},
  "history_check": {"performed": false}
}
JSON
```

### Helper input schema

- `current_time` (required string): current date/time. ISO-like timestamps and `MM/DD/YYYY` dates are accepted.
- `identity_verified` (required boolean): true only after two-factor confirmation and verification logging.
- `account` (required object): requires `account_id`, `user_id`, `card_type`, `date_of_account_open`, and `current_balance`; `reward_points` and `annual_fee_posted_date` are optional.
- `dispute_check` (required object): `performed` boolean and, when performed, `active_for_target` boolean. Set it only after target-account association has been reliably reviewed.
- `replacement_check` (required object): `performed` boolean and, when performed, an `orders` array. Each order may contain `status`.
- `history_check` (optional object): used only after eligibility. It has `performed` and, if performed, `records_within_past_year` booleans.

The helper emits `ok`, `closure_ready`, individual checks, blockers, recommended next steps, reward redemption information, and annual-fee-refund status. `closure_ready: true` means only that the supplied eligibility facts meet the closure prerequisites; the executor must still follow the retention/decision workflow before closing unless prior-attempt history permits skipping it.

Validate that `ok` is true, every required check reports `status: "pass"`, and `closure_ready` is true before treating it as eligibility confirmation. An `unknown` or `fail` status is a blocker.