---
name: credit-card-rewards-audit
version: 1.0.0
description: Audit posted credit-card transaction reward accruals against documented rates, explain points-versus-cash-back representation, identify transactions needing review, and guide a verified customer through the documented self-service cash-back dispute process. Use for questions about incorrect card rewards or cash back.
---

# Credit-card rewards audit

Use this Skill when a customer believes card rewards or cash back may be incorrect. It audits **individual posted transactions** from runtime-supplied account and transaction data. It does not assume that an account's current reward balance equals the sum of the supplied transactions: balances can reflect older activity, redemptions, adjustments, or transactions outside the retrieved range.

## Privacy and verification

1. Identify the customer using a supplied name or email and retrieve the account only through the declared banking tools.
2. Before disclosing account-specific findings or taking account action, obtain and confirm at least two of the four identity fields: date of birth, email, phone number, and address.
3. Retrieve the authoritative user record, get the current timestamp, and call `log_verification` with the complete required fields only after two fields match. Do not treat a name alone as verification.
4. If verification is incomplete, ask for the missing identity information. You may give general rate information but must not expose transaction-specific findings.

## Runtime workflow

1. Clarify the concern when possible: affected card, statement period, and transactions or reward amounts. If the customer cannot identify them, explain that you can review the posted transactions available for the account after verification.
2. Retrieve credit-card accounts and transaction history using the declared tools. Audit only transactions that are posted/completed in the supplied data. Returns or credits reduce rewards at their original rate; do not call a reward error based solely on a pending, reversed, fee, cash-equivalent, balance-transfer, or otherwise unsupported record.
3. Save the retrieved transaction objects as JSON and run:

   ```sh
   python3 scripts/audit_rewards.py < transactions.json
   ```

   The script receives one JSON object on stdin:

   ```json
   {"transactions": [{"transaction_id": "...", "credit_card_type": "...", "merchant_name": "...", "transaction_amount": 0, "category": "...", "status": "COMPLETED", "rewards_earned": 0}]}
   ```

   It emits JSON containing `audited`, `discrepancies`, `review_needed`, `skipped`, and `summary`. It never accesses banking systems or performs an account action.
4. Review `discrepancies` with the customer. A discrepancy is an arithmetic comparison to the documented rate based on the supplied category and known exclusions, not a guarantee of adjustment. `review_needed` means the rate cannot safely be determined from the available data, such as a potentially excluded transaction or an unclear green qualification.
5. State cash-back values accurately: for cash-back cards, stored reward points equal cash back at **1 point = $0.01**. EcoCard points are sustainability points and also redeem at $0.01 per point, but its earning rate is points per dollar rather than a percentage.
6. Do not infer that a merchant is eligible merely from its brand. Merchant coding controls travel, software, and advertising qualification. Request receipts or invoices when classification needs review.

## Rate rules encoded by the helper

- **Silver Rewards Card:** 4% on Travel and Software/SaaS; 1% on other purchase categories.
- **Business Platinum Rewards Card:** 4% on Travel, Software/SaaS, and Media/Advertising; 1.5% otherwise.
- **Crypto-Cash Back:** 2% on eligible purchases.
- **EcoCard:** 5 sustainability points per dollar for qualifying green purchases; 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp are standard-rate exclusions. EV charging gets the green rate only at Tesla Supercharger, ChargePoint, or EVgo.

The helper truncates fractional points toward zero, matching whole-point transaction storage. It recognizes the categories represented in runtime data; it deliberately reports unsupported card products or uncertain eligibility instead of inventing a rate.

## Dispute handling

The documented dispute action is customer self-service, not an agent-initiated adjustment. For each transaction the customer wants disputed:

1. Confirm the relevant `transaction_id` and the verified customer's `user_id`.
2. Use `give_discoverable_user_tool` to provide `submit_cash_back_dispute_0589` to the customer, with no fabricated identifiers. Tell them to run:

   `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

3. Explain that supporting category or promotion documentation may be requested during review. Do not promise approval, alter rewards, or submit the customer-side tool on their behalf.

If there is no identifiable transaction, ask the customer to select one after presenting the eligible findings. If the request is not covered by the rate rules or cannot be resolved from available records, explain the limitation and use the appropriate declared escalation process rather than guessing.

## Validate the audit output

Before using an audit result, confirm that output is a JSON object, every `discrepancies` item has a `transaction_id`, `recorded_points`, and `expected_points`, and every expected calculation has `calculation_status` equal to `calculated`. Treat malformed transaction fields and non-completed statuses as skipped/review items, not evidence that the customer is wrong.
