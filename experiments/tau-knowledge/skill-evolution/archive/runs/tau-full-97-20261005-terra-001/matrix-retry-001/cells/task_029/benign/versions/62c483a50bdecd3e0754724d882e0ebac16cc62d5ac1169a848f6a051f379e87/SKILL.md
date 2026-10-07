---
name: credit-card-rewards-audit
description: Audit posted credit-card purchase rewards against the documented rates for Business Platinum Rewards, Silver Rewards, Crypto-Cash Back, and EcoCard. Use when a verified customer reports that earned cash back or points for one or more transactions may be incorrect.
---

# Credit-card rewards audit

Use this Skill to calculate an expected whole-point reward for each supplied transaction, identify discrepancies, explain the cash value of reward points, and route a customer to the prescribed self-service dispute tool.

## Prerequisites and privacy

1. Locate the customer using the identity information they provide. If more than one customer matches, do not select an account; request a unique identifier.
2. Before disclosing account-specific transactions, balances, rewards, or audit results, confirm **two of four** identity fields against the customer record: date of birth, email, phone number, and address.
3. After two fields match, obtain the current timestamp and call `log_verification` with the complete record fields and timestamp. Never ask the customer to provide card number, CVV, or other sensitive card data.
4. Retrieve the customer’s card accounts and transaction history with the normal read-only banking tools. Supply structured transaction objects to the audit script; do not hardcode a customer, account, transaction ID, or an expected result into this Skill.

If the customer does not complete verification, provide only general rewards information and ask them to verify before discussing their records.

## Audit method

1. Run `scripts/audit_rewards.py` with a JSON object containing `transactions`. Include every transaction the customer asks about, or all relevant posted transactions when they ask for a statement review.
2. The script treats database `rewards_earned` as whole points. For cash-back cards, one point is $0.01 of cash back. EcoCard points also redeem at $0.01 per point.
3. The expected result is truncated to a whole point per transaction, matching the observed whole-point transaction representation. The script does not invent fractional stored points.
4. Review the output:
   - `discrepancies` are assessed transactions whose recorded and expected points differ.
   - `correct` transactions match the documented rate.
   - `needs_review` includes records whose status, category, card type, or information is insufficient to calculate a reliable result. Do not call these errors.
   - `excluded_or_non_purchase` records are not eligible for a normal purchase-rate calculation.
5. Explain each discrepancy using transaction date, merchant, amount, recorded points, expected points, point difference, and cash-equivalent difference. State that eligibility ultimately depends on the merchant-submitted category and the net posted purchase amount. A category mismatch or a later refund/credit may change the final result.
6. Do not alter rewards, create a dispute, or promise an adjustment. For a customer who wants to challenge a discrepancy, provide the prescribed user-run tool `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`. Use `give_discoverable_user_tool` to pass that tool to the customer with their own verified user ID and the selected transaction ID. Confirm the transaction ID with the customer first. Repeat for each transaction they choose to dispute.

## Card-rate rules applied by the script

- **Business Platinum Rewards Card:** 4% for Travel, Software, and Media; 1.5% for other ordinary purchases. Fees, cash equivalents, balance transfers, and similar non-purchases do not earn rewards.
- **Silver Rewards Card:** 4% for Travel and Software; 1% for other ordinary purchases.
- **Crypto-Cash Back:** 2% for eligible ordinary purchases.
- **EcoCard:** 5 points per dollar for Green/Sustainable purchases and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp always receive the standard rate. EV charging receives the enhanced rate only at Tesla Supercharger, ChargePoint, or EVgo. The script relies on an explicit qualifying Green/Sustainable category or optional supplied green confirmation; it marks ambiguous cases for review rather than asserting merchant eligibility.

Read `references/rewards_rules.md` before manually overriding or explaining an edge case.

## Script interface

Run:

```text
python scripts/audit_rewards.py < input.json
```

Input is one JSON object:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Business Platinum Rewards Card | Silver Rewards Card | Crypto-Cash Back | EcoCard",
      "merchant_name": "string",
      "transaction_amount": "decimal number or currency string",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": "integer points",
      "transaction_date": "optional string",
      "green_merchant_confirmed": "optional boolean"
    }
  ]
}
```

The script writes one JSON object with `summary`, `discrepancies`, `correct`, `needs_review`, `excluded_or_non_purchase`, and `errors`. Monetary fields are decimal strings in dollars; `delta_points` is `actual - expected`, so a negative value indicates missing points. Validate that the supplied transactions belong to the verified user and that returned/refunded credits have not been mistakenly treated as new purchases.

If the script has input errors, correct the source data and run it again. If it reports an unsupported card or ambiguous classification, explain the limitation and, where applicable, offer the cash-back dispute process rather than guessing.