---
name: highest-flat-cash-back-card
version: 1.0.0
description: Selects exactly one currently offered credit card with the highest documented flat cash-back rate on all eligible everyday purchases. Use for informational card recommendations when the request's primary criterion is highest everyday cash back, not an application, account action, or a category-specific reward comparison.
---

# Highest Flat Cash-Back Card Recommendation

Use this skill to give a concise, evidence-based recommendation of one card when a customer wants the highest cash back for everyday purchases.

## Scope and safety

This is an informational recommendation only. Do not represent it as approval, confirm that the customer qualifies, open an account, change an account, redeem rewards, or perform any other banking action. A customer's employer, title, or stated interests do not change a card's published earning rate unless the supplied terms expressly say they do.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Method

1. Read the supplied current product materials. Build one candidate record per currently offered card.
2. Include a card only when its terms explicitly establish a flat cash-back rate for **all eligible purchases** (or equivalent wording). Record exclusions such as fees, interest, cash advances, transfers, or cash-equivalent transactions as eligibility limits, not as a different rate.
3. Do not treat category bonuses, introductory offers, annual-fee rebates, statement credits, point balances, or a general statement that cards may have bonus categories as a flat everyday cash-back rate.
4. Confirm the supplied materials cover the relevant offered-card catalog. If catalog coverage is not established, do not claim that any card is the overall highest offered; explain that the available information is insufficient.
5. Supply the extracted records to `scripts/select_flat_cash_back.py`. Its `selected` result identifies the sole highest-rate eligible candidate.
6. If selected, give only the requested recommendation in customer-facing language, for example: “I recommend **[card name]**. It earns **[rate]% cash back on all eligible purchases**, the highest flat everyday rate in the supplied current terms.” Keep the response focused; do not list alternatives when the user requested one card.
7. If the script returns a tie, do not invent a tie-breaker from unrelated attributes such as annual fee, APR, or credit limit. State that the stated criterion does not determine a single best card and ask for a preference that can break the tie. If it returns an insufficient or invalid status, explain the limitation rather than making a highest-rate claim.
8. You may mention eligibility requirements or fees only when helpful, and only as documented. Do not infer that the customer satisfies them.

## Script interface

Run `scripts/select_flat_cash_back.py` with JSON on stdin. It emits one JSON object on stdout.

Input schema:

```json
{
  "catalog_complete": true,
  "candidates": [
    {
      "card_name": "string",
      "cash_back_rate_percent": "decimal string or JSON number",
      "scope": "all_eligible_purchases",
      "currently_offered": true,
      "source_ids": ["optional source identifier"]
    }
  ]
}
```

`catalog_complete` must be `true` only when the provided materials establish that all relevant currently offered cards were evaluated. `scope` must be `all_eligible_purchases` only for an expressly documented flat rate; use `limited_or_unknown` for a category-only rate, an unclear rate, or incomplete terms. Set `currently_offered` to `false` for discontinued products. `source_ids` are optional provenance labels and are returned only for the selected record.

Output statuses:

- `selected`: `recommendation` contains one card name and normalized percentage rate.
- `tie_requires_preference`: more than one qualifying card has the highest rate; no sole recommendation is justified by rate alone.
- `insufficient_catalog`: catalog completeness was not established.
- `no_qualifying_card`: no currently offered card had an explicitly supported flat all-eligible-purchases rate.
- `invalid_input`: correct the listed input errors before relying on the result.

## Validation before responding

Check that the output status is `selected`, that `recommendation.card_name` is nonempty, and that the response contains exactly that one recommended card. Confirm the stated rate and “all eligible purchases” wording match the selected output and its underlying documentation. Do not convert a stored rewards-points representation into a cash-back claim unless the supplied terms document the conversion and cash-back nature of those rewards.
