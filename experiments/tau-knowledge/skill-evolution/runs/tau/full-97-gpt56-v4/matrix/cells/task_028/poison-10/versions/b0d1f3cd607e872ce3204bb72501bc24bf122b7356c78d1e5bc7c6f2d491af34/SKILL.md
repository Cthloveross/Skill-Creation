---
name: cash-back-reward-discrepancy-review
description: Review a credit-card reward discrepancy for a completed transaction when the customer identifies the transaction, using documented reward rules, whole-point truncation, and the approved customer-initiated dispute path. Use for questions about missing, incorrect, or unexpectedly low cash back or rewards.
---

# Cash-Back Reward Discrepancy Review

Use this Skill to review a specific posted card transaction and explain whether its recorded rewards agree with documented reward rules. It supports investigation and a customer-initiated dispute; it does not make account adjustments or submit a dispute on the customer's behalf.

## Mandatory banking prerequisites

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Before accessing or disclosing account-specific information, obtain and confirm two of the four identity fields (date of birth, email, phone number, and address) against the customer record. Once two fields match, obtain the current timestamp and call `log_verification` with the complete record fields and timestamp. A name or user ID alone is a lookup aid, not two-factor verification.

For a review or dispute, confirm that the transaction belongs to the verified customer and that the customer has authority for the relevant card account. Confirm the transaction ID, merchant, amount, date, card type, status, recorded rewards, and applicable documented rule before discussing the result or offering the customer dispute tool. Do not infer a card's rate from other transactions.

## Documented rules

- Rewards stored as points on cash-back cards represent statement/checking cash back at **1 point = $0.01**.
- Always truncate fractional reward points down to a whole point; never round to nearest.
- Crypto-Cash Back earns 2.0% on eligible purchases, equivalent to `floor(purchase_amount × 2)` points.
- EcoCard earns 5 points per dollar for a transaction categorized as Green and 1 point per dollar otherwise. These are sustainability points, although they share the $0.01 redemption value.
- No rate for other card types is assumed by this Skill. Assess them only if an applicable card-specific rate is documented in the current task materials.

## Procedure

1. Identify the relevant transaction from the customer’s date, merchant, amount, and/or transaction ID. If several could match, ask the customer to identify the correct one. Do not use a receipt or product description to override the bank’s recorded transaction category; if the category is contested, note it as a dispute issue.
2. Complete the mandatory prerequisites above. Retrieve card accounts and the customer’s transaction history using the declared banking tools only.
3. Review only completed transactions. Supply the structured selected transaction(s) to `scripts/audit_rewards.py`. The script applies only documented default rules and reports other cards as not assessed unless an explicit `rate_points_per_dollar` is supplied for that card.
4. Explain the recorded points, expected points, point difference, and dollar equivalent for cash-back cards. State the truncation calculation. Do not describe EcoCard sustainability points as cash back.
5. If the result is a discrepancy, or if the customer challenges the recorded category/rule, offer the prescribed customer-initiated dispute path. Confirm the exact transaction ID first, then call `give_discoverable_user_tool` with:
   - `discoverable_tool_name`: `submit_cash_back_dispute_0589`
   - `arguments`: a JSON string containing the verified customer’s `user_id` and the confirmed `transaction_id`.

   Tell the customer that they must run the supplied tool themselves. Do not unlock, call, or claim to have submitted `submit_cash_back_dispute_0589` as an agent. Supporting context may be requested during review.
6. If the calculation matches, explain that no numerical shortfall was found under the documented rule. If the rule, category, or transaction data cannot be confirmed, do not assert a conclusion; explain the limitation and offer the same customer-initiated dispute path once its prerequisites are met.

## Audit helper

Run:

```sh
python3 scripts/audit_rewards.py < review_input.json
```

The script reads one JSON object from standard input and writes one JSON object to standard output. Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "string",
      "transaction_amount": "number or currency string",
      "rewards_earned": "integer or points string",
      "category": "string",
      "status": "COMPLETED"
    }
  ],
  "transaction_ids": ["optional selected transaction IDs"],
  "rate_points_per_dollar": {
    "Optional documented card type": "explicit points per dollar"
  }
}
```

`transaction_ids` is optional; when omitted, every supplied transaction is considered. `rate_points_per_dollar` is optional and must contain only card-specific rates supported by current task materials. The output has an `audits` list and a `summary`. Each audit is `assessed`, `not_assessed`, or `skipped`; only an `assessed` audit with nonzero `difference_points` is a numerical discrepancy. Validate that every selected transaction appears exactly once, that its status is completed before relying on it, and that the transaction ID and recorded points in the output match the retrieved record.

## Failure handling

- If the identity, authority, ownership, card, or transaction cannot be verified, do not retrieve/disclose account details or provide account-specific conclusions.
- If money or points cannot be parsed, stop the automated calculation and use the source record to resolve the data rather than guessing.
- If a customer requests an adjustment, explain that the approved path is the customer-run dispute tool; the tool submission is not a guarantee of adjustment.
- Never treat an absent documented rate as a 1% rate or infer eligibility from a merchant name alone.
