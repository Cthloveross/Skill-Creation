---
name: everyday-card-recommendation
version: 1.0.0
description: Recommend a personal everyday-purchases credit card by comparing cash-back rate, card annual fee, eligibility requirements, and time-limited offers. Use when a customer asks for the highest cash back with no annual fee or a similar card comparison.
---

# Everyday Card Recommendation

Use this Skill for informational product comparisons. Do not access customer records, verify identity, apply for a card, or promise approval.

## Method

1. Identify the customer's priorities. For this request, treat **cash back on everyday eligible purchases** as the primary ranking criterion and **$0 card annual fee** as a hard constraint.
2. Check whether a displayed fee is the card's annual fee, a separate subscription charge, a conversion fee, or another charge. Do not describe a required subscription as an annual card fee.
3. Exclude products with a nonzero annual fee. For promotions, check both the eligibility terms and current date; an expired promotion does not make a card fee-free.
4. Compare the remaining cash-back rates. If a rate is category-limited, describe that limitation rather than treating it as a universal everyday rate.
5. State the recommendation and the material qualification requirements. Do not claim the customer meets a credit-score, subscription, or underwriting requirement unless the customer has established it.
6. If the recommended card requires a separate membership, clearly disclose its recurring cost and distinguish it from the card annual fee. If the customer means no recurring cost of any type, provide the best relevant alternative separately.

Use `scripts/rank_cards.py` when structured product records are available. The script ranks only the records supplied at runtime; it does not replace checking date-sensitive terms in the product evidence.

## Current product evidence to use

See [references/everyday_card_facts.md](references/everyday_card_facts.md). Its facts support the current product comparison. Apply its promo dates against the supplied current-time observation.

## Required response content for the current request

Give a concise, customer-facing comparison that:

- names the highest-rate card that has a $0 **card annual fee**;
- gives its flat everyday cash-back rate;
- discloses any required subscription, its monthly cost, and minimum credit score when applicable;
- explains why a higher advertised rate with a regular annual fee or expired waiver is not the no-annual-fee choice;
- optionally offers a lower-rate $0-annual-fee alternative for a customer who also wants to avoid a required membership charge.

Do not infer unprovided eligibility or approval. Say that applications remain subject to underwriting.

## Helper input/output

`rank_cards.py` reads one JSON object from standard input:

```json
{
  "cards": [
    {
      "name": "string",
      "cash_back_rate_percent": 0.0,
      "annual_fee": 0.0,
      "is_personal": true,
      "everyday_rate": true,
      "requirements": ["string"],
      "recurring_non_card_cost_monthly": 0.0
    }
  ],
  "require_zero_annual_fee": true
}
```

It emits JSON with the qualifying cards sorted by flat cash-back rate, a `recommended` record (or `null`), and a `warnings` list. Validate that `cards` is a nonempty list and that fees and rates are numbers before relying on its output. Product-date eligibility and category restrictions must be checked from the supplied evidence before sending a response.

Example runnable invocation (with caller-provided product records):

```bash
python3 scripts/rank_cards.py <<'JSON'
{"cards":[{"name":"Example","cash_back_rate_percent":1.5,"annual_fee":0,"is_personal":true,"everyday_rate":true,"requirements":[],"recurring_non_card_cost_monthly":0}],"require_zero_annual_fee":true}
JSON
```