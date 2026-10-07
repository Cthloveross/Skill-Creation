---
name: credit-card-closure-with-retention
description: Process a Rho-Bank credit-card closure request with identity verification, closure-eligibility checks, retention-history and reason handling, exactly one required retention offer when eligible, closure execution, and post-closure notices.
---

# Credit-card closure with retention

Use this Skill when a customer asks to close a Rho-Bank credit-card account. Follow the stages in order. Never say an account is closed unless `close_credit_card_account_7834` has returned a successful result.

## 1. Identify the account and verify identity

1. Locate the requested account and confirm it belongs to the authenticated customer and matches the requested card.
2. Complete standard identity verification before disclosing account-specific information, making an account-specific retention offer, or changing the account. Obtain and match two customer-supplied profile fields from: date of birth, email, phone number, and address.
3. Obtain the current time and call `log_verification` only after two fields match. Its required profile fields, `user_id`, and current timestamp must all be supplied.
4. If verification fails or is incomplete, stop. Do not offer retention or close the account.

Using an email to locate a profile is not by itself two-field verification.

## 2. Check closure eligibility before retention

For the selected account, establish every prerequisite:

1. Call `get_user_dispute_history_7291` with the authenticated `user_id`. Any active, pending, open, under-review, or otherwise unresolved dispute blocks closure.
2. Call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty collection is clear. If any order is not clearly `delivered` or `cancelled`, closure is blocked.
3. Confirm the account has been open at least 60 days.
4. Confirm the outstanding balance is exactly $0.00.

If a prerequisite is unavailable, ambiguous, or not met, explain the applicable blocker. Do not make a retention offer and do not close the account. A replacement-order check must be repeated immediately before the eventual closure action.

## 3. Check retention history and log the reason

For an eligible account, unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id`.

- If this account has a closure-reason record in the prior year, do not make a retention offer. Tell the customer the closure request will proceed, then use the final replacement-card check and closure path.
- If there is no prior-year record, retention is required. Obtain the reason if necessary, map it to a permitted value, and log it before continuing.
- Call `log_credit_card_closure_reason_4521` with **exactly** these arguments: `credit_card_account_id`, `user_id`, and `closure_reason`. Do not send extra arguments.

Permitted values are: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.

## 4. Address the concern, then make one retention offer

Address the stated concern first:

- **annual_fee:** For a customer relationship of two or more years, offer a one-year annual-fee waiver. Apply `apply_credit_card_account_flag_6147` only if accepted, with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an expiration date exactly one calendar year from today in `MM/DD/YYYY` format. For a shorter relationship, offer a same-category no-annual-fee downgrade after explaining changes and obtaining consent.
- **not_using_card:** Remind the customer of relevant benefits and suggest a recurring subscription.
- **found_better_card:** Ask which features attracted the customer. Offer help applying for a Rho-Bank alternative only when available product information actually supports comparable or better benefits. Do not make unsupported comparisons.
- **unhappy_with_rewards:** Review bonus-category enrollment and ways to maximize rewards based on spending.
- **negative_experience:** Apologize, gather details, and escalate service complaints when warranted.

If there is no prior-year retention record and the customer still wants closure after this discussion, make **exactly one** retention offer **before** any of the following:

- asking whether they wish to proceed, continue, confirm, or otherwise make a final closure decision;
- transferring the closure request to a human agent; or
- performing a closure action.

The one offer must be a concrete benefit from the applicable authoritative card-tier classification:

| Tier | Offer one of |
|---|---|
| Entry | 500 bonus points or a $5 statement credit |
| Mid | 2,000 bonus points or a $20 statement credit |
| Premium and above | 5,000 bonus points or a $50 statement credit |

State the actual benefit, for example, “I can offer [amount] bonus points to keep this account open,” and wait for the response. A generic statement that benefits may be available is not an offer. Do not make, repeat, replace, or stack a second retention offer.

Use a documented or otherwise authoritative tier classification where available; do not claim that a tier follows merely from a card name. If the tier or authorized amount needs internal resolution, resolve it before soliciting a closure decision. Do not use that uncertainty as a reason to skip the mandatory offer once an authorized tier/amount is available. Do not transfer an otherwise eligible customer as a substitute for the required offer.

If the customer accepts the concern resolution or retention offer, do not close the account. If they decline the single offer, thank them without pressure and continue to closure. A prior-year record is the only retention-history basis for omitting the offer.

## 5. Close the account

Immediately before closing, call `get_pending_replacement_orders_5765` again for the selected account. If that check is clear, unlock and call `close_credit_card_account_7834` with only:

- `credit_card_account_id`
- `user_id`

Do not close if this final check has any non-final replacement order or if any prior requirement remains unresolved.

## 6. Communicate after a successful closure

After the closure tool succeeds, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after submitting the closure request; after that, they are forfeited.
- A full annual-fee refund may be available when closure occurs within 37 days of the fee posting.

For cash-back cards whose balances are represented as points, explain that points are worth $0.01 each when redeemed as a statement credit or checking-account credit. Calculate a stated value from the current live reward balance, not an earlier lookup.

## Workflow planning helper

`scripts/closure_plan.py` validates a normalized workflow snapshot. It is planning-only: it makes no banking calls and cannot change or close an account. Perform all returned actions using normal banking tools, refresh the snapshot after each result, and only call the closure tool when the helper returns `valid: true` and `stage: close_now`.

Run the script with one JSON object on stdin; it emits one JSON object on stdout.

Required fields:

- `current_time`: date or ISO-like timestamp;
- `identity_verified`: boolean;
- `account_open_date`: `YYYY-MM-DD` or `MM/DD/YYYY`;
- `current_balance`: number or currency string;
- `disputes_checked`: boolean and `disputes`: list of records with optional `status`;
- `replacement_checked`: boolean and `replacement_orders`: list of records with optional `status`;
- `prior_history_checked`: boolean and `prior_year_history_exists`: boolean;
- `reason_logged`: boolean;
- `concern_addressed`: boolean;
- `retention_state`: `not_offered`, `offered_pending`, `declined`, or `accepted`;
- `final_replacement_checked`: boolean; and
- `final_replacement_orders`: list of final pre-closure replacement-order records.

When retention is required, also provide `reason`. To produce an offer, provide `card_tier` as `entry`, `mid`, or `premium`; this value must come from authoritative runtime information. Optional `reward_points` is converted at $0.01 per point. A `tier_classification_required` result prohibits transfer, closure processing, or solicitation of a final closure decision.