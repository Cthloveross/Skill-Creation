---
name: audit-crypto-cash-back-rewards
description: Audit completed Crypto-Cash Back transactions when a customer reports incorrect cash back, calculate the documented 2.0% earn rate from stored reward points, and guide a supported cash-back dispute for identified discrepancies.
---

# Audit Crypto-Cash Back Rewards

Use this Skill for a customer who believes their credit-card cash back is wrong and whose transaction history may include the **Crypto-Cash Back** card. It evaluates only that card because this package has a documented 2.0% eligible-purchase rate. Do not infer reward rates for other cards from their transaction data alone.

## Evidence and assumptions

* Crypto-Cash Back earns 2.0% on eligible spend.
* Its backend `rewards_earned` value is stored as points even though it is cash back. For cash-back cards, one point is worth $0.01 when redeemed to a statement credit or eligible checking credit.
* With whole-number stored points, this Skill treats the expected stored value as the whole-point amount obtained by rounding the exact 2%-of-purchase cents **down**. This matches a points field that cannot store fractions. State this rounding assumption when it materially affects an explanation.
* Only completed transactions are evaluated. The rate documentation says “eligible” purchases; if a transaction is not completed or eligibility cannot be established, report it as not assessable rather than calling it an error.

## Workflow

1. Identify the customer using the normal read-only lookup tools and retrieve their credit-card accounts and transaction history. A supplied name, email, or user ID may be used for lookup. Do not expose unrelated sensitive profile fields.
2. Select transactions whose `credit_card_type` is `Crypto-Cash Back` and whose status is `COMPLETED`.
3. Provide the selected transaction objects to `scripts/audit_crypto_cash_back.py`. The script emits auditable per-transaction results, totals, and only transactions whose recorded reward points differ from the documented-rate calculation.
4. Explain the result in customer-friendly terms: show the purchase amount, recorded points and cash value, expected points and cash value, and difference for each finding. Explain that points on this cash-back card represent cents of cash back.
5. Do not label transactions from cards with unknown rate schedules as incorrect. If asked about them, say that their applicable card terms or a transaction-specific review is needed.
6. For each supported discrepancy the customer wants reviewed, provide the customer-facing dispute tool documented below. The customer must run it with their own `user_id` and the exact `transaction_id`; do not submit it as an agent action. Before offering it, ensure the transaction ID came from the customer’s transaction history.

### Supported dispute handoff

Use `give_discoverable_user_tool` to provide:

* `discoverable_tool_name`: `submit_cash_back_dispute_0589`
* `arguments`: a JSON string containing the customer’s `user_id` and the selected `transaction_id`, e.g. `{"user_id":"<user_id>","transaction_id":"<transaction_id>"}`

Tell the customer the submission may later request context such as the expected category or promotion. Do not request card numbers or other sensitive card details.

## Script interface

Run the package script as follows (the runtime sends the JSON to stdin):

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Crypto-Cash Back",
      "transaction_amount": "$12.34",
      "rewards_earned": "24 points",
      "status": "COMPLETED"
    }
  ]
}
```

`transaction_amount` may be a JSON number or a currency-formatted string. `rewards_earned` may be an integer/decimal number or a string such as `"24 points"`. The output contains `audited`, `not_assessable`, `findings`, and aggregate point/cash totals. Invalid rows are returned under `not_assessable` with a reason rather than silently discarded.

Validation before relying on the result: confirm every finding has a nonempty transaction ID, `expected_points` is an integer, `recorded_points` is an integer, and `difference_points != 0`. The tool arguments must use the original transaction ID, not a merchant name or record number.

If no findings are returned, say the completed Crypto-Cash Back transactions reviewed match the documented 2.0% rate under whole-point rounding. This is not a statement about transactions on other card types or transactions that were not assessable.
