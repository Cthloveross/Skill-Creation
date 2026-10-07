---
name: business-card-large-purchase-comparison
description: Compare business credit-card options for a planned high-value purchase using supplied card terms, merchant-category information, current/expected opening date, fees, credit-line ranges, and promotional conditions. Use for informational recommendations only; it does not submit applications or make charges.
---

# Business Card Comparison for a Large Purchase

Use this Skill when a customer wants to choose a business card for a planned purchase and asks which option has the best return. It is designed for transparent, source-grounded comparisons when a purchase may be close to a card's possible credit limit and when enhanced rewards depend on merchant classification.

## Scope and safety boundary

This Skill provides product information and calculations only. Do not use account lookup, identity lookup, profile-change, application-submission, or card-transaction tools merely to answer a general comparison question. Do not imply that approval, a particular credit line, available credit, merchant category, promotion enrollment, or a reward outcome is guaranteed.

If the conversation changes from advice to an actual banking action, stop the comparison workflow and use the execution agent's normal banking tools and procedures. Preserve this prerequisite with any resulting banking procedure:

> Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

## Inputs to collect or read

Use the current task's supplied product documents and observations. Extract only terms that are explicitly supported there:

1. Planned purchase amount and whether it is a single charge.
2. Merchant and its known payment-network merchant category code/category. A description such as “dealership,” “vendor,” or “work equipment” is **not** proof of a bonus category.
3. Current date and, where relevant, expected account-opening date.
4. Whether new-customer status is established; otherwise mark new-customer offers as conditional.
5. Per-card facts: standard rate, explicitly eligible bonus categories, exclusions, annual fee and any dated first-year waiver, sign-up offer, credit-line range, and stated application criteria.
6. Purchase eligibility constraints, including net-purchase treatment, posting deadline, excluded transaction types, and merchant coding requirements.

Do not request sensitive personal data for a high-level comparison. If the customer wants a personalized approval assessment, explain the documented criteria and what they may need to provide during a formal application; do not determine approval from incomplete information.

## Method

1. **Establish the merchant-category assumption.**
   - If the category is known and is expressly eligible for a card, use that card's published category rate, subject to stated exclusions.
   - If the merchant category is unknown, calculate the purchase at each card's documented default/non-bonus rate. Do not label a merchant as travel, software, operations, media, sustainable, or another bonus category based on the item being purchased.
   - State that the merchant's submitted category controls the final reward rate and that a merchant can have a category different from the customer's business purpose.

2. **Screen credit capacity without promising approval.**
   - A documented maximum line below the purchase amount means the card cannot support the full single charge on the disclosed range.
   - If the amount is within a published range but above its minimum, say the customer would need an approved line of at least the purchase amount.
   - Even where a minimum line exceeds the purchase amount, state that the actual approved line and available credit at authorization must cover the charge. Approval and available credit are separate from the published range.

3. **Calculate first-year economics.**
   - Use net purchase amount × applicable cash-back rate.
   - Subtract the applicable first-year annual fee once when comparing a one-purchase, first-year outcome.
   - Add a sign-up credit only if the supplied terms support it and the amount, net-purchase, posting, timing, new-customer, and account-opening conditions are met. When any are unknown, show it as a conditional outcome rather than a guaranteed return.
   - Apply a promotional rate multiplier only when its opening-date, duration, category, and exclusion conditions are supported. Do not stack offers unless the supplied terms say they stack.
   - For programs whose transaction system represents cash back as points, normalize only when supplied terms expressly give a conversion rate. Identify the cash value and do not present raw points as dollars without that support.

4. **Separate firm calculations from conditional scenarios.**
   Present, for each viable card:
   - standard/default reward and standard first-year fee result;
   - potential result if a specific dated waiver, multiplier, or sign-up offer qualifies;
   - credit-capacity status;
   - exact facts still needing verification (merchant category, approved line/available credit, new-customer status, posting timing, and eligibility).

5. **Recommend transparently.**
   Rank only the stated scenarios. Name the best documented default-case option and, separately, any option that becomes better only if its conditions are satisfied. Include material fees, requirements, and stated credit standards, rather than recommending solely from the headline reward rate.

6. **Close with a practical next step.**
   Tell the customer to verify the dealership/vendor's coding before relying on a bonus rate; confirm the approved line and available credit before attempting the charge; and review the account-opening and promotional disclosures. For qualifying-spend offers, remind them that returns/credits reduce net spend and that posting deadlines matter.

## Deterministic calculator

Use `scripts/compare_card_returns.py` after extracting the current product facts. The script does not retrieve data, decide merchant categories, or perform banking actions.

### Script input schema

The script reads one JSON object from standard input:

- `purchase_amount` (number or numeric string, required): positive net planned purchase amount.
- `merchant_category` (string or `null`): normalized known category; `null`/`"unknown"` causes default rates to be used.
- `application_date` and `account_open_date` (optional `YYYY-MM-DD`): use the expected/known opening date for date-bound promotions.
- `is_new_customer` (optional boolean or `null`): `null` retains new-customer benefits as conditional.
- `cards` (array): each card has:
  - `name` (required string), `default_cash_back_rate` (required decimal fraction such as `0.015`), and optional `category_cash_back_rates` mapping;
  - optional `annual_fee`, `minimum_credit_limit`, `maximum_credit_limit`, `eligibility_notes`, and `terms`;
  - optional `first_year_fee_promotions`, each with `fee`, optional `start`, `end`, and `requires_new_customer`;
  - optional `spend_bonuses`, each with `amount`, `spend_threshold`, optional `start`, `end`, `requires_new_customer`, `period_months`, and `requires_posting`;
  - optional `rate_multiplier_promotions`, each with `multiplier`, optional `start`, `end`, `requires_new_customer`, and `eligible_categories`. Omit `eligible_categories` only when the supplied terms say the multiplier applies to all eligible purchases.

All rates are decimal fractions, not whole-number percentages. Dates define inclusive promotion windows.

### Runnable call shape

For an empty, schema-valid comparison request, call the packaged runner with:

```json
{
  "relative_path": "scripts/compare_card_returns.py",
  "input_json": {
    "purchase_amount": 1,
    "merchant_category": null,
    "cards": []
  }
}
```

Replace the empty `cards` array with records extracted from the task's supplied product documents before using the output for a recommendation.

### Script output and validation

The script emits JSON with `ok`, `errors`, `results`, and rankings. Each result has conservative `standard_first_year_net`, condition-dependent `potential_first_year_net`, selected rate, credit-capacity status, and conditions. Monetary values are decimal strings rounded to cents.

Before using a result, verify:

- `ok` is `true` and `errors` is empty;
- every candidate card has a supported standard rate and fee;
- the merchant category is `null` unless it is actually known from the merchant/payment record;
- fees, offer windows, thresholds, and exclusion handling match the supplied terms; and
- the final customer-facing answer retains all `conditions` and does not treat `potential` ranking as guaranteed.

If documents conflict, lack a fee, do not disclose a credit range, or do not establish promotion eligibility, identify the gap in the response and omit the unsupported calculation rather than filling it with an assumption.
