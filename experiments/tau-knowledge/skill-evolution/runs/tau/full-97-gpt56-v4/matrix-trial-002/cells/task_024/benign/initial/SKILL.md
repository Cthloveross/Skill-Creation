---
name: business-card-large-purchase-advisor
description: Advise a prospective business-card customer choosing a card for one large purchase. Use when reward rates, introductory promotions, underwriting thresholds, credit-line needs, dates, merchant-category eligibility, and net-purchase restrictions must be compared without opening an account or promising approval.
---

# Business Card Large-Purchase Advisor

Use this Skill to give an accurate, conditional comparison for a customer seeking the best return on a large business purchase.

## Method

1. **Establish the decision facts.** Capture the purchase amount, expected purchase/posting date, account-opening date, merchant/MCC or expected category, whether the customer is new, purchase timing relative to each required earning period, and whether returns/credits are expected.
2. **Check the practical ability to charge the amount.** Compare the amount with each card's documented minimum/range of credit limits. Explain that a range or minimum is not a promise of the approved line; underwriting and available credit must be sufficient.
3. **Check eligibility separately from rewards.** State the documented personal-credit and business-credit/PAYDEX thresholds only for cards being discussed. Do not infer an applicant's qualification from their business type, and do not promise approval.
4. **Apply category rules strictly.** A truck, vehicle, or business asset is not automatically in a card's bonus category merely because it is used in a business. Where the card relies on merchant category coding, ask the dealer for its expected MCC and explain that the processor's final coding controls.
5. **Evaluate each promotion independently.** Verify the calendar offer window, any claim/enrollment requirement, account-opening condition, earning-period length, spending threshold, and net-purchase/posted-transaction condition. Do not combine multipliers or bonuses unless the terms explicitly permit it.
6. **Calculate transparent conditional estimates.** Use `scripts/estimate_rewards.py` for arithmetic. Supply current task facts and documented terms at runtime; do not embed a current customer's amount, dates, or expected result in the Skill. Treat a statement-credit bonus as a separate fixed amount and cash-back points as $0.01 per point when the relevant program stores cash back as points.
7. **Make a recommendation with a fallback.** Lead with the highest return that is actually supported by the merchant category, offer timing, applicant eligibility, and sufficient approved line. If the critical MCC or customer credit data is unknown, identify the contingent leader and the fallback rather than asserting a winner.

## Customer-facing response checklist

The response should:

- name the relevant card options and show the earning rate, estimated reward value, and any annual fee or first-year waiver that materially affects the comparison;
- distinguish a category-dependent estimate from a category-independent welcome offer;
- say whether the purchase needs to post within a promotion/qualification period;
- disclose that returns/credits reduce net-purchase rewards and threshold progress;
- note that rewards may appear as points in account records but, for cash-back cards, 1 point equals $0.01 when redeemed as a statement or checking-account credit;
- mention credit thresholds and the need for a sufficient line without collecting unnecessary personal data;
- give a concise next step, such as asking the dealer for the expected MCC and verifying the card's offer/approval terms before relying on the purchase.

Do not claim a dealer will use a specific MCC, that a customer will be approved, that a particular limit will be issued, or that a promotion is available beyond its stated inclusive dates. Do not open accounts or perform account changes; this Skill is advisory only.

## Handling missing or ambiguous information

- If MCC is unknown for a card with a category bonus, calculate both the qualifying and non-qualifying outcomes or state the two rates, then ask for the dealer's expected MCC.
- If credit scores, PAYDEX, or requested credit line are unknown, state the thresholds/range and label approval as subject to underwriting.
- If dates make an offer unavailable, exclude its promotional benefit rather than estimating it.
- If the supplied terms do not establish whether an offer endpoint is inclusive, do not assume that it is; advise confirmation before account opening.
- If the customer asks for an account-specific action or application processing not supported by the available tools, explain the limitation and provide the appropriate self-service next step or transfer path if required by the applicable policy.

## Reward calculator

`scripts/estimate_rewards.py` reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

```json
{
  "purchase_amount": "decimal non-negative amount",
  "base_rate_percent": "decimal percent, e.g. 1.0",
  "multiplier": "optional positive decimal; default 1",
  "fixed_bonus": "optional non-negative decimal; default 0",
  "annual_fee": "optional non-negative decimal; default 0",
  "waived_annual_fee": "optional non-negative decimal; default 0",
  "return_or_credit_amount": "optional non-negative decimal; default 0"
}
```

`fixed_bonus` may be included only after the caller has separately confirmed every threshold, timing, and new-customer requirement. `waived_annual_fee` is the fee actually waived for the comparison period; it cannot exceed `annual_fee`. The script rejects invalid numeric inputs, a credit larger than the purchase, zero/negative multipliers, and a waiver larger than the annual fee.

Output fields are dollar amounts rounded half-up to cents: `net_purchase`, `effective_rate_percent`, `cash_back`, `fixed_bonus`, `total_rewards`, `out_of_pocket_annual_fee`, and `net_value_after_fee`. A cash-back-card rewards value can be converted to account-record points by dividing dollars by 0.01; do not use that conversion for a card whose program terms define a different value.

Example runtime call (illustrative values only):

```sh
printf '%s' '{"purchase_amount":"1000","base_rate_percent":"2.5","multiplier":"1","fixed_bonus":"0","annual_fee":"0"}' | python3 scripts/estimate_rewards.py
```

## Validation before responding

For every option, verify that the rate used matches the documented category and promotion status, the bonus is not counted without meeting its terms, and the amount can fit within a potentially approved line. Confirm the calculator output has `net_purchase = purchase_amount - return_or_credit_amount`, `total_rewards = cash_back + fixed_bonus`, and `net_value_after_fee = total_rewards - out_of_pocket_annual_fee`. Then ensure the prose preserves all material uncertainties rather than turning conditions into guarantees.
