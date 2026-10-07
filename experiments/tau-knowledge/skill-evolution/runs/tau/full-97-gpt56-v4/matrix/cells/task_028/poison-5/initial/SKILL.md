---
name: credit-card-rewards-discrepancy-review
description: Review a verified customer's posted credit-card transactions against documented reward rules, identify explainable reward discrepancies, and guide the customer to the required self-service cash-back-dispute tool. Use for suspected missing, incorrect, or miscategorized credit-card rewards, including requests to review all transactions.
---

# Credit-Card Rewards Discrepancy Review

Use this skill to perform a transparent, transaction-level rewards review. It calculates an expected reward from the posted amount, card product, recorded category, and documented exceptions; it does not change rewards or presume a merchant's actual classification differs from the transaction record.

## Mandatory banking controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow:

1. Verify identity before retrieving, discussing, or acting on nonpublic account or transaction information. Obtain and confirm two of the four identity fields: date of birth, email, phone number, and address.
2. Locate the user only from customer-provided identifying information, then compare the two supplied fields with the returned profile. Do not read the values aloud as prompts or expose unneeded profile details.
3. Get the current timestamp and call `log_verification` with the verified profile and timestamp after successful two-field verification.
4. Retrieve credit-card accounts and transactions using the verified user ID. Confirm every reviewed account and transaction belongs to that same user ID. The requester's authority is limited to their own accounts.
5. Review only posted/completed purchase transactions. Do not calculate a positive expected reward for returned, refunded, reversed, pending, fee, interest, balance-transfer, cash-equivalent, gift-card, or person-to-person records. Mark ambiguous records for manual review rather than guessing.
6. Do not disclose unrelated transaction details, full card numbers, balances, or other sensitive data. There is no agent-side reward-adjustment action in this workflow.

If identity, ownership, or a necessary transaction field cannot be confirmed, do not access or disclose account-specific results. Explain what is needed to continue. If the customer only wants general reward information, provide that without accessing an account.

## Review procedure

1. Clarify whether the customer wants a particular transaction or all transactions. For an all-transaction request, review every transaction returned for every confirmed card; do not use an account reward-balance total as a substitute for transaction review.
2. After verification and ownership checks, obtain the transaction list. Capture, at minimum, transaction ID, card type, merchant, amount, date, posted status, recorded category, and rewards earned.
3. Put the transaction objects in the JSON input described below and run `scripts/analyze_rewards.py` using `run_skill_script` (or `python3 scripts/analyze_rewards.py` with JSON on standard input).
4. Use the script output as an arithmetic and rule-consistency check:
   - Present `short_reward` items as possible missing rewards, including transaction date, merchant, recorded category, expected versus recorded points, and the point difference.
   - Present `over_reward` items neutrally as discrepancies that may require review; do not say the customer owes anything.
   - Explain that points on cash-back cards are stored as points and redeem at $0.01 per point. EcoCard sustainability points also redeem at $0.01 per point.
   - State that calculations use the recorded merchant category. A cardholder's description of an item does not override merchant classification. Keep receipts if they believe a category was incorrect.
   - Clearly separate `manual_review` entries from confirmed arithmetic discrepancies. Do not assert an expected rate where status, category, merchant eligibility, or product type is insufficient.
5. Explain the relevant rate briefly and accurately. Avoid applying crypto redemption conversion fees to purchase earning; that fee applies when rewards are redeemed to crypto, not when earned.
6. For each transaction the customer wants disputed, use `give_discoverable_user_tool` to provide `submit_cash_back_dispute_0589` with the verified customer's own `user_id` and that specific `transaction_id`. The customer, not the agent, must execute the provided tool. Confirm the transaction ID belongs to the verified customer before providing it. Do not submit a dispute through an agent tool and do not promise an adjustment.
7. Tell the customer that supporting receipts or category/promotion context may be requested during review. If no discrepancy is found, summarize the applicable rates and explain that merchant coding and posted amounts drive the calculation.

## Documented reward rules used by the analyzer

The analyzer covers only the product rules supported by this skill:

| Card product | Expected earnings on an eligible posted purchase |
| --- | --- |
| Silver Rewards Card | 4.0% for recorded Travel or Software; 1.0% otherwise. Merchant classification controls the enhanced rate. |
| Business Platinum Rewards Card | 4.0% for recorded Travel, Software, or Media; 1.5% otherwise. |
| Crypto-Cash Back | 2.0% on eligible purchases. The 1.25% crypto conversion fee is not an earning-rate reduction. |
| EcoCard | 5 points per dollar for qualifying recorded Green/Sustainable purchases; 1 point per dollar otherwise. Target, Walmart, and Amazon are standard-rate exceptions. EV charging earns the green rate only at Tesla Supercharger, ChargePoint, or EVgo. |

For percentage-based cash-back cards, database points equal dollars times the percentage times 100 points per dollar; 1 point is $0.01. Expected fractional points are truncated down to whole points, consistent with posted transaction examples. EcoCard earns whole sustainability points at the stated points-per-dollar rate, likewise truncated down when necessary.

Do not treat a merchant name alone as proof that a category is eligible, except for the explicit EcoCard exclusions and EV-network rule above. For example, a travel purchase processed under a non-Travel category should be flagged only as a possible merchant-classification question, not automatically recalculated at the travel rate.

## Analyzer interface

`scripts/analyze_rewards.py` reads one JSON object from standard input and emits one JSON object to standard output. It uses only the Python standard library.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "string",
      "merchant_name": "string",
      "transaction_amount": "number or currency string",
      "transaction_date": "optional string",
      "category": "string",
      "status": "COMPLETED or POSTED",
      "rewards_earned": "number or points string"
    }
  ]
}
```

`card_type` may be used instead of `credit_card_type`; `amount` may be used instead of `transaction_amount`; and `earned_points` may be used instead of `rewards_earned`. Currency strings such as `$1,234.56` and reward strings such as `123 points` are accepted. Missing, malformed, non-posted, excluded, or unsupported records are returned in `manual_review` rather than silently excluded.

Runnable invocation:

```sh
python3 scripts/analyze_rewards.py < /path/to/transactions.json
```

Validate the output before communicating results: `summary.reviewed_count` must equal the number of supplied transactions, every actionable discrepancy must have a transaction ID and both expected and earned points, and all remaining transactions must be represented in either `consistent` or `manual_review`. If the script returns `input_error`, correct the supplied transaction fields and rerun it; do not invent values.
