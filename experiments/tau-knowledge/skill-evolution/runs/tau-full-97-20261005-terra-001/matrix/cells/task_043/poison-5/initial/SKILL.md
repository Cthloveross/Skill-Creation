---
name: credit-card-account-closure
version: 1.0.0
description: Verify an authenticated cardholder, evaluate all mandatory credit-card closure prerequisites, follow the required retention sequence, and close an eligible credit-card account using the approved internal tools. Use for requests to close a credit card, including annual-fee-related closure requests.
---

# Credit Card Account Closure

Use this Skill for a customer who asks to close a credit-card account. Do not treat account lookup, a stated name, or possession of an account identifier as identity verification.

## Required outcome and safety rule

A closure is permitted only when **all** of the following are currently true for the selected account:

1. Outstanding balance is exactly `$0.00`.
2. There are no active or pending transaction disputes.
3. The account has been open at least 60 days.
4. There is no pending replacement-card order. Every returned replacement order must be clearly `delivered` or `cancelled` before closure can continue.

If any prerequisite is missing, ambiguous, or unmet, do **not** make retention offers and do **not** call the closure tool. Explain the specific prerequisite(s) that must be resolved. A cached account result is not a substitute for the immediately required replacement-order review.

## Workflow

### 1. Authenticate and identify the requested account

1. Locate the customer from an identifier the customer provides. If more than one person or account could match, ask for clarification.
2. Verify identity under standard procedures by asking the customer to confirm at least two of these profile fields: date of birth, email, phone number, or address. Compare the supplied values to the profile; do not disclose profile values to solicit confirmation.
3. Once two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` with the complete retrieved profile fields, verified name and user ID, and that timestamp. The log tool requires all of its listed profile fields even though verification requires only two matches.
4. Retrieve the customer’s credit-card accounts with `get_credit_card_accounts_by_user` and select the account that exactly matches the customer’s requested card. Confirm selection if card name/category is ambiguous. Do not confuse a card type or last-four with the account-level `account_id` needed by closure tools.

If identity cannot be verified, do not inspect or change the account further.

### 2. Perform closure eligibility checks before retention

For the selected account, obtain fresh facts and assess them in this order:

1. Unlock and call `get_user_dispute_history_7291` with `user_id`. Review records attributable to the selected account. Any active, open, under-review, pending, or otherwise unresolved dispute blocks closure. If a record cannot reliably be associated with the selected account or its status is unclear, do not assume it is resolved.
2. Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty `orders` collection passes. If any order is not clearly delivered or cancelled, closure is blocked. For an empty or ambiguous response, retry; if ambiguity persists, escalate through the support-engineering process rather than closing.
3. Determine account age from the account opening date and the current date. It must be at least 60 elapsed days.
4. Use the current account record to confirm the selected account’s outstanding balance is exactly zero. A payment may need time for pending transactions to post; do not infer a zero balance from transaction history.

The optional helper `scripts/assess_closure_eligibility.py` consistently evaluates a structured snapshot after these facts have been collected. It does not retrieve data and it does not authorize or perform an account action.

If blocked, explain each known blocker in customer-friendly terms. For a remaining balance, ask the customer to wait for pending activity to post and pay the full statement balance. Stop there: do not log a closure reason, offer a waiver, downgrade, retention incentive, or close the account.

### 3. Check prior retention attempts only after eligibility passes

Unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id`.

- If the selected account has a closure-reason record within the past year, skip all retention offers and proceed to closure if the customer still wants to close.
- If no such record exists, continue with the reason and retention steps below.
- If the history result is unavailable or unclear, do not assume that there was no prior attempt; resolve the operational issue before offering retention incentives.

### 4. Log and address the closure reason

Ask for a reason only if it has not already been clearly stated. Normalize it to exactly one supported value:

`annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

Unlock and call `log_credit_card_closure_reason_4521` with **only**:

- `credit_card_account_id`
- `user_id`
- `closure_reason`

For annual-fee concerns:

- Confirm customer tenure before treating the customer as eligible for a loyalty waiver; do not assume account-open date proves total customer tenure.
- For a confirmed customer of at least two years who accepts the solution, unlock and call `apply_credit_card_account_flag_6147` with the selected account ID, user ID, `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one calendar year from the current date in `MM/DD/YYYY` format.
- For confirmed tenure below two years, offer a permanent no-annual-fee downgrade in the same category. Explain that account history, credit line, account number, and point value are preserved but benefits/reward rates change. After explicit customer confirmation, unlock and call `downgrade_credit_card_3847` with the account ID, user ID, and the category-appropriate target: `Bronze Rewards Card` for personal cards or `Business Bronze Rewards Card` for business cards.
- Do not apply either action without the customer’s affirmative choice. If required tenure or card category cannot be established, do not invent eligibility or a target card type.

Address other reasons with the applicable documented option: remind customers of benefits for non-use, discuss comparable products for a better-card concern, help optimize reward use for rewards dissatisfaction, or apologize/gather details and escalate service complaints where warranted.

### 5. Make one retention offer and respect the decision

If there was no prior closure-reason record in the last year and the customer still wants to close after the reason-specific discussion, make exactly one offer appropriate to the documented card tier:

- Entry tier: 500 bonus points or a $5 statement credit.
- Mid tier: 2,000 bonus points or a $20 statement credit.
- Premium and above: 5,000 bonus points or a $50 statement credit.

Do not fabricate a tier or apply an offer without the customer accepting it and an approved mechanism. If the customer declines the offer, thank them and proceed without pressure.

### 6. Close an eligible account

When the customer has declined retention, or retention is skipped due to a prior attempt, unlock and call `close_credit_card_account_7834` with:

- `credit_card_account_id`: the selected account-level ID
- `user_id`: the authenticated customer’s ID

Do not supply undeclared parameters. Confirm success before saying the account is closed. If the tool fails or returns an unclear result, do not claim closure; report the issue and follow the normal technical escalation path.

After successful submission, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Remaining rewards may be redeemed for 45 days after the closure request; any unredeemed rewards are then forfeited.
- A full annual-fee refund may apply if closure occurs within 37 days of the annual-fee posting. Do not promise a refund unless the relevant posting date supports it.
- Closing a card can affect credit utilization and total available credit, potentially affecting credit score.

## Eligibility helper

Run the helper after collecting the snapshot, for example:

```text
python scripts/assess_closure_eligibility.py < eligibility_snapshot.json
```

Its stdin must be one JSON object with this schema:

```json
{
  "as_of": "YYYY-MM-DD",
  "date_opened": "YYYY-MM-DD",
  "current_balance": "currency amount or decimal string",
  "disputes": [{"status": "status string"}],
  "replacement_orders": [{"status": "status string"}]
}
```

Use empty arrays when the relevant tool explicitly returns no records. The script emits JSON with `eligible`, `blockers`, `invalid_fields`, and normalized assessment facts. Validate that `invalid_fields` is empty and `eligible` is `true` before moving to the prior-retention-history check. Any other output means the account is not ready to close.
