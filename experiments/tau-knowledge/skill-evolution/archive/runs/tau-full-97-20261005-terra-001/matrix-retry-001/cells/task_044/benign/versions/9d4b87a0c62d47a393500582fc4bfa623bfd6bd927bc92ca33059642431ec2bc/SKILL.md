---
name: credit-card-closure-with-retention
description: Safely process a Rho-Bank credit-card closure request after identity verification, closure eligibility checks, required retention-history and reason handling, a single tier-appropriate retention offer when required, closure execution, and required post-closure notices.
---

# Credit-card closure with retention

Use this Skill for a customer requesting closure of a Rho-Bank credit-card account. Follow the stages in order. Never state that an account is closed unless the closure tool has returned success.

## 1. Identify and verify the customer

1. Locate the requested credit-card account and verify that it belongs to the authenticated customer and matches the card the customer wants to close.
2. Complete standard identity verification before disclosing account details, making an account-specific offer, or changing the account. Verification requires confirmation of two of these profile fields: date of birth, email, phone number, and address.
3. Obtain the current timestamp and call `log_verification` only after two customer-supplied fields match the retrieved profile. Supply every required profile field, `user_id`, and the current timestamp.
4. If identity cannot be verified, do not continue with retention or closure.

An email used to locate a profile is not, by itself, two-field verification.

## 2. Establish closure eligibility

Before attempting retention, use current account data and confirm all requirements:

1. Call `get_user_dispute_history_7291` with `user_id`. Any active, pending, open, under-review, or otherwise unresolved dispute blocks closure.
2. Call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty collection is clear. If any order is not clearly `delivered` or `cancelled`, closure is blocked.
3. Confirm the account has been open for at least 60 days.
4. Confirm the outstanding balance is exactly $0.00.

If a check is unavailable, ambiguous, or fails, explain the applicable blocker and do not make a retention offer or close the account. Do not rely on an earlier replacement-card result for the final closure action: repeat this check immediately before closing.

## 3. Determine whether retention is required

For an eligible account, unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id`.

- If a record exists for this account within the past year, skip all retention offers. Tell the customer that you will proceed with the closure request, then move to the final replacement-card check and closure path.
- If no such record exists, retention is required. Obtain the reason if it was not already clear, map it to one permitted value, and log it before continuing:
  `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
- Call `log_credit_card_closure_reason_4521` with **exactly** `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add arguments.

## 4. Address the reason, then make the required offer

First address the stated concern:

- **annual_fee:** If the customer relationship is at least two years, offer a one-year annual-fee waiver. Apply `apply_credit_card_account_flag_6147` only if accepted, using `annual_fee_waived`, `loyalty_benefit`, and an expiration date exactly one calendar year from today in `MM/DD/YYYY` format. For less than two years, offer a same-category no-annual-fee downgrade after explaining benefit changes and obtaining consent.
- **not_using_card:** Remind the customer of relevant benefits and suggest a recurring subscription.
- **found_better_card:** Ask which features are better. Offer help applying for a Rho-Bank alternative only if available product information genuinely supports comparable or better benefits; do not make unsupported product claims.
- **unhappy_with_rewards:** Review available bonus-category enrollment and ways to maximize rewards.
- **negative_experience:** Apologize, gather details, and escalate service complaints when warranted.

After addressing the concern, and **before asking whether the customer still wants to close or accepting any final closure decision**, make exactly one retention offer based on an authoritative card-tier classification:

| Card tier | One permitted offer |
|---|---|
| Entry | 500 bonus points **or** a $5 statement credit |
| Mid | 2,000 bonus points **or** a $20 statement credit |
| Premium and above | 5,000 bonus points **or** a $50 statement credit |

State a concrete permitted benefit and await the customer's response. Do not make more than one retention offer.

Do not infer a tier merely from a product name. If the applicable classification cannot be determined from authoritative available information, transfer or otherwise escalate **before** soliciting a final closure decision. Do not skip the mandatory offer by asking whether the customer wants to proceed. Use `account_closure_request` as the transfer reason when transferring an otherwise eligible unresolved closure request.

If the customer accepts the concern resolution or the retention offer, do not close the account. If the customer declines the one offer, thank them without pressure and proceed. A prior-year retention record is the only retention-history reason to skip the offer.

## 5. Close the account

Immediately before closure, call `get_pending_replacement_orders_5765` again for the selected account. If clear, unlock and call `close_credit_card_account_7834` with only:

- `credit_card_account_id`
- `user_id`

Do not close if the repeat check shows a non-final replacement order, or if any earlier prerequisite is unresolved.

## 6. Required communication after successful closure

After a successful closure tool result, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards can be redeemed for 45 days after submitting the closure request; after that, they are forfeited.
- A full annual-fee refund may be available if the closure occurs within 37 days of the fee posting.

For cash-back cards represented as points, explain values at 1 point = $0.01 when redeemed as a statement credit or checking-account credit. Calculate any stated value from the current live reward balance rather than from an earlier lookup.

## Workflow planning helper

`scripts/closure_plan.py` validates a normalized workflow snapshot. It performs no banking calls and cannot close an account. The executor must perform the returned `next_actions`, refresh the snapshot after each tool call, and use normal banking tools for all account actions.

Run `scripts/closure_plan.py` with one JSON object on stdin. It emits one JSON object on stdout.

Required input fields:

- `current_time`: date or ISO-like timestamp;
- `identity_verified`: boolean;
- `account_open_date`: `YYYY-MM-DD` or `MM/DD/YYYY`;
- `current_balance`: number or currency string;
- `disputes_checked`: boolean and `disputes`: list of objects with optional `status`;
- `replacement_checked`: boolean and `replacement_orders`: list of objects with optional `status`;
- `prior_history_checked`: boolean and `prior_year_history_exists`: boolean;
- `reason_logged`: boolean;
- `reason`: permitted reason when retention is required;
- `concern_addressed`: boolean when retention is required;
- `retention_state`: one of `not_offered`, `offered_pending`, `declined`, or `accepted`;
- `card_tier`: `entry`, `mid`, or `premium` when making an offer;
- `final_replacement_checked`: boolean; and
- `final_replacement_orders`: list of final pre-closure order records when that check was made.

Optional `reward_points` is converted to a cash-back value at one cent per point. Example: invoke `run_skill_script` with `relative_path` `scripts/closure_plan.py` and `input_json` containing the fields above. Only a result with `valid: true` and `stage: close_now` permits a closure call. A `determine_card_tier_or_escalate` result explicitly prohibits asking for a final closure decision.
