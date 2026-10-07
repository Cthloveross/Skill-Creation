---
name: business-card-large-purchase-rewards-comparison
description: Compare documented business credit-card options for a proposed large purchase, calculate cash-back points using the applicable merchant category and rounding policy, and explain credit-capacity, underwriting, merchant-coding, fee, and promotion conditions. Use for informational card-selection requests; do not use it to apply for, open, or modify an account.
---

# Business Card Large-Purchase Rewards Comparison

Use this Skill to give an evidence-based comparison of the packaged business-card products for a specific proposed purchase. It is an informational workflow: a product's documented limit range or reward rate is not an approval, an available-credit confirmation, or a guarantee of merchant classification.

## Banking safety boundary

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This Skill does not itself perform a banking action. If the conversation progresses from advice to an application, account opening, credit-line request, or other account action, use the execution agent's normal banking tools and complete the prerequisite checks and required confirmation before acting. Do not treat the calculator output as a substitute for those checks.

## Inputs to collect

Collect or explicitly mark as unknown:

- Proposed purchase amount and currency (the packaged rules are USD).
- The merchant category as it will be submitted by the payment processor, plus whether that coding is confirmed. Do **not** infer a guaranteed category solely from the merchant name or purchase description.
- The date the applicant expects to open the account, whether they are a new customer, and whether promotional conditions can be met.
- Whether the business is established, personal credit score, business PAYDEX score, and requested credit limit, if the user wants an eligibility screen.
- Whether the transaction is an eligible purchase rather than a cash equivalent, balance transfer, or fee.

For a streaming, advertising, travel, software, or operations purchase, describe the likely category separately from confirmed payment-processor coding. Enhanced rates depend on the actual code submitted by the merchant.

## Procedure

1. Read the proposed amount and payment category. State that merchant category coding controls bonus treatment.
2. Run `scripts/recommend_cards.py` with the current runtime date and the known inputs. The script reads `references/business_rewards_catalog.json`; do not edit the catalog for an individual customer.
3. Use the script's `options` in rank order. Separate:
   - documented capacity (the requested limit is no more than the documented maximum),
   - underwriting status (only a screen from supplied scores, not an approval), and
   - reward status (confirmed, conditional on coding, or base rate).
4. Report both whole reward points and dollar-equivalent cash back. Packaged cash-back cards store rewards as points worth $0.01 each. The calculator floors fractional points per purchase.
5. Discuss annual fees and first-year fee waivers only with their stated date, new-customer, account-opening, and good-standing conditions. A future promotional opportunity is not a current waiver.
6. Give a concise recommendation only when its prerequisites are clear. Otherwise identify the leading *conditional* option and exactly what must be confirmed (for example, eligible media coding, approved available credit at least equal to the charge, and required credit profile).

## Product facts represented

The catalog contains these documented products and facts:

- **Business Platinum Rewards Card:** 4.0% on eligible travel, software, and media/advertising coding; 1.5% otherwise; documented limits $75,000–$400,000; personal score 765 and established-business PAYDEX 77; standard annual fee $450; dated first-year waiver for qualifying new accounts opened 2025-11-01 through 2026-02-28.
- **Business Gold Rewards Card:** 2.5% on eligible operations coding and 1.0% otherwise; documented limits $37,500–$225,000; personal score 735 and established-business PAYDEX 67; annual fee $200.
- **Business Silver Rewards Card:** 10.0% on eligible travel or software coding and 1.0% otherwise; documented limits $17,500–$112,500; personal score 700 and established-business PAYDEX 47; standard annual fee $122.50. Its catalog record notes the documented new-customer fee-waiver material should be confirmed when a dated offer is relevant.
- **Business Bronze Rewards Card:** 1.0%; documented initial range $10,000–$50,000, so it cannot establish documented capacity for a charge over $50,000.

No product's maximum limit establishes that the applicant will be approved for that limit or that a single charge will have sufficient available credit after approval.

## Script interface

Run with JSON on stdin and receive JSON on stdout:

```text
python scripts/recommend_cards.py
```

A runnable invocation pattern is:

```sh
printf '%s\n' "$INPUT_JSON" | python scripts/recommend_cards.py
```

`INPUT_JSON` must be a JSON object with:

```text
purchase_amount             required positive USD decimal as a JSON number or string
purchase_category           required category, such as media, travel, software, or operations
merchant_coding_confirmed   optional boolean; defaults to false
eligible_purchase           optional boolean; defaults to true
current_date                optional YYYY-MM-DD date used for dated promotions
account_open_date           optional YYYY-MM-DD; defaults to current_date for promotion review
new_customer                optional boolean
account_in_good_standing    optional boolean
established_business        optional boolean
personal_credit_score       optional number
business_paydex             optional number
requested_credit_limit      optional positive decimal; defaults to purchase_amount
```

The response has `ok`, normalized `input`, ranked `options`, `best_option`, and `warnings`. Each option supplies the applied or potential rate, whole `reward_points`, `cash_back_dollars`, annual-fee assessment, capacity screen, underwriting screen, and source document IDs. A malformed input produces `{ "ok": false, "errors": [...] }` and no recommendation.

## Validation before responding

- Require a positive amount and a recognized category; ask a follow-up rather than guessing either.
- Treat an unconfirmed bonus category as conditional, not earned.
- Do not call a card viable for the proposed charge if its documented maximum is lower than the requested limit.
- Preserve `reward_points` as an integer and ensure `cash_back_dollars = reward_points / 100`.
- Explain that returns and credits reduce net purchases and associated rewards.
- If promotion date, applicant status, or good-standing condition is unknown, label the waiver conditional or unconfirmed rather than subtracting it as guaranteed.
