---
name: credit-card-rewards-audit
description: Audit completed Gold Rewards Card and EcoCard transactions against published earn rates, whole-point truncation, and EcoCard green-purchase exclusions. Use when a customer reports missing or incorrect cash back/rewards and transaction data is available.
---

# Credit Card rewards audit

Use this Skill to provide a transaction-level, evidence-based review. It calculates expected database `points`, compares them with points recorded on the transaction, and distinguishes confirmed discrepancies from transactions whose EcoCard green eligibility cannot be determined from the available data.

## Policy implemented

- Gold Rewards Card earns 2.5% cash back. In the rewards database that is **2.5 points per dollar**; 1 point has a $0.01 cash-back value.
- EcoCard earns **5 points per dollar** for qualifying green purchases and **1 point per dollar** otherwise. EcoCard points also have a $0.01 redemption value.
- Every per-transaction reward calculation is truncated down to a whole point. Do not round expected points, aggregate decimals before flooring, or calculate a discrepancy from displayed cash values.
- Target, Walmart, Amazon, and ThredUp always earn EcoCard's standard rate, even if another field says green. Tesla Supercharger, ChargePoint, and EVgo are recognized qualifying EV charging networks.
- A completed EcoCard transaction categorized as `Green` may be treated as a qualifying classification when no exclusion overrides it. If green qualification is not supplied or cannot be inferred from a supported classification, report it as `unknown`, rather than asserting a rate.

## Required runtime input

Obtain the customer's identity and use normal read-only banking tools to retrieve their relevant card accounts and transactions. Do not disclose account details until identity handling required by the live workflow has been completed. Use only completed purchase transactions in this calculation; refunds, returns, pending, reversed, or malformed records must be excluded or explicitly called out.

Create JSON for `scripts/audit_rewards.py` with:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Gold Rewards Card or EcoCard",
      "merchant_name": "string",
      "transaction_amount": "currency/number",
      "rewards_earned": "points/number",
      "status": "COMPLETED",
      "category": "optional category",
      "green_status": "optional: qualifying, nonqualifying, or unknown"
    }
  ]
}
```

The script emits a JSON report with a record-level audit and totals by card. `expected_points` is null for an EcoCard transaction with unknown qualification. `delta_points` is expected minus recorded, so a positive value means fewer points were recorded than expected. `delta_cash_value` is that delta at $0.01 per point.

Run it from the package root, for example:

```sh
python3 scripts/audit_rewards.py < review_input.json > review_output.json
```

## Review and customer response procedure

1. Confirm the customer and obtain the relevant accounts and transaction history using the available normal tools. Do not assume a transaction amount, merchant classification, account balance, or statement period from the customer's initial description.
2. Pass all available transactions to the script. Read `excluded_transactions` and `unknown_eligibility` too; they explain omissions and prevent accidental conclusions.
3. For each `mismatch`, validate that the transaction is completed and that the card type and amount were parsed correctly. Explain the expected calculation as `floor(purchase amount × points-per-dollar)`. For Gold, clarify that the database label “points” represents cash back at one cent per point.
4. Do not present an EcoCard green rate merely because an item sounds sustainable. State the documented basis for each classification, including exclusions and the certified EV-network rule. Ask for a receipt or merchant details when eligibility remains unknown.
5. Summarize confirmed shortages and over-awards separately, both in points and one-cent cash-equivalent value. Do not imply that the current account reward balance equals the sum of the displayed transactions; the history may cover only part of the balance.
6. If the live environment provides a documented, authorized reward-correction or dispute workflow, follow that workflow exactly after explaining the confirmed discrepancy. Never invent a correction tool, alter an account with unrelated tools, or claim that a correction was posted unless the authorized tool reports success. If no authorized resolution path is available, give the customer the documented findings and use the applicable escalation workflow only when required by the live policy.

Meaningful validation before communicating results: every definite audit row should have nonnegative whole-number expected and recorded points; a Gold row must use 2.5 points/dollar; an excluded EcoCard merchant must use 1 point/dollar; and a fractional result must have been floored per transaction.
