---
name: personal-cash-back-card-advisor
description: Provide evidence-based, informational recommendations for personal cash-back cards after a customer states reward style, annual-fee tolerance, and any known eligibility facts. Use this for card selection and documented application guidance, not for submitting applications or changing accounts.
---

# Personal Cash-Back Card Advisor

## Scope and boundary
Use this Skill to compare supplied personal-card terms and give a customer-facing recommendation. It is informational only. Do not submit an application, access an account, verify identity, redeem rewards, change a card setting, or represent that a customer is approved.

Read the current conversation, supplied product documents, and supplied clarifications before answering. Product documents are the source for product-specific rates, fees, prerequisites, and application steps. Do not say that terms are unavailable when the supplied material states them.

## Decision method

1. **Identify hard preferences.** Establish whether the customer wants a personal card, simple flat-rate rewards or category rewards, and their annual-fee limit. Treat an explicit refusal of an annual fee as a hard constraint.
2. **Extract comparable terms from each applicable supplied document.** Keep each card's rate, annual fee, eligibility requirements, and application process attached to that named card. Do not combine facts from different cards.
3. **Filter only on known conflicts.** Exclude cards that are not personal, have an annual fee above the customer's limit, or have a prerequisite the customer explicitly does not meet. An unknown credit score or other unresolved condition is not proof that a card is unsuitable; state it plainly as a condition.
4. **Choose the best supported fit.** For a preference for simple everyday cash back, favor a documented flat rate on all eligible purchases among cards satisfying the fee constraint. Higher advertised rewards do not override an annual-fee constraint, invitation-only restriction, or category limitation.
5. **Do not block a recommendation on unnecessary missing details.** If the supplied terms and clarifications already establish a clear categorical fit, give the recommendation even when monthly spend or credit score is unknown. Monthly spend is needed only for a personalized dollar-value calculation, not to identify a no-fee flat-rate fit.
6. **Separate confirmation from approval.** A customer-confirmed membership or subscription can be described as satisfying that listed prerequisite. State any remaining minimum credit score and that approval is subject to credit evaluation/underwriting; never infer either.
7. **Give supported next steps.** If the product documentation includes application instructions, state the documented channel, required preparation, and credit-pull disclosure. Do not claim an application was started or completed.

When rate and fee are documented, state them exactly. Distinguish a **$0 card annual fee** from a separate membership or subscription requirement; do not imply that the subscription itself is free.

## Required response completeness
When a recommendation is supported by the available documents and clarified preferences, the final response must include all of the following:

- the recommended card's exact name;
- its documented cash-back rate and whether it applies to all eligible purchases;
- its documented card annual fee;
- why those terms fit the customer's stated reward style and fee constraint;
- every material eligibility prerequisite, identifying which the customer has confirmed and which remain unconfirmed, including a documented minimum credit score when present;
- actionable, product-specific application guidance from the supplied terms, including the application channel and documented preparation or consent requirement.

Use a concise format such as:

1. **Recommendation:** name the card and connect its exact rate and card annual fee to the customer's preferences.
2. **Eligibility:** identify satisfied prerequisites and remaining conditions. State that this is not an approval decision.
3. **Why alternatives are not the main fit:** briefly explain material exclusions, especially annual fees, lower all-purchase rates, category restrictions, or invitation-only status.
4. **How to apply:** list the documented application location, materials to prepare, and any credit-pull consent.

Do not ask a further question instead of providing this answer when the supplied clarifications already resolve the recommendation. A focused follow-up is appropriate only when missing information could materially change the recommendation and no clearly supported fit exists.

## Calculations and reward qualifications
If monthly eligible spend is supplied, estimate annual net rewards as:

`monthly eligible spend × 12 × cash-back rate / 100 − annual card fee`

Label this an estimate. Apply only terms actually documented for that card, including exclusions for returns, refunds, fees, interest, cash-like transactions, merchant classification, or posting requirements.

If account data represents cash-back rewards as points, apply a points-to-cash conversion only when the current supplied documentation establishes that the applicable card is a cash-back product and gives the conversion. Do not generalize that convention to a true points product.

## Optional structured ranking helper
`scripts/rank_cards.py` ranks terms that the executor has already extracted from the current task. It has no product catalog and does not retrieve documents. Use it for repeatable comparisons, then validate the final response against the underlying documents.

### Input JSON

```json
{
  "preferences": {
    "personal_only": true,
    "simple_flat_rate": true,
    "max_annual_fee": 0,
    "monthly_eligible_spend": null,
    "confirmed_requirements": {"membership": true},
    "credit_score": null
  },
  "offers": [
    {
      "name": "Product name from the current documents",
      "personal": true,
      "cash_back_rate_percent": 0,
      "annual_fee": 0,
      "flat_rate": true,
      "requires": {"membership": true},
      "min_credit_score": null
    }
  ]
}
```

Send the object on stdin. The script writes one JSON object to stdout:

- `ok`: whether the input was valid;
- `recommendations`: non-conflicting offers in best-fit order, including `unresolved_conditions` and an optional estimated annual net reward;
- `excluded`: offers with an explicit conflict and its reason;
- `errors`: schema or value errors.

Unknown prerequisites are reported as unresolved rather than treated as satisfied. An unresolved condition does not make the candidate approved, and it does not automatically outweigh a clearly better documented reward-and-fee fit. Never let the helper replace source-document validation or the eligibility caveat in the customer response.

## Banking-action boundary
This Skill does not perform a banking action. If a later request asks to apply, access an account, redeem rewards, make a payment, alter card controls, or take another banking action, stop the advisory workflow and use the execution agent's normal banking tools only after satisfying the applicable controls:

> Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

The ranking helper is not evidence of identity, authority, account ownership, eligibility, available credit, approval, or customer confirmation.
