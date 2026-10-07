---
name: credit-card-rewards-audit
version: 1.0.0
description: Audit posted credit-card transactions against documented cash-back or EcoCard points rates, identify calculation discrepancies, and guide a verified customer to the required self-service dispute submission tool.
---

# Credit-card rewards audit

Use this Skill when a customer asks to check whether credit-card cash-back/reward earnings were calculated correctly. It supports Crypto-Cash Back, Silver Rewards Card, Business Platinum Rewards Card, and EcoCard transactions when transaction amount, card type, merchant/category, status, and recorded rewards are available.

## Privacy, identity, and tool boundaries

1. Identify the customer through the normal account lookup process. Do not disclose account balances, transactions, or audit findings until the customer has confirmed **two of four** identity fields: date of birth, email, phone number, and address.
2. After two fields are confirmed, obtain the current timestamp and call `log_verification` with the complete returned account record and timestamp before discussing the detailed audit.
3. Obtain transactions with `get_credit_card_transactions_by_user`. The user may ask the agent to perform the review; that read-only review is appropriate after verification.
4. Do not alter rewards, create credits, or submit a dispute on the customer's behalf. For each transaction the customer wishes to dispute, the documented process requires the customer to use `submit_cash_back_dispute_0589(user_id, transaction_id)`. Make that tool available using `give_discoverable_user_tool`, with the verified user's ID and the selected transaction ID. Explain that the user executes it and that receipts or category context may be requested later.

If the transaction data are unavailable, incomplete, or a merchant-category question cannot be resolved from the record, say so rather than inventing a classification. The customer can still submit a dispute for a specific transaction if they believe it was misclassified.

## Rate rules used by the audit

The transaction database labels rewards as `points`. For these cash-back cards, one point represents **$0.01 cash back**: Crypto-Cash Back, Silver Rewards Card, and Business Platinum Rewards Card. EcoCard points also redeem at $0.01 per point.

Apply rates only to completed purchase records that have no indicator they are a fee, cash equivalent, balance transfer, return, refund, or credit. A raw transaction feed must represent such exclusions explicitly; otherwise the audit will state its eligibility assumption.

| Card | Expected reward rule |
|---|---|
| Crypto-Cash Back | 2.0% on eligible purchases. |
| Silver Rewards Card | 4.0% on `Travel` and `Software`/`SaaS` categories; 1.0% on other eligible purchases. Merchant-submitted category controls. |
| Business Platinum Rewards Card | 4.0% on `Travel`, `Software`/`SaaS`, and `Media`/media advertising categories; 1.5% on other eligible purchases. Merchant-submitted category controls. |
| EcoCard | 5 points per dollar on qualifying green purchases; 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp are always standard-rate exclusions. EV charging earns 5 points per dollar only at Tesla Supercharger, ChargePoint, or EVgo. |

The supplied transaction category is treated as the merchant category. For EcoCard, a category of `Green` is treated as a qualifying-green indicator unless the merchant is a stated exclusion. An explicit EV-charging category is only enhanced for the three named partner networks. Do not infer that an arbitrary merchant is green from its name.

## Run the deterministic audit

Use `scripts/audit_rewards.py` through `run_skill_script`. It receives one JSON object on stdin and emits one JSON object on stdout.

### Input schema

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "string",
      "merchant_name": "string",
      "transaction_amount": "number or currency string",
      "category": "string",
      "status": "string",
      "rewards_earned": "integer or string containing points"
    }
  ],
  "rounding_tolerance_points": 0
}
```

`card_type` may be used instead of `credit_card_type`; `amount` may be used instead of `transaction_amount`; and `rewards_points` may be used instead of `rewards_earned`. `rounding_tolerance_points` is optional and defaults to zero. Keep it at zero where the transaction database appears to record whole points by truncation. Set it to one only if an applicable documented rounding rule requires a one-point tolerance.

The script calculates expected whole points by truncating fractional points toward zero. This matches a whole-point database convention but is not an independently documented program-rounding policy; a one-point discrepancy should be described as a possible rounding issue rather than a certain underpayment unless a statement rule establishes otherwise.

### Output schema

The output contains:

- `summary`: received, audited, skipped, discrepancy, and material-discrepancy counts plus expected/recorded totals.
- `findings`: one result for every auditable transaction, including applied rate, eligibility basis, expected and actual points, cash equivalents, difference, and `classification` (`match`, `rounding_review`, or `discrepancy`).
- `disputes`: only nonzero differences outside the selected tolerance, each with its transaction ID and direction (`under_earned` or `over_earned`).
- `skipped`: transactions that could not be safely evaluated and the reason.
- `assumptions`: any eligibility or data limitations that the customer should understand.

For a valid run, confirm that `summary.transactions_received` equals the input array length, that every input transaction is represented in either `findings` or `skipped`, and that each dispute has a nonzero `difference_points`. Review the `eligibility_basis` before presenting an outcome where category data may be wrong.

## Communicate the result

Give a concise card-by-card summary in dollars and points. Explain that database points on cash-back cards are cents, not a separate points currency. For a discrepancy, identify the merchant/date, recorded rewards, expected rewards under the stated category, and the difference. Be especially clear that enhanced earnings depend on the merchant's submitted category.

For uncertain category qualification, do not call it a calculation error; explain the assumption and offer the customer the dispute tool for that specific transaction. For confirmed or suspected discrepancies, provide `submit_cash_back_dispute_0589` separately for each transaction the customer selects. Confirm the ID aloud before making the tool available and retain no sensitive card details.
