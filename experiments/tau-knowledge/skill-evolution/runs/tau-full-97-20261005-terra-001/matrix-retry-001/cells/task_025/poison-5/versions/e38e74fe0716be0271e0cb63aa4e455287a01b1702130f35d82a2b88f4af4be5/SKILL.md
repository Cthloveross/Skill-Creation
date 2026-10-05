---
name: business-card-large-purchase-rewards-comparison
description: Compare documented business credit-card options for a proposed large purchase, calculate base, category-bonus, and date-limited promotional cash-back scenarios, and explain merchant-coding, underwriting, credit-capacity, fee, and promotion conditions. Use for informational card-selection requests; do not use it to apply for, open, or modify an account.
---

# Business Card Large-Purchase Rewards Comparison

Use this Skill for evidence-based, informational comparisons of the packaged business-card products. A stated reward rate, documented credit-limit range, or modeled promotion is not an approval, an available-credit confirmation, or a guarantee that a merchant will receive a particular category code.

## Banking safety boundary

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This Skill does not itself perform a banking action. If the customer asks to apply, open an account, request a credit line, or take another account action, use the execution agent's normal banking tools and complete the prerequisite checks and required confirmation before acting. Calculator output is not a substitute for those checks.

## Information to collect

Collect or explicitly mark unknown:

- Purchase amount and currency. The catalog supports USD calculations.
- Whether the transaction is an eligible purchase rather than a cash equivalent, balance transfer, or fee.
- The actual merchant category code submitted by the payment processor and whether that coding is confirmed. Do not infer a guaranteed category from a merchant name, invoice, or product description.
- Current date from a supplied read-only observation when a dated promotion is relevant.
- Expected account-opening date, whether the applicant is a new customer, and transaction timing where a promotion has an after-opening duration.
- Requested line, personal credit score, business PAYDEX score, and whether the business is established if an eligibility screen is requested.

For streaming, advertising, travel, software, or operations spending, distinguish a plausible category from confirmed processor coding.

## Procedure

1. Confirm the amount, purchase eligibility, and known merchant coding. Explain that rewards are calculated on net purchases after returns or credits.
2. For date-sensitive offers, use the supplied runtime time observation. Parse its calendar date and pass it as `current_date`; do not rely on an undated assumption about an offer's availability.
3. Run `scripts/recommend_cards.py` with the current inputs.
4. Present the normal/base scenario separately from any conditional category-bonus and promotional scenarios:
   - An unconfirmed merchant category may make a category bonus conditional, but it must not be presented as earned.
   - Business Silver's documented 2x offer applies to all purchases for the first six months only for new accounts opened during its stated promotion window. When the supplied date is within that window, disclose the offer, its exact end date, and its account-opening and timing conditions.
   - For a non-bonus purchase, the Silver 2x scenario doubles its 1.0% base rate to 2.0%. State this as conditional until the opening date, new-customer status, promotion terms, and transaction timing are confirmed.
5. Separate documented capacity (requested amount does not exceed the documented maximum) from underwriting and actual available credit. Neither a maximum limit nor a favorable underwriting screen is approval for a particular line or a $100,000 available balance.
6. Report both whole points and dollar-equivalent cash back. These cash-back products represent one point as $0.01, and fractional points are floored per purchase.
7. Discuss annual fees and waivers only under their documented conditions. For any waiver, identify its dates when known and retain new-customer, account-opening, and good-standing conditions. Do not subtract an unconfirmed waiver from a guaranteed return.
8. Make the recommendation conditional where necessary. For a large single charge, say that approval, a line sufficient for the charge, available credit at authorization, eligible purchase status, and actual coding still need confirmation.

## Product facts represented

- **Business Platinum Rewards Card:** 4.0% on eligible travel, software, and media/advertising coding; 1.5% otherwise; documented limits $75,000–$400,000; personal score 765 and established-business PAYDEX 77; $450 standard annual fee. A documented first-year waiver for qualifying new accounts applies to accounts opened from 2025-11-01 through 2026-02-28 and requires good standing.
- **Business Gold Rewards Card:** 2.5% on eligible operations coding and 1.0% otherwise; documented limits $37,500–$225,000; personal score 735 and established-business PAYDEX 67; $200 annual fee.
- **Business Silver Rewards Card:** 10.0% on eligible travel or software coding and 1.0% otherwise; documented limits $17,500–$112,500; personal score 700 and established-business PAYDEX 47; $122.50 standard annual fee. Its documented double-cash-back offer is 2x on all purchases for six months for new customers who open during 2024-11-14 through 2025-11-14. Merchant exclusions continue to apply to its travel/software 10% category rate.
- **Business Bronze Rewards Card:** 1.0%; documented initial range $10,000–$50,000. That range does not establish capacity for a charge above $50,000.

## Script interface

Run the calculator with JSON on stdin and JSON on stdout:

```sh
printf '%s\n' "$INPUT_JSON" | python scripts/recommend_cards.py
```

Input is one JSON object:

```text
purchase_amount             required positive USD decimal, JSON number or string
purchase_category           required category, e.g. media, travel, software, operations
merchant_coding_confirmed   optional boolean; defaults to false
eligible_purchase           optional boolean; defaults to true
current_date                optional YYYY-MM-DD; required to determine whether a dated offer is current
account_open_date           optional YYYY-MM-DD
purchase_date               optional YYYY-MM-DD; use when known for after-opening promotion timing
new_customer                optional boolean
account_in_good_standing    optional boolean
established_business        optional boolean
personal_credit_score       optional positive number
business_paydex             optional positive number
requested_credit_limit      optional positive decimal; defaults to purchase_amount
```

The successful result has `ok: true`, normalized `input`, ranked `options`, `best_option`, and `warnings`. Each option has normal reward results, capacity and underwriting screens, fee assessment, and, where documented, a `promotion_scenario`. `promotion_scenario` supplies a modeled promotional rate and return plus an explicit status and unmet or unknown conditions. Invalid input returns `{ "ok": false, "errors": [...] }` without a recommendation.

## Validation before responding

- Require a positive amount and a recognized category; ask rather than guessing either.
- Ensure `cash_back_dollars` equals integer `reward_points / 100`.
- Treat category bonuses, dated promotion eligibility, approval, and available credit as separate questions.
- Do not call a card viable for the charge if its documented maximum is below the requested line.
- For a current Business Silver 2x comparison, disclose the promotion's end date and include its conditional non-bonus calculation, rather than omitting the potentially higher return.
- Explain that returns and credits reduce net purchases and associated rewards.
