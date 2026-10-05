---
name: business-card-large-purchase-comparison
description: Compare business credit-card returns for a large prospective purchase when merchant acceptance, surcharge, merchant category code, promotional timing, underwriting, credit limit, and payoff plan can change the recommendation. Use for informational card-selection guidance; not for opening, charging, redeeming, or modifying an account.
---

# Business Card Large-Purchase Comparison

Use this Skill to give a conditional, evidence-based comparison for a large purchase. It is especially useful when a purchase's business purpose does not itself establish its rewards category.

## Scope and safety

This is an informational workflow. Do not apply for a card, submit a credit-limit request, charge a card, redeem rewards, or access customer account data as part of this comparison.

If a later workflow includes any banking action, apply this prerequisite before that action:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Information to collect or label as unknown

Use supplied product terms and the current observed date. Do not assume any unavailable fact. Identify these decision inputs:

1. **Merchant acceptance:** whether the merchant accepts cards, its maximum card-payment amount, and whether split tender is permitted.
2. **Merchant cost:** percentage surcharge and any fixed processing fee. Confirm whether the customer pays it and whether it applies to only the card-paid portion.
3. **Merchant classification:** merchant legal/billing name and its expected MCC/category. Rewards depend on the processor-assigned category, not merely on the buyer's use of the item.
4. **Timing:** anticipated account-opening date, purchase posting date, and dates/conditions of any welcome offer, rate multiplier, or fee waiver.
5. **Approval and capacity:** applicant eligibility, underwriting uncertainty, stated card limit range or minimum, requested/approved limit, and available credit. A published maximum is not a promise that a particular applicant will receive that limit.
6. **Payment plan:** whether the balance will be paid in full. If it will be carried, disclose the applicable purchase APR and avoid presenting cash back as a net gain without an interest estimate.
7. **Reward exclusions and mechanics:** transaction eligibility, merchant-specific exclusions, returns/credits, post-and-clear timing, point conversion, and per-transaction rounding.

For a vehicle, equipment, or other business asset, do not equate “for the business” with Operations, Travel, Software, Media, or any other bonus category. Treat the bonus rate as unknown until the merchant's actual classification and exclusion status are known.

## Method

1. Extract the relevant terms for each candidate card from the supplied current materials: baseline rate, every potentially relevant bonus rate, exclusions, annual fee applicable in the first year, welcome offer, promotion dates, eligibility, credit limits, and APR.
2. Check promotion dates against the observed date and planned account-opening date. State date-bound offers as conditional when opening or posting timing is not confirmed.
3. Build at least two MCC scenarios when the merchant category is unknown:
   - **Non-bonus scenario:** use the card's ordinary eligible-purchase rate.
   - **Confirmed-bonus scenario(s):** use a higher rate only when the supplied terms explicitly cover the merchant's confirmed category and no exclusion applies.
4. For each scenario, calculate rewards transaction by transaction. Cash-back cards represented in points should be converted using the supplied redemption value. Floor each transaction's points to a whole point before converting to currency when the applicable policy requires it.
5. Subtract known first-year annual fees and merchant-paid processing fees. Keep a welcome credit separate unless all of its conditions, including posting deadline and net-spend requirement, are met by the plan.
6. Verify that the entire intended card amount can be accepted and that the approved/available line can support it. If not, calculate only the confirmed card-paid amount and explain that any remaining amount earns no rewards from that card.
7. Present a provisional recommendation, the conditions that could reverse it, and the concise questions the customer should ask the merchant and issuer. Do not promise approval, a particular credit line, merchant recategorization, promotion eligibility, or a reward posting date.

## Using the calculator

`scripts/reward_compare.py` performs deterministic reward, rounding, surcharge, and conditional-welcome-credit arithmetic. The executor supplies current sourced terms in JSON; the script contains no product catalog or customer-specific facts.

### Input schema

```json
{
  "purchase_amount": "decimal dollars, required and greater than zero",
  "merchant_card_cap": "optional decimal dollars",
  "merchant_processing_percent": "optional nonnegative percent",
  "merchant_fixed_fee": "optional nonnegative decimal dollars",
  "cards": [
    {
      "name": "display name",
      "reward_rate_percent": "rate selected for this one MCC/promotion scenario",
      "annual_fee": "first-year fee applicable to this scenario",
      "welcome_credit": "optional decimal dollars",
      "welcome_credit_status": "qualified, not_qualified, or unknown",
      "approved_credit_limit": "optional decimal dollars",
      "available_credit": "optional decimal dollars",
      "transaction_amounts": ["optional charged transaction amounts; must total the card-paid amount"]
    }
  ]
}
```

Invoke it by sending a JSON object matching this schema to `scripts/reward_compare.py` on standard input (or through `run_skill_script` with that object as `input_json`). It emits one JSON object on standard output. To compare multiple MCC or promotional outcomes for one card, submit separate card entries with distinct scenario names and the appropriate sourced rate and fee.

### Output interpretation and validation

For each scenario, the script returns:

- `card_paid_amount`, capped by a known merchant card cap and known card limit/available credit;
- `earned_points`, floored per listed transaction;
- `reward_value`, using one point = $0.01;
- `net_without_welcome_credit` and, if applicable, `net_if_welcome_credit_earned`;
- `full_purchase_chargeable`, plus warnings for unknown capacity, surcharge, or welcome-offer status.

Validate before relying on the result:

- Confirm that the selected rate is supported by the actual MCC and exclusions.
- Confirm that `transaction_amounts`, if supplied, equal the amount actually chargeable to that card.
- Confirm the merchant processing terms rather than treating an omitted surcharge as zero.
- Use the `net_without_welcome_credit` ranking if a welcome offer is not already demonstrably qualified.
- Treat calculator results as pre-interest only. If the balance is carried, explain that interest can exceed rewards.

## Response structure

1. Start with the direct answer to the customer's clarification: acceptance determines how much can earn rewards; surcharge reduces or can erase the return; MCC determines the rate; and approved limit determines whether the purchase can be placed on the card.
2. Give a compact scenario table showing gross reward, welcome-credit condition, first-year fee, processing-fee treatment, and net result. Clearly distinguish known facts from assumptions.
3. State the leading option only under its conditions. For an unknown MCC, the baseline-rate comparison is the default; do not lead with a bonus-rate outcome.
4. Explain the break-even test for a percentage surcharge: compare the surcharge percentage against the net reward percentage for the card-paid amount, after applicable fixed fees and annual fee. A fixed fee must also be subtracted separately.
5. List the next questions: full charge versus cap, surcharge amount, MCC/billing entity, split-payment policy, expected posting date, and likely approved limit. Include any needed credit-score or business-credit eligibility checks from the sourced terms.

Do not infer an MCC from the merchant's marketing description or recommend paying a surcharge until the resulting net return is positive and the customer is comfortable with the payment and credit implications.
