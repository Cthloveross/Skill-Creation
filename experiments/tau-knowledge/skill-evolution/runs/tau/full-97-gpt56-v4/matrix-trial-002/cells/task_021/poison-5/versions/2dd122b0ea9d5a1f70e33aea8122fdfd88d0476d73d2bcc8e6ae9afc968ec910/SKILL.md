---
name: credit-card-rewards-audit
description: Audit posted Business Bronze Rewards Card and EcoCard transaction rewards against documented earn rates, exclusions, point representation, and per-purchase truncation. Use when a customer asks whether rewards or cash back were calculated correctly.
---

# Credit-card rewards audit

Use this Skill to distinguish a confirmed reward-calculation discrepancy from a transaction whose green eligibility or subscription tenure cannot be established from the available data.

## Required runtime input

Obtain the customer's accounts and transaction history using the normal read-only banking tools. An account identifier supplied solely to locate records is not, by itself, confirmation of two identity fields. Do not perform account-changing actions unless the applicable verification and action policy is satisfied.

Form a JSON object for `scripts/run_audit.py`:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Business Bronze Rewards Card or EcoCard",
      "merchant_name": "string",
      "transaction_amount": "decimal amount",
      "transaction_date": "YYYY-MM-DD",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": "whole number of points",
      "green_qualified": true,
      "subscription_months": 0
    }
  ]
}
```

Only `transactions` is required. `green_qualified` is optional and should be supplied only when a reliable merchant/category eligibility result explicitly confirms it. `subscription_months` is optional and must mean the age of that SaaS subscription, not the card-account age.

Run it from the package root, for example:

```sh
printf '%s\n' '{"transactions":[]}' | python3 scripts/run_audit.py
```

The script writes one JSON object to stdout. It uses `Decimal` and floors each individual purchase, rather than rounding or aggregating purchases first.

## Interpretation and customer response

1. Review `confirmed_errors`. These are completed, determinable transactions where posted points differ from the documented expectation. State the date, merchant, posted points, expected points, and the point difference. For cash-back cards, clarify that database points represent cash back at $0.01 per point.
2. Review `review_items`. Do **not** call these errors. For example, an EcoCard transaction labeled Green but without a documented eligibility determination can be either the standard or green rate; a SaaS transaction without subscription tenure may be either eligible or excluded after its first year.
3. Explain transactions marked `correct` briefly when useful, especially explicit exclusions and the truncation rule. Do not expose unrelated account details.
4. The available information establishes calculation results only. Do not claim that a statement credit, point correction, refund, or dispute was submitted unless an authorized normal banking tool actually reports that result. If the customer requests a formal correction that cannot be completed with available tools, follow the current escalation policy rather than inventing an adjustment.

## Rules implemented

- **Business Bronze Rewards Card:** eligible net purchases earn 1.0% cash back. Because cash-back points are worth $0.01 each, this is one point per eligible dollar; expected points are `floor(amount)`. WeWork, Regus, Industrious, Gusto, ADP, Paychex, and Rippling earn zero. Slack, Zoom, HubSpot, and Salesforce earn zero only after the first 12 months of that subscription.
- **EcoCard:** qualifying green purchases earn five points per dollar and other purchases earn one point per dollar. Amazon, Target, Walmart, and ThredUp are always standard-rate. Tesla Supercharger, ChargePoint, and EVgo charging are documented green-rate charging partners. A generic Green category is not enough to infer merchant recognition unless eligibility is explicitly confirmed.
- All expected point amounts are truncated downward **per purchase**. Returns, credits, non-completed transactions, unsupported cards, malformed amounts, and facts required to establish a conditional rate are reported for review rather than guessed.

## Output validation

Before using the result, confirm that `input_errors` is empty and that the number of `audits` plus `skipped` records equals the number of supplied transactions. Only records with `determination: "confirmed_error"` belong in a claimed calculation-error total.
