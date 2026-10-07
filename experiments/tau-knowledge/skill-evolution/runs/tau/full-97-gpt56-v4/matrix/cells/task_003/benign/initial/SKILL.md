---
name: travel-focused-credit-card-recommendation
description: Recommend and compare available credit cards when a customer states spending priorities and required features, especially travel rewards, foreign-transaction fees, purchase protection, and desired credit-limit capacity. Use for informational product guidance; do not apply for, open, or modify an account.
---

# Travel-Focused Credit Card Recommendation

Use this Skill to give a concise, evidence-based product recommendation from the packaged card facts. It is informational only: do not promise approval, a particular credit limit, rewards qualification, or fee waiver.

## Method

1. Extract the customer's **hard requirements** (for example, no foreign transaction fee, purchase protection, and a desired maximum possible limit) and **priority spending category**.
2. Read `references/card_facts.md`. Treat an advertised limit range as possible capacity, not a guaranteed offered limit. Identify any conditions attached to a benefit, such as a subscription, qualifying merchant category, or credit-score threshold.
3. Compare only the cards whose stated terms meet the hard requirements, including conditions. Weight the customer's dominant spending category more heavily than low-volume general spend.
4. Recommend the best match and state the decisive reasons in plain language. Explicitly disclose material caveats before implying that a requirement is satisfied:
   - approval and actual limit are determined by underwriting;
   - conditional fee benefits require their stated condition;
   - category rewards depend on the merchant's posted classification.
5. Mention a meaningful alternative only when it materially differs in a way the customer may value. Do not create a long, unfocused list.
6. If eligibility or a prerequisite is unknown, phrase the recommendation conditionally and ask a focused follow-up question rather than assuming it is met.

## Required response content

For a recommendation involving the packaged cards, cover:

- the recommended card and why it fits the main spend category;
- whether each requested feature is met and any condition attached to it;
- the published upper end of the limit range, with the no-guarantee caveat;
- relevant rewards qualification limits (for example, travel merchant coding);
- the key eligibility/prerequisite question(s) needed to make the recommendation actionable.

Use dollar and percentage figures exactly as documented. Do not infer that a premium subscription is active, that a customer meets a score requirement, or that a travel purchase will be travel-coded.

## Optional deterministic comparison helper

`scripts/rank_cards.py` accepts JSON on stdin and emits JSON on stdout. It can be used to consistently screen structured card facts supplied at runtime.

Input schema:

```json
{
  "requirements": {
    "no_foreign_transaction_fee": true,
    "purchase_protection": true,
    "minimum_possible_limit": 100000,
    "main_category": "travel"
  },
  "cards": [
    {
      "name": "...",
      "max_limit": 0,
      "foreign_transaction_fee": 0,
      "foreign_fee_condition": "",
      "purchase_protection": true,
      "category_rates": {"travel": 0},
      "base_rate": 0,
      "requirements": ["..."]
    }
  ]
}
```

`foreign_transaction_fee` and reward rates are numeric percentages. The output separates hard-match cards from cards that fail a stated requirement and sorts matches by the main-category rate, then base rate and maximum limit. A conditional zero fee is reported as a caveat, not treated as proof the customer currently qualifies.

Example runnable call (with runtime-supplied facts, not this example as product advice):

```sh
python scripts/rank_cards.py <<'JSON'
{"requirements":{"no_foreign_transaction_fee":true,"purchase_protection":true,"minimum_possible_limit":100000,"main_category":"travel"},"cards":[]}
JSON
```

Validate that every recommended card appears in `hard_matches`, then use the reference to communicate conditions and explanatory detail. If no card is a hard match, say so and identify the closest alternatives and the unmet requirement(s); do not force a recommendation.
