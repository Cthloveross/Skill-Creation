---
name: credit-card-rewards-discrepancy-audit
description: Audit posted credit-card transactions against supported rewards rules, identify reproducible rewards discrepancies, guide customer dispute submission, and apply only independently recalculated corrections for already approved disputes.
---

# Credit-Card Rewards Discrepancy Audit

Use this Skill when a customer believes credit-card rewards are incorrect, including when they cannot identify the affected transactions. It audits transaction-level rewards; it does not infer discrepancies from an account-level rewards balance.

## Prerequisites and safeguards

1. Resolve the customer to one account holder. Before handling account-specific results, confirm at least two of date of birth, email, phone number, and address against the user record. Call `log_verification` with all record fields and the current timestamp after successful verification.
2. Retrieve the customer's card accounts and transaction history with the normal banking tools. Use the card type, posted/completed status, merchant-coded category, amount, merchant, and recorded `rewards_earned` from the transaction record.
3. Treat the transaction category as the merchant coding available for the audit. Do not promote a transaction to a bonus category based on merchant name alone. If the record lacks a category, amount, card type, status, or rewards value, mark it for manual review rather than guessing.
4. Do not alter a transaction merely because the audit finds a mismatch. A customer must submit a dispute, and an internal correction is permitted only after the dispute is resolved and approved.

## Audit procedure

1. Prepare a JSON object containing `transactions`, and optionally `assume_ordinary_purchases` (defaults to `true`). Run:

   ```sh
   python3 scripts/audit_rewards.py < /path/to/audit-input.json
   ```

   The executor may instead invoke `scripts/audit_rewards.py` through the packaged script runtime with the same JSON object.
2. Review each output item:
   - `match`: the recorded whole-point value equals the independently calculated value.
   - `discrepancy`: the recorded value differs. Preserve the transaction ID, recorded and expected points, rate, and reason for the case notes.
   - `manual_review`: the available record cannot support a reliable calculation. Do not characterize this as an error.
   - `not_audit_eligible`: do not calculate a reward for a non-posted, non-positive, or clearly excluded transaction.
3. Explain that cash-back card database points represent cash back at 1 point = $0.01. EcoCard points are sustainability points, though the same whole-point truncation policy applies. Do not round fractional points upward.
4. For each reproducible cash-back discrepancy, provide the customer the discoverable tool `submit_cash_back_dispute_0589` using their user ID and that exact transaction ID. The customer performs this action; do not submit it on their behalf. If the runtime permits only one tool handoff at a time, hand off one tool invocation for each affected transaction.
5. If the customer says a transaction should have been in another merchant category, explain that classification is determined by merchant-submitted coding and supporting receipts may be requested. Such a claim is a dispute/review issue, not evidence to change the calculation locally.

## Rules implemented

The helper supports the documented card programs below.

- **Silver Rewards Card:** 4 points per dollar for `Travel` and `Software`; 1 point per dollar otherwise. The enhanced rate requires a posted transaction with the corresponding merchant category.
- **Business Platinum Rewards Card:** 4 points per dollar for `Travel`, `Software`, and `Media`; 1.5 points per dollar otherwise. Enhanced classification is merchant-category dependent.
- **Crypto-Cash Back:** 2 points per dollar on eligible ordinary purchases.
- **EcoCard:** 5 sustainability points per dollar for `Green` purchases and 1 point per dollar otherwise. `Target`, `Walmart`, `Amazon`, and `ThredUp` never receive the Green rate. EV charging receives the Green rate only at `Tesla Supercharger`, `ChargePoint`, or `EVgo`.

For all supported rules, expected points are `floor(amount × points_per_dollar)`, calculated separately for each transaction. The helper flags clear excluded categories for Silver and Business Platinum rather than applying an ordinary-purchase rate. For Crypto-Cash Back, the source only defines the rate for eligible purchases. With `assume_ordinary_purchases: true`, ordinary positive posted purchase records are treated as eligible, while clear cash-equivalent/balance-transfer/fee-like categories are held for review. Set it to `false` when eligibility cannot be established from the supplied record.

## Handling approved disputes

Perform this section only after locating a resolved **approved** dispute in the applicable `cash_back_disputes` data source. Never rely on an `expected_rewards` field from the dispute.

1. Retrieve the original transaction using the dispute's exact transaction ID and rerun the independent calculation.
2. If the result is `discrepancy`, unlock `update_transaction_rewards_3847` with `unlock_discoverable_agent_tool`.
3. Call it through `call_discoverable_agent_tool` with the exact transaction ID and `new_rewards_earned` formatted exactly as `"X points"`, where `X` is the helper's expected whole-point value.
4. Retrieve/confirm the transaction history reflects the new reward value and retain calculation details in the internal case record.
5. If the transaction remains unreviewable, is unsupported, or the dispute is not approved, do not call the update tool; route it for the appropriate rewards review.

## Helper input and output

`audit_rewards.py` reads one JSON object from standard input:

```text
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "string",
      "merchant_name": "string",
      "transaction_amount": "decimal amount or currency string",
      "category": "string",
      "status": "COMPLETED or posted status",
      "rewards_earned": "integer or '<integer> points'"
    }
  ],
  "assume_ordinary_purchases": true
}
```

It emits one JSON object with `summary` counts and an `audits` array. Each audit includes the supplied transaction ID, outcome, expected and recorded points when calculable, the applied points-per-dollar rate, and an explanatory reason. Validate that every supplied transaction has one audit record and that each `discrepancy` contains an integer `expected_points` before using it in a dispute or approved correction.

The helper intentionally does not call banking tools, submit disputes, or update rewards.