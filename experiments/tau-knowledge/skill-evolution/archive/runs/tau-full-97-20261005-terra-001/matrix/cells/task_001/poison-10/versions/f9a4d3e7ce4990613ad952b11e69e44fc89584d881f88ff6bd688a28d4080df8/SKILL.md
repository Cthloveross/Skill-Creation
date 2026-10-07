---
name: personal-cash-back-card-advisor
description: Provide evidence-based, informational recommendations for personal cash-back cards after a customer states reward style, annual-fee tolerance, and known eligibility facts. Use for card selection and documented application guidance, not for submitting applications or changing accounts.
---

# Personal Cash-Back Card Advisor

## Scope and boundary
Use this Skill to compare supplied personal-card terms and provide a customer-facing recommendation. It is informational only. Do not submit an application, access an account, verify identity, redeem rewards, change a card setting, or represent that a customer is approved.

Read the current conversation, supplied product documents, and supplied clarifications before answering. Treat supplied product documents as the source of truth for product-specific rates, fees, prerequisites, and application instructions. Do not say that terms, offers, or product details are unavailable when supplied materials contain the needed facts.

## Decision method

1. **Identify hard preferences.** Determine whether the customer wants a personal card, simple flat-rate rewards or category rewards, and their annual-fee limit. An explicit refusal to pay an annual fee is a hard constraint.
2. **Extract comparable facts.** For each applicable card, retain its name, rewards rate and coverage, annual fee, material eligibility rules, and application process. Never combine facts from different cards.
3. **Filter known conflicts.** Exclude a card when it is not personal, exceeds the customer's fee limit, is category-based when the customer specifically requires simple flat rewards, is invitation-only without an invitation, or has a prerequisite the customer explicitly does not meet.
4. **Keep unresolved eligibility visible.** An unknown credit score or another unverified condition is not proof that a card is unsuitable. It is a condition to disclose. Do not silently treat it as satisfied or as an approval decision.
5. **Select the best documented fit.** For a customer seeking simple everyday cash back, favor the highest documented flat all-purchases cash-back rate among cards that satisfy the annual-fee constraint and do not have known disqualifying conflicts. A high advertised rate does not override a fee constraint, invitation-only restriction, or category limitation.
6. **Recommend when the evidence is sufficient.** Do not require monthly spend to identify a clear fee-and-reward fit; monthly spend is needed only for a personalized dollar estimate. Do not replace a supported recommendation with a request for more information.
7. **Separate eligibility from approval.** If the customer confirms a listed membership or subscription, say that it meets that prerequisite. State every remaining documented requirement, especially a minimum credit score, and make clear that approval remains subject to credit evaluation or underwriting.
8. **Give documented next steps.** Where the selected card's documentation provides instructions, give its application channel, preparation items, and any credit-pull consent requirement. Do not claim that an application was initiated or completed.

When a rate and fee are documented, state them exactly. Distinguish a **$0 card annual fee** from any separate paid membership or subscription prerequisite; never imply that a required subscription itself has no cost unless that is documented.

## Mandatory response assembly
When the supplied preferences and documentation establish a recommendation, provide the recommendation in the same response. Before sending, verify that every applicable item below appears explicitly:

- the recommended card's exact name;
- its exact documented cash-back percentage and that it applies to all eligible purchases when documented as an all-purchases rate;
- its exact documented card annual fee;
- a direct connection between those terms and the customer's flat-reward and fee preferences;
- each material eligibility condition, with confirmed prerequisites distinguished from conditions still unknown;
- each documented minimum credit score, if any, close enough to the words "credit score" to be unambiguous;
- an approval/underwriting caveat where eligibility has not been decided;
- documented application next steps: application channel, requested preparation, and credit-pull consent when supplied.

Use a concise structure such as:

1. **Recommendation:** “I recommend **[exact card name]**. It earns **[exact rate]** on **[all eligible purchases / documented coverage]** and has a **[exact annual fee] card annual fee**, which fits your [flat/simple] cash-back preference and fee limit.”
2. **Eligibility:** “[Confirmed prerequisite] is satisfied based on what you told me. You still need to meet the documented minimum credit score of **[number]**, if applicable, and approval is subject to credit evaluation/underwriting.”
3. **How to apply:** “Apply through **[documented channel]**. Prepare **[documented items]** and be ready to **[documented consent, such as a credit pull]**.”
4. **Optional comparison:** Briefly explain only material alternatives or exclusions, such as a lower flat rate, annual fee, category restriction, or invitation-only condition.

Do not ask a follow-up instead of giving this answer when the current clarifications and documents already resolve the recommendation. A focused follow-up is appropriate only if missing information could materially change the choice and there is no clear supported fit.

## Calculations and reward qualifications
If monthly eligible spend is supplied, estimate annual net rewards as:

`monthly eligible spend × 12 × cash-back rate / 100 − annual card fee`

Label the result as an estimate. Apply only exclusions and qualifications documented for that specific card, such as returns, refunds, fees, interest, cash-like transactions, merchant classification, or posting requirements.

If account data represents cash-back rewards as points, convert points to cash only when current supplied documentation both identifies the card as a cash-back product and gives the conversion. Do not generalize such a convention to a true points product.

## Optional structured ranking helper
`scripts/rank_cards.py` ranks terms that the executor has already extracted from current-task source material. It has no product catalog and does not retrieve documents. Use it for repeatable comparisons, then validate the final customer response against the underlying documents and the mandatory response assembly checklist.

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
      "name": "Product name from current documents",
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

Send the object on stdin. The script emits one JSON object on stdout containing:

- `ok`: whether the input schema was valid;
- `recommendations`: non-conflicting offers in best-fit order, with unresolved conditions and an optional annual net-reward estimate;
- `excluded`: offers excluded for explicit conflicts and their reasons;
- `errors`: schema or value errors.

Unknown prerequisites are returned as unresolved rather than satisfied. An unresolved condition does not mean approval, and it does not automatically outweigh a clearly better documented fee-and-reward fit. The helper is decision support only; it never replaces source-document validation or eligibility disclosures.

## Banking-action boundary
This Skill does not perform a banking action. If a later request asks to apply, access an account, redeem rewards, make a payment, alter card controls, or take another banking action, stop the advisory workflow and use the execution agent's normal banking tools only after satisfying the applicable controls:

> Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

The ranking helper is not evidence of identity, authority, account ownership, eligibility, available credit, approval, or customer confirmation.
