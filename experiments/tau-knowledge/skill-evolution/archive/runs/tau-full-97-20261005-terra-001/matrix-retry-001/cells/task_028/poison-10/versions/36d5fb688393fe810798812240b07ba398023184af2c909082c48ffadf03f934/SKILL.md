---
name: credit-card-rewards-audit-and-dispute-routing
description: Audit posted credit-card transaction rewards against documented card rates, flag definite or inconclusive discrepancies, and route customers to the required self-service dispute flow. Use when a customer reports incorrect cash back or rewards, including an unspecific request for a transaction-history review.
---

# Credit Card Rewards Audit and Dispute Routing

## Scope and safety

Use this Skill to review rewards already recorded on credit-card purchases. It calculates whole-number reward points from supplied transaction data; it does not make reward changes.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A name lookup is not identity verification. Before retrieving or discussing account-specific transaction details, ask the customer to provide any two of the following facts and compare them to the customer record: date of birth, email, phone number, and address. After two fields match, obtain the current time and call `log_verification` with all fields from the matched customer record and that timestamp. If two fields cannot be verified, do not disclose transaction details or submit, route, or adjust a dispute.

Also confirm the reviewed card accounts belong to the verified user and that each transaction belongs to that user and card. Discuss only the requested period; if no period is given and the customer asks for a broad review, explain the period being reviewed before presenting results.

## Documented calculation rules

All calculations below are in stored reward points. Always truncate fractional points down once per transaction; never round to the nearest point and never pool fractions across transactions.

- Cash-back cards store rewards as points, where 1 point equals $0.01 of cash back. EcoCard sustainability points also redeem at $0.01 per point.
- Crypto-Cash Back earns 2.0% on eligible purchases: `floor(amount × 2)` points.
- Business Platinum Rewards Card earns 4.0% on Travel, Software, and Media purchases: `floor(amount × 4)` points. Other eligible purchases earn 1.5%: `floor(amount × 1.5)` points. Cash equivalents, balance transfers, and fees earn no rewards.
- Silver Rewards Card earns 4.0% on posted Travel and Software purchases: `floor(amount × 4)` points. The available documentation establishes only that non-category purchases earn **at least** 1.0%, so use `floor(amount × 1)` only as a lower-bound check; do not claim that a transaction at or above that lower bound is correct without the applicable terms or promotion data. Merchant category coding controls enhanced-rate eligibility.
- EcoCard earns 5 points per dollar on qualifying Green/Sustainable purchases and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp always receive the standard rate, even for eco-labeled items. EV charging receives the green rate only at Tesla Supercharger, ChargePoint, or EVgo. A transaction must have qualifying merchant/category recognition to receive the higher rate.

Do not treat an `expected_rewards` field in a dispute record as evidence. Independently calculate from the transaction amount, posted status, card, merchant/category eligibility, documented exclusions, and a verified applicable promotion. If an active promotion, merchant classification, green eligibility, return/credit status, or fee/cash-equivalent status cannot be established from the transaction data, label the result inconclusive rather than asserting a correction.

## Workflow

1. **Verify and scope.** Complete identity verification and account ownership checks above. Ask for a statement period or transaction IDs when practical. For an unspecific review, retrieve the verified user’s relevant credit-card accounts and transactions using the normal read-only tools.
2. **Prepare eligible records.** Review posted/completed purchase transactions only. Exclude or mark inconclusive returned/refunded purchases, fees, interest, gift cards, person-to-person payments, balance transfers, cash equivalents, transactions with missing amounts, and transactions with missing merchant/category data needed for the claimed rate.
3. **Audit deterministically.** Send the transaction records to `scripts/reward_audit.py`. Add `green_eligible` only when eligibility has been verified. Add a `verified_rate_override` only when a documented active promotion or authoritative card term establishes that rate; never derive it from a dispute’s expected value.
4. **Validate the output.** Check every audit entry has a transaction ID, integer nonnegative expected and recorded points, and a supported basis. A `definite_mismatch` has a nonzero point difference under an exact documented or verified rate. `lower_bound_shortfall` means the recorded points are definitely below a documented minimum. `inconclusive` and `skipped` entries must not be represented as errors.
5. **Explain the result.** State the transaction date, merchant, recorded versus calculated points, calculation basis, and the point difference for each definite issue. Include both shortages and over-awards. Explain that points correspond to $0.01 each where relevant. Do not state that a rate was guaranteed when the output says `lower_bound_only` or `inconclusive`.
6. **Route a customer dispute; do not submit it as the agent.** For every transaction the customer wants disputed, confirm the exact transaction ID, then provide `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` through `give_discoverable_user_tool`. The customer must run it with their own verified user ID and that specific transaction ID. Do not collect card numbers or sensitive card details. Note that receipts and category/promotion context may be requested during review.
7. **Apply a correction only after approval.** A review finding or submitted dispute alone never authorizes an update. For a resolved and approved dispute, identify affected transaction IDs in `cash_back_disputes`, independently rerun the calculation (including verified promotion facts), unlock `update_transaction_rewards_3847`, and call it with the exact `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`. Then confirm the result in `credit_card_transaction_history` and retain calculation notes in the internal case record. If resolved-dispute data or a required verification is unavailable, do not invoke the update tool.

## Script interface

Run with `run_skill_script` using `scripts/reward_audit.py`. The script reads one JSON object from stdin and emits one JSON object on stdout.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Crypto-Cash Back | Business Platinum Rewards Card | Silver Rewards Card | EcoCard",
      "transaction_amount": "$12.34 or 12.34",
      "category": "string",
      "merchant_name": "string",
      "status": "COMPLETED or POSTED",
      "rewards_earned": "24 points or 24",
      "green_eligible": true,
      "verified_rate_override": {
        "rate_points_per_dollar": "3.0",
        "reason": "verified active promotion or card terms"
      }
    }
  ]
}
```

`green_eligible` and `verified_rate_override` are optional. Omit `green_eligible` when it has not been verified; a Green/Sustainable transaction category is treated as the recorded category classification, while the stated EcoCard exceptions still override it. An override is accepted only for an exact, independently verified rate. Unknown fields, including `expected_rewards`, are ignored.

Output contains `audits`, `definite_discrepancies`, `inconclusive`, `skipped`, and a count summary. For a confirmed candidate, `new_rewards_earned` is a calculation result for later approved-dispute processing, not authorization to update it.

Example runnable call (values are illustrative only):

```json
{
  "relative_path": "scripts/reward_audit.py",
  "input_json": {
    "transactions": [
      {
        "transaction_id": "transaction-id-from-record",
        "credit_card_type": "Silver Rewards Card",
        "transaction_amount": "125.75",
        "category": "Travel",
        "merchant_name": "merchant-from-record",
        "status": "COMPLETED",
        "rewards_earned": "503 points"
      }
    ]
  }
}
```

Expected validation for this example: the expected value is `floor(125.75 × 4) = 503` points and the audit status is `match`.
