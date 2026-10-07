---
name: eligibility-aware-card-recommendation
description: Provide a single evidence-based credit-card recommendation while handling an unknown eligibility prerequisite without using protected-status or job information as a proxy.
---

# Eligibility-Aware Card Recommendation

Use this Skill when a customer asks for the best or highest-reward card but the available product information includes an eligibility threshold that the customer cannot provide.

## Method

1. Identify the requested selection criterion (for example, the highest cash-back rate for everyday eligible purchases).
2. Compare only products and terms documented in the supplied knowledge. Do not invent alternative cards, eligibility paths, approval criteria, or tools.
3. Select one option only when the supplied information supports that comparison. State the qualifying product and the relevant benefit precisely.
4. Separately state whether personal eligibility can be determined from the information available.
   - If a required criterion is known but the customer will not or cannot provide it, say that eligibility cannot be assessed.
   - State the documented minimum or prerequisite.
   - Do not use occupation, seniority, government affiliation, environmental interests, or any other unrelated personal characteristic as an eligibility proxy.
   - Do not request account lookup, identity verification, or sensitive personal data when no account action is required.
5. If no documented alternative assessment method exists, say so plainly. Do not claim approval or denial, and do not imply that meeting a minimum guarantees approval.
6. Include material terms that affect the recommendation when documented, such as an annual fee and what purchases qualify for the advertised reward.

## Response pattern

Write a direct customer-facing answer in this order:

- Name the single recommended product and why it wins under the requested criterion.
- Clarify the scope of the advertised reward (for example, eligible posted purchases).
- Explain the known eligibility threshold and that the customer’s eligibility cannot be determined without the missing criterion.
- State that no other documented way to assess eligibility is available, if applicable.
- Mention material documented tradeoffs, without adding unsupported terms.

## Handling insufficient information

If the knowledge only documents one card, describe it as the best or highest option **among the documented options**, rather than asserting a market-wide ranking. If eligibility data is unavailable, preserve the recommendation as conditional: recommend the product for its documented benefit while making clear that qualification remains unconfirmed.

## Example execution for this task

Using the supplied card evidence, answer substantially as follows (adapt wording to the current customer message):

> Based on the available card information, the Platinum Rewards Card is the single best documented choice for everyday eligible purchases because it earns 10.0% cash back on eligible purchases. Eligible purchases are posted point-of-sale and online purchases; cash advances, balance transfers, fees, interest, and cash-equivalent transactions are excluded. It has a $200.00 annual fee.
>
> I cannot determine whether you personally qualify because the card has a stated minimum required credit score of 750 and your score or range is unavailable. Your EPA role or environmental interests cannot be used to assess credit eligibility. No other eligibility-assessment method is documented here. If you choose to check your score privately, a score of at least 750 satisfies the stated minimum, but I cannot confirm approval from the information available.

Do not transfer or perform account actions solely to answer a product-information and eligibility-question request.