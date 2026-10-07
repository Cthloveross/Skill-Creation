---
name: credit-card-closure-with-payoff-and-retention
description: Process a verified customer's credit-card closure request, including an authorized checking-funded payoff, mandatory eligibility checks, retention protocol, and compliant closure communication. Use for Rho-Bank credit-card account closures; never use it to close an account without verified identity and all eligibility conditions.
---

# Credit-card closure with payoff and retention

## Scope and principles

Use the normal banking tools declared in the runtime. Specialized tools named below must first be enabled with `unlock_discoverable_agent_tool`, then invoked through `call_discoverable_agent_tool` using exactly the documented arguments. Tool recommendations or script output do not execute banking actions.

Do not guess an account ID, checking account, card tier, eligibility result, tool result, or product benefit. Do not close an account while any required check is missing, ambiguous, or failed. If a state-changing call returns an unknown/ambiguous result, do not repeat it; investigate through supported records or escalate as a technical-system issue.

## Required workflow

### 1. Identify the customer, target account, and verify identity

1. Locate the user using information supplied by the customer and list that user's credit-card accounts. Confirm the requested card with the customer if more than one account could match.
2. Verify **two of the four** identity fields against the profile: date of birth, email, phone number, and address. A name alone is not one of these two fields. Ask for only the missing verification information necessary to reach two matching fields.
3. Obtain the current timestamp with `get_current_time` and call `log_verification` only after the two-field verification succeeds. Populate every required field of that tool from the verified profile, with the retrieved timestamp.
4. Confirm that the selected credit-card account belongs to the authenticated user. Stop and escalate rather than act on a mismatch.

### 2. Resolve any balance only with authorization

A closure requires a current outstanding balance of exactly $0.00. Refresh the target card balance before acting.

If there is a positive balance and the customer asks to pay it from checking:

1. Ensure the customer has expressly authorized the amount. If authorization is not clearly for the full current balance, ask for the amount and confirmation.
2. Use the declared checking-account lookup capability to identify a checking account owned by the verified user and confirm available funds cover the payment. If the runtime lacks a supported way to identify/verify a checking account, do not fabricate an ID or payment; explain that payment cannot be completed through this workflow and escalate if needed.
3. Enable `pay_credit_card_from_checking_9182` and call it with exactly `user_id`, `checking_account_id`, `credit_card_account_id`, and positive dollar `amount`. The amount must not exceed either the confirmed checking balance or the refreshed card balance.
4. Read the payment confirmation and refresh the credit-card account. Continue only when the target balance is $0.00. A failed, partial, or unclear payment blocks closure.

Never debit a checking account merely because the customer wants closure; there must be explicit authorization and sufficient funds.

### 3. Perform closure eligibility checks

Complete these checks immediately before the retention/closure decision. Account age may be calculated from the profile's account-open date and the current date. The included helper can be used to conservatively summarize structured results, but the executor remains responsible for collecting live tool results.

1. **Disputes:** Enable and call `get_user_dispute_history_7291` with `user_id`. Any active or pending dispute blocks closure. Treat `open`, `pending`, and `under_review` as blocking. Do not treat an unfamiliar status as cleared without reliable evidence that it is fully resolved.
2. **Replacement cards:** Enable and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty result passes. If orders are returned, every order must clearly be `delivered` or `cancelled`; any `pending`, `shipped`, unknown, or ambiguous order blocks closure.
3. **Account age:** The account must have been open at least 60 days at the time of the request.
4. **Balance:** Reconfirm the target account balance is $0.00 after any payoff.

If any condition fails, tell the customer which condition must be resolved and do not make retention offers or call the closure tool. Do not disclose irrelevant details of disputes or other accounts.

### 4. Apply the retention protocol only after eligibility passes

1. Enable and call `get_closure_reason_history_8293` with `credit_card_account_id` to check the prior year.
2. If a closure-reason record exists within the past year, skip the retention flow and proceed to closure if the customer still wants it. Do not pressure the customer.
3. If there is no such record, obtain the customer's reason and map it to exactly one permitted value: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`. Enable and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
4. Address the reason before making an offer:
   - For `found_better_card`, ask which features matter and offer help applying for a Rho-Bank alternative only when a supported source confirms it offers comparable or better benefits. Do not claim product features that have not been verified.
   - For `annual_fee`, a customer of at least two years may receive the documented one-year waiver through `apply_credit_card_account_flag_6147` only if the customer accepts it. Use `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from today in `MM/DD/YYYY`. For less than two years, discuss the documented no-annual-fee downgrade rather than inventing an offer.
   - For other documented reasons, provide the applicable non-binding guidance: missed benefits/recurring use, comparable-card discussion, bonus-category/reward maximization, or apology and appropriate escalation for a negative experience.
5. If the customer still wants to close, make exactly one tier-based retention offer: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium-and-above: 5,000 points or $50 statement credit. Determine the card tier from reliable runtime information; do not infer it from a card name. If no supported offer-fulfillment tool exists, present the offer but do not claim it has been applied.
6. Wait for the customer's decision. A continued wish to close before the offer is not a rejection of the offer. If the customer accepts retention, do not close the account. If they decline (or prior history required skipping retention), continue without pressure.

### 5. Close and communicate

1. Immediately recheck any time-sensitive condition if the workflow was delayed or a relevant account state changed.
2. Enable `close_credit_card_account_7834` and call it with exactly `credit_card_account_id` and `user_id`.
3. Only report the account closed after a successful tool response. On success, state that a confirmation email and final statement will arrive within several business days.
4. Also state that unredeemed rewards may be redeemed for 45 days after the closure request and are forfeited afterward. If an annual fee was posted recently, explain conditionally that a full refund may apply when closure occurs within 37 days of the fee charge; do not promise a refund unless the posting date and eligibility are confirmed.

If a customer asks for a human agent or a technical limitation prevents a compliant completion, use the appropriate transfer reason. For a closure request that cannot be completed by this workflow, `account_closure_request` is appropriate; for a tool/platform failure, use `technical_system_error`.

## Helper usage

`scripts/evaluate_closure_eligibility.py` accepts a JSON object on stdin and emits a JSON eligibility summary on stdout. It performs only a conservative local check; it does not call tools or authorize actions.

Input schema:

```json
{
  "current_date": "YYYY-MM-DD",
  "account_open_date": "MM/DD/YYYY or YYYY-MM-DD",
  "balance": 0,
  "disputes": [{"status": "closed"}],
  "replacement_orders": [{"status": "delivered"}]
}
```

`disputes` and `replacement_orders` must be actual lists from the relevant live checks. An omitted or malformed result is reported as a blocker. Example runnable call after converting live results to this schema:

```sh
python3 scripts/evaluate_closure_eligibility.py <<'JSON'
{"current_date":"2025-01-01","account_open_date":"2024-01-01","balance":0,"disputes":[],"replacement_orders":[]}
JSON
```

A valid result has `eligible: true`, no `blockers`, an account age of at least 60 days, zero balance, no unresolved disputes, and only final/no replacement orders. Before a closure call, reconcile this summary with the latest live account and tool responses.
