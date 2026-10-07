---
name: credit-card-closure-with-payoff-and-retention
description: Safely process a customer's credit-card closure request when a balance may need to be paid from an eligible internal checking account and the closure-retention protocol applies. Use for verified customers requesting closure; it covers eligibility checks, payment authorization, retention handling, and final closure.
---

# Credit Card Closure With Payoff and Retention

Use this workflow for a credit-card account closure. Do not use account identifiers, balances, dates, account selections, or authorization from a prior case; obtain and validate them in the current interaction.

## Required controls before any banking action

Before any lookup that exposes customer account data, payment, account credit, account flag, downgrade, or closure:

1. Verify the customer's identity under standard procedures by having them confirm at least two of the four identity fields (date of birth, email, phone number, address) without disclosing the stored values. Retrieve the profile only as needed to compare the provided data.
2. Obtain the current time and call `log_verification` after successful verification. Supply every required verification field, the authenticated `user_id`, and the actual verification timestamp.
3. Confirm the authenticated customer is authorized for the requested account and that the account belongs to that customer. For a business card, also confirm the customer has authority to act for the business account.
4. Before a transfer, confirm source-account status, available balance, the current target-card balance, payment amount, account details, applicable limits or cutoffs, and the customer's explicit authorization. Never select a checking account or amount merely because it was used in another interaction.
5. Before closure, confirm the selected card, customer authority and ownership, product eligibility, and all closure prerequisites below. Do not close an account on ambiguous, stale, incomplete, or failed checks.

If identity, authority, ownership, authorization, or a required result cannot be established, stop the affected action and explain what is needed. Escalate through the normal support path when the issue cannot be resolved.

## Workflow

### 1. Identify the requested account and determine the current state

1. After verification, use `get_credit_card_accounts_by_user` with the authenticated `user_id`.
2. Ask the customer to identify the intended card if there is more than one plausible match. Confirm its account ID, card type/category, current balance, opening date, and rewards balance from the returned data.
3. Record the customer's stated reason. Map it to exactly one accepted closure reason:
   - `annual_fee`
   - `not_using_card`
   - `found_better_card`
   - `unhappy_with_rewards`
   - `simplifying_finances`
   - `negative_experience`
   - `other`

Use the customer's actual primary reason; do not log multiple values.

### 2. Pay an outstanding balance when the customer requests payment from checking

A card cannot be closed while it has an outstanding balance. If the balance is nonzero and the customer wants to pay from a Rho-Bank checking account:

1. Use `get_all_user_accounts_by_user_id_3847` with the authenticated `user_id`. Consider only checking accounts that are owned by the customer, active/eligible, and have sufficient available funds.
2. If more than one eligible checking account exists, have the customer choose the specific account. If none is eligible, do not attempt payment; explain that the balance must be paid by another valid method and posted before closure.
3. Re-fetch the credit-card account immediately before payment and state the exact current payoff amount. Obtain explicit authorization for that exact amount and selected checking account. The payment must be positive and no greater than both the available checking balance and current card balance.
4. Unlock `pay_credit_card_from_checking_9182` using `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` with this JSON object:
   ```json
   {
     "user_id": "<authenticated user id>",
     "checking_account_id": "<chosen checking account id>",
     "credit_card_account_id": "<target card account id>",
     "amount": 0.0
   }
   ```
   Replace the amount with the authorized current payoff amount; do not send `0.0`.
5. Read the confirmation and verify the returned checking and card balances. Re-query the card account if the confirmation does not unambiguously establish a zero balance. If payment remains pending or the balance is not exactly zero, do not continue to closure.

If the customer chooses to pay separately, stop closure processing until the payment has posted and a fresh lookup confirms a zero balance.

### 3. Verify closure eligibility

All conditions are mandatory:

- Outstanding balance is exactly `$0.00`.
- There are no active or pending transaction disputes on the target card.
- The account has been open at least 60 days.
- There is no pending replacement-card order.

Perform the checks as follows:

1. Derive account age from the account opening date and current date. Use `scripts/evaluate_closure_readiness.py` if helpful; it only evaluates supplied facts and does not perform banking actions.
2. Use `get_user_dispute_history_7291` with `user_id`. Review status and transaction/card context to determine whether an active or pending dispute belongs to the target card. Treat any non-final dispute associated with the target card as a blocker. If the response cannot be reliably associated with the target card, obtain a definitive account-level determination or do not close.
3. Use `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any order not clearly `delivered` or `cancelled` blocks closure. Record the outcome in case notes according to normal procedures.
4. If any requirement fails, explain the specific condition and required resolution. Do not make retention offers and do not call the closure tool.

### 4. Apply the retention protocol only after eligibility

1. Query `get_closure_reason_history_8293` with the target `credit_card_account_id` to determine whether this specific account has a closure-reason record in the past year.
2. If a prior record exists within the past year, skip retention offers and proceed to final pre-closure validation and closure if the customer still requests it.
3. Otherwise, unlock/call `log_credit_card_closure_reason_4521` with **only**:
   ```json
   {
     "credit_card_account_id": "<target card account id>",
     "user_id": "<authenticated user id>",
     "closure_reason": "<one allowed reason>"
   }
   ```
4. Address the stated concern without pressure. For `found_better_card`, ask which features motivated the alternative and, if a suitable Rho-Bank product is actually available, offer help applying for it rather than making unsupported comparisons.
5. If the customer still wants to close, make one retention offer based on the documented card tier: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium and above: 5,000 points or $50 statement credit. Determine tier from authoritative product information; do not infer it from an account nickname.
6. Wait for the customer's choice. Do not apply points, a statement credit, a fee waiver, or a downgrade unless the customer explicitly accepts the relevant offer and any required confirmation has been obtained.
7. For an accepted statement-credit retention offer, unlock `apply_statement_credit_8472` and call it with `user_id`, `credit_card_account_id`, the accepted positive amount, and `reason: "retention_offer"`. Confirm the result. Because a credit can change the balance, re-check the card and resolve any nonzero or credit balance under normal procedures before considering closure.
8. If the customer declines the offer, or retention is skipped because of prior attempts, thank them and continue without pressure. If they accept retention or no longer want closure, do not close the account.

Annual-fee concerns have additional options: a customer of at least two years may be offered a one-year annual-fee waiver using the documented flag procedure; one with less than two years may be offered a same-category no-annual-fee downgrade. Obtain explicit acceptance and follow the relevant product workflow before taking either action.

### 5. Final just-in-time validation and closure

Immediately before closure, re-fetch the credit-card account and re-confirm zero balance and ownership. Re-run `get_pending_replacement_orders_5765`; this check must be immediately before initiating closure. Confirm no active/pending target-card disputes and that the customer continues to request closure.

Unlock `close_credit_card_account_7834` if the runtime requires discoverable-tool access, then call it using exactly:

```json
{
  "credit_card_account_id": "<target card account id>",
  "user_id": "<authenticated user id>"
}
```

Only report success after the closure tool confirms it. If it fails, do not represent the account as closed; communicate the returned issue and resolve or escalate appropriately.

### 6. Required customer communication after confirmed closure

Tell the customer that they will receive a confirmation email and final statement within several business days. State that unredeemed rewards may be redeemed for 45 days after the closure request and are forfeited afterward. If an annual fee posted within 37 days of closure, explain that a full refund may be available; do not promise a refund without verifying its posting date. Where relevant, explain that closing a card can reduce available credit and affect utilization and credit score.

## Discoverable-tool handling

For an internal tool that is exposed through the discoverable-tool runtime, unlock it before its first call in the session with `unlock_discoverable_agent_tool`, then call it using `call_discoverable_agent_tool` and a JSON-string `arguments` value. Use the exact documented tool names and argument names. Do not add arguments to `log_credit_card_closure_reason_4521`, and do not retry a value-changing action merely because its result is ambiguous; first determine whether it completed.

## Optional readiness helper

`scripts/evaluate_closure_readiness.py` reads JSON from stdin and emits JSON to stdout. It accepts:

```json
{
  "as_of_date": "YYYY-MM-DD",
  "account_open_date": "YYYY-MM-DD",
  "balance": 0.0,
  "target_active_disputes": [{"dispute_id": "...", "status": "open"}],
  "replacement_orders": [{"order_id": "...", "status": "pending"}]
}
```

`target_active_disputes` must contain only disputes already confirmed to belong to the target card. The output contains `eligible`, `account_age_days`, and `blockers`. Validate its output against fresh tool data; it cannot establish identity, ownership, dispute-to-card association, authorization, or tool success.
