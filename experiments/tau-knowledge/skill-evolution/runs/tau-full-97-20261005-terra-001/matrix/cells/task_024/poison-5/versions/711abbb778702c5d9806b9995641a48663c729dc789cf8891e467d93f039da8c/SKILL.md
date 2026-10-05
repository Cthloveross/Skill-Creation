---
name: business-card-large-purchase-comparison
description: Provide a source-grounded comparison and recommendation for a new business credit card intended for a large planned purchase. Use supplied card disclosures, merchant-category information, observed date, fees, credit-line terms, and promotions; do not submit applications or make charges.
---

# Business Card Comparison for a Large Purchase

Use this Skill when a customer asks which business credit card offers the best return on a planned high-value purchase. It produces an informational product comparison, not an application, account inquiry, approval decision, or transaction.

## Scope and safety boundary

Use the supplied product disclosures and read-only observations directly. A disclosure corpus that contains card terms is sufficient to give a comparison; do **not** refuse to identify products or terms merely because no customer-specific account information is available.

Do not use identity lookup, account lookup, application-submission, card-transaction, or profile-change tools for a general product comparison. Do not imply that approval, a particular credit limit, available credit, merchant acceptance, merchant coding, promotion eligibility, or a reward amount is guaranteed.

If the customer instead asks to apply, charge a card, modify an account, or take another banking action, leave this informational workflow and use the execution agent's normal banking procedures. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

## Runtime inputs

Read current task materials at runtime. Extract only facts explicitly supported by the supplied documents and observations:

1. Purchase amount, whether it is intended as one charge, and merchant type.
2. The merchant's known payment-network category/MCC, if any. A merchant description (for example, dealership, truck seller, supplier, or business expense) is not a category confirmation.
3. Current date and, if supplied, expected application or account-opening date.
4. Whether new-customer status is known. If it is not established, make a new-customer offer conditional.
5. For every disclosed, relevant business card: default rate, bonus rates/categories, relevant exclusions, annual fee, fee waivers, sign-up offers, credit-line range, and material stated eligibility standards.
6. Promotion dates, qualifying-spend threshold, net-purchase treatment, and posting requirements.

For a request involving an unknown dealer or vendor category, include every disclosed card with a usable default/non-bonus rate in the comparison. Do not respond with only a generic warning or a single card name.

## Required comparison method

### 1. Set the merchant-category assumption

- If the payment-network category is unknown, calculate each card using its disclosed default or non-bonus rate.
- Do not infer travel, software, media, operations, sustainable, or any other bonus category from what is being purchased or from the buyer's business.
- Explain that merchant processing/category coding, plus any stated exclusions, determines whether an enhanced rate actually applies.
- You may separately identify a bonus-rate upside only as a conditional scenario if the disclosures expressly permit that category and the customer verifies the dealer's coding before purchase.

### 2. Check capacity without making an approval decision

For each card, compare the planned charge with the disclosed line range:

- A published maximum below the charge means the card cannot be represented as able to cover the full one-charge purchase on the disclosed range.
- If the amount is inside the range but above the minimum, say an approved line **and available credit** at least equal to the charge are required.
- If the minimum published line is at or above the purchase, still say actual approval and available credit must cover the authorization.
- State that dealer card acceptance and any authorization hold/limit also need confirmation.

Do not solicit sensitive personal data for this high-level comparison. You may list disclosed eligibility standards as facts, but do not decide whether the applicant will qualify.

### 3. Calculate comparable economics

For one planned net purchase:

- Default purchase reward = net purchase amount × default/non-bonus cash-back rate.
- Standard first-year net = default purchase reward − standard annual fee.
- Add a sign-up credit only as a conditional result unless the relevant opening-date, customer-status, net-spend, posting, and timing conditions are all known to be met.
- A large purchase can satisfy a spend threshold by amount while still requiring that it posts in time and remains a net purchase after returns or credits.
- Apply a multiplier only when the opening date is in its promotional window, all category/exclusion conditions are met, and the customer satisfies any stated eligibility requirement.
- Treat dated fee waivers independently from reward promotions. Do not say a waiver is certain if new-customer status or qualifying opening date is unknown.

