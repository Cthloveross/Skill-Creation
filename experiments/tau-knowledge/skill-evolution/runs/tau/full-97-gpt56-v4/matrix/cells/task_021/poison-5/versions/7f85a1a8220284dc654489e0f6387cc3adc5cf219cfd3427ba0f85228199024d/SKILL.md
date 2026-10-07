---
name: credit-card-rewards-audit
description: Audit posted Business Bronze Rewards Card cash-back and EcoCard sustainability-point transactions against published earning rules, explain any discrepancies, and prepare a customer-facing review without making account changes.
---

# Credit-card rewards audit

Use this Skill when a customer asks whether credit-card rewards or cash-back earnings were calculated correctly. It covers the **Business Bronze Rewards Card** and **EcoCard** policies represented in the supplied knowledge.

## Safety and scope

1. Identify the customer from an exact name, email address, or user ID, then use the normal read-only account and transaction tools for that user. Do not use another customer's data.
2. This is a read-only review. Do not change balances, rewards, accounts, or contact details. The packaged script only calculates an audit; it cannot perform banking actions.
3. Review only posted/completed transactions. Pending transactions have not necessarily earned rewards yet. A return, credit, or refund reverses rewards at the *original* earning rate, so request or preserve original-transaction details when they are needed.
4. Do not infer that the displayed account-level rewards balance is wrong merely because a subset of transaction history was audited. A balance can include older activity, reversals, or prior redemptions.
5. If the user requests an adjustment, follow only a documented normal banking workflow available in the current runtime. If no supported correction workflow is available, report the documented discrepancy and explain that it requires follow-up rather than claiming an adjustment was made.

## Policy used by the audit

### Business Bronze Rewards Card

- Eligible posted purchases earn **1.0% cash back**. In the transaction database this is represented as **1 point per dollar**, truncated to whole points; 1 point redeems for $0.01.
- WeWork, Regus, Industrious, Gusto, ADP, Paychex, and Rippling earn 0 points.
- Slack, Zoom, HubSpot, and Salesforce earn 1 point per dollar only during the first 12 months of the subscription; later subscription payments earn 0. The subscription age must be supplied to decide this exception. Account age is not necessarily subscription age.

### EcoCard

- A qualifying green purchase earns **5 points per dollar**, truncated to whole points. Other purchases earn **1 point per dollar**, truncated to whole points.
- Target, Walmart, Amazon, and ThredUp always receive the standard 1-point rate, including eco-labeled goods bought there.
- EV charging earns the 5-point rate only at Tesla Supercharger, ChargePoint, or EVgo.
- A transaction explicitly classified as `Green` may be treated as qualifying green unless it is an explicit exclusion. For a merchant/category not identified as green, use the standard rate unless the input explicitly supplies `green_qualified: true`.
- Returned EcoCard purchases reverse points at the original rate.

## Run the deterministic audit

Convert the read-only transaction records into structured JSON and run:

```bash
python3 scripts/audit_rewards.py <<'JSON'
{
  "transactions": [
    {
      "transaction_id": "transaction identifier from the runtime",
      "credit_card_type": "Business Bronze Rewards Card or EcoCard",
      "merchant_name": "merchant name",
      "transaction_amount": "12.34",
      "category": "Green or source category",
      "status": "COMPLETED",
      "rewards_earned": 12
    }
  ],
  "subscription_months_by_merchant": {
    "Slack": 5
  }
}
JSON
```

The script reads one JSON object from stdin and writes one JSON object to stdout. `transactions` is required. Amounts may be JSON numbers or strings with an optional `$`; rewards must be whole points. `subscription_months_by_merchant` is optional and is only used for the four listed SaaS merchants. Per-transaction `green_qualified` can explicitly override category-based green classification. For a return/refund/credit, provide a signed negative amount plus `original_rate_points_per_dollar` when the original rate is not otherwise evident.

Output fields:

- `audited_transactions`: completed review rows, with actual/expected points, point delta, policy reason, and `match`/`discrepancy`/`needs_review` verdict.
- `discrepancies`: only rows whose recorded points differ from the calculated expectation.
- `needs_review`: rows where a necessary fact is missing, such as SaaS subscription duration or an unsupported card/status.
- `summary`: counts and total point delta. A positive `total_customer_shortfall_points` means the customer appears to have received too few points.

Before relying on the result, confirm `ok` is true, the number of audited rows agrees with the included posted records, every discrepancy has an expected-points explanation, and all unresolved rows are disclosed rather than silently treated as errors.

## Customer response

Give a concise transaction-by-transaction result for discrepancies and any exceptions that were correctly calculated. State points and, for cash-back cards, the equivalent statement-credit value at $0.01 per point. Explain that Business Bronze database points represent cash back. Avoid describing EcoCard sustainability points as cash-back dollars.

For example, say whether a merchant was correctly excluded, correctly standard-rate, correctly green-rate, or was awarded fewer/more points than the calculated rate. Do not expose internal user IDs or unrelated account details. If useful and relevant to the customer's question, redemption thresholds are $37 available cash back for Business Bronze and 3,000 EcoCard points; only assess redemption availability from a current account balance, not from the partial audit total.
