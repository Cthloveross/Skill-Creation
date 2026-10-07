---
name: credit-card-rewards-discrepancy-review
description: Review posted Gold Rewards Card and EcoCard transaction rewards, calculate expected whole-point awards, explain discrepancies, and guide an authenticated customer to submit a transaction-specific cash-back dispute.
---

# Credit Card Rewards Discrepancy Review

Use this skill when a customer reports missing, incorrect, or unexplained credit-card cash back or EcoCard sustainability points. It supports read-only transaction review and customer-initiated dispute submission; it does not apply reward corrections.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Prerequisites and verification

Before retrieving or discussing nonpublic account or transaction details:

1. Identify the customer using a supplied name or email and locate the candidate customer record.
2. Verify identity by having the customer confirm at least two of the four stored fields: date of birth, email, phone number, or address. Do not disclose unconfirmed values as verification prompts.
3. Obtain the current timestamp and call the runtime's verification-log tool with the full record only after the customer has correctly confirmed two fields.
4. Confirm authority and account ownership by checking that every reviewed card account and transaction belongs to the verified customer ID. Only review the card products the customer identifies or authorizes.
5. For a rewards review, document applicability of the remaining control checks: no payment, transfer, redemption, recipient, credit-limit, fee, or cutoff action is being requested; available credit is not relevant to a read-only calculation. Confirm the card type and the exact transaction before any dispute is submitted.

Do not treat a name alone, an account ID alone, or information found in a record as identity verification.

## Review workflow

1. After verification, retrieve the customer's card accounts and transaction history using the normal read-only banking tools.
2. Limit the calculation to completed purchase transactions. Do not infer rewards for pending, reversed, returned, refunded, disputed, malformed, negative-amount, or otherwise non-purchase entries. Explain that return/refund point reversals occur at the original earn rate and need the original transaction context.
3. Send the applicable transaction records to `scripts/audit_rewards.py`. Preserve source transaction IDs and do not alter transaction data.
4. For each reviewable transaction, compare the stored whole-point award with the script's expected whole-point award. Explain points as money only where applicable: stored Gold Rewards Card points represent cash back at 1 point = $0.01; EcoCard sustainability points also redeem at $0.01 per point.
5. Tell the customer which specific transaction(s) appear under- or over-awarded, the expected points, awarded points, and the relevant rate. If eligibility cannot be established from the record, describe the result as provisional and request a receipt, merchant information, or directory evidence rather than asserting a higher rate.
6. Before a dispute, reconfirm the customer wants to dispute each exact transaction ID. Confirm the transaction belongs to the verified customer, is a completed purchase, and that the customer understands the rate/eligibility basis. A dispute has no stated fee, balance requirement, limit, cutoff, recipient, or card-detail prerequisite; do not invent one.
7. Disputes must be submitted by the customer, not by the agent. Provide `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` through the runtime's user-tool handoff mechanism and instruct the customer to use their own verified user ID and one confirmed transaction ID. Give a separate handoff for each transaction if the runtime requires one transaction per call.
8. Do not unlock or call an internal reward-update tool during the initial review or submission. Any post-resolution correction is a separate internal process: locate a resolved approved dispute, independently recalculate the award, apply the resulting whole-point value with the authorized internal tool, confirm the transaction-history update, and retain calculation notes.

If the customer cannot identify a transaction, conduct the authenticated read-only review, summarize any apparent discrepancies, and ask the customer to choose the exact transaction to dispute. If no discrepancy is identifiable, explain the calculation and offer to review a statement period or receipt when available.

## Reward rules used by the calculator

- **Gold Rewards Card:** all purchases earn 2.5% cash back. Since one stored point is $0.01, expected stored points are `floor(amount × 2.5)`.
- **EcoCard:** qualifying green purchases earn 5 sustainability points per dollar; other purchases earn 1 point per dollar. Expected points are `floor(amount × applicable_rate)`.
- All credit-card reward calculations truncate fractional points down to a whole number.
- EcoCard exclusions override a green category: Target, Walmart, Amazon, and ThredUp earn the standard rate in all channels. Amazon-processed marketplace purchases are Amazon purchases for this rule.
- EV charging earns the EcoCard green rate only at Tesla Supercharger, ChargePoint, or EVgo. Charging at other networks earns the standard rate.
- A transaction explicitly marked green by the transaction source is treated as qualifying unless an exclusion overrides it. If the source does not provide explicit green eligibility or a Green category, treat it as standard-rate for deterministic calculation and report that eligibility was not independently evidenced. Gift cards, cash equivalents, mixed carts at non-partner merchants without item-level green evidence, and marketplace/delivery payments processed through a non-green parent should not be assumed green.

## Calculator interface

Run the packaged script with JSON on stdin:

```sh
python3 scripts/audit_rewards.py <<'JSON'
{"transactions": []}
JSON
```

Input object:

- `transactions` (required): list of transaction objects.
- Each transaction requires `transaction_id`, `card_type`, `merchant_name`, `transaction_amount`, `category`, `status`, and `rewards_earned`. Amount and earned points may be numeric or strings such as `"12.34"` and `"30 points"`.
- Optional `green_eligible` is an explicit boolean eligibility determination. Optional `is_ev_charging` identifies a charging transaction when the merchant name is not sufficient. Optional `certified_ev_networks` replaces the documented EV-network list only when a current authorized source supplies it.

The script emits an object containing `reviews`, `summary`, and `errors`. Each review has `expected_points`, `awarded_points`, `difference_points`, `discrepancy`, `rate_points_per_dollar`, `eligibility_basis`, and `reviewable`. Positive `difference_points` means the record appears under-awarded. Entries that cannot safely be calculated are returned as non-reviewable with a reason. Treat script errors as a request for corrected source data, not as a rewards conclusion.

Validate that every customer-facing transaction ID in the result matches a retrieved transaction owned by the verified customer and that the calculation applies only to the recorded card type and completed purchase status.