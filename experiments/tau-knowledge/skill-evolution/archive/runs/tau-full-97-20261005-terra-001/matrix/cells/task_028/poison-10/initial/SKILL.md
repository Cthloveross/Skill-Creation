---
name: credit-card-rewards-discrepancy-review
description: Review posted credit-card transactions for plausible rewards discrepancies, calculate only rates supported by supplied program terms, initiate customer cash-back disputes for identified transactions, and apply approved corrections through the authorized internal workflow. Use when a customer reports missing or incorrect credit-card cash back or points.
---

# Credit-Card Rewards Discrepancy Review

Use this Skill for a read-only rewards audit, a customer-initiated cash-back dispute, or an approved rewards correction. Treat transaction `rewards_earned` values as **points**, not dollars. For cash-back cards, 1 point is worth $0.01 when redeemed; EcoCard sustainability points also redeem at $0.01 per point.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Prerequisites and controls

1. Verify identity before retrieving non-public account or transaction data: confirm two of date of birth, email, phone number, and address against the customer record. Obtain the current time and call `log_verification` with the complete required record.
2. Confirm the customer is the account owner or otherwise authorized, and confirm the card account and every reviewed transaction belong to that customer.
3. Confirm the scope: specific transaction IDs if available, or explicit permission to review the account's posted transaction history when the customer cannot identify transactions. Do not expose transactions from another cardholder or account.
4. For a dispute or correction, verify the relevant card product, transaction status, posted merchant category, transaction amount, net-of-return/credit treatment, applicable fees or limits, the exact transaction ID, and required customer or approval confirmation. Check any applicable cutoff or program terms in the runtime before acting; do not invent a cutoff, fee, or rate.
5. A transaction-history record alone is not evidence that a merchant was coded correctly or that a promotion applied. Preserve receipts, posted-category evidence, and calculation notes where review is inconclusive.

If identity cannot be verified, authority/ownership is unclear, a transaction is not attributable to the customer, or required approval is missing, do not submit a dispute or change rewards. Explain what is needed or use the appropriate authorized escalation path.

## Supported calculation rules

Calculate per transaction and truncate downward to a whole number of points. Never round to nearest. Use decimal arithmetic, not binary floating-point arithmetic.

| Card | Supported rule |
|---|---|
| Crypto-Cash Back | 2.0% on eligible purchases = `floor(amount × 2)` points. Eligibility must still be checked; fees, cash equivalents, balance transfers, returns, and credits are not ordinary eligible purchases. |
| EcoCard | `floor(amount × 5)` points for qualifying Green/Sustainable purchases; otherwise `floor(amount × 1)`. Target, Walmart, Amazon, and ThredUp always receive the standard rate. EV charging receives the higher rate only at Tesla Supercharger, ChargePoint, or EVgo. |
| Business Platinum Rewards Card | `floor(amount × 4)` for posted Travel, Software, and verified Media **advertising** purchases; `floor(amount × 1.5)` for other eligible purchases. Merchant-submitted category controls. |
| Silver Rewards Card | `floor(amount × 4)` for posted Travel and Software purchases. The supplied terms do not establish its ordinary-purchase rate. Do not infer that rate from a transaction history; mark non-Travel/non-Software entries as needing the applicable terms. |

For all cards, returns and credits reduce net eligible purchases and rewards are reversed at the original rate. Do not apply an enhanced rate based only on a merchant name when the posted category or required qualification conflicts with it. For Business Platinum Media, obtain evidence that the purchase is advertising rather than assuming every Media-category transaction qualifies.

## Audit procedure

1. After the prerequisites, retrieve the customer's credit-card accounts and transaction history using the normal banking tools. Limit the review to completed, posted purchase entries; separately identify returns, credits, pending entries, fees, cash-equivalent transactions, and ambiguous classifications.
2. Normalize the retrieved transactions into the JSON schema accepted by `scripts/rewards_audit.py`. Supply explicit qualification fields when available, especially `qualifies_media_advertising`, `reward_eligible`, and `is_return_or_credit`.
3. Run the packaged script. It produces one of `match`, `mismatch`, `insufficient_information`, or `skipped` for each record. A `mismatch` is an audit finding, not a reason to alter a transaction.
4. Review every mismatch against the source record and applicable terms. Never use an `expected_rewards` value from a dispute record as the calculation source.
5. Present a concise result to the customer: transaction date/merchant/amount, recorded and independently calculated points, and any assumptions or unresolved classification issue. Do not claim a discrepancy for a rate that is not documented.

### Script interface

Run `scripts/rewards_audit.py` with one JSON object on stdin:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Crypto-Cash Back | EcoCard | Business Platinum Rewards Card | Silver Rewards Card",
      "transaction_amount": "decimal amount",
      "category": "posted category",
      "merchant_name": "merchant",
      "status": "COMPLETED",
      "rewards_earned": "whole points",
      "reward_eligible": true,
      "qualifies_media_advertising": true,
      "is_return_or_credit": false
    }
  ]
}
```

Only `transactions` is required. Optional fields make the conclusion more reliable. Amounts may be numbers or strings with `$` and commas. The script emits JSON:

```json
{
  "summary": {"match": 0, "mismatch": 0, "insufficient_information": 0, "skipped": 0},
  "results": [
    {
      "transaction_id": "string",
      "outcome": "match | mismatch | insufficient_information | skipped",
      "expected_points": 0,
      "recorded_points": 0,
      "rate_points_per_dollar": "4",
      "reason": "string",
      "assumptions": ["string"]
    }
  ]
}
```

Validate that each returned `transaction_id` exists in the retrieved history, every expected value is an integer, and the output count equals the input count. Treat parser errors, unsupported card types, missing amounts, malformed points, and unestablished rates as unresolved rather than guessing.

## Customer dispute submission

A cash-back discrepancy dispute applies to any credit-card transaction, but it requires the customer's user ID and an exact transaction ID.

After the prerequisites and after identifying a specific transaction, instruct the customer to submit it with `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`. Provide this through `give_discoverable_user_tool` using the verified customer's user ID and the exact transaction ID. The customer—not the agent—executes the supplied tool. Do not collect card numbers or other unnecessary sensitive card details. Explain that supporting receipts or category/promotion context may be requested during review.

If the customer cannot identify a transaction, complete the permitted audit first and provide the candidate transaction IDs. Do not submit a blanket dispute or invent a transaction ID.

## Approved correction workflow

Only correct rewards after the dispute is demonstrably resolved and approved. A customer assertion, audit mismatch, or submitted dispute is not approval.

1. Reconfirm the mandatory prerequisites above, including ownership, product eligibility, account/card and transaction details, applicable fees/limits/cutoffs, and approval confirmation.
2. Look up the customer's resolved cash-back disputes in the authorized `cash_back_disputes` data source and identify the exact affected transaction IDs. If the runtime does not provide an authorized resolved-dispute lookup, do not update rewards; retain the audit result and follow the available escalation process.
3. Independently recalculate each approved transaction from its card type, posted category, eligibility evidence, and any active promotion. Do not rely on a dispute record's `expected_rewards` field.
4. Unlock `update_transaction_rewards_3847` with `unlock_discoverable_agent_tool`.
5. For each approved transaction, call `update_transaction_rewards_3847` through `call_discoverable_agent_tool` with JSON arguments containing the exact `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`, where `X` is the independently calculated whole-number value.
6. Confirm the completed update in credit-card transaction history. Record the inputs, rate/eligibility rationale, prior and new points, approved dispute reference, and confirmation result in the internal case record.

If the update fails or confirmation does not show the expected value, do not retry blindly or represent it as completed. Preserve the tool result and escalate through the authorized process.
