---
name: credit-card-rewards-discrepancy-review
description: Review posted credit-card transactions for potentially incorrect reward earnings using documented card rates, explain findings, and route the customer to the required cash-back dispute submission flow. Use when a customer reports missing, low, or incorrect cash back and cannot identify the affected transaction.
---

# Credit-Card Rewards Discrepancy Review

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow to investigate a suspected rewards discrepancy. It is a read-only review until the customer submits a dispute. Do not change reward balances or transaction rewards merely because the calculation identifies a possible discrepancy.

Rewards recorded as `points` are redeemable at $0.01 per point for cash-back cards and EcoCard. The database label does **not** mean cash-back cards earn a separate points currency. Keep calculations in whole points; the script uses truncation to whole points because corrections require a whole-number point value.

## Required prerequisites

1. Confirm the requester is the customer or an authorized account representative.
2. Verify identity by asking the customer to confirm **two of the following four** fields: date of birth, email address, phone number, or address. Do not expose values retrieved from the customer record as verification prompts.
3. Use the matched customer identifier to retrieve the customer record. Once two fields match, obtain the current time and call `log_verification` with the complete retrieved record and that timestamp.
4. Confirm ownership by retrieving the credit-card accounts for the verified user and ensure every reviewed transaction belongs to that same `user_id` and an owned card.
5. Review only completed, non-returned purchase transactions. Flag pending, reversed, refunded, negative, or ambiguous records for manual review rather than treating them as an underpayment.

If verification, authority, ownership, transaction identification, or category eligibility cannot be confirmed, do not submit a dispute or make a correction. Explain what is needed next.

## Review procedure

1. Ask which statement period, card, merchant, or purchase the customer is concerned about. If they cannot identify one, offer to review their posted transactions after verification.
2. Retrieve the verified user's credit-card accounts and transaction history using the normal banking tools.
3. Convert the returned records to the JSON input described below and run:

   ```sh
   python3 scripts/review_rewards.py < transactions.json
   ```

   The executor may instead call `run_skill_script` with `scripts/review_rewards.py` and the same JSON object.
4. For each `possible_discrepancy`, explain the transaction date, merchant, amount, recorded points, documented expected points, and difference. Describe values as cash-back dollars only by multiplying points by $0.01 for cash-back cards.
5. Treat `manual_review` results as unresolved, not as errors. The available policy does not establish a Silver Rewards Card base rate, does not establish a rate for unsupported card types, and cannot prove merchant-category coding beyond the transaction data. A receipt or a category review may be needed.
6. If the customer wishes to challenge a possible discrepancy, provide the user-facing tool `submit_cash_back_dispute_0589` through `give_discoverable_user_tool`. Tell the customer to run it with **their own** `user_id` and the exact `transaction_id` for each transaction they wish to dispute. Confirm the transaction ID before providing this instruction. Do not collect card numbers or sensitive card details.
7. State that supporting context, such as receipts and why the category should qualify, may be requested during review. Do not promise approval or a rewards adjustment.

## Documented reward rules implemented

- **Crypto-Cash Back:** 2.0% on eligible purchases. A cash-equivalent, balance-transfer, fee, or otherwise explicitly ineligible transaction must be excluded instead of calculated.
- **Silver Rewards Card:** Travel and Software purchases earn 4.0% only when the merchant is classified in the qualifying category. The supplied policy does not state a base rate, so non-bonus purchases are manual review.
- **Business Platinum Rewards Card:** Travel, Software, and Media earn 4.0%; other purchases earn 1.5%. Cash equivalents, balance transfers, and fees earn no cash back.
- **EcoCard:** qualifying Green/Sustainable purchases earn 5 points per dollar; other purchases earn 1 point per dollar. Target, Walmart, Amazon, and ThredUp always receive the standard rate. EV charging receives the 5x rate only at Tesla Supercharger, ChargePoint, or EVgo; other charging networks receive the standard rate.

Merchant classification controls category eligibility. For example, a travel-like purchase that is not coded as Travel is not automatically eligible for the Silver 4% rate. Record it for category review instead.

## Dispute resolution and corrections

A dispute submission is not a resolved dispute. Only after a dispute is resolved and approved may an authorized internal agent update rewards. The agent must independently recalculate the rate and eligibility, not use an `expected_rewards` dispute field, then follow the approved internal correction process: unlock `update_transaction_rewards_3847`, call it with the exact transaction ID and `new_rewards_earned` formatted as `X points`, confirm the result in transaction history, and retain calculation notes. Before this banking action, re-confirm the mandatory prerequisites above. Never correct a transaction solely from this review output.

## Script input and output

`review_rewards.py` reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "user_id": "string",
      "credit_card_type": "Crypto-Cash Back | Silver Rewards Card | Business Platinum Rewards Card | EcoCard",
      "merchant_name": "string",
      "transaction_amount": "decimal number or currency string",
      "transaction_date": "string",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": "integer or string containing integer",
      "is_cash_equivalent": false,
      "is_balance_transfer": false,
      "is_fee": false,
      "is_return_or_credit": false
    }
  ]
}
```

The four boolean eligibility fields are optional and default to `false`. Include them when the transaction record provides the information. The script rejects missing essential fields, invalid amounts, and invalid recorded reward values as manual-review records without crashing the complete batch.

Output contains `possible_discrepancies`, `matches`, `manual_review`, and `summary`. Each calculated finding includes the documented rate, whole expected points, recorded points, and point difference. Validate that every calculated result has a nonnegative whole expected-points value and that every possible discrepancy has a nonzero difference. Review all manual-review entries before communicating a conclusion.
