---
name: documented-credit-card-comparison
description: Provide evidence-based, read-only comparisons of documented credit cards for customers evaluating rewards, fees, international use, purchase protection, potential credit limits, and eligibility. Use for informational card-selection requests; do not use this skill to apply for, open, modify, or close an account.
---

# Documented Credit-Card Comparison

Use this skill when a customer asks which documented card options may fit their spending and benefit priorities. Answer directly from the product documents supplied with the current task. This is informational guidance, not a banking action: do not perform an application, credit pull, account lookup, account change, or transfer merely to answer the comparison.

## Evidence and safety rules

- Treat supplied product documents as the authoritative source for the current comparison. Do not claim the catalog is unavailable when relevant documentation is supplied.
- Use only facts documented for the specific card being discussed. Do not combine one card's rewards, fee, limit, or protection with another card's terms.
- Treat a documented credit-limit range as a possible range, not a promised line of credit.
- Never state that a customer qualifies when score, underwriting, invitation, subscription, or other eligibility facts are unknown.
- A card is **not currently actionable** if a required condition is known to be missing, such as an invitation-only product when the customer says they have no invitation.
- A card is a **conditional potential fit** when it otherwise meets the request but approval, score, underwriting, or another requirement is unknown.
- If the user subsequently asks to apply or to take another banking action, first verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

## Comparison method

1. Extract the customer's hard requirements and preferences. These may include main spending category, desired foreign-transaction-fee treatment, purchase protection, a possible minimum credit line, and annual-fee preference.
2. Build a fact record for each plausible product using all supplied documents for that product. Record:
   - annual fee;
   - reward rate relevant to the user's primary spending category and material merchant/category restrictions;
   - foreign-transaction-fee rule and any subscription condition;
   - purchase-protection period and per-claim cap;
   - documented initial-limit range or maximum;
   - minimum score, subscription, invitation, credit-check, and underwriting conditions.
3. Exclude only products with a known failed prerequisite. Keep products with unknown score or underwriting as conditional candidates.
4. Rank remaining candidates by hard-requirement fit. For a category-led spending request, prefer a documented reward specifically tied to that primary category over a general all-purchase rate. Use annual fee as a tie-breaker or stated preference, not as a reason to omit a materially useful comparison.
5. Give the best documented conditional fit first, then a compact comparison of alternatives that make a real tradeoff clearer.

Do not ask the customer to resupply a score, product catalog, or terms before giving the best documented conditional answer. A follow-up question may be offered only after the comparison if it would refine the result.

## Required response content

The response must be a substantive recommendation, not a generic offer to compare products. For the leading card, include all facts that are documented and material to the request:

1. Card name and clear status as a potential/conditional fit when eligibility is unconfirmed.
2. The reward rate relevant to the customer's primary spending category. State any documented merchant-category or posting limitations.
3. The foreign transaction fee, including the condition that determines it. If the customer has confirmed a required subscription, explicitly connect that known status to the resulting fee.
4. Purchase-protection duration and cap per covered claim.
5. The documented initial-limit range or maximum, and whether it can potentially reach the requested target.
6. Annual fee.
7. Minimum credit-score threshold and any invitation or subscription condition.
8. A clear limitation: where the customer did not provide a score, eligibility cannot be confirmed; approval and the particular initial limit depend on the application, credit check, and underwriting and are not guaranteed.

Use concise customer-facing language such as:

> Based on the documented terms, **[Card]** is the strongest conditional fit for your [primary category] spending. It earns **[rate]** on eligible [category] purchases, subject to [documented category/merchant condition]. Because you have [known condition], its foreign transaction fee is **[fee]**. It provides purchase protection for **[duration]**, up to **[cap]** per covered claim. Its documented initial-limit range is **[range]**, so it can potentially reach your **[target]** goal, and its annual fee is **[fee]**. It requires a minimum credit score of **[score]**. Since you have not provided a score, I cannot confirm eligibility; approval and any exact credit limit depend on a credit check and underwriting and are not guaranteed.

If a known missing invitation blocks an invitation-only product, say plainly that it is not currently actionable. Do not present it as an available option.

## Alternative comparison

Include alternatives only when they help the customer decide. For each alternative, identify the practical tradeoff, such as a higher possible line, stronger general earning, better protection, a higher annual fee, a higher score threshold, or a required subscription. Do not imply that a card is better solely because its maximum documented limit is larger.

When two products have the same low annual fee, distinguish their reward structure and qualification requirements. When a customer prioritizes travel, distinguish travel-specific rewards from a flat all-purchase reward.

## Optional deterministic helper

`scripts/evaluate_cards.py` accepts normalized facts on standard input and writes a JSON assessment on standard output. It is a sorting aid only: it does not retrieve facts, perform an eligibility decision, take a banking action, or replace review of the source documents.

Input schema:

```json
{
  "customer": {
    "credit_score": null,
    "premium_subscription": null,
    "has_invitation": null,
    "spend_priorities": ["travel"]
  },
  "requirements": {
    "minimum_limit": null,
    "maximum_foreign_transaction_fee": null,
    "purchase_protection_required": true,
    "prefer_lowest_annual_fee": true
  },
  "cards": [
    {
      "name": "Card name",
      "annual_fee": null,
      "limit_min": null,
      "limit_max": null,
      "foreign_fee_standard": null,
      "foreign_fee_with_premium": null,
      "foreign_fee_without_premium": null,
      "purchase_protection_days": null,
      "purchase_protection_cap": null,
      "minimum_credit_score": null,
      "premium_required": null,
      "invitation_only": null,
      "reward_rates": {"travel": null, "all": null},
      "reward_note": null
    }
  ]
}
```

Run it with:

```sh
python3 scripts/evaluate_cards.py < candidates.json
```

Output fields include each card's hard-fit result, eligibility status, foreign-fee basis, primary-category reward information, and a ranked conditional lead. Unknown facts remain unknown.

## Final validation

Before responding, verify:

- A documented card is named and the informational question is answered directly.
- Every lead-card benefit belongs to that same card.
- The primary-spend reward, foreign-fee condition, protection, possible limit, and annual fee are addressed when documented and requested.
- Known subscription status is accurately connected to a conditional foreign-fee term.
- An unknown credit score is described as unknown alongside the relevant minimum score.
- Approval and the requested limit are explicitly conditional on credit review/underwriting.
- A known absent invitation or subscription is not represented as satisfied.
- No bank action, human transfer, or request for unnecessary customer information was made solely to provide this comparison.
