---
name: credit-card-reward-audit
description: Audit posted credit-card reward entries against documented card earn rates, identify likely under- or over-crediting, and guide a customer to the required self-service cash-back dispute tool. Use when transaction records and card type/category data are available.
---

# Credit-card reward audit

Use this Skill to review completed transaction-level reward entries. It compares the reward points recorded for each transaction with the documented rate for the card and transaction category. Do not alter rewards, submit disputes, or claim a final adjustment is guaranteed.

## Applicable reward rules

All displayed transaction rewards are points. For cash-back cards, **1 point = $0.01** when redeemed. EcoCard is a sustainability-points card, but its points also redeem at $0.01 each.

| Card | Expected points |
|---|---|
| Silver Rewards Card | Travel or Software: 4% (amount × 4 points per dollar); other purchases: 1% |
| Business Platinum Rewards Card | Travel, Software, or Media: 4%; other purchases: 1.5% |
| Crypto-Cash Back | 2% on eligible purchases |
| EcoCard | Qualifying Green purchases: 5 points per dollar; other purchases: 1 point per dollar |

The ledger uses whole points. Use truncation to whole points for the expected value, consistent with transaction-level displayed entries. Never compare a dollar cash-back amount directly to a points amount.

For EcoCard, Target, Walmart, Amazon, and ThredUp receive the standard rate even if an item is described as green. EV charging receives the higher rate only at Tesla Supercharger, ChargePoint, or EVgo. A transaction whose category is explicitly `Green` may be treated as qualifying unless an express exclusion applies. If the provided data do not establish green eligibility, describe the result as uncertain rather than as an error.

Cash equivalents, balance transfers, and fees earn no rewards. Returns, credits, pending, reversed, or otherwise non-completed entries must not be treated as ordinary positive purchases.

## Runtime input and analysis

1. Work only from transaction records supplied in the current task/runtime. Do not hardcode a customer, account, transaction ID, or expected finding into the Skill or response.
2. Convert each runtime transaction into a JSON object with at least:
   ```json
   {
     "transaction_id": "string",
     "credit_card_type": "string",
     "merchant_name": "string",
     "transaction_amount": 0.00,
     "category": "string",
     "status": "COMPLETED",
     "rewards_earned": 0
   }
   ```
3. Run `scripts/audit_rewards.py` through `run_skill_script`. Supply `transactions` as an array of these objects. The script reads JSON from stdin and emits JSON to stdout. It uses only the standard library.
4. Treat only `findings` with `determination: "likely_mismatch"` as transaction entries to raise with the customer. Review `unreviewable` records separately; do not infer a rate where eligibility or transaction state is not established.
5. Present every likely mismatch clearly: transaction ID, merchant/date if available, amount, recorded points, expected points, and whether the difference is an under-credit or over-credit. State the cash-equivalent difference (`point_difference × $0.01`) for clarity. An over-credit is also a discrepancy and can be corrected by review.
6. Mention that category coding and posting can affect enhanced rewards. A calculated mismatch is a documented-rate comparison, not a promise of an adjustment.

## Required dispute path

A customer must initiate a discrepancy review themselves. For each transaction the customer wants reviewed, provide the discoverable user tool:

`submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

Use `give_discoverable_user_tool` with `discoverable_tool_name` set to `submit_cash_back_dispute_0589` and arguments containing that customer's own `user_id` and one identified `transaction_id`. Submit one transaction at a time so the customer can review and execute each request. Do **not** use an agent-discoverable tool, and do not submit the dispute on the customer's behalf.

Tell the customer that supporting receipts or category/promotion context may be requested during review. Confirm the transaction ID shown to the customer before exposing the tool. If no mismatch is found, explain that the reviewed posted entries match the documented rates and ask whether there is a specific transaction or merchant classification they want reviewed.

## Output validation

Before responding, confirm that:

- each cited transaction was `COMPLETED` and had a supported card type;
- `expected_points` was calculated from the documented rate and truncated to whole points;
- EcoCard exclusions and unconfirmed eligibility were handled correctly;
- cash-back dollar explanations use $0.01 per point;
- every dispute tool invocation has both the customer’s user ID and exactly one validated transaction ID; and
- no reward adjustment, account change, or dispute was represented as completed before the customer executes the provided tool.

## Example script call

```json
{
  "transactions": [
    {
      "transaction_id": "runtime transaction id",
      "credit_card_type": "Silver Rewards Card",
      "merchant_name": "merchant from runtime",
      "transaction_amount": 100.00,
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": 400
    }
  ]
}
```

The expected script result has an empty `findings` array for this example and reports the entry as reviewed. Script validation errors mean the affected record must be corrected or excluded from the audit rather than guessed.
