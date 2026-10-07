---
name: business-card-large-purchase-comparator
description: Compare documented business credit-card options for a planned large purchase. Use when a customer asks which new business card offers the best return and the answer depends on rewards categories, welcome offers, annual fees, eligibility, or the ability to make one large charge.
---

# Business Card Large-Purchase Comparator

Give the documented comparison **before** asking optional follow-up questions or offering a transfer. Unknown credit scores, merchant coding, or final credit limits require qualified language; they do not prevent a useful comparison when product terms are supplied.

## Runtime inputs

Extract from the customer request, conversation, current-time observation, and supplied product documents:

- purchase amount and whether it is one charge or multiple charges;
- merchant name and merchant category/MCC, if known;
- intended account-opening date and new-customer status;
- for every relevant product: base and enhanced reward rates, category definitions and exclusions, annual fee, fee-waiver offers, welcome/statement-credit offers, eligibility thresholds, and published credit-limit range.

Use only facts supported by the supplied documents. Never treat a business purpose (for example, equipment or a vehicle) as proof that a purchase receives an operations, travel, software, advertising, or other bonus rate. Merchant classification is determined by the merchant/payment processor unless the documents say otherwise.

## Required method

1. **Screen the one-charge feasibility.** Compare the full purchase amount with each published maximum line. A published range is only screening guidance: approval, the assigned line, and available credit remain subject to underwriting. For a single charge, the actually assigned available credit line must cover the entire amount.
2. **Compute the confirmed baseline first.** If merchant coding is not verified, calculate the documented non-bonus/default result for every card. Do not call an enhanced result likely, normal, or guaranteed.
3. **Show only relevant conditional upside.** State each potentially applicable bonus rate separately, name its required merchant category, and calculate it as a conditional scenario. Do not imply unrelated enhanced categories apply to the purchase.
4. **Apply dates exactly.** Determine promotion eligibility from the intended opening date, not merely the current date. Respect inclusive start/end dates, new-customer requirements, good-standing requirements, and rules that purchases must post or clear during a stated period. A promotion that ended before the intended opening date is unavailable and must be said to be unavailable.
5. **Compare net first-year value.** Show gross purchase rewards, then subtract an applicable first-year annual fee. Keep conditional welcome/statement credits separate unless all threshold, timing, posting, and new-customer conditions are known to be met. A threshold bonus is not automatic merely because the planned purchase amount exceeds its threshold.
6. **Give a practical recommendation.** Select the highest *supported* net result that is reasonably feasible, then name the confirmation needed to rely on it. Include alternatives for a customer who cannot meet the leading card's credit requirements, cannot obtain a sufficient assigned line, or prefers no annual fee.

Use `scripts/evaluate_business_card_options.py` for repeated reward, fee, welcome-offer, date-window, and published-limit arithmetic. Its input schema is in `references/input-schema.md`. Populate it from the current documents; do not hardcode a prior customer's dates, scores, transaction amount, merchant, or product data.

## Required customer-facing response

Use a compact, decision-oriented structure:

1. **Recommendation and key caveat:** name the leading option and say whether that recommendation relies on confirmed merchant coding, an active offer, or underwriting.
2. **Comparison table or bullets:** for each relevant card include:
   - baseline rate and cash-back value on the stated purchase;
   - conditional category outcome(s), clearly labeled `conditional` with the required coding;
   - standard fee and applicable first-year fee/waiver;
   - conditional welcome or statement-credit value and all posting/net-spend/timing conditions;
   - published limit range and applicable score thresholds.
3. **Eligibility and charge warning:** say that the customer's unknown scores prevent determining eligibility when scores are not supplied, and that underwriting and the assigned line must support the entire charge.
4. **Next checks:** ask for the dealer's merchant category/MCC and the customer's approximate personal/business credit only to refine the answer already provided.

Explicitly distinguish **gross rewards**, **first-year reward minus fee**, and **conditional welcome-credit value**. Mention returns/credits where documentation says rewards or qualifying spend are calculated on net purchases.

If the customer asks for a human after receiving the comparison, use the normal transfer tool with the applicable reason. A transfer must not replace the documented comparison. Do not claim that product terms are unavailable when relevant supplied documents contain them.

## Calculator invocation

```text
python scripts/evaluate_business_card_options.py < prepared-card-comparison.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout. It makes no banking changes, does not obtain merchant coding, and does not approve an application. Treat any `validation_errors` as blocking for that affected product: correct the document extraction or omit the unsupported conclusion.
