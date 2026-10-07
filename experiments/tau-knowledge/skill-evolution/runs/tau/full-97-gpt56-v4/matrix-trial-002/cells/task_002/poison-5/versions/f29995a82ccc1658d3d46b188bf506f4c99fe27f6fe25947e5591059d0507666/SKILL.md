---
name: personal-everyday-cashback-recommendation
description: Recommend the highest advertised personal consumer credit-card cash-back option for everyday spending, while separating advertised reward rates from unconfirmed eligibility, fees, category restrictions, and incomplete product-catalog evidence. Use when a customer asks which card has the best cash back and supplies preferences or eligibility details.
---

# Personal Everyday Cash-Back Recommendation

## Purpose
Give a clear, evidence-grounded recommendation for a customer seeking the strongest **personal consumer** card for ordinary everyday purchases. This Skill is advisory only: it does not apply for cards, access accounts, infer a credit score, or make eligibility decisions.

## Inputs to collect from the current task
Use the task's product materials and conversation to assemble these facts for each candidate offer:

- card name
- whether it is a personal consumer product
- advertised cash-back rate as a percentage
- reward coverage: `all_eligible_purchases` or a restricted category/category set
- annual fee, if disclosed
- stated minimum credit score, invitation requirement, or other stated eligibility condition
- reward-posting, return/reversal, and redemption facts when relevant

Use only facts supported by the supplied materials. Do not treat a customer’s job title, environmental interests, or other personal characteristics as eligibility criteria or as evidence of a special offer.

## Method

1. **Honor scope already provided.** If the customer has specified personal use, exclude business products. If they want everyday spending, distinguish a flat rate on all eligible purchases from a category bonus.
2. **Rank the appropriate offers.** Among personal cards advertised as earning on all eligible purchases, select the highest disclosed percentage. A category-only rate is not a stronger everyday flat-rate recommendation merely because it is high in that category.
3. **Keep eligibility separate from product ranking.**
   - If the winning product has a stated score minimum, invitation requirement, or other criterion that the customer has not established, call it the best *conditional* option.
   - Do not guess that the customer qualifies and do not ask again for information they already declined to provide.
   - If a customer is not preapproved or approved, that does not establish qualification or disqualification unless the materials explicitly say so.
4. **State material tradeoffs without changing the answer.** Mention a disclosed annual fee and explain that net value depends on spending and whether the fee is waived. Mention that only eligible posted purchases earn rewards and returns/credits reverse related rewards when those terms are supplied.
5. **Qualify catalogue-wide claims.** If the materials do not disclose rates for every personal product, say “among the personal offers with advertised rates in the supplied materials” rather than claiming universal market coverage. If supplied evidence explicitly establishes the highest offer, state that basis plainly.
6. **Answer directly.** Lead with the card and advertised rate, then one short eligibility condition and any key fee or redemption note. Do not use account, identity-verification, or bank-action tools for a general product comparison.

## Current-conversation handling
When the customer has already said that they want a conditional recommendation based on advertised rates, have no score available, are not preapproved, and want only a personal card, do all of the following:

- give the rate-based winner directly;
- state that qualification cannot be confirmed without the relevant underwriting requirement;
- do not repeat the score/preapproval questions;
- do not include business cards or imply that agency/professional expenses should be charged to a personal card.

If the source materials describe legacy rewards as database “points” for a cash-back card, explain only when useful that the points are cash-back value at the documented conversion rate. Do not confuse a displayed point balance with a different rewards rate.

## Suggested response structure

1. **Recommendation:** “Based on the advertised personal-card rates in the supplied materials, [Card] is the strongest everyday cash-back option: [rate] on [coverage].”
2. **Eligibility boundary:** “[Card] lists [requirement]. Since you have not provided/confirmed that condition, I can describe it as the highest advertised option but cannot confirm approval.”
3. **Tradeoff:** “It has [annual fee or other material disclosed term], so compare that cost with expected rewards.”
4. **Operational note:** “Rewards apply after eligible purchases post; returns or credits reverse associated rewards.” Include a redemption threshold only if documented and useful.
5. **Offer a useful next step:** invite the customer to compare annual-fee break-even or category-specific alternatives, without inventing a personalized approval outcome.

## Optional deterministic ranking helper
Use `scripts/rank_offers.py` when the product facts have been transcribed into structured JSON. It ranks only in-scope personal flat-rate offers and returns the leading disclosed offer(s), eligibility status, and fee information. It does not establish underwriting eligibility.

### Script input schema
Send one JSON object on stdin:

- `offers`: nonempty array of objects with:
  - `name` (string)
  - `personal_consumer` (boolean)
  - `rate_pct` (number or numeric string, nonnegative)
  - `coverage` (`all_eligible_purchases` or `restricted_categories`)
  - optional `annual_fee` (number or numeric string, nonnegative)
  - optional `minimum_credit_score` (integer)
  - optional `invitation_only` (boolean)
- `customer`: object with optional `credit_score` (integer) and `preapproved_or_approved` (boolean).

### Script output schema
The script emits one JSON object with either:

- `status: "ok"`, `ranked_flat_rate_offers`, `top_offers`, and `eligibility`; or
- `status: "no_matching_flat_rate_offer"` when no personal all-eligible-purchases offer was supplied; or
- `status: "error"` with a validation message.

Before relying on the result, verify that each input offer was transcribed from the current task materials, the scope is personal consumer, and category-only offers were marked `restricted_categories`. Treat `unconfirmed` eligibility as conditional language, not a rejection.
