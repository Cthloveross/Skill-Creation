---
name: personal-cash-back-card-advisor
description: Provide evidence-based, informational recommendations for personal cash-back cards using supplied card documents and stated customer preferences. Use when selecting or comparing cards and explaining documented eligibility and application steps; do not use to submit an application or alter an account.
---

# Personal Cash-Back Card Advisor

## Scope

Use this Skill for an informational card recommendation. Read the current conversation, supplied clarifications, and supplied product documents before responding. Product documents are the source of truth for card-specific rewards, fees, eligibility, and application instructions.

This Skill does **not** submit an application, access an account, determine approval, verify identity, redeem rewards, change card settings, or take any other banking action. Do not imply that a recommendation is an approval or that an application has been started.

## Immediate-answer rule

When the customer has stated their relevant preferences and the documents establish a clear fit, provide the recommendation immediately in that same response. Do not claim that a catalogue, offer, or terms are unavailable when the supplied documents contain the necessary facts. Do not replace a supported answer with a request for monthly spending, a request to supply card names, or a generic offer to compare cards.

Monthly spending is useful for estimating reward dollars, but it is not required to select a clear flat-rate, fee-compatible recommendation.

## Decision procedure

1. **Identify binding preferences.** Determine whether the customer seeks a personal card, wants flat/simple everyday cash back or category bonuses, and has an annual-fee limit. A statement that the customer is not open to an annual fee is a hard constraint.
2. **Extract terms card by card.** Keep each card's name, reward rate and coverage, annual fee, material eligibility conditions, and application instructions together. Never combine terms from separate card documents.
3. **Exclude known conflicts.** Do not recommend a card as the fit if it exceeds the annual-fee limit, is category-based when simple flat rewards are required, is invitation-only without an invitation, or has a prerequisite the customer says they do not meet.
4. **Disclose unresolved conditions.** A prerequisite that is not confirmed, including a minimum credit score, is not automatically a rejection. State it clearly and do not represent it as satisfied. Conversely, explicitly acknowledge a requirement that the customer has confirmed they meet.
5. **Choose the best documented fit.** Among non-conflicting personal cards, favor the highest documented all-purchases flat cash-back rate for a customer seeking simple everyday cash back. A higher advertised rate does not override a fee conflict, invitation-only restriction, category limitation, or known unmet requirement.
6. **Keep approval separate from eligibility.** State that approval remains subject to documented credit evaluation, underwriting, or other documented approval conditions. Never infer a customer's score or approval outcome.
7. **Give only documented application guidance.** If the selected card documentation gives application steps, provide the channel, preparation items, and any consent requirement exactly as documented. This is guidance only, not an instruction that an application has been submitted.

Distinguish a **$0 card annual fee** from a separate membership or subscription prerequisite. Do not imply that a required subscription is free unless its cost is documented.

## Required response content

For every supported recommendation, include all applicable items below explicitly before sending:

- the selected card's exact name;
- its exact documented cash-back percentage and whether it applies to all purchases when documented that way;
- its exact documented card annual fee;
- why those terms satisfy the stated reward and fee preferences;
- every material eligibility condition;
- confirmation that any customer-confirmed prerequisite satisfies that prerequisite;
- every documented minimum credit score, expressed close to the words "credit score";
- a statement that approval remains subject to credit evaluation or underwriting when approval is not known;
- documented application channel, preparation items, and credit-pull consent when present.

A reliable response structure is:

1. **Recommendation:** Name the card and state its exact all-purchases cash-back rate and card annual fee. Tie both directly to the customer's simple-reward and fee preferences.
2. **Eligibility:** State which confirmed prerequisite is satisfied. State every remaining threshold, especially any minimum credit score, and separate this from approval.
3. **Next steps:** State the documented application location, documents or details to prepare, and any required credit-pull consent.
4. **Brief comparison (optional):** Mention an alternative only when it helps explain a material difference, such as a lower flat rate, annual fee, category limitation, or invitation-only rule. Do not present a fee-conflicting card as the customer's fit.

Do not ask a follow-up instead of providing this answer when the available clarifications and documents already resolve the choice.

## Calculations

When the customer supplies monthly eligible spending and the selected card's rate and fee are documented, an annual net-reward estimate is:

`monthly eligible spending × 12 × cash-back rate / 100 − annual card fee`

Label this as an estimate. Apply only card-specific qualifications supported by the current documents, such as exclusions, refunds, transaction posting, or merchant-category rules.

If documentation says a particular cash-back card stores rewards as points and supplies a point-to-cash conversion, use that conversion only for that documented card type. Do not generalize it to a true points product.

## Helper scripts

The scripts are optional decision support. They do not retrieve a catalogue, establish eligibility, make an approval decision, or perform banking actions. The executor must extract all input terms from the current task documents and must validate the final response against those documents.

### `scripts/rank_cards.py`

Provide one JSON object on stdin:

```json
{
  "preferences": {
    "personal_only": true,
    "simple_flat_rate": true,
    "max_annual_fee": 0,
    "monthly_eligible_spend": null,
    "confirmed_requirements": {"required membership": true},
    "credit_score": null
  },
  "offers": [
    {
      "name": "Exact current-document product name",
      "personal": true,
      "flat_rate": true,
      "cash_back_rate_percent": 0,
      "annual_fee": 0,
      "requires": {"required membership": true},
      "min_credit_score": null,
      "invitation_only": false
    }
  ]
}
```

It emits JSON with `ok`, non-conflicting `recommendations` in best-fit order, `excluded` offers, and `errors`. Unknown required conditions and an unknown customer score are emitted as unresolved conditions; they still require disclosure in the customer response.

Example invocation with a current-task JSON file is `python3 scripts/rank_cards.py < current_terms.json`.

### `scripts/validate_advice.py`

Use this after drafting a recommendation when a mechanical completeness check is useful. It receives JSON containing the draft response, selected-offer terms extracted from current documents, and documented application phrases. It emits `ok`, `missing`, and `checks`. A passing result is not a substitute for checking that all facts came from the correct current product document.

## Banking-action boundary

If the customer later asks the agent to submit an application, access an account, redeem rewards, make a payment, change card controls, or take another banking action, stop this advisory workflow. Use the execution agent's normal banking tools and satisfy the controls applicable to that action, including identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient or card details, and required confirmation. Do not use either helper as evidence of any such prerequisite.
