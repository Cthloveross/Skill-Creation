---
name: credit-card-account-closure
version: 1.0.0
description: Handle a customer's request to close a credit card account, including identity verification, eligibility checks, pending-replacement review, retention handling, and closure disclosures. Use for authenticated Rho-Bank credit-card closure requests.
---

# Credit Card Account Closure

Use this Skill when a customer asks to close a credit card account. Treat each account independently and only act on the account the verified customer identifies. Do not close an account merely because it is listed in the customer's profile.

## Required information and tools

Obtain or look up the authenticated customer's `user_id`, then use `get_credit_card_accounts_by_user` to identify the requested account and its current balance and opening date. Use the exact account-level ID returned by that lookup.

Before any irreversible action, verify identity under the standard procedure:

1. Retrieve the customer's profile using an available user lookup.
2. Ask the customer to confirm at least two of these profile fields: date of birth, email, phone number, and address. An identifier supplied solely to locate the profile is not itself a completed two-field verification.
3. Compare the supplied fields with the profile. If two fields match, get the current timestamp with `get_current_time` and call `log_verification` with all required profile fields, the `user_id`, and that exact timestamp.
4. If verification does not succeed, do not disclose account details or perform retention, downgrade, waiver, or closure actions. Request correct verification information or transfer when appropriate.

## Eligibility gate

Eligibility must be established **before** retention activity or the closure action. A closure requires all of the following:

- Current outstanding balance is exactly `$0.00`.
- There are no active or pending transaction disputes.
- The account has been open at least 60 days.
- There are no pending replacement-card orders. A delivered or cancelled order is final; any other order status blocks closure.

Use `get_pending_replacement_orders_5765` immediately before a closure workflow. Unlock it first with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` using only `credit_card_account_id`. Interpret an empty order collection as clear; if an order response is ambiguous, retry or escalate rather than assuming it is clear.

Review available account/transaction information for disputes. If the available tools or records cannot establish dispute status, do not represent the account as eligible or call the closure tool; explain that closure must wait until any pending dispute status is resolved/confirmed.

If any gate fails, state the specific blocking condition and required remedy. Do not make a retention offer, log a closure reason, apply a waiver, downgrade, or call the closure tool while blocked. A balance must be paid in full after pending transactions post; do not attempt to take a payment unless a separately authorized payment workflow is available.

`scripts/closure_plan.py` can evaluate supplied account facts consistently, but it only returns a recommendation and never calls banking tools.

## Eligible-account retention workflow

Once eligibility is confirmed, use this sequence.

1. Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id`.
2. If it returns closure-reason records within the past year, skip all retention offers and proceed to closure if the customer still requests it.
3. Otherwise, obtain the customer's reason if it is not already clear. Normalize it to exactly one permitted value:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
4. Unlock and call `log_credit_card_closure_reason_4521` using exactly `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add parameters.
5. Address the reason, then make at most one appropriate retention offer if the customer still wishes to close:
   - Entry tier: 500 points or $5 statement credit.
   - Mid tier: 2,000 points or $20 statement credit.
   - Premium and above: 5,000 points or $50 statement credit.

For an `annual_fee` reason, first determine tenure from the account opening date. A customer with at least two years of tenure may be offered a one-year fee waiver. If accepted, unlock and call `apply_credit_card_account_flag_6147` with `credit_card_account_id`, `user_id`, `flag_type` = `annual_fee_waived`, `reason` = `loyalty_benefit`, and an `expiration_date` exactly one calendar year after the current date in `MM/DD/YYYY` format. Use the helper to calculate this date rather than estimating it. For tenure below two years, offer a same-category no-fee downgrade instead: `Bronze Rewards Card` for personal accounts or `Business Bronze Rewards Card` for business accounts. Explain preserved history/credit line and changed benefits, obtain consent, then use `downgrade_credit_card_3847` with the exact target type.

Do not pressure a customer who declines a retention option. If they decline, or retention is skipped due to prior closure-reason history, proceed to closure.

## Closing and customer communication

Unlock `close_credit_card_account_7834` and call it through `call_discoverable_agent_tool` only after verification and every eligibility check is clear. Supply the verified `credit_card_account_id` and matching `user_id` exactly as required by the tool. Report the actual tool result; never claim success before it returns success.

When closure is submitted or completed, tell the customer:

- Remaining rewards may be redeemed for 45 days after the closure request, then are forfeited.
- A full annual-fee refund applies only when closure occurs within 37 days of the annual-fee posting.
- A confirmation email and final statement arrive within several business days.
- Closing can reduce available credit and affect utilization and credit score.

If the customer only needs an explanation of requirements, provide the applicable requirements without attempting account actions. If a tool fails, returns conflicting data, or a required status cannot be established, do not retry an action that may have completed; explain the limitation and transfer using the most applicable transfer reason if needed.

## Helper usage

Run the helper with JSON on standard input and read JSON from standard output:

```json
{
  "account_open_date": "MM/DD/YYYY",
  "current_balance": "$0.00",
  "as_of_date": "YYYY-MM-DD",
  "has_pending_dispute": false,
  "replacement_order_statuses": [],
  "annual_fee_reason": true
}
```

Example command in a compatible executor:

```sh
python3 scripts/closure_plan.py <<'JSON'
{"account_open_date":"01/01/2020","current_balance":"0.00","as_of_date":"2025-01-01","has_pending_dispute":false,"replacement_order_statuses":[],"annual_fee_reason":true}
JSON
```

Validate that `eligible_to_close` is true before using its retention recommendations. `unknown` dispute or replacement status is intentionally treated as a blocker. The script rejects malformed dates and balances instead of guessing.
