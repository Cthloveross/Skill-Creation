---
name: credit-card-closure-with-retention
description: Verify a customer and safely handle a credit-card closure request, including eligibility checks, replacement-card and dispute checks, closure-reason history, required retention handling, closure execution, and post-closure notices. Use for a customer who asks to close a Rho-Bank credit card.
---

# Credit-card closure with retention

Use this Skill only after identifying the requested credit-card account and its owner. Follow the steps in order. Do not close an account merely because the balance shown in an earlier lookup was zero.

## Required information and verification

1. Identify the customer and locate the requested card account. Confirm that the selected account belongs to the authenticated customer and matches the card type they want to close.
2. Complete standard identity verification before any account-changing action. The available verification audit process requires the customer to confirm **two of four** profile fields: date of birth, email, phone number, and address.
   - A supplied email may locate a profile, but do not treat it alone as two-factor confirmation.
   - Retrieve the profile by the appropriate supported lookup, obtain the current time with `get_current_time`, and call `log_verification` only after two supplied customer confirmations match the profile.
   - `log_verification` requires the complete returned profile fields plus its `user_id` and the current timestamp.
3. If identity cannot be verified, do not disclose additional account details, make offers, or perform the closure.

## Eligibility checks

After verification, check all four closure requirements before retention:

1. **Disputes:** unlock and call `get_user_dispute_history_7291` with `user_id`. Any active or pending dispute blocks closure until it is resolved. Treat statuses such as `open`, `under_review`, `pending`, or `active` as unresolved. If a returned dispute cannot be confidently associated or its state is ambiguous, resolve that ambiguity before closing rather than assuming it is clear.
2. **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty order collection is clear. If any returned order is not clearly `delivered` or `cancelled`, the closure is blocked.
3. **Account age:** verify the account has been open for at least 60 days.
4. **Balance:** verify the account's outstanding balance is exactly $0.00.

If any requirement fails, state the specific requirement that must be resolved and stop. Do not make a retention offer while closure eligibility fails.

Use the current account data rather than relying on a stale account lookup. In particular, call `get_pending_replacement_orders_5765` again immediately before the eventual closure call; a new pending or shipped order blocks closure.

## Retention workflow for an eligible account

1. Unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id`.
   - If it returns one or more records within the past year, do not make or repeat retention offers. Thank the customer and continue to the final replacement-order recheck and closure path.
2. If there is no prior-year record, obtain the reason if it has not already been clearly stated. Normalize it to exactly one accepted value:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
3. Unlock and call `log_credit_card_closure_reason_4521` with exactly `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add fields.
4. Address the stated concern before the single retention offer:
   - `annual_fee`: for a customer of at least two years, offer a one-year annual-fee waiver. Only if accepted, use `apply_credit_card_account_flag_6147` with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one calendar year from the current date in `MM/DD/YYYY` format. For less than two years, offer a same-category no-fee downgrade instead, after explaining benefit changes and obtaining consent. Use `downgrade_credit_card_3847` with the appropriate personal `Bronze Rewards Card` or business `Business Bronze Rewards Card` target.
   - `not_using_card`: remind the customer of relevant benefits and suggest a recurring subscription.
   - `found_better_card`: ask which features are better and, if an available Rho-Bank option genuinely matches them, offer help applying. Do not assert that a comparable product exists without support.
   - `unhappy_with_rewards`: review available bonus-category enrollment and reward-maximization options.
   - `negative_experience`: apologize, gather specifics, and escalate service complaints when warranted.
5. If the customer still wishes to close, make **one** tier-appropriate retention offer and wait for their decision. Entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium-and-above: 5,000 points or $50 statement credit. Use an authoritative product/tier classification; do not infer a tier merely from an unsupported product name. Where the task evidence explicitly directs a premium-tier offer, use the premium offer.
6. If the customer accepts a resolution or retention offer, do not close the account. If they decline the offer, or prior-year closure history requires skipping offers, thank them and proceed without pressure.

## Close and communicate

Immediately before closure, rerun the replacement-order check and confirm it remains clear. Unlock and call `close_credit_card_account_7834` with `credit_card_account_id` and `user_id` only after identity, eligibility, retention decision, and final replacement check have all passed.

Do not say the account is closed unless the closure tool succeeds. On success, tell the customer that a confirmation email and final statement will arrive within several business days. Also tell them:

- Unredeemed rewards may be redeemed for 45 days after the closure request; then they are forfeited.
- If an annual fee was posted within 37 days of closure, a full refund may be available.

For cards whose stored rewards are cash-back points, communicate the value using 1 point = $0.01 when redeemed as a statement credit or checking-account credit. Calculate from the live reward balance; do not hardcode a balance or value.

If a required tool returns ambiguous data or errors, do not bypass the requirement or claim completion. Resolve the data issue or use the normal support path for a technical system error.

## Planning helper

`scripts/closure_plan.py` is a deterministic guardrail for a normalized snapshot of the checks. It does not call banking tools and does not perform a closure. The executor must perform every tool action indicated by its result.

Invoke it through the supplied script runtime as `scripts/closure_plan.py` with a JSON object containing:

- `current_time`: ISO-like timestamp or date;
- `identity_verified`: boolean;
- `account_open_date`: `YYYY-MM-DD` or `MM/DD/YYYY`;
- `current_balance`: numeric or currency string;
- `disputes_checked`: boolean and `disputes`: a list of objects with optional `status`;
- `replacement_checked`: boolean and `replacement_orders`: a list of objects with optional `status`;
- `prior_history_checked`: boolean and `prior_year_history_exists`: boolean;
- `reason`, when applicable, plus `reason_logged`: boolean;
- `retention_state`: `not_offered`, `offered_pending`, `declined`, or `accepted`;
- `card_tier`: `entry`, `mid`, or `premium` when an offer is needed;
- `final_replacement_checked`: boolean after the immediate pre-closure replacement check; and
- optional `reward_points` for a cash-back value calculation.

Example runtime invocation: call `run_skill_script` with `relative_path` set to `scripts/closure_plan.py` and an `input_json` object using the schema above. The JSON result contains `stage`, blocking reasons, the required next actions, and an offer/value when determinable. Validate that `valid` is true and that `stage` is `close_now` before invoking the closure tool; otherwise perform the indicated action and collect a fresh snapshot.
