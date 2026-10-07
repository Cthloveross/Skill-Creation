---
name: personal-cash-back-card-advisor
description: Recommend and compare personal cash-back credit cards when a customer states spending preferences, fee tolerance, and known eligibility details. Use for informational card-selection advice; do not use it to submit an application, modify an account, redeem rewards, or perform another banking action.
---

# Personal Cash-Back Card Advisor

## Purpose
Provide a concise, evidence-based recommendation for a personal credit card, prioritizing the customer's stated constraints before headline reward rates. This workflow is informational only: it recommends a product and explains remaining eligibility or application steps without taking an action on the customer's behalf.

## Inputs to collect or use
Use the current task's supplied knowledge and conversation. Establish:

- Whether the customer wants personal rather than business cards.
- Spending pattern and whether a simple flat rate is preferred over category optimization.
- Annual-fee tolerance, including whether the customer requires a $0 annual fee.
- Known product prerequisites, such as memberships, invitations, and minimum credit score.
- Any stated card constraints, such as foreign-transaction fees, redemption minimums, or virtual-card availability, only when material to the request.

Do not infer a credit score, invitation, account ownership, approval outcome, or membership status. A confirmed prerequisite may be described as satisfied; an unstated prerequisite must remain a condition.

## Method

1. Identify the hard constraints first. Exclude products that are not personal cards, exceed the customer's annual-fee limit, or have a prerequisite the customer has explicitly said they do not meet.
2. For the remaining products, favor the stated reward style. For a simple everyday-spend preference, favor a flat rate on all eligible purchases over category-limited rates.
3. Compare net value, not only reward rate. When spending is supplied, calculate annual net rewards as:

   `annual eligible spend × cash-back rate / 100 − annual fee`

   State that returns, credits, fees, interest, cash-like transactions, or merchant-category rules can reduce or prevent earnings when the product terms say so.
4. Separate **confirmed facts** from **conditions**. For example, a card may be the best match if the customer has a required subscription, while still requiring that the applicant meet a minimum-score requirement and underwriting review.
5. Give one primary recommendation and brief alternatives or exclusions. Explain why each excluded high-rate card does not meet a hard constraint rather than presenting it as equally suitable.
6. If the customer asks how to proceed, describe only the application steps supported by the applicable product material (for example, documents to prepare, application channel, and whether a credit pull is required). Never represent the application as approved or submitted.

For a current-product answer, quote the exact rate, annual fee, eligibility criteria, and application process from the supplied product documents. Resolve apparent differences by keeping terms tied to their named card; do not combine rates, fees, or eligibility rules across cards. If terms are absent or contradictory, say that the product terms need confirmation instead of guessing.

## Current-task reasoning guidance
When the available evidence establishes a no-annual-fee, flat-rate personal card whose required subscription the customer has confirmed, compare that card directly against other no-fee alternatives. If its cash-back rate is higher on all eligible purchases, it is normally the primary recommendation, subject to every unconfirmed eligibility requirement. Mention no-fee lower-rate alternatives briefly. Exclude annual-fee products when the customer rejects annual fees, even if their advertised rate is higher. Invitation-only products are not ordinary alternatives unless the customer confirms an invitation.

When reading account or transaction data for a cash-back card, recognize that backend reward balances may be represented as points. Apply the documented conversion of 1 point = $0.01 only when the applicable product documentation confirms that the card is a cash-back card; do not use this convention to characterize an EcoCard or another true points product without checking its terms.

## Optional deterministic ranking helper
Use `scripts/rank_cards.py` when the current task has already been converted into a structured list of offers. The script does not retrieve product terms and does not know any card catalog; supply current facts in its input.

### Input JSON schema

```json
{
  "preferences": {
    "personal_only": true,
    "simple_flat_rate": true,
    "max_annual_fee": 0,
    "monthly_eligible_spend": null,
    "confirmed_requirements": {
      "requirement_key": true
    },
    "credit_score": null
  },
  "offers": [
    {
      "name": "Current product name",
      "personal": true,
      "cash_back_rate_percent": 0,
      "annual_fee": 0,
      "flat_rate": true,
      "requires": {"requirement_key": true},
      "min_credit_score": null
    }
  ]
}
```

`monthly_eligible_spend`, `credit_score`, and `min_credit_score` may be `null` when unknown. `requires` contains only boolean prerequisite flags whose keys are also used in `confirmed_requirements`. A missing customer confirmation is treated as an unresolved condition, not satisfaction.

Send this JSON on standard input to the script. It emits one JSON object on standard output with `ok`, `recommendations`, `excluded`, and `errors`. Each recommended item has a calculated annual net value when monthly spend is known and lists unresolved requirements. If `ok` is false, correct the reported schema or value errors before relying on its result. The helper ranks known-eligible products above conditional products and never converts a conditional match into an approval.

Validate the final advice against the source material after ranking: verify the named card's rate, fee, and requirement wording, ensure every hard customer constraint is addressed, and preserve any material caveat in the final response.

## Response format
Use a customer-facing structure such as:

1. **Best fit:** card name, rate, annual fee, and one sentence connecting those facts to the stated preference.
2. **Eligibility caveat:** clearly list requirements already confirmed and those still unknown. Do not say the customer is approved.
3. **Why not the main alternatives:** one short, factual comparison for each material alternative.
4. **Next step:** supported application preparation and channel, or a focused question if an unresolved preference would change the answer.

Do not ask for identity information merely to provide a recommendation. Do not imply that the organization charges no subscription fee when only the card annual fee is $0.

## Banking-action boundary
This Skill does not itself perform a banking action. If a later request moves beyond advice into an application, account lookup, rewards redemption, payment, card-management change, or other banking action, pause the advisory workflow and satisfy the applicable controls before using the execution agent's normal banking tools. Preserve this prerequisite verbatim with the resulting banking procedure:

> Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Never use the ranking script as evidence of identity, authority, eligibility, available credit, account ownership, or confirmation. It only organizes facts that were already provided.
