---
name: credit-card-rewards-audit-and-dispute-correction
description: Verify a credit-card customer, audit posted transaction rewards against documented rates, route customer-initiated disputes, and apply corrections only after independently verifying approved and resolved cash-back disputes. Use when a customer reports incorrect cash back or rewards, including an unspecific transaction-history review or a later notice that submitted disputes were resolved.
---

# Credit Card Rewards Audit and Dispute Correction

## Scope and controls

Use this Skill for credit-card reward reviews and the documented post-resolution correction workflow. Rewards are stored as whole-number points. This Skill may update rewards only after the dispute record itself verifies that the dispute is both approved and resolved.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A name lookup is not identity verification. Before retrieving or discussing account-specific transaction details, ask the customer to provide any two of the following facts and compare them with the customer record: date of birth, email, phone number, and address. After two fields match, obtain the current time and call `log_verification` with all fields from the matched customer record and that timestamp. If two fields cannot be verified, do not disclose account details, submit or route a dispute, or make a reward correction.

Confirm the reviewed card accounts belong to the verified user and every reviewed transaction belongs to that user and an account being reviewed. Discuss only the requested period. For a broad review without a period, state the period that will be reviewed before presenting account-specific results.

## Calculation rules

Calculate stored reward points separately for each transaction. Always truncate fractional points down once per transaction; never round to the nearest point and never combine fractions across transactions.

- Cash-back-card points represent cash back at 1 point = $0.01. EcoCard sustainability points also redeem at $0.01 per point.
- Crypto-Cash Back earns 2.0% on eligible purchases: `floor(amount × 2)` points.
- Business Platinum Rewards Card earns 4.0% on Travel, Software, and Media purchases: `floor(amount × 4)` points. Other eligible purchases earn 1.5%: `floor(amount × 1.5)` points. Cash equivalents, balance transfers, and fees earn no rewards.
- Silver Rewards Card earns 4.0% on posted Travel and Software purchases: `floor(amount × 4)` points. For non-category purchases, the available documentation establishes only an at-least-1.0% lower bound. Use `floor(amount × 1)` only to identify a definite lower-bound shortfall; do not call an amount at or above that value correct without verified applicable terms or promotion facts. Merchant category coding controls enhanced-rate eligibility.
- EcoCard earns 5 points per dollar on qualifying Green/Sustainable purchases and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp receive the standard rate even for eco-labeled items. EV charging receives the green rate only at Tesla Supercharger, ChargePoint, or EVgo. Green eligibility must be supported by the transaction classification or verified merchant eligibility.

Do not use an `expected_rewards` field in a dispute record as calculation evidence. Independently calculate using transaction amount, posted status, card, category, merchant eligibility, exclusions, and an independently verified active promotion. If a required promotion, merchant classification, green qualification, return/credit status, or exclusion fact is not established, mark the result inconclusive rather than asserting a correction.

## Initial audit and dispute-routing workflow

1. **Verify, log, and scope.** Complete identity verification and the account-ownership checks above. For an unspecific review, retrieve the verified user’s relevant credit-card accounts and transaction history using the normal read-only tools.
2. **Prepare records.** Review posted/completed purchase transactions only. Exclude or mark inconclusive returned/refunded purchases, fees, interest, gift cards, person-to-person payments, balance transfers, cash equivalents, missing amounts, and transactions missing data required for the claimed rate.
3. **Audit.** Run `scripts/reward_audit.py` with the transaction records. Supply `green_eligible` only when it is verified. Supply `verified_rate_override` only for a documented, independently verified applicable promotion or authoritative term; never derive it from a dispute record’s expected value.
4. **Validate and explain.** Ensure each audit entry has an identifier, integer nonnegative recorded and expected points, and a supported basis. Explain every definite discrepancy with its transaction ID, date, merchant, recorded and independently calculated points, basis, and point difference. Include over-awards as well as shortages. State the truncation rule and the $0.01-per-point representation where relevant. Do not represent `lower_bound_only`, `inconclusive`, or `skipped` results as definite errors.
5. **Route customer-initiated disputes.** For each transaction the customer chooses to dispute, confirm the exact transaction ID and provide `submit_cash_back_dispute_0589` using `give_discoverable_user_tool`, with a valid JSON arguments string containing the verified `user_id` and that transaction ID. The customer, not the agent, runs the submission tool. Do not collect card numbers or other sensitive card details. Explain that receipt, category, or promotion context may be requested during review.

