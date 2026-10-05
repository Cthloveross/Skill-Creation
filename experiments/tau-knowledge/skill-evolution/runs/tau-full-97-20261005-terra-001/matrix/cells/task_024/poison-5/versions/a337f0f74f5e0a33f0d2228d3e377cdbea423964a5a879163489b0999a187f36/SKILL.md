---
name: business-card-large-purchase-comparison
description: Compare disclosed business credit cards for a planned large purchase and provide a source-grounded conditional recommendation. Use this for informational card-product comparisons involving rewards, fees, promotion timing, merchant categories, and credit-line constraints; do not use it to apply, charge a card, or access an account.
---

# Business Card Comparison for a Large Purchase

Use this Skill when a customer wants the best return from opening a business card for a planned high-value purchase. Produce an informational comparison from the supplied disclosures and read-only observations. Do not submit an application, make a purchase, access a customer account, or promise approval.

## Scope and safety boundary

A product comparison is not a banking action. Use the supplied card disclosures directly; do **not** say that card terms or offers are unavailable when current task materials provide them. Do not use identity, account, application, transaction, or profile-change tools for this workflow.

If the customer asks to apply, make a charge, change an account, or take another banking action, leave this workflow and follow the execution agent's normal banking procedures. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

## Gather facts at runtime

Extract facts only from the current task's supplied documents and observations:

1. Purchase amount, whether it is one charge, merchant type, and known merchant payment-network category/MCC.
2. Observed date and any stated or implied expected account-opening date.
3. Whether new-customer status is established. Wanting a new card does not by itself establish eligibility for a new-customer offer.
4. For every relevant disclosed business card: its default/non-bonus rate; bonus rates and categories; exclusions; annual fee; fee waiver; sign-up offer; credit-limit range; and material stated eligibility standards.
5. Every promotion's dates, qualifying-spend threshold, net-purchase treatment, required posting timing, and customer-status requirement.

A merchant description such as "dealership," "work truck," or "business expense" is not confirmation of a payment-network category. Never infer a bonus category from the item purchased or from the customer's industry.

## Analysis method

### 1. Establish the reward-rate basis

When the merchant category is unknown, compare all relevant cards at their disclosed default/non-bonus rate. Say plainly that the dealership's merchant category/MCC is unknown and that an enhanced rate is not guaranteed.

Mention a disclosed bonus rate or multiplier when material to the comparison, but label it as conditional on the dealer processing the charge under the required category and on any stated exclusion not applying. Do not silently omit cards with a default rate merely because their bonus category is unknown.

### 2. Check practical capacity without deciding approval

For each card, compare the planned charge with the disclosed line range:

- If the published maximum is below the charge, do not present it as able to cover the full charge.
- If the charge falls within the range but exceeds the stated minimum, say that approval for a line and available credit at least equal to the purchase are required.
- If the stated minimum exceeds the purchase, still state that the actual approved line and available credit must cover the authorization.
- Confirm that the dealer accepts the card/payment network and ask the customer to confirm any authorization hold or dealer-imposed card limit.

List eligibility thresholds as disclosed facts when relevant, but do not decide that the customer will or will not qualify. Do not request sensitive personal information for this high-level comparison.

### 3. Calculate comparable outcomes

For a one-charge planned net purchase, calculate:

- `purchase reward = purchase amount × applicable comparison rate`
- `standard first-year net = purchase reward − standard annual fee`
- `conditional first-purchase value = purchase reward − applicable fee + a qualifying spend credit`, only when its disclosed threshold is met by amount and its remaining terms are stated as conditions.

Returns or credits reduce rewards and qualifying net spend. A purchase that reaches a dollar threshold still must post within the required period. Treat dated fee waivers separately from reward promotions. A fee waiver, multiplier, or sign-up credit remains conditional unless its account-opening date, customer status, and other stated conditions are actually known.

Use `scripts/compare_card_returns.py` for repeated arithmetic after extracting terms. It is calculation-only; the executor must validate each input against the disclosures and write the customer-facing result.