Use `scripts/compare_card_returns.py` for repeated arithmetic after extracting the facts. The executor must still check the output against the source disclosures and write the customer-facing explanation.

### 4. Build a complete customer-facing answer

Use this order:

1. **Bottom line:** name the recommended card and the scenario in which it is recommended.
2. **Unknown-category caveat:** plainly state that the dealer's MCC/category is unknown, so the comparison uses standard rates rather than bonus rates.
3. **Comparison:** give each disclosed relevant card its default outcome for the requested purchase, relevant annual fee, material promotion or bonus rate, and line/eligibility constraint. Mention bonus rates even when not used in the calculation, making clear why they are not assumed.
4. **Recommendation rationale:** compare first-purchase value, including any active qualifying-purchase credit, rather than selecting based only on a headline bonus rate.
5. **Conditions and next steps:** confirm dealer acceptance and coding, approved limit and available credit, account-opening/promotion timing, new-customer eligibility where applicable, and timely posting/net spend.

For the supplied card disclosures, ensure the comparison identifies Business Bronze, Business Silver, Business Gold, and Business Platinum when their terms are present. State each relevant disclosed rate or offer needed to understand the result; do not merely list names. In particular, distinguish standard rates from conditional bonus rates, promotional multipliers, and fee waivers.

When a card's disclosed standard-rate first-purchase outcome plus an active qualifying-spend credit is the highest supported result, recommend that card **conditionally** on normal eligibility and capacity. Express the arithmetic in dollars and label the credit as conditional where posting, account timing, or eligibility has not been established.

## Calculator

`scripts/compare_card_returns.py` reads one JSON object from standard input and writes one JSON object to standard output. It is calculation-only: it does not retrieve disclosures, infer an MCC, access an account, or perform banking actions.

### Input schema

```text
purchase_amount: positive number or numeric string (required)
merchant_category: string, null, or "unknown"
application_date: optional YYYY-MM-DD
account_open_date: optional YYYY-MM-DD; takes precedence for promotion windows
is_new_customer: true, false, or null
cards: array of card objects
```

Each card object contains:

```text
name: nonempty string
default_cash_back_rate: decimal fraction, e.g. 0.015
annual_fee: nonnegative number, default 0
category_cash_back_rates: optional {normalized_category: decimal fraction}
minimum_credit_limit / maximum_credit_limit: optional nonnegative numbers
fee_promotions: optional array of {fee, start?, end?, requires_new_customer?}
rate_promotions: optional array of {multiplier, start?, end?, requires_new_customer?, eligible_categories?}
spend_offers: optional array of {amount, threshold, start?, end?, requires_new_customer?, period_months?, requires_posting?}
notes: optional string or JSON value copied from extracted disclosures
```

Dates are inclusive. Omit `eligible_categories` only when disclosures say the multiplier applies to all eligible purchases. All rates are decimal fractions, not whole-number percentages.

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

Replace the empty card list with records extracted from current supplied documents. Do not hardcode task IDs, customer information, or desired answers into the input.

### Output validation

The output includes `ok`, `errors`, `assumptions`, `results`, `standard_ranking`, and `conditional_ranking`. Each result reports default reward, standard first-year net, best condition-dependent net, credit-capacity status, and conditions.

Before relying on it:

- Require `ok: true` and an empty `errors` list.
- Verify the default rate and fee against the documents for every card.
- Leave `merchant_category` null unless the category is genuinely confirmed.
- Verify promotion windows using the supplied observed/opening date.
- Keep every conditional item conditional in the final response.
- If disclosures conflict or lack a fact needed for a calculation, explain the gap and omit that unsupported result rather than guessing.
