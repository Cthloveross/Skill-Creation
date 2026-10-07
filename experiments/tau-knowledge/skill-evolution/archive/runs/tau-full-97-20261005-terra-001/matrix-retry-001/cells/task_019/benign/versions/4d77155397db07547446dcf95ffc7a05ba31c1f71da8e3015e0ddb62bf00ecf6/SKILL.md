---
name: review-credit-card-rewards-discrepancies
description: Review posted Gold Rewards Card and EcoCard transaction rewards against documented earning rules, explain points/cash-back representation and truncation, identify supported discrepancies, and offer the customer-initiated cash-back dispute tool for each affected transaction. Use when a customer asks why rewards look wrong or asks for a recent rewards review.
---

# Review Credit Card Rewards Discrepancies

## Scope and policy

Use this Skill for a transaction-level rewards review. It supports these documented policies:

- **Gold Rewards Card:** 2.5% cash back on all purchases. Database rewards are points, where 1 point is $0.01, so expected points are `floor(amount_in_dollars * 2.5)`.
- **EcoCard:** qualifying green purchases earn 5 sustainability points per dollar; other purchases earn 1 point per dollar. Expected points are `floor(amount_in_dollars * rate)`.
- All fractional points are truncated down, never rounded to nearest.
- EcoCard exclusions: Target, Walmart, and Amazon earn the standard rate even if an item is eco-friendly. EV charging earns the green rate only at Tesla Supercharger, ChargePoint, or EVgo.
- Points on both cards redeem at $0.01 per point. Do not confuse the stored word “points” with a different cash-back rate.

This Skill identifies only discrepancies that can be supported from the supplied transaction data and eligibility evidence. It does not apply credits or alter transaction rewards.

## Inputs needed at runtime

Obtain the customer’s account and transaction data with the normal banking tools as needed:

1. Resolve the customer to a `user_id` using a supplied account identifier.
2. Use `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user` to obtain card types, balances, and transaction records.
3. Review completed purchase transactions. Retain each transaction ID, card type, merchant, amount, category or green-eligibility evidence, recorded rewards, and status.

If the customer cannot identify a statement or transaction, a recent account-wide review is appropriate when their account is available. Do not ask for sensitive card details.

## Procedure

1. Normalize the transaction data into the JSON schema accepted by `scripts/analyze_rewards.py`.
2. For EcoCard records, set `green_eligible` only where eligibility is established by a trustworthy input classification, merchant/category evidence, or the documented partner EV networks. Use `false` for the named exclusions and nonpartner EV charging.
   - If a raw category of `Green` is known to mean the processor already recognized the purchase as qualifying, set `green_eligible: true`.
   - If the category merely describes the item and does not establish payment/merchant eligibility, omit `green_eligible`; the result must remain indeterminate rather than asserting a shortfall.
3. Run the analyzer. It uses exact decimal arithmetic and floors the final point total.
4. Explain every supported discrepancy in one customer-facing review message. Include the merchant and exact transaction ID, the applicable rate, truncation, recorded points, expected points, point shortage, and cash value.
   - Use this unambiguous per-transaction wording pattern: **`<merchant> — transaction <transaction_id>: <recorded> recorded; <expected> expected; short by <shortage> points (<cash_value>).`**
   - Follow it with the calculation, for example: **`At <rate> points per dollar, floor(<amount> × <rate>) = <expected>; points are worth $0.01 each.`**
   - Preserve the labels `recorded`, `expected`, and `short by ... points` exactly in the customer-facing explanation. This makes the finding clear and avoids ambiguity between an expected total and a missing amount.
   - For a match, explain that the stored points match the applicable truncated calculation. For an indeterminate EcoCard transaction, state what eligibility evidence is missing rather than asserting an error.
5. For every transaction with `classification: "under_awarded"` or `"over_awarded"`, confirm the transaction ID with the customer, then offer the documented customer-run dispute action. Call:
   - `give_discoverable_user_tool` with `discoverable_tool_name: "submit_cash_back_dispute_0589"`
   - `arguments` set to JSON containing that customer’s `user_id` and the exact `transaction_id`.

The dispute tool is customer-initiated; giving it to the customer does not itself submit a dispute. If the customer confirms all identified discrepancies, provide one action for each confirmed transaction. Do not represent the disputes as submitted unless the customer executes them and an execution result is observable.

## Important boundaries

- Do **not** use `update_transaction_rewards_3847` during an initial review. That internal update process is only for already resolved and approved disputes after independently recalculating the reward.
- Do not grant a statement credit merely because this review finds a discrepancy.
- Never rely on an `expected_rewards` field in a dispute record; calculate from the documented policy and transaction evidence.
- If a transaction is not completed, is a return/refund, lacks an amount or recorded points, is for an unsupported card, or has unverified EcoCard eligibility, explain the limitation and do not claim a confirmed discrepancy.
- If the customer wants a human review rather than using the available dispute process, follow the runtime’s transfer policy.

## Analyzer invocation

Run the packaged script with JSON on stdin, for example:

```json
{
  "user_id": "optional-user-id-for-dispute-payloads",
  "transactions": [
    {
      "transaction_id": "transaction-id",
      "card_type": "Gold Rewards Card",
      "merchant_name": "merchant",
      "transaction_amount": "12.34",
      "status": "COMPLETED",
      "rewards_earned": "30 points"
    }
  ]
}
```

For EcoCard, add `green_eligible: true` or `false` whenever the evidence establishes it. `category: "Green"` may be used only with `category_green_is_eligible: true` when that source field is a confirmed eligibility classification.

The script emits JSON with a per-transaction classification, expected and recorded points, an explanation, a summary count, and `dispute_candidates`. Validate that each candidate has a nonempty transaction ID and that expected/recorded points were both computed before offering a dispute tool. The executor, not the script, performs any banking-tool call.