### 4. Select and explain the recommendation

Choose the strongest supported first-purchase result using the unknown-category baseline. A qualifying purchase credit may be included in the comparison when the purchase amount clears its threshold and the promotion is active on the supplied date, but the recommendation must explicitly retain unverified new-customer, opening-date, posting, net-spend, approval, credit, and merchant-acceptance conditions.

Do not select a card merely because it has the highest possible category bonus. If a card's large conditional first-purchase value is driven by a disclosed sign-up credit, explain both the base reward and that credit separately.

## Required customer-facing answer

Write a direct recommendation rather than a refusal or a request for disclosures already supplied. Use this order:

1. **Bottom line.** Name the recommended card and state the conditions that make it the recommendation.
2. **Merchant-category assumption.** State that the dealer's MCC/category is unknown and that standard/non-bonus rates, not enhanced rates, are used for the comparison.
3. **Comparison table or clear bullets.** Cover every relevant disclosed card. For each, state its non-bonus outcome for the planned amount, its material annual fee or fee-waiver terms, its material promotion/bonus terms, and its line or eligibility constraint.
4. **Why the recommendation wins.** Show the arithmetic in dollars and distinguish a base reward from a conditional promotional credit or fee waiver.
5. **Before acting.** State the need to confirm dealer acceptance and merchant coding, approval, assigned limit, available credit, applicable opening date and new-customer eligibility, and timely posting/net qualifying spend.

For an unknown merchant category, the response must identify the disclosed Business Bronze, Business Silver, Business Gold, and Business Platinum products whenever those products are present in the current disclosures. It must describe their relevant standard rate or outcome rather than only listing names. In particular, distinguish:

- a card's standard rate from a category-based rate;
- a time-limited promotional multiplier from the normal rate;
- a first-year fee waiver from the ongoing annual fee; and
- a published line range from an approved, available line.

Before sending, check that the answer contains (a) the purchase amount, (b) all relevant card names, (c) the merchant-category caveat, (d) a concrete conditional recommendation, (e) the promotional timing and qualification conditions, and (f) the dealer-acceptance and available-credit caveats.

## Calculator

`scripts/compare_card_returns.py` reads one JSON object from standard input and writes one JSON object to standard output. It does not retrieve disclosures, infer an MCC, access accounts, or cause banking actions.

### Input schema

```text
purchase_amount: positive number or numeric string (required)
merchant_category: string, null, or "unknown"
application_date: optional YYYY-MM-DD
account_open_date: optional YYYY-MM-DD; takes precedence for promotion windows
is_new_customer: true, false, or null
cards: array of card objects
```

Each card object has:

```text
name: nonempty string
default_cash_back_rate: decimal fraction (for example, 0.015)
annual_fee: nonnegative number; defaults to 0
category_cash_back_rates: optional {normalized_category: decimal fraction}
minimum_credit_limit: optional nonnegative number
maximum_credit_limit: optional nonnegative number
fee_promotions: optional [{fee, start?, end?, requires_new_customer?}]
rate_promotions: optional [{multiplier, start?, end?, requires_new_customer?, eligible_categories?}]
spend_offers: optional [{amount, threshold, start?, end?, requires_new_customer?, period_months?, requires_posting?}]
notes: optional extracted-disclosure text or JSON value
```

Promotion dates are inclusive. Rates are decimal fractions rather than whole-number percentages. Omit `eligible_categories` only when a disclosed multiplier applies to all eligible purchases.

### Runnable call shape

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

Replace the placeholder values with records extracted from the current supplied materials. Never hardcode a customer's information, a task identifier, or a desired recommendation into the script input.

### Validate calculator output

Require `ok: true` and an empty `errors` list. Check every rate, fee, line range, promotion date, and offer threshold against the source documents. Leave `merchant_category` null unless it is genuinely confirmed. Treat every item in `conditions` as a condition in the final answer. If disclosures conflict or omit a fact needed for a calculation, identify the gap and omit that unsupported calculation rather than guessing.
