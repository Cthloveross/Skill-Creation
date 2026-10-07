---
name: credit-card-closure-and-retention
version: 1.0.0
description: Safely process a verified customer's credit-card closure request, including mandatory eligibility gates, closure-history abuse prevention, reason logging, retention handling, rewards notices, and the final closure action. Use for any request to close a credit card account.
---

# Credit Card Closure and Retention

## Purpose

Use this Skill for a customer who asks to close a credit-card account. It prevents closure, reason logging, and retention activity before identity and closure eligibility have been established.

Use `scripts/assess_closure.py` to evaluate normalized account facts and determine the next permitted workflow stage. The script is advisory only: the execution agent must perform all customer communication and banking-tool calls.

## Required workflow

### 1. Identify the requested account and authenticate the customer

1. Resolve the customer and retrieve their credit-card accounts using the normal read-only customer/account tools.
2. Ensure the requested account belongs to the authenticated customer and is the exact card the customer wishes to close. Do not act on another card merely because it is listed on the same profile.
3. Before discussing nonpublic account details or taking an account action, verify identity by asking the customer to confirm **two of four** fields: date of birth, email, phone number, or address. Do not disclose the stored values while asking.
4. Compare the two supplied values to the customer record. On a successful match, call `log_verification` with all required stored identity fields and the current timestamp from `get_current_time`.
5. If identity cannot be verified, do not log verification, disclose account details, make offers, log a reason, or close the account. Follow the applicable support/escalation process.

### 2. Confirm every eligibility requirement before retention

For the selected account, confirm all of these requirements, in this order:

1. No active or pending transaction dispute.
2. No pending replacement card (ordered but not received or activated).
3. Account has been open at least 60 days.
4. Outstanding balance is exactly $0.00.

A customer statement can inform the dispute/replacement checks where it is the available evidence, but do not represent an unverified condition as system-confirmed. Use available account/dispute/card-order information when the runtime provides it.

If **any** requirement fails or cannot be confirmed, explain the specific issue(s) that must be resolved. Do not make retention offers, call the closure-history tool, log a closure reason, apply a waiver, or close the account. In particular, a positive balance must be paid in full before closure or retention can proceed.

### 3. Check prior closure-reason records only after eligibility passes

Unlock and call `get_closure_reason_history_8293` with only:

```json
{"credit_card_account_id":"<selected-account-id>"}
```

Determine whether the selected account has a closure-reason record within the preceding year.

- If a record exists within that period, skip all retention offers and proceed to final closure once the customer still wants to close.
- If no such record exists, continue with reason handling.

### 4. Capture the reason and conduct retention

Ask for the reason if it is not already clear. Map the customer's stated reason to exactly one allowed value and unlock/call `log_credit_card_closure_reason_4521` with **only** these arguments:

```json
{
  "credit_card_account_id":"<selected-account-id>",
  "user_id":"<authenticated-user-id>",
  "closure_reason":"annual_fee|not_using_card|found_better_card|unhappy_with_rewards|simplifying_finances|negative_experience|other"
}
```

Do not add arguments to that tool. If no allowed category reasonably fits, use `other` rather than inventing a value.

Address the concern before making a retention offer:

- `annual_fee`: for a customer with at least two years of customer tenure, offer a one-year annual-fee waiver. Only if they accept, unlock/call `apply_credit_card_account_flag_6147` using `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one calendar year from today in `MM/DD/YYYY`. For shorter tenure, offer a permanent downgrade to a no-annual-fee card while preserving account history; no downgrade tool is specified by this Skill, so do not claim to complete one without an available approved tool.
- `not_using_card`: remind the customer of relevant benefits and suggest a recurring subscription if appropriate.
- `found_better_card`: ask which features prompted the choice. Offer help applying for a comparable Rho-Bank card only when such a card is actually available.
- `unhappy_with_rewards`: review available bonus-category enrollment and ways to maximize rewards based on actual spending patterns.
- `negative_experience`: apologize, gather details, escalate to a supervisor where warranted, and consider a modest goodwill credit only through an available approved process.
- `simplifying_finances` or `other`: acknowledge the reason without inventing a benefit or offer.

If the customer still wants closure, make at most one tier-based retention offer:

| Card tier | Offer |
|---|---|
| Entry | 500 bonus points or $5 statement credit |
| Mid | 2,000 bonus points or $20 statement credit |
| Premium and above | 5,000 bonus points or $50 statement credit |

Use an explicitly supplied or reliably known tier; do not infer a tier from a card name alone. If the customer accepts a retention solution or offer, do not close the account. If they decline (or prior-record rules skipped retention), accept the decision without pressure.

### 5. Close and communicate

Immediately before the irreversible action, ensure the verified user ID and selected account ID still match, all eligibility checks remain satisfied, and the customer has clearly confirmed that they want closure.

Unlock and call `close_credit_card_account_7834` with:

```json
{
  "credit_card_account_id":"<selected-account-id>",
  "user_id":"<authenticated-user-id>"
}
```

Report success only after the tool confirms it. After successful closure, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; they are forfeited thereafter.
- If an annual fee posted recently, a full refund may be available when closure occurs within 37 days of that fee charge.

For the listed cash-back cards, transaction-system `points` represent cash back at **$0.01 per point** when redeemed as a statement credit or checking-account credit. Do not characterize these as ordinary points. The `EcoCard` is the points-based exception, although its sustainability points also redeem at $0.01 per point.

## Assessment helper

Run:

```text
python3 scripts/assess_closure.py < input.json
```

The script reads one JSON object on stdin and emits one JSON object on stdout. It does not call banking tools or write records.

### Input schema

```json
{
  "authenticated_user_id": "string or null",
  "identity_verified": "boolean",
  "account": {
    "account_id": "string",
    "user_id": "string",
    "card_type": "string",
    "date_of_account_open": "MM/DD/YYYY or YYYY-MM-DD",
    "current_balance": "number or currency string",
    "reward_points": "integer optional",
    "pending_disputes": "true, false, or null",
    "pending_replacement_cards": "true, false, or null",
    "card_tier": "entry, mid, premium, premium_plus, or null"
  },
  "today": "YYYY-MM-DD or timestamp beginning YYYY-MM-DD",
  "history_checked": "boolean optional",
  "prior_closure_reason_within_year": "boolean or null",
  "closure_reason": "allowed reason or null",
  "reason_logged": "boolean optional",
  "concern_addressed": "boolean optional",
  "retention_offer_declined": "boolean optional",
  "customer_accepts_retention": "boolean optional",
  "final_close_confirmed": "boolean optional"
}
```

The output contains `decision`, `blockers`, `next_actions`, and, after identity verification, safe computed facts such as account age and rewards value. Treat an `invalid_input` result or an `unknown_*` blocker as a stop condition requiring correction or more evidence.

### Validation expectations

Before following a tool recommendation, verify that the script reports no blockers, the selected account ownership matches, the account balance is exactly zero, both pending-status values are `false`, account age is at least 60 days, and the recommended workflow stage matches the documented sequence. The helper deliberately never recommends closure before identity verification and an explicit final closure confirmation.
