---
name: credit-card-rewards-discrepancy-review
description: Review posted Gold Rewards Card and EcoCard transaction rewards, explain points-to-cash value and per-transaction truncation, identify supportable discrepancies, and offer the documented customer-initiated dispute tool for selected transactions.
---

# Credit Card Rewards Discrepancy Review

Use this Skill when a customer says that credit-card cash back or EcoCard sustainability points look incorrect. It supports an investigation from transaction records; it does not change rewards or submit a dispute on the customer's behalf.

## Policy applied

- Database `rewards_earned` is stored in points. A point is worth **$0.01** when redeemed as a statement credit or checking-account credit.
- Gold Rewards Card earns 2.5% on every purchase, which is **2.5 points per dollar**.
- EcoCard earns **5 points per dollar** for qualifying green purchases and **1 point per dollar** otherwise.
- EcoCard's explicitly excluded merchants (Target, Walmart, Amazon, and ThredUp) earn 1 point per dollar even for eco-friendly items. EV charging earns 5 points per dollar only at Tesla Supercharger, ChargePoint, or EVgo; other charging networks earn 1 point per dollar.
- For every card and category, calculate rewards **per transaction** and truncate fractional points down to a whole point. Never round the transaction result or aggregate purchases before truncating.
- Only the Gold Rewards Card's earning rate is established by this Skill for non-EcoCard transactions. Do not infer a rate for another cash-back card merely because its rewards are represented as points.

## Agent workflow

1. Treat a vague concern as a review request, not as a dispute request. If the customer can identify a purchase, use that purchase; otherwise, after the normal access/identity requirements of the surrounding workflow are met, obtain their card accounts and posted transaction history with the available read-only banking tools.
2. Do not expose or repeat unnecessary personal data. Transaction IDs, merchant, date, amount, card type, and rewards result are sufficient for this review.
3. Convert the returned transaction records to the JSON input for `scripts/analyze_rewards.py` and run it. The helper deterministically applies the known rates, explicit EcoCard exclusions, and flooring rule.
4. Review `discrepancies` with the customer. State the transaction amount, expected and posted points, difference in points and dollars, and the rule used. Also explain that Gold points are cash back despite their database label, while EcoCard points are sustainability points; both currently redeem at $0.01 per point.
5. Treat `review_required` as inconclusive. For example, an unknown merchant that is not clearly coded as a qualifying green category cannot be confirmed from these materials. Explain the qualification limitation instead of asserting that it should receive the 5x rate.
6. A transaction that matches the policy calculation is not a reward error. A visible point balance is a balance, not proof that the sum of the displayed transaction rows must equal it (it may include prior activity, redemptions, reversals, or pending adjustments).
7. For each transaction the customer wants disputed, confirm the transaction ID and provide the customer the documented tool using `give_discoverable_user_tool`:
   - `discoverable_tool_name`: `submit_cash_back_dispute_0589`
   - `arguments`: a JSON string containing the customer's own `user_id` and that one `transaction_id`.

   The customer, not the agent, executes the provided tool. Offer it separately for each selected transaction. Do not call an agent-side dispute tool, do not promise a correction, and do not fabricate a dispute where the calculation is inconclusive.

## Helper interface

Run `scripts/analyze_rewards.py` with one JSON object on standard input and read one JSON object from standard output.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Gold Rewards Card or EcoCard",
      "merchant_name": "string",
      "transaction_amount": "number or currency string",
      "transaction_date": "optional string",
      "category": "optional string",
      "status": "COMPLETED",
      "rewards_earned": "integer or points string"
    }
  ],
  "accounts": [
    {
      "account_id": "optional string",
      "card_type": "optional string",
      "reward_points": "integer or points string"
    }
  ]
}
```

`transactions` is required. `accounts` is optional and is used only to show each supplied point balance's $0.01 equivalent. The script accepts numeric values or strings containing currency/points formatting. It analyzes only positive, `COMPLETED` transactions. Other statuses, nonpositive amounts, malformed records, refunds without an original earn rate, and unsupported card types are returned in `review_required` rather than guessed.

Output includes `discrepancies`, `matches`, `review_required`, and optional `account_reward_values`. Each discrepancy contains the posted and expected points, the points/dollar rate, the dollar impact, and the policy basis. A positive `difference_points` means the transaction appears under-awarded; a negative value means it appears over-awarded.

A runnable invocation is `python3 scripts/analyze_rewards.py`, with an input object matching the schema supplied on stdin. Validate before communicating results: `ok` must be true; each selected dispute must have a nonempty transaction ID and a nonzero `difference_points`; and expected points must be an integer produced per transaction, not a rounded total.

## Limits and escalation

This Skill contains no authority to modify an account, credit points, or decide a merchant-review outcome. If a customer requests a human after the available review, or an issue needs information not returned by the records, follow the surrounding support escalation policy. Do not transfer solely because a customer has not yet selected a transaction; first provide the available factual review and the customer-initiated dispute option.
