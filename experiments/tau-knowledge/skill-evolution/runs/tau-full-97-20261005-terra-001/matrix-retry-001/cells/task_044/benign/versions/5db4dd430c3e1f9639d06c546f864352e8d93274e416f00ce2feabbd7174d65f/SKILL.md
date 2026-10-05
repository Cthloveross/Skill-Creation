---
name: credit-card-closure-with-retention
description: Process a Rho-Bank credit-card closure request through verification, eligibility checks, required retention history/reason handling, one compliant retention offer where required, closure, and required post-closure notices.
---

# Credit-card closure with retention

Use this Skill for a request to close a Rho-Bank credit-card account. Follow the stages in order. Never state that an account is closed unless `close_credit_card_account_7834` succeeded.

## 1. Identify the account and verify the customer

1. Locate the requested card account and confirm that it belongs to the requesting customer and matches the requested card type.
2. Complete standard verification before disclosing account-specific information, offering retention, or changing the account. Match two customer-supplied profile fields from date of birth, email, phone number, and address. An email used only to locate a profile is not itself two-field verification.
3. Obtain the current time and call `log_verification` after two fields match. Supply its required profile fields, `user_id`, and the current timestamp.
4. If verification fails or remains incomplete, stop. Do not offer retention or close the account.

## 2. Establish closure eligibility before retention

For the selected account, establish all requirements:

1. Use `get_user_dispute_history_7291` with the authenticated `user_id`. An active, pending, open, under-review, or otherwise unresolved dispute blocks closure.
2. Use `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty result is clear. If any returned order is not clearly `delivered` or `cancelled`, closure is blocked.
3. Confirm the account has been open for at least 60 days.
4. Confirm the outstanding balance is exactly $0.00.

If any check is unavailable, ambiguous, or fails, explain the specific blocker. Do not make a retention offer and do not close the account. Repeat the replacement-order check immediately before the eventual closure action.

## 3. Check prior retention and log the reason

For an eligible account, unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id`.

- If there is a closure-reason record for this account within the past year, skip retention. Tell the customer that the closure request will proceed and use the final replacement-card check and closure path.
- If there is no such record, retention is required. Obtain the reason when needed, map it to a permitted value, and log it before continuing.
- Unlock and call `log_credit_card_closure_reason_4521` with **exactly** `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add parameters.

Permitted reasons are `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.

## 4. Address the concern

Address the stated reason before the retention offer:

- **annual_fee:** For a relationship of two or more years, offer a one-year annual-fee waiver. Apply `apply_credit_card_account_flag_6147` only after acceptance, using `annual_fee_waived`, `loyalty_benefit`, and an expiration date one calendar year from today in `MM/DD/YYYY` form. For a shorter relationship, offer a same-category no-annual-fee downgrade after explaining the benefit changes and obtaining consent.
- **not_using_card:** Explain relevant benefits and suggest a recurring subscription.
- **found_better_card:** Ask which features attracted the customer. Offer help applying for a Rho-Bank alternative only where available product information supports comparable or better benefits. Do not make unsupported comparisons.
- **unhappy_with_rewards:** Review available bonus-category enrollment and ways to maximize rewards based on spending.
- **negative_experience:** Apologize, gather details, and escalate a service complaint when warranted.

## 5. Mandatory single retention offer

When there is no prior-year closure-reason record, and the customer still wants closure after the concern discussion, make **exactly one concrete retention offer before any closure-workflow endpoint**. This rule is mandatory.

A closure-workflow endpoint includes asking the customer whether they want to proceed, continue, confirm, or otherwise make a final closure decision; transferring the closure request; or calling a closure tool. Do not use an inability to identify an offer as a reason to solicit closure or refuse the request.

Use an authoritative runtime tier classification or an authoritative configured retention offer. A card name alone is not an authoritative tier classification. The policy-recognized offers are:

| Tier | Offer one of |
|---|---|
| Entry | 500 bonus points or a $5 statement credit |
| Mid | 2,000 bonus points or a $20 statement credit |
| Premium and above | 5,000 bonus points or a $50 statement credit |

State the chosen actual benefit plainly, for example: “I can offer 2,000 bonus points to keep this account open.” A vague reference to possible benefits is not an offer. Wait for the customer’s response. Do not repeat, replace, stack, or make a second retention offer.

If the authoritative tier or configured amount is genuinely unavailable, obtain that internal classification before asking for a closure decision, transferring the closure request, or closing the account. Do not invent a tier or tier-specific amount. The absence of a tier is a workflow hold, not an authorization to bypass the offer.

If the customer accepts the concern resolution or retention offer, do not close the account. If the customer declines the one offer, thank them without pressure and continue to closure. A prior-year closure-reason record is the only retention-history basis for omitting this offer.

## 6. Close the account

Immediately before closure, call `get_pending_replacement_orders_5765` again for the selected account. If it is clear, unlock and call `close_credit_card_account_7834` with only:

- `credit_card_account_id`
- `user_id`

Do not close if the final replacement check has a non-final order or any other prerequisite is unresolved.

## 7. Communicate after successful closure

After the closure tool succeeds, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after submitting the closure request; after that they are forfeited.
- A full annual-fee refund may be available if closure occurs within 37 days of the fee posting.

For cash-back cards represented as points, points equal $0.01 each when redeemed as a statement credit or checking-account credit. Calculate any stated value from a current live reward balance, not an earlier lookup.

## Workflow planning helper

`scripts/closure_plan.py` validates a normalized workflow snapshot and determines the next permissible workflow stage. It is planning-only: it does not make banking calls, apply offers, transfer a customer, or close an account. Execute returned actions with normal banking tools and refresh the snapshot after each result.

Run it with one JSON object on stdin; it emits one JSON object on stdout. Required fields are:

- `current_time`: date or ISO-like timestamp;
- `identity_verified`: boolean;
- `account_open_date`: `YYYY-MM-DD` or `MM/DD/YYYY`;
- `current_balance`: number or currency string;
- `disputes_checked`: boolean and `disputes`: list of records with optional `status`;
- `replacement_checked`: boolean and `replacement_orders`: list of records with optional `status`;
- `prior_history_checked`: boolean and `prior_year_history_exists`: boolean;
- `reason_logged`: boolean;
- `concern_addressed`: boolean;
- `retention_offer_count`: nonnegative integer;
- `retention_state`: `not_offered`, `offered_pending`, `declined`, or `accepted`;
- `final_replacement_checked`: boolean; and
- `final_replacement_orders`: list of final pre-closure replacement-order records.

When retention is required, provide `reason`. To obtain an offer, provide either an authoritative `card_tier` of `entry`, `mid`, or `premium`, or `authorized_retention_offer` containing exactly one permitted `bonus_points` or `statement_credit` value. The helper rejects a closure path until exactly one offer was made and declined. Optional `reward_points` is converted at $0.01 per point.

Example planning call:

```json
{"current_time":"2025-01-01","identity_verified":true,"account_open_date":"2024-01-01","current_balance":"$0.00","disputes_checked":true,"disputes":[],"replacement_checked":true,"replacement_orders":[],"prior_history_checked":true,"prior_year_history_exists":false,"reason":"found_better_card","reason_logged":true,"concern_addressed":true,"retention_offer_count":0,"retention_state":"not_offered","card_tier":"mid","final_replacement_checked":false,"final_replacement_orders":[]}
```

The resulting `make_retention_offer` stage means the executor must make the returned single concrete offer before discussing a final closure decision.