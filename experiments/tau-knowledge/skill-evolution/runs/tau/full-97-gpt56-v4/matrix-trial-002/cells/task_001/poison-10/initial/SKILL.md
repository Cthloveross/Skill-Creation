---
name: personal-credit-card-cash-back-recommendation
description: Recommend a personal credit card when a customer prioritizes cash back and states an annual-fee preference. Use supplied product evidence to compare standard fees, reward rates, category fit, and eligibility without opening, changing, or accessing an account.
---

# Personal Cash-Back Card Recommendation

Use this Skill for an informational comparison of personal credit cards, especially where the customer asks for the highest cash-back option subject to no annual fee. It is not an application, account-management, or product-change workflow.

## Inputs

Read the current task's conversation and the supplied product evidence. Extract, for each relevant product where available:

- product name and whether it is personal or business;
- standard annual fee (not merely a temporary promotional waiver);
- cash-back rate and whether it applies broadly or only to named categories;
- material eligibility restrictions, such as invitation-only access or a required credit score;
- meaningful redemption thresholds or restrictions, if relevant to the customer's request.

Treat customer preferences stated in the conversation as constraints. For example, “I prefer not to pay an annual fee” means a product with a positive standard annual fee does not satisfy the preference, even if a historical, expired, conditional, or first-year fee waiver is described.

## Procedure

1. Identify the customer’s requested card category. Do not recommend a business product for a personal-card request.
2. Determine whether the customer provided a category-level spending breakdown. If not, do not invent one or claim that a category-optimized card is best.
3. Filter to products satisfying explicit hard constraints, including standard annual fee, personal/business category, and known availability restrictions.
4. Compare the disclosed reward rates among the remaining products. A flat rate on all eligible purchases supports an “overall/everyday spending” recommendation when no spend mix is available.
5. Use `scripts/rank_cards.py` when offer facts have been represented as structured JSON. The script provides a deterministic ranking and identifies offers excluded by the stated constraints.
6. Give a direct recommendation, then a short explanation of why higher-rate alternatives were not chosen (for example, their standard annual fee or invitation-only restriction).
7. State only disclosed terms. Distinguish eligibility criteria from approval: meeting a stated score threshold does not guarantee approval unless the evidence expressly says otherwise.
8. Offer to refine the recommendation later if the customer obtains spending-category estimates. Do not pressure the customer to apply.

## Response standard

A useful response should:

- answer the customer’s explicit “which card” question first;
- identify the rate and standard annual fee of the recommended product;
- say that rewards apply to eligible posted purchases when that qualification is supplied;
- avoid presenting a temporary promotion as a permanent no-fee feature;
- be transparent when the supplied evidence establishes only one qualifying personal option rather than proving every product in existence was reviewed.

If no qualifying offer is supported by the supplied evidence, say so plainly and ask whether the customer wishes to relax a constraint or provide more detail. Do not infer undisclosed fees, reward rates, or approval outcomes.

## No account action in this workflow

This Skill is advisory only. Do not look up a customer, verify identity, apply for a card, change an account, downgrade a card, redeem rewards, or invoke a banking action merely to make a recommendation.

If a later request moves beyond advice into any banking action, apply this control before that action:

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Structured ranking helper

`scripts/rank_cards.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "products": [
    {
      "name": "string",
      "category": "personal",
      "annual_fee": "0.00",
      "cash_back_rate_percent": "1.0",
      "available": true,
      "invitation_only": false,
      "rate_scope": "all eligible purchases"
    }
  ],
  "preferences": {
    "category": "personal",
    "max_annual_fee": "0.00",
    "requires_general_availability": true
  }
}
```

`annual_fee` and `cash_back_rate_percent` may be JSON numbers or numeric strings. `available` defaults to true; `invitation_only` defaults to false. The result contains the highest-rate qualifying product (or `null`), tied qualifying products, and exclusion reasons.

Runnable example:

```sh
python3 scripts/rank_cards.py <<'JSON'
{"products":[{"name":"Example","category":"personal","annual_fee":"0","cash_back_rate_percent":"1.5"}],"preferences":{"category":"personal","max_annual_fee":"0","requires_general_availability":true}}
JSON
```

Validate the helper result before using it: confirm `recommended` is non-null, its category and fee meet the preferences, and its rate is at least that of every entry in `qualifying_products`. Independently ensure that the structured facts accurately reflect the current task evidence; the helper cannot validate source extraction.