## Mandatory approved-dispute correction workflow

Follow this workflow when a verified customer says that one or more cash-back disputes were approved and resolved, or when a resolved dispute is otherwise identified. A customer statement is a trigger to look up records, not sufficient authorization by itself. Do not transfer the customer solely because correction is required.

1. **Look up dispute records first.** After the resolution notice, query the `cash_back_disputes` records for the verified user with the runtime’s available dispute read/query capability. When the runtime exposes `get_cash_back_disputes_by_user`, call it with `user_id`; otherwise use the available get/list/search/lookup/find/query operation for `cash_back_disputes` scoped to that verified user. Do this before any unlock or reward update.
2. **Verify record-level authorization.** From the retrieved records, retain only disputes that are explicitly associated with the verified user, identify an exact `transaction_id`, and have both approved and resolved outcomes/statuses. A pending, denied, missing, ambiguous, or user-mismatched record is not authorized for correction. Do not update a transaction merely because it was part of the initial audit or because the customer says it was approved.
3. **Re-read and recalculate.** Retrieve or use the authoritative transaction-history record for every retained exact transaction ID. Confirm account ownership, matching transaction identity, completed/posted status, purchase eligibility, and all rate inputs. Independently rerun the reward calculation; never copy a dispute record’s expected amount. Retain calculation basis and resulting whole-number value in the internal case record.
4. **Unlock only after verification.** Call `unlock_discoverable_agent_tool` with `agent_tool_name` exactly `update_transaction_rewards_3847` once the resolved records and calculations have been verified.
5. **Update each authorized transaction.** For every verified approved-and-resolved dispute, call `call_discoverable_agent_tool` using `agent_tool_name` exactly `update_transaction_rewards_3847`. Its arguments must be valid JSON containing the exact `transaction_id` from the verified dispute and `new_rewards_earned` exactly formatted as `"X points"`, where X is the independently calculated nonnegative whole-number value. Make one exact-ID update per verified transaction. Do not omit a verified record and do not update unrelated transactions.
6. **Confirm completion.** Check that each update call completed successfully. Then confirm the corrected reward in `credit_card_transaction_history` using the normal transaction-history read capability. Tell the customer which verified transaction IDs were corrected and their final point values. If an update fails, report the failure accurately, do not claim the correction completed, and do not silently substitute an unverified value.

If no dispute-read capability is available or no record verifies approved-and-resolved status, do not unlock or call the update tool. Explain the unresolved prerequisite and preserve the audit notes. If only some records are verified, correct only those records and clearly distinguish the unresolved ones.

## Script interface

Run `scripts/reward_audit.py` through `run_skill_script`. It reads one JSON object from stdin and emits one JSON object on stdout.

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

`green_eligible` and `verified_rate_override` are optional. Omit `green_eligible` when eligibility has not been verified; a Green/Sustainable category represents the recorded category classification, subject to documented EcoCard exceptions. Unknown fields, including `expected_rewards`, are ignored.

The output contains `audits`, `definite_discrepancies`, `inconclusive`, `skipped`, and `summary`. A `new_rewards_earned` value in the output is only an independently calculated candidate. It is not permission to make a correction until the approved-and-resolved workflow above is completed.

Example runnable call:

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

Expected validation: the script reports `floor(125.75 × 4) = 503 points` with an audit status of `match`.
