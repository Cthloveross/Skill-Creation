---
name: business-card-large-purchase-comparison
description: Compare current business credit-card terms and likely return for a large prospective purchase, including merchant acceptance, surcharge, MCC, promotion timing, underwriting, credit-limit capacity, and payoff plan. Use for informational card-selection guidance, not for opening, charging, redeeming, or modifying an account.
---

# Business Card Large-Purchase Comparison

Use this Skill to provide a substantive, conditional comparison when a customer wants a new business card for a large purchase. A purchase's business purpose does not by itself establish a rewards category.

## Scope and safety

This is an informational workflow. Do not apply for a card, submit a credit-limit request, charge a card, redeem rewards, access customer account data, or transfer the customer merely because a final approval or merchant classification is unknown.

If a later workflow includes any banking action, apply this prerequisite before that action:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required decision inputs

Use supplied current product materials and the current observed date. Do not assume an unavailable fact. Identify or label as unknown:

1. **Merchant acceptance:** whether cards are accepted, the maximum card-payment amount, and whether split tender is allowed.
2. **Merchant cost:** percentage surcharge and any fixed processing fee, including whether it applies to the entire card-paid portion.
3. **Merchant classification:** merchant legal/billing name and expected merchant category code (MCC).
4. **Timing:** anticipated account-opening date, transaction-posting date, and all promotion, welcome-offer, or fee-waiver dates.
5. **Approval and capacity:** eligibility, underwriting uncertainty, published limit range, approved limit, and available credit.
6. **Payment plan:** whether the balance will be paid in full. If it will be carried, disclose APR and do not portray rewards as a net gain without an interest estimate.
7. **Reward mechanics:** transaction eligibility, exclusions, returns, post-and-clear requirements, point value, and rounding.

For a vehicle, equipment, or other business asset, do not equate “for the business” with Operations, Travel, Software, Media, or another bonus category. A bonus rate is conditional on the actual processor-assigned MCC and any card-specific exclusions.

## Method

1. Extract current terms for each relevant candidate card: ordinary rate, potentially applicable bonus rates, MCC conditions, exclusions, first-year fee, welcome offer, promotion dates, eligibility, published credit limits, and APR.
2. Compare every date-bound offer with the observed date and expected opening/posting date. An unconfirmed date condition remains conditional.
3. Where MCC is unknown, calculate the ordinary-rate outcome as the baseline. Calculate a bonus-rate outcome only as a separately labeled conditional scenario when supplied terms explicitly cover the confirmed MCC and no exclusion applies.
4. Calculate rewards transaction by transaction. When a rewards program records cash back as points, apply the supplied point value and floor points per transaction if the terms require it.
5. Subtract known first-year annual fees and merchant-paid processing fees. Keep a welcome credit separate unless the plan demonstrably meets every requirement.
6. Check whether the merchant can accept the intended amount and whether the actual approved and available line can support the entire card charge. A published maximum never establishes a customer's available credit.
7. Give the best-supported recommendation and the facts that could change it. Do not promise approval, a specific line, merchant recategorization, promotion eligibility, or reward-posting time.

## Mandatory completion for a request for current options and terms

When supplied materials contain current terms, answer the customer's comparison request directly before suggesting any referral. Do not say that terms are unavailable simply because approval, MCC, merchant acceptance, or surcharge is unknown.

For every named candidate with available terms, provide a concise comparison that includes:

- ordinary eligible-purchase reward rate;
- each relevant conditional bonus rate and its MCC condition;
- standard annual fee and an applicable first-year fee or waiver, with dates and eligibility where supplied;
- published credit-limit range or minimum/maximum;
- material applicant thresholds, such as personal-credit and established-business-credit thresholds; and
- any applicable welcome offer or promotion and its conditions.

For a large-purchase request, the response must contain all of the following:

1. **A direct explanation of uncertainty.** State that dealer acceptance controls how much can be charged, a surcharge reduces the return, MCC controls category bonuses, and approved/available credit controls whether the charge can be completed.
2. **An ordinary-rate comparison.** Do not omit candidate cards solely because their category bonus is uncertain. If the request identifies several cards with available sourced terms, name and compare at least three of them.
3. **A specific conditional leader.** Rank using the documented ordinary-purchase case, including a welcome credit only when the proposed plan satisfies its sourced opening, net-purchase, and posting requirements. Show the reward arithmetic rather than merely naming a card.
4. **Capacity disclosure.** If a recommendation requires a large line, state the relevant published range and that underwriting and available credit must be sufficient; do not imply that a stated maximum will be approved.
5. **MCC disclosure.** Explicitly say that a truck or other business asset does not automatically qualify for travel, software, media, operations, or other category bonuses merely because it is used for the business. State that the bonus depends on the processor-assigned MCC/merchant category.

If the supplied materials and customer assumptions establish that one candidate's ordinary-rate reward plus a currently available welcome credit exceeds the alternatives, recommend it conditionally. State every required date window, minimum net-spend threshold, transaction-posting deadline, eligibility requirement, applicable first-year fee, and line-capacity condition next to that conclusion. Do not present a conditional promotional result as guaranteed.

## Calculator

`scripts/reward_compare.py` performs deterministic reward, rounding, surcharge, capacity, and conditional-welcome-credit arithmetic. The executor supplies sourced current terms at runtime; the script contains no product catalog, customer identity, or preselected recommendation.

### Input schema

```json
{
  "purchase_amount": "decimal dollars, required and greater than zero",
  "merchant_card_cap": "optional decimal dollars",
  "merchant_processing_percent": "optional nonnegative percent",
  "merchant_fixed_fee": "optional nonnegative decimal dollars",
  "cards": [
    {
      "name": "display name or scenario name",
      "reward_rate_percent": "rate selected for this MCC/promotion scenario",
      "annual_fee": "first-year fee applicable to this scenario",
      "welcome_credit": "optional decimal dollars",
      "welcome_credit_status": "qualified, not_qualified, or unknown",
      "approved_credit_limit": "optional decimal dollars",
      "available_credit": "optional decimal dollars",
      "transaction_amounts": ["optional charged transaction amounts; must total card-paid amount"]
    }
  ]
}
```

Send this JSON object to `scripts/reward_compare.py` on standard input, or invoke `run_skill_script` with it as `input_json`. For alternative MCC or promotion outcomes for one card, submit distinct entries with clear scenario names.

### Output interpretation and validation

For each scenario, the script returns the capped card-paid amount, floored points, cash value, annual fee, known merchant surcharge, baseline net result, conditional welcome-credit result, and warnings. It values one point at $0.01.

Before using a result:

- Confirm the selected rate is supported by the actual MCC and exclusions.
- Confirm supplied transaction amounts exactly total the card-paid amount.
- Treat an omitted surcharge as unknown, not as confirmed zero.
- Use `net_without_welcome_credit` for the baseline ranking unless the welcome offer is demonstrably qualified.
- Treat all results as pre-interest. If a balance will be carried, explain that interest may exceed rewards.

## Response structure

1. Answer how acceptance, surcharge, MCC, and credit capacity affect the recommendation.
2. Present a compact comparison table or bullets with rate, fee, limit, eligibility, promotion, and ordinary-purchase outcome for each candidate.
3. State the leading card only under explicit assumptions, with visible arithmetic for rewards and any conditional welcome credit.
4. Separately identify bonus-rate scenarios as MCC-dependent; do not lead with them when MCC is unknown.
5. State that a percentage surcharge must be lower than the relevant net reward percentage after fees; subtract any fixed fee separately.
6. End with only the unresolved questions needed to finalize the choice: full-charge acceptance or cap, surcharge, MCC/billing entity, split-payment policy, expected posting date, and actual approved/available line.

Do not infer an MCC from marketing descriptions, recommend paying a surcharge unless the resulting net return is positive, or replace an available sourced comparison with an unsupported refusal or escalation.
