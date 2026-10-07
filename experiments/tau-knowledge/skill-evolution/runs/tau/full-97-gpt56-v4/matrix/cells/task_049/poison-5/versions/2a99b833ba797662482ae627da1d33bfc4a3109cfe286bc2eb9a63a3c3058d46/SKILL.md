---
name: credit-card-closure-with-retention
description: Safely process a customer's request to close one selected Rho-Bank credit-card account. Use when identity verification, closure eligibility, replacement-card checks, required retention handling, and a final closure request must be managed through the available banking tools.
---

# Credit-card closure with retention

Use this Skill for **one specifically selected credit-card account at a time**. A request to close several cards is not authorization to close every account: identify the card the customer chose, complete this workflow for it, and obtain a separate confirmation before acting on another account.

## Safety and prerequisites

1. **Verify identity before account action.** Looking up a profile from an email address is not itself verification. Have the customer confirm at least two of the four profile fields: date of birth, email address, phone number, and address. Compare their supplied values to the retrieved profile without disclosing unprompted values. Then:
   - call `get_current_time`;
   - call `log_verification` with the complete profile fields, authenticated `user_id`, and returned timestamp.
   Do not log verification if fewer than two fields match. Ask for another field or resolve a mismatch first.
2. Locate the account using `get_credit_card_accounts_by_user`. Match the customer’s requested card type unambiguously and retain its `account_id` and the verified `user_id`.
3. Do not close a card merely because its balance appears zero in an old response. Check the applicable information during the current workflow. Do not process any other account.
4. The closure tool may only be called after every eligibility item below is affirmatively satisfied and the required retention path is complete.

## Eligibility checks

A card can be closed only when all of these are true:

- outstanding balance is exactly `$0.00`;
- the account has no active or pending disputes;
- it has been open at least 60 days;
- it has no pending replacement-card order.

Review available transaction/dispute information for active or pending disputes. Do not treat an unavailable or ambiguous dispute result as a pass; tell the customer the closure cannot proceed until the status is confirmed or any dispute is resolved.

For replacement cards, unlock and call the specialized tool:

1. `unlock_discoverable_agent_tool` with `agent_tool_name: "get_pending_replacement_orders_5765"`.
2. `call_discoverable_agent_tool` using that name and exactly `{"credit_card_account_id":"<account_id>"}`.

An empty orders collection passes. If any returned order is not clearly `delivered` or `cancelled`, closure is blocked. If retention discussion causes a delay, repeat this replacement-order check immediately before the final close call.

`scripts/closure_plan.py` can calculate the date/balance/order portions of this assessment from runtime data. Its recommendations are a checklist only; the executor must make the actual banking-tool calls.

## Retention workflow

After eligibility is met, unlock and call `get_closure_reason_history_8293` with the selected `credit_card_account_id`.

- If it reports a record for this account within the past year, **skip reason logging and all retention offers**. Respect the customer’s decision and continue to final closure after rechecking any time-sensitive eligibility item.
- If there is no such record, obtain the reason if it is not already clear. Normalize it to exactly one permitted value:
  `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
  Unlock `log_credit_card_closure_reason_4521`, then call it with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
- Address the stated concern, then make exactly one applicable retention offer. The tiers are: entry: 500 points or $5 statement credit; mid: 2,000 points or $20 statement credit; premium and above: 5,000 points or $50 statement credit. Green Rewards Card is mid-tier.
- For annual-fee concerns, a customer of at least two years may be offered a one-year waiver. Unlock `apply_credit_card_account_flag_6147` only if applying this documented offer, with `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` form. For less than two years, offer a permanent no-annual-fee downgrade instead; do not invent a downgrade tool.
- Wait for the customer’s response to the offer. If accepted, do not close the account. If declined, or retention was skipped due to recent history, proceed without pressure.

## Final closure and customer communication

Immediately before the final action, ensure eligibility remains satisfied (including the replacement-card check). Unlock `close_credit_card_account_7834`, then call it with exactly:

```json
{"credit_card_account_id":"<selected account id>","user_id":"<verified user id>"}
```

Only report success after the tool reports success. If a tool fails, is ambiguous, or returns an ineligible state, do not retry a potentially state-changing closure blindly; explain the blocker and follow the result.

After a successful closure, tell the customer that a confirmation email and final statement will arrive within several business days. Remind them that unredeemed rewards may be redeemed for 45 days after the closure request and are then forfeited. For Green Rewards Card, and other listed cash-back cards, database reward points represent cash back at `$0.01` per point; calculate a disclosed balance from current account data only. State that a full annual-fee refund may apply if closure occurs within 37 days of the fee posting, but do not promise one without the fee-posting date.

## Planner script

Run the script with JSON on stdin and read one JSON object from stdout:

```json
{
  "now": "2025-01-15 10:00:00 EST",
  "identity_confirmed_fields": ["email", "date_of_birth"],
  "account": {
    "account_id": "runtime account id",
    "card_type": "Green Rewards Card",
    "date_of_account_open": "01/01/2024",
    "current_balance": "$0.00",
    "reward_points": 0
  },
  "pending_disputes": false,
  "replacement_orders": [],
  "prior_closure_history": {"known": true, "has_records_past_year": false},
  "closure_reason": "simplifying_finances",
  "retention_decision": "declined"
}
```

`pending_disputes` must be `true`, `false`, or `null` when unconfirmed. `replacement_orders` is either a tool-derived list (records or status strings) or `null` when unchecked. `retention_decision` is `pending`, `declined`, `accepted`, or `null`. The output contains eligibility conditions, any blockers or missing checks, the applicable tier/offer, reward value when supplied, and a workflow stage. Validate that `eligible_to_close` is true and `workflow_stage` is `ready_to_close` before making the closure call; also independently perform the required just-in-time replacement check.
