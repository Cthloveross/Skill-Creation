---
name: eligibility-aware-credit-card-recommendation
description: Recommend one personal credit card when a customer seeks the best everyday cash-back option but eligibility information is incomplete. Use the supplied card terms and conversation clarifications to distinguish published reward rates from cards that can actually be recommended without unsupported assumptions.
---

# Eligibility-Aware Credit Card Recommendation

Use this Skill for a card-comparison conversation that asks for a single best recommendation, especially where the customer has declined or cannot provide eligibility details such as a credit score, invitation status, subscription status, or business eligibility.

## Inputs

At execution time, read the current task's supplied knowledge documents and the complete conversation, including clarification answers. Treat the documents as the authority for product terms. Do not infer unstated underwriting approval, eligibility, fees, reward categories, or product availability.

Identify:

1. The requested use case (for example, everyday purchases versus a limited category such as travel).
2. Whether the customer wants a personal card or has explicitly ruled out business products.
3. The required response shape (here, exactly one recommendation).
4. Eligibility facts the customer has provided and facts they have declined or do not know.
5. For every plausible card, its reward rate, scope of that rate, and any stated prerequisite (score threshold, invitation, membership/subscription, or business ownership/authority).

## Decision method

1. Make a compact candidate comparison from the supplied terms.
   - A rate advertised only for named categories is not an everyday-purchase rate.
   - Do not compare a business-card offer after the customer has requested a personal-only recommendation or cannot establish business eligibility.
   - Separate a published rate from availability to this customer.
2. Exclude from a no-additional-information recommendation any card that has a stated prerequisite the customer cannot confirm. Do not assume that a score is high enough, that an invitation exists, or that a subscription is active.
3. From the remaining personal cards, choose the one with the highest documented cash-back rate that covers eligible everyday purchases.
4. If the evidence does not establish any such card, state that no supported single recommendation can be made and explain exactly which missing fact would change the answer. Do not fabricate a fallback card.
5. If a lower-rate card is selected because it is the best supported option without more information, explain the decisive limitation of each higher-rate alternative relevant to the request. This prevents a customer from mistaking an unavailable headline rate for a recommendation.

## Response requirements

Give a direct, customer-facing answer with one named card first. Then include:

- its documented cash-back rate and that it applies to eligible posted everyday purchases, using only terms supported by the supplied materials;
- a brief reason it is the appropriate recommendation given the missing eligibility information;
- concise contrasts with higher advertised rates only where needed to explain why they were not selected (for example, score, invitation, subscription, or category limits);
- an optional next step: if the customer later supplies the missing eligibility detail, the comparison can be revisited.

Do not claim guaranteed approval. Do not imply that the customer's job title, government position, or other personal status overrides published eligibility. Do not ask another clarification when the customer has expressly asked for the best option that does not require the unavailable information. Do not recommend multiple cards, and do not perform account actions or use customer-data tools for a general product recommendation.

## Validation before sending

Check that the draft:

- names exactly one recommended product;
- answers the requested purchase type rather than a bonus-category use case;
- does not include business products when the final customer preference is personal-only;
- does not assume any unknown prerequisite is met;
- accurately preserves each cited rate, category restriction, and prerequisite from the supplied documents; and
- distinguishes cash-back display units from any backend reward-point representation when that distinction is relevant to the explanation.
