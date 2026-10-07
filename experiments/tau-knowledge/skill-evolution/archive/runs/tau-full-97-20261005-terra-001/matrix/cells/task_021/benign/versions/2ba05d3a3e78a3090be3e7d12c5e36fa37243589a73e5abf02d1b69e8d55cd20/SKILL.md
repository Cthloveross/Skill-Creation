---
name: credit-card-rewards-audit
version: 1.0.0
description: Review posted Business Bronze Rewards Card and EcoCard transactions for reward-calculation discrepancies, explain the result, and prepare customer dispute or post-resolution correction steps without making unsupported eligibility assumptions.
---

# Credit Card Rewards Audit

Use this Skill when a customer asks whether credit-card rewards, cash back, or sustainability points were calculated correctly. It supports these known products:

- **Business Bronze Rewards Card:** eligible net posted purchases earn 1.0% cash back. Transaction storage represents this as points, where 1 point = $0.01, so the expected stored reward is one point per eligible dollar, rounded down. Named coworking and payroll merchants earn 0 points. Named SaaS subscriptions earn 0 points only after the first 12 months of that subscription.
- **EcoCard:** qualifying green purchases earn 5 points per dollar; other purchases earn 1 point per dollar. Amazon, Target, Walmart, and ThredUp always earn the standard rate. Tesla Supercharger, ChargePoint, and EVgo EV-charging sessions qualify for the higher rate. All points are rounded down to a whole point.

The audit script is advisory: it never calls banking tools, alters a transaction, applies a credit, or submits a dispute.

## Runtime input and script interface

Run `scripts/reward_audit.py` with one JSON object on stdin and consume its JSON object from stdout.

### Input schema

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "card_type": "Business Bronze Rewards Card | EcoCard",
      "merchant_name": "string",
      "transaction_amount": "decimal number or string",
      "net_eligible_amount": "optional decimal; use if it is the final net posted purchase amount",
      "rewards_earned": "optional integer or '<integer> points'",
      "status": "optional transaction status",
      "category": "optional category",
      "qualifying_green": "optional boolean",
      "subscription_months": "optional number, for named Business Bronze SaaS merchants"
    }
  ],
  "green_category_is_verified": true
}
```

`transaction_amount` is used unless `net_eligible_amount` is supplied. It must be the final net purchase amount after known credits or returns. Use `qualifying_green` when merchant eligibility has been verified. With the default `green_category_is_verified: true`, a transaction category exactly labeled `Green` is treated as a verified green classification; set it to `false` if that field is not reliable.

Only `COMPLETED` or `POSTED` positive purchase records are audited. Refunds, credits, reversals, pending records, malformed amounts, unknown card types, and Business Bronze named SaaS records without subscription tenure are returned as non-determinable or unsupported rather than guessed.

### Output schema

The script emits:

- `results`: one record per input transaction, including `determination` (`correct`, `under_awarded`, `over_awarded`, `not_determinable`, or `unsupported`), expected and recorded points where available, rate, rationale, and a recommended next step.
- `summary`: counts and totals across determinable transactions.
- `update_candidates`: payload-shaped recommendations for determinate discrepancies only. These are **not authorization** to update records; they may be used only after a dispute is resolved and approved.
- `input_errors`: top-level schema errors. Per-transaction problems remain visible in `results`.

A minimal runnable invocation is:

```sh
python3 scripts/reward_audit.py <<'JSON'
{"transactions": []}
JSON
```

Validate that every discrepancy has a transaction ID, a whole-number expected reward, and explicit rationale before communicating or acting on it. Treat `not_determinable` results as requests for missing merchant, subscription, or final-net-amount information, not as findings of an error.

## End-to-end agent procedure

1. Obtain the customer's account identifier through the normal supported account-lookup flow, then retrieve the relevant card accounts and transaction history using the available read-only tools. Scope transactions to the identified customer and the supported card types.
2. Convert the retrieved transaction records to the script input. Preserve the recorded reward, status, merchant, category, amount, and any known green-eligibility or SaaS-subscription-tenure data. Do not substitute an account balance for transaction rewards.
3. Run the script and inspect each result. The result’s rationale is the calculation record. Named merchant exclusions override a generic `Green` category.
4. Explain only determinate findings. For Business Bronze, clarify that database “points” are cash back at $0.01 per point; for EcoCard, they are sustainability points, also redeemable at $0.01 per point. State that fractional rewards are truncated, not rounded to nearest.
5. For a potential discrepancy, do not directly edit the transaction merely because this review found it. The customer-facing cash-back-dispute process applies to credit-card transactions. Confirm the exact transaction ID and use `give_discoverable_user_tool` to provide `submit_cash_back_dispute_0589` with the customer’s own `user_id` and that transaction ID. Do not collect card numbers or other sensitive card details.
6. If an internal case is later resolved and approved, first identify the affected transaction IDs from the resolved `cash_back_disputes` data source available in the runtime. Independently rerun the calculation; never trust an `expected_rewards` field in a dispute record. Only then unlock `update_transaction_rewards_3847` with `unlock_discoverable_agent_tool` and call it with the exact `transaction_id` and `new_rewards_earned` formatted exactly as `X points`. Confirm the resulting value in transaction history and retain the calculation rationale in the case record.
7. Do not use a statement-credit tool as a substitute for correcting transaction rewards unless a separately applicable, authorized statement-credit policy directs that action.

## Important interpretation rules

- Use a named exclusion exactly as recorded after case-insensitive whitespace normalization. Do not infer that a similarly named merchant is excluded.
- For EcoCard, merchant qualification that is not supplied and is not represented by a verified `Green` category must not be invented. The normal rate is used for known non-green purchases; request review evidence if the customer claims the higher rate.
- For Business Bronze named SaaS merchants, `subscription_months > 12` earns zero; 12 or fewer months earns the base rate. If tenure is absent, no conclusion can be reached for that exception.
- A completed record whose displayed reward differs from the independently calculated whole-point value is a discrepancy, whether it is under- or over-awarded. The process remains dispute-first rather than automatically changing either kind.
