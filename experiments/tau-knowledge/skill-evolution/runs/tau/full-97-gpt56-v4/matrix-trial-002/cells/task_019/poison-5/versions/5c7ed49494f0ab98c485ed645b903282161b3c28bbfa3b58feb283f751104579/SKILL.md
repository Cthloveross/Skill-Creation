---
name: credit-card-rewards-discrepancy
version: 1.0.0
description: Handle a customer's suspected credit-card cash-back or EcoCard sustainability-points discrepancy: explain the applicable earning rules, identify reviewable transactions from authorized records, submit the customer-directed dispute tool for a specific transaction, and safely process only already-resolved disputes.
---

# Credit-card rewards discrepancy handling

## Scope and prerequisites
Use this Skill for a credit-card rewards discrepancy. Do not request card numbers or other sensitive card details. Verify identity under the runtime's verification policy before disclosing account or transaction information, accessing internal dispute history, or making account changes. If verification is required, obtain and confirm two of the available identity fields (date of birth, email, phone number, address), then log the verification with the current timestamp.

A complaint alone is not a resolved dispute and is not authorization to edit rewards. Never change a transaction merely because its displayed reward looks unexpected.

## Explain the earning rules accurately

* **Gold Rewards Card:** 2.5% cash back on all purchases. Transaction records store this as points; for cash-back cards, 1 point is $0.01. Thus the unrounded mathematical value is purchase amount × 2.5 points per dollar.
* **EcoCard:** earns 5 sustainability points per dollar on a qualifying green purchase and 1 point per dollar otherwise. A return or refund reverses points at the original rate.
* A `Green` category alone may be useful review context but does not establish eligibility where merchant recognition is uncertain. Qualifying examples include public transport, EV charging, renewable energy, certified sustainable retailers, bike share, and micromobility. Marketplaces, mixed carts, gift cards, cash equivalents, and payment processing through a non-green parent may not qualify.
* Target, Walmart, Amazon, and ThredUp always receive EcoCard's standard rate. EV charging receives the higher rate only at Tesla Supercharger, ChargePoint, or EVgo.

Do not invent a whole-point rounding convention. If the applicable transaction system or reward terms do not establish one, retain the exact computed point value as review evidence rather than proposing a whole-number correction.

## Customer-facing intake and dispute submission

1. Acknowledge the concern and ask which transactions or statement period appear wrong. If authorized transaction data are available, offer a concise list of recent merchant/date/amount entries so the customer can identify one; do not expose unrelated private data.
2. For each transaction the customer identifies, explain the relevant rate and any green-eligibility uncertainty. Ask for receipt, merchant, category, or promotion context only if needed for review.
3. Confirm the exact `transaction_id` with the customer. The required submission is customer-directed: give the user the discoverable tool `submit_cash_back_dispute_0589` with no prefilled sensitive details. Tell them to run it with their own `user_id` and that exact `transaction_id`.
4. Do not call the submission tool on the customer's behalf. A user who cannot identify a transaction should be asked to return with a statement/receipt or select an authorized transaction, rather than guessing an ID.

Use `give_discoverable_user_tool` with `discoverable_tool_name` set to `submit_cash_back_dispute_0589`. The customer supplies the arguments when they execute it.

## Optional deterministic review aid

Use `scripts/audit_rewards.py` on structured transaction data only after eligibility is supported by transaction/receipt/merchant evidence. It reads one JSON object on stdin and writes one JSON object on stdout.

Input schema:

```json
{
  "rounding": "unresolved|floor|nearest|ceiling",
  "transactions": [
    {
      "transaction_id": "string",
      "card_type": "Gold Rewards Card|EcoCard",
      "amount": "decimal string or number",
      "status": "COMPLETED|REFUNDED|...",
      "rewards_earned": "optional integer/string such as '125 points'",
      "eco_green_eligible": true,
      "merchant_name": "optional string"
    }
  ]
}
```

For EcoCard, `eco_green_eligible` must be explicit. If it is absent, the result is `needs_eligibility_review`; the script will not infer eligibility from the merchant name or category. `rounding` must be `unresolved` unless an applicable source establishes a whole-point rule. With a supplied rounding mode, output includes `expected_whole_points` and a comparison to the recorded integer. Review statuses and refund handling before relying on a result.

## Applying an approved, resolved correction

Only after identity verification and confirmation that a dispute is resolved and approved:

1. Retrieve the user's dispute history with `get_user_dispute_history_7291(user_id)` and select only approved/resolved disputes that identify the affected transaction. Do not use an `expected_rewards` dispute field as the calculation source.
2. Independently determine the card rate, green eligibility, purchase/refund status, and established rounding convention. Use the audit helper only as calculation support.
3. If and only if a correct whole-number value is established, unlock `update_transaction_rewards_3847` via `unlock_discoverable_agent_tool`.
4. Invoke it through `call_discoverable_agent_tool` using the exact `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`.
5. Re-query credit-card transaction history and verify the updated value. Record the calculation basis and confirmation in the authorized internal case record.

If dispute status, qualifying evidence, rounding treatment, or tool completion is missing or ambiguous, do not update rewards; leave the case for review/escalation according to available procedures.
