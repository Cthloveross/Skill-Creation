---
name: business-checking-referral-advisor
description: Assess whether a business-checking referral can proceed and identify the qualifying referral product with the highest referrer bonus. Use for referral questions, comparisons, and conditional referral guidance; do not use it to submit a referral or open an account.
---

# Business Checking Referral Advisor

Use this skill to give evidence-based, conditional guidance on business-checking referral programs. It separates eligibility screening from product comparison so that referral terms are not recommended before the referrer can participate.

## Scope and safety

This workflow provides information only. It does not create a referral, open an account, move funds, or access a prospective customer's records.

For any banking action, preserve and complete this prerequisite verbatim with the resulting banking procedure:

> Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

If account or referral-history data must be retrieved, first verify the current customer's identity and authority/ownership using the normal banking workflow. Do not access a prospective referred business's account information without that business's own authorization. A third party may receive only general referral guidance.

## Required screening order

Before giving referral recommendations or explaining referral terms, check all available general eligibility facts:

1. Establish the referrer's checking tenure from the earliest Rho-Bank checking-account opening date, not their current product.
2. Check the cross-product rolling cap: no more than two successful referral bonuses in the preceding rolling nine days, using exact timestamps when records are available.
3. Check the selected product's calendar-year bonus count against its product-specific annual cap.
4. Confirm the referred business is a new Rho-Bank customer, including no existing account and no account closed in the preceding 12 months.
5. Confirm the businesses have different registered addresses and different primary owners/primary authorized-signer SSNs.
6. Confirm the intended qualifying deposit is new money, not transferred from another Rho-Bank account.
7. Confirm no incompatible new-account promotion or sign-up bonus will be combined with the referral, and that both accounts are or will remain in good standing.

If any required fact is unknown, ask only for the missing facts rather than recommending a product. If a restriction fails, explain the relevant blocker and do not suggest bypassing it.

## Product comparison method

1. Read `references/referral_terms.md` for the supported product terms and universal restrictions.
2. Identify the deposit amount and timing the referred business actually intends to meet. A larger bonus is not a qualifying option when its required deposit or deadline is not met.
3. Keep only products for which the proposed deposit meets the product minimum, the intended deposit timing meets the product window, the referrer's tenure meets the product threshold, and the product annual cap remains available.
4. For a request to **maximize the referrer's bonus**, select the highest referrer-bonus amount among the qualifying products. State the result conditionally with the deposit, retention, good-standing, rolling-cap, and annual-cap conditions.
5. The November 1–30, 2025 promotion priority (Sky Blue, then Lime Green) applies only when making a general account recommendation among products that meet all stated requirements. It cannot override an explicit requirement to maximize the referrer's bonus; a lower bonus does not satisfy that objective.
6. Mention that the referred business may open a different product from the referrer's existing account, provided the tenure requirement is met.

Use precise language: deposits must be new money and must remain for at least 30 days after the qualifying period ends; a qualifying referred account closed within 90 days may result in bonus clawback; and only one referral code/promotion can apply.

## Deterministic assessment helper

Run the packaged helper when facts and candidate program terms are available:

```sh
python3 scripts/assess_referral.py < request.json
```

The script reads one JSON object from standard input and writes one JSON object to standard output. It makes no network calls and takes no banking action.

### Input schema

- `as_of` (required): ISO-8601 timestamp with an explicit UTC offset.
- `proposed_deposit`: object with `amount` (number or decimal string), `within_days` (integer), and `new_money` (boolean).
- `general` (required): booleans for `referred_is_new_customer`, `different_registered_address`, `different_primary_owner`, `no_promotion_stacking`, `referrer_good_standing`, and `referred_good_standing`; integer `referrer_checking_tenure_days`; `rolling_bonus_timestamps` as an array of offset-bearing ISO timestamps; and `annual_bonus_counts` as an object mapping product ID to this-calendar-year successful-bonus count.
- `programs` (required): array of product terms. Each object must have `id`, `referrer_bonus`, `deposit_min`, `deposit_window_days`, `tenure_days`, and `annual_cap`.

The script returns `recommendation` only when every general gate is supplied and passes. It returns product-level `blockers`, `warnings`, and `conditions` so the executor can explain why a higher nominal reward did not qualify. Invalid or ambiguous timestamps yield structured errors rather than a recommendation.

### Validate before responding

- Do not treat an approximate recollection as an exact rolling-window record when an account-history check is required.
- Reconcile annual counts by product; do not add distinct product annual caps together.
- Ensure the response names the referrer bonus, not the new-business welcome bonus.
- Do not promise payment: qualification, retention, good standing, and applicable caps remain required.

## If the referred business wants to open an account

Treat account opening as a separate banking action. Verify identity; confirm the business-opening requirements (verified customer, at least one OPEN personal checking account, no more than six business checking accounts, no CLOSED accounts, and at least $500 in the existing checking account); confirm the desired `account_class`; then use the normal authorized account-opening workflow. The prospective business must participate directly and authorize its own application.
