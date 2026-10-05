---
name: cash-back-discrepancy-review
version: 1.0.0
description: Review posted Business Silver Rewards Card and Silver Rewards Card transactions for cash-back discrepancies, calculate expected whole-point rewards, explain results, and prepare approved corrections without performing unapproved banking changes.
---

# Cash-Back Discrepancy Review

Use this Skill when a customer reports that cash back on a Business Silver Rewards Card or Silver Rewards Card appears incorrect, or when an approved cash-back dispute requires a transaction-reward correction. It separates an informational audit from any reward update.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and prerequisites

1. Do not disclose transaction, account, card, reward-balance, or dispute details based only on a name, email address, or an account lookup.
2. Verify the caller by asking them to confirm two of the four identity fields: date of birth, email, phone number, and address. Compare the supplied values with the customer record.
3. After two fields match, obtain the current timestamp with `get_current_time` and create the audit record with `log_verification`, supplying all required customer-record fields.
4. Retrieve card accounts and confirm that the verified user owns the relevant card account(s). Confirm that the customer has authority to discuss any business-card account before discussing it or taking action.
5. For a review, identify the relevant transaction(s), ensure the transaction belongs to the confirmed account/card, and use posted/completed transactions only. Pending, declined, returned, refunded, or otherwise ambiguous entries require review rather than a final expected-reward calculation.
6. Never modify transaction rewards merely because the audit finds a discrepancy. A correction requires a resolved and approved cash-back dispute covering the exact transaction, independent rate verification, applicable product/promotion eligibility, and all applicable confirmation requirements.

If the customer cannot identify a purchase, after verification offer to review the available posted transactions for the relevant card(s) or ask for a statement period, merchant, date, and amount. Do not state or expose the supplied public task's customer data as reusable examples.

## Product rules used for the audit

Rewards stored as `points` for these cards represent cash back at **1 point = $0.01**. Therefore, a whole-point result is also the cash-back value in cents.

### Business Silver Rewards Card

- Standard rate: 1.0% (1 point per dollar).
- Eligible Travel and Software rate: 10.0% (10 points per dollar), when the posted merchant category is Travel or Software.
- The following merchants receive the standard 1.0% rate even when categorized as Travel or Software: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight.
- The double-cash-back offer is available to accounts opened from 2024-11-14 through 2025-11-14. For a qualifying account, it doubles both the eligible rate and the standard rate for the first six calendar months from account opening. The normal Business Silver rates resume after that window.
- The audit treats the six-month anniversary as a boundary requiring current-program review rather than assuming an inclusive or exclusive interpretation. Transactions clearly before the anniversary use doubled rates; transactions clearly after it use normal rates.

Eligible Travel categories include airlines, lodging, car rentals, rideshare/taxis, passenger rail/buses/ferries, qualifying travel parking/tolls, and travel agencies/platforms categorized as travel. Eligibility is determined by the recorded merchant category, not by a merchant name or the customer’s intended purchase. Travel/software charges routed through processors or miscoded by the merchant may not qualify and should be referred for category review with receipts.

### Silver Rewards Card

- Standard rate: 1.0% (1 point per dollar).
- Eligible Travel and Software rate: 4.0% (4 points per dollar), when the posted merchant category is Travel or Software.
- Rewards are calculated after posting. Classification exceptions include charges processed through third parties that mask the category and travel-like purchases that post under another category.

For both cards, round the calculated points to the nearest whole point using decimal half-up rounding. Returned or refunded purchases have rewards reversed when the credit posts and are not treated as a missing-reward claim.

## Audit workflow

1. Complete the prerequisite verification and ownership checks above.
2. Obtain the current account opening date, card type, merchant name, transaction amount, transaction date, posted status, category, and recorded reward points for each transaction in scope.
3. Normalize the data into the JSON schema below and run:

   ```sh
   python3 scripts/audit_rewards.py < audit_input.json
   ```

4. Inspect `review_items`, `matches`, and `discrepancies` in the JSON response. A `review` result is not a correction recommendation; obtain missing card terms, category evidence, posting information, or boundary interpretation first.
5. Explain results by card and transaction. State point and dollar equivalents accurately, but do not infer that an account’s total reward balance equals the sum of currently visible transactions because redemptions, adjustments, and older activity may exist.
6. For an apparent shortfall, gather the transaction date, merchant, amount, recorded reward amount, expected amount, and supporting receipt/category evidence. If a merchant category appears wrong, request the appropriate category review rather than overriding the category yourself.
7. If no approved dispute exists, explain that the discrepancy needs investigation/handling by customer service. Do not call an update tool.

## Applying an approved correction

Use this section only after the dispute is resolved and approved, identity/authority/account ownership remain verified, and the exact transaction is confirmed.

1. Identify the transaction IDs requiring correction from the resolved cash-back-dispute record. Do not rely on an `expected_rewards` value from that record.
2. Re-run the independent audit calculation using the transaction’s actual card, category, date, merchant, account opening date, and applicable promotion.
3. Confirm the transaction is a shortfall and the calculated whole-point total is final. Check that no returned/refunded status, transaction mismatch, category-review hold, or promotion-boundary review remains.
4. Unlock `update_transaction_rewards_3847` with `unlock_discoverable_agent_tool`.
5. For each approved transaction only, invoke `call_discoverable_agent_tool` with tool name `update_transaction_rewards_3847` and arguments containing the exact `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`, where `X` is the independently calculated whole-point total. The tool update is an action; do not invoke it for a suggested, unapproved, or over-credit discrepancy.
6. Confirm completion by retrieving the transaction history and checking that the exact transaction now shows the expected whole-point reward. Retain the calculation basis and approval reference in the internal case record.

If a correction cannot be independently calculated or confirmed, do not guess, retry blindly, or make a partial update. Escalate for rewards/category review through the normal support process.

## Script interface

`scripts/audit_rewards.py` reads one JSON object from stdin and emits one JSON object to stdout. It makes no bank-tool calls and cannot update an account.

Required input fields:

- `accounts`: list of objects with `card_type` and `date_of_account_open` (`YYYY-MM-DD`).
- `transactions`: list of objects with `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `transaction_date` (`YYYY-MM-DD`), `category`, `status`, and `rewards_earned`.

Optional input field:

- `resolved_dispute_transaction_ids`: a list of exact transaction IDs from already resolved and approved dispute records. The script only marks a calculated shortfall as an `update_candidate`; it never performs an update.

The output contains `matches`, `discrepancies`, `review_items`, and `update_candidates`. Validate that every input transaction appears in exactly one of the first three result lists and that every update candidate is also a shortfall discrepancy with a matching approved-dispute transaction ID.
