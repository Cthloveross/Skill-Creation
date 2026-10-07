---
name: rho-credit-card-closure
version: 1.0.0
description: Process a verified Rho-Bank credit-card closure request safely, including eligibility, retention history, standardized reason logging, required final replacement-order check, and customer disclosures. Use for one specifically identified card at a time.
---

# Rho-Bank Credit Card Closure

## Purpose and boundaries

Process only the card the customer has selected. A request to close several cards is not authorization to close every card at once: finish or explain the outcome for the selected account, then obtain a separate confirmation for each additional account.

The executor must perform banking actions with the normal banking tools. `scripts/closure_check.py` is only a deterministic aid for evaluating facts already returned by tools; it neither calls banking tools nor closes an account.

## Required inputs

Before closure, establish all of the following at runtime:

- Authenticated `user_id` and the selected `credit_card_account_id`.
- The card belongs to that authenticated user and is the intended card. If card type matching is absent or ambiguous, ask the customer to identify the account; never guess.
- Successful identity verification using **two of four** profile fields: date of birth, email, phone number, and address.
- Current account balance and account-open date.
- Current dispute status, replacement-order status, and closure-reason history.
- A customer closure reason that can be represented by one of: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

Do not treat a name alone as one of the two required profile-field verifications. If only one of the four fields has been confirmed, request one additional field before making any closure-related state change.

## Procedure

### 1. Locate account and verify identity

1. Locate the user and retrieve their credit-card accounts using the ordinary profile/account lookup tools.
2. Match the requested card to an account owned by that user. Confirm the selected account if there is more than one plausible match.
3. Compare customer-provided identity responses against the profile until two of DOB, email, phone, and address match.
4. Obtain the current timestamp with `get_current_time`, then call `log_verification` after successful verification. Supply every required profile value exactly as recorded, plus `name`, `user_id`, and `time_verified`.
5. If identity cannot be verified, do not disclose account information, make offers, log a closure reason, or call a closure tool.

### 2. Collect closure facts and evaluate eligibility

Use current source-of-record responses rather than prior conversation assumptions.

1. Read the selected account's balance and open date. It must have a balance of exactly `$0.00` and be open at least 60 calendar days as of the current date.
2. Unlock and call `get_user_dispute_history_7291` with `{"user_id": "..."}`. Review all returned disputes. A dispute that is active, pending, open, under review, or otherwise not clearly final/resolved blocks closure when it belongs to the selected account. If a non-final dispute cannot be tied confidently to the requested account, do not assume it is irrelevant; resolve the ambiguity or escalate rather than close.
3. Unlock and call `get_pending_replacement_orders_5765` with `{"credit_card_account_id": "..."}`. Any order not clearly `delivered` or `cancelled` blocks closure.

If any eligibility condition fails, explain the specific blocker and what must happen first. Do not offer retention and do not call the closure tool. A failed or ambiguous eligibility lookup also means closure cannot proceed until the lookup is retried successfully or handled through the normal support escalation path.

### 3. Check retention history and record the reason

Only after the account is eligible:

1. Unlock and call `get_closure_reason_history_8293` with the selected `credit_card_account_id`.
2. If a closure-reason record exists within the prior year, skip all retention offers and proceed to the final pre-closure check.
3. If no such record exists, obtain/normalize the customer's reason to the supported enum. If their explanation maps to more than one enum or is unclear, ask them to select one; do not invent a reason.
4. Unlock and call `log_credit_card_closure_reason_4521`. Its arguments must be **only**:
   ```json
   {
     "credit_card_account_id": "<account-id>",
     "user_id": "<user-id>",
     "closure_reason": "<supported-enum>"
   }
   ```

### 4. Retention, when permitted

For a customer with no prior closure-reason record in the last year, address the stated concern before making one tier-based retention offer:

- `annual_fee`: for a customer of at least two years, an annual-fee waiver for one year may be offered with `apply_credit_card_account_flag_6147`; use `flag_type: annual_fee_waived`, a MM/DD/YYYY expiration one year from today, and `reason: loyalty_benefit`. For less than two years, offer a permanent no-annual-fee downgrade that preserves account history.
- `not_using_card`: discuss relevant benefits and a recurring subscription option.
- `found_better_card`: ask about desired features and offer help applying for a comparable Rho-Bank card if one is available.
- `unhappy_with_rewards`: review bonus-category enrollment and ways to maximize rewards.
- `negative_experience`: apologize, obtain details, and escalate a supervisor-worthy complaint.
- Other reasons: acknowledge the concern without pressure.

If the customer still wishes to close, make no more than one offer based on card tier:

- Entry: 500 bonus points or a $5 statement credit.
- Mid-tier: 2,000 bonus points or a $20 statement credit.
- Premium and above: 5,000 bonus points or a $50 statement credit.

Do not apply an offer, waiver, downgrade, points, or credit without the customer choosing it and the applicable authorized action being available. If an offer was already presented and declined in the current interaction, acknowledge that decision and do not repeat or substitute another offer. If the customer accepts retention, do not close the account.

### 5. Final just-in-time replacement check and closure

Immediately before the irreversible closure action, run `get_pending_replacement_orders_5765` again. This check is required even if an earlier check was clear. If any returned order is not clearly delivered or cancelled, stop.

When all of the following are true—identity logged, selected account ownership confirmed, zero balance, age at least 60 days, no applicable non-final dispute, no non-final replacement order, and the customer has declined or is exempt from retention—unlock and call `close_credit_card_account_7834` with exactly:

```json
{
  "credit_card_account_id": "<account-id>",
  "user_id": "<authenticated-user-id>"
}
```

Do not report success unless that tool reports success. If it fails, state that closure was not completed, avoid retrying blindly, and use normal escalation for a technical or access error.

## Customer communication after successful closure

Tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Remaining rewards can be redeemed for 45 days after the closure request, after which they are forfeited.
- A recently posted annual fee may receive a full refund only if closure occurs within 37 days of that fee posting.
- Closing a card can affect credit utilization and credit score.

For a Green Rewards Card specifically, also explain that closing or unlinking it ends its `+0.4%` Green Account savings APY bonus while eligibility would otherwise be maintained. Green Rewards reward points are cash-back value at `$0.01` per point; where the current point balance is known, calculate the value accurately but do not imply rewards are automatically redeemed.

## Script: eligibility evaluator

`closure_check.py` reads one JSON object from stdin and emits one JSON object to stdout. It accepts:

```json
{
  "as_of": "2025-01-31",
  "account_open_date": "MM/DD/YYYY or YYYY-MM-DD",
  "current_balance": "$0.00",
  "disputes": [{"status": "closed", "matches_target": true}],
  "replacement_orders": [{"status": "delivered"}],
  "annual_fee_posted_date": "MM/DD/YYYY or YYYY-MM-DD",
  "reward_points": 0
}
```

`matches_target` must be true only when the dispute is confidently associated with the requested account. Omit `disputes` or `replacement_orders` only when no records were returned; use `null` if the corresponding lookup was unavailable or ambiguous. Output includes `eligible`, `blockers`, `account_age_days`, optional annual-fee-window status, and optional reward cash value. The script does not replace the mandatory final replacement-order tool call.

Runnable example:

```sh
printf '%s' '{"as_of":"2025-01-31","account_open_date":"2024-01-01","current_balance":"$0.00","disputes":[],"replacement_orders":[]}' | python3 scripts/closure_check.py
```

Validate that `eligible` is true only when `blockers` is empty. Before closure, independently ensure the identity, ownership, retention-history, reason-logging, customer-decision, and just-in-time replacement-check steps above have also been completed.
