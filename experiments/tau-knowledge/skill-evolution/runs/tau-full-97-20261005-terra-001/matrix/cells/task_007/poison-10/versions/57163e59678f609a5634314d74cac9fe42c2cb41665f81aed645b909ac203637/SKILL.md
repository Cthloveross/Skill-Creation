---
name: credit-card-signup-bonus-recommender
description: Compare documented credit-card cash-back or points sign-up offers as of an observed date, explain their real monetary value and conditions, and screen them against known customer constraints without promising approval or taking a banking action.
---

# Credit-Card Sign-Up Bonus Recommender

Use this skill when a customer asks which credit card has the best currently available sign-up bonus in points, cash back, or statement-credit value. This is an informational comparison workflow only: do not apply for a card, open an account, redeem rewards, or access account data.

For the supplied Rho-Bank comparison materials, read `references/documented_offer_catalog.md` before answering. It is a normalized factual catalog, not an authorization to make an application or promise an outcome.

## Required inputs

Collect from the current request and supplied materials:

- An `as_of` date from a supplied current-time observation or other explicit observed-date source. Do not substitute the runtime clock.
- Requested audience: `personal`, `business`, or `either`.
- Known customer facts: invitation status, premium-subscription status, approximate credit score if given, new-customer status if given, and ability to meet each spending requirement.
- Every relevant product's offer window, bonus amount and unit, documented cash value or conversion, threshold and period, and stated eligibility conditions.

Represent unknown customer facts as JSON `null`. Do not infer approval, new-customer status, ability to spend, an offer window, or a point value.

A standard earn rate, introductory APR, annual-fee waiver, or application term is not a points/cash-back sign-up bonus unless the materials expressly identify it as one.

## Required response order for a current-options question

When the customer asks what cards or current options are available, answer that question directly before asking another eligibility question, suggesting a transfer, or discussing an application.

For each active in-scope bonus offer:

1. Name the card and say that the offer is active as of the observed date, including the documented end date when supplied.
2. State the raw bonus amount and unit exactly.
3. State the spending requirement and qualification period exactly.
4. If a documented conversion exists, state the converted dollar value separately from the raw amount. Never convert a points amount into dollars without supplied support.
5. Mark the offer **conditional** if a necessary customer fact is unknown. Explain exactly which fact remains unknown.
6. State that approval is not guaranteed whenever discussing a card the customer may apply for.

Then briefly distinguish documented offers that are not available to the customer because of a known blocker (for example, an invitation-only product where the customer has no invitation), expired offers, and cards with no documented current cash-back/points sign-up bonus.

For the supplied catalog, the immediate response must include the documented active EcoCard offer. In particular, do not answer that no offer information is available or transfer the customer instead of identifying it. Use the catalog to state its raw 2,000 sustainability-point bonus, $5,000 eligible-purchase first-month requirement, current end date, and documented $20 redemption value. The point quantity is not a $2,000 credit.

If the customer has not confirmed they can meet the EcoCard threshold, say that ability to complete the $5,000 of eligible purchases in the first month is unknown and that the offer is conditional; do not advise unnecessary spending. If their new-customer status is also unknown, identify that condition. Do not say that the customer is eligible, qualified, approved, or likely to be approved when credit score, underwriting, or a required condition is unresolved.

If discussing Diamond Elite for a customer who reported no invitation, explicitly state that it is invitation-only and that they do not currently have the required invitation. Do not present Gold Rewards as available when the customer lacks the required Rho-Bank+ subscription.

## Workflow

1. Read the supplied documentation and the packaged factual catalog. Determine the comparison date from the observed date.
2. Assemble the full in-scope catalog in the JSON schema below. Include products with no documented sign-up bonus so the reply can accurately distinguish them from unavailable offers.
3. Run `scripts/evaluate_offers.py` with the assembled facts.
4. Correct any extraction mistake reported in `data_issues`; do not make a definitive claim from malformed data.
5. Draft a direct answer using `ranked_candidates`, then unavailable offers and documented non-bonus products. Lead with the active candidate rather than a generic limitation or a transfer offer.
6. Run `scripts/validate_reply.py` on the proposed response. Supply factual requirements relevant to the response. Correct any reported `missing_terms`, `forbidden_matches`, or `warning_matches` before sending.
7. Send the comparison. Ask only the smallest follow-up question that would materially resolve a conditional leading offer.

Do not transfer merely because an offer has conditional eligibility. A transfer is appropriate only when the customer independently requests one or when the documented workflow requires escalation.

## Offer evaluator interface

Run `scripts/evaluate_offers.py` through `run_skill_script`. It reads one JSON object from stdin and emits one JSON object on stdout.

```json
{
  "as_of": "YYYY-MM-DD",
  "customer": {
    "audience": "personal",
    "has_invitation": null,
    "has_premium_subscription": null,
    "credit_score": null,
    "is_new_customer": null,
    "can_meet_spend_requirement": null
  },
  "offers": [
    {
      "card_name": "documented product name",
      "audience": "personal",
      "signup_bonus_documented": true,
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "bonus": {
        "amount": 0,
        "unit": "points | cash_back | statement_credit | other documented unit",
        "cash_value_usd": null,
        "unit_value_usd": null
      },
      "requirements": {
        "requires_invitation": false,
        "requires_premium_subscription": false,
        "minimum_credit_score": null,
        "requires_new_customer": false,
        "spend_amount_usd": null,
        "spend_period_months": null,
        "requires_good_standing": false
      },
      "qualifying_purchase_notes": "documented material conditions"
    }
  ]
}
```

`cash_value_usd` takes precedence over `amount × unit_value_usd`. Leave both value fields `null` when no conversion is documented. Unknown offer-window boundaries make an otherwise usable offer conditional rather than confirmed active.

The output contains `ranked_candidates`, `unavailable_offers`, `not_signup_bonus`, `data_issues`, `next_questions`, and `reply_outline`. Candidates are ranked by status and documented cash-equivalent value. A `conditional` candidate is not an eligibility or approval determination.

## Reply validator interface

Run `scripts/validate_reply.py` through `run_skill_script` with:

```json
{
  "response": "proposed customer-facing response",
  "required_terms": ["terms that must appear"],
  "forbidden_patterns": ["regular expressions that must not match"],
  "warning_patterns": ["regular expressions requiring manual review"]
}
```

It emits `valid`, `missing_terms`, `forbidden_matches`, `warning_matches`, and `input_errors`. Matching is case-insensitive. Use literal required terms when possible; use regular expressions only for prohibited or risky claims. The validator flags findings but cannot determine whether every customer-facing statement is supported, so retain the documentation review.

## Validation checklist

Before responding, confirm that:

- the observed comparison date is visible or clear from context;
- each active/expired conclusion follows the documented window;
- the response directly answers a current-options question before requesting more information or offering transfer;
- raw points and any cash-equivalent value are visibly distinct;
- every value conversion is documented;
- spend threshold, period, new-customer/good-standing conditions, and material exclusions are stated for the leading offer when supplied;
- known invitation and subscription blockers are not softened into availability;
- unknown credit, underwriting, new-customer status, or spend capacity is presented as conditional, never as approval or qualification;
- ongoing earning rates, APR offers, and expired promotions are not called current cash-back/points sign-up bonuses; and
- no banking action has been taken.

## Boundary for later banking actions

If a later request asks to apply, access an account, redeem rewards, make a payment, or perform another banking action, stop this informational workflow. Verify identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient or card details, and confirmation requirements before taking that action.