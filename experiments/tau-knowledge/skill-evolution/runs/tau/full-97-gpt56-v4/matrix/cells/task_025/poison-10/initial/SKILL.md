---
name: business-card-large-purchase-advisor
description: Compare Business Bronze, Silver, Gold, and Platinum Rewards Cards for a proposed large business purchase. Use when a customer asks which new business card offers the best return and the answer depends on credit-line capacity, merchant category, named merchant exclusions, promotional timing, and cash-back rates.
---

# Business-card large-purchase advisor

Use this Skill to give a careful, evidence-based comparison rather than promising approval or a bonus category that has not been confirmed.

## Required runtime input

Run `scripts/compare_cards.py` with JSON on stdin. Its input schema is:

```json
{
  "purchase_amount": "decimal amount greater than zero",
  "merchant_name": "merchant/billing name, if known",
  "purchase_description": "what is being bought",
  "as_of": "YYYY-MM-DD",
  "is_new_customer": true,
  "account_open_date": "YYYY-MM-DD",
  "merchant_category": "optional confirmed category: travel, software, media_advertising, operations, or other"
}
```

`account_open_date` is required to determine the Silver double-cash-back offer. For a customer who is considering opening today, use the supplied current date as both `as_of` and `account_open_date`, and say that the calculation assumes the account opens that day. Do not infer a merchant category merely from a product description. If the merchant category is not confirmed, omit `merchant_category` or send `other`.

Example runnable call (illustrative placeholders only):

```sh
python3 scripts/compare_cards.py <<'JSON'
{"purchase_amount":"5000","merchant_name":"Vendor","purchase_description":"subscription","as_of":"2025-01-01","is_new_customer":true,"account_open_date":"2025-01-01"}
JSON
```

The script emits JSON containing:

- `cards`: every relevant card, its stated maximum line, capacity result, calculated known rate/reward, and conditional bonus possibilities;
- `ranked_capacity_options`: cards whose stated maximum line can accommodate the single proposed charge, sorted by known reward; and
- `limitations`: material facts that prevent a guaranteed recommendation.

Amounts and calculated reward values are decimal dollar strings rounded to cents. A `max_line_can_cover_single_charge` result means only that the product's published maximum is at least the purchase amount; it is **not** an approval or assigned-limit prediction.

## How to respond

1. State the amount, the assumed billing merchant/category, and the date assumption. Merchant category code controls bonus eligibility.
2. Remove or clearly mark cards whose published maximum line is below the full single-payment amount. Do not suggest splitting the charge unless the customer asks; the request is for a single payment.
3. Lead with the highest *known* result among cards that can accommodate the charge. Present the rate and dollar cash back. Separate conditional upside from the known result:
   - A conditional rate needs the actual qualifying merchant category to be confirmed.
   - A named exclusion overrides the otherwise relevant Silver travel/software bonus.
4. For Silver, explain that Apple is a specified hardware/electronics merchant exclusion. Apple-billed transactions earn the Silver standard rate rather than the 10% software rate. During a qualifying six-month double-cash-back window, that standard 1% rate is doubled to 2%; exclusions still apply.
5. For Platinum, only call 4% confirmed when the transaction is actually coded as travel, software, or media advertising. Do not equate a consumer streaming subscription with a media-advertising charge without confirmation. For Gold, only call 2.5% confirmed for an operations-coded charge.
6. Mention salient qualification constraints without assuming customer eligibility: Silver requires personal FICO 700 and, for established businesses, PAYDEX 47; Gold requires FICO 735/PAYDEX 67; Platinum requires personal credit 765/PAYDEX 77. Published maximum lines are Silver $112,500, Gold $225,000, Platinum $400,000, and Bronze $50,000.
7. Mention fees when relevant to the comparison. Silver's standard annual fee is $122.50 (with a separately stated new-customer fee-waiver offer window); Gold is $200; Platinum is $450 with a stated new-customer first-year waiver when opened in its offer window. Only claim a waiver when the applicable date window is satisfied by supplied dates.
8. End with the practical verification step: obtain the billing merchant name and merchant category code before applying/charging, and ensure the approved line is at least the entire amount. Do not apply for a card or make account changes for the customer.

## Validation

Before relying on the result, verify that `purchase_amount` parsed successfully, `as_of` and any opening date use `YYYY-MM-DD`, and the response distinguishes `known_rate_percent` from `conditional_bonus`. If dates or merchant category are missing, explain the uncertainty rather than manufacturing a rate. The script deliberately returns structured errors for invalid input.
