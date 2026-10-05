---
name: cash-back-discrepancy-review
description: Safely authenticate a cardholder, review posted credit-card cash-back earnings against documented Silver and Business Silver reward rules, identify explainable discrepancies, submit a customer-initiated dispute, and apply corrections only after an approved dispute.
---

# Cash-Back Discrepancy Review

Use this Skill when a customer reports missing, incorrect, or unexpectedly low credit-card cash back. It supports an investigation of posted transactions for the documented Silver Rewards Card and Business Silver Rewards Card. It does not infer merchant coding beyond the transaction category supplied by the transaction system.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and prerequisites

1. Treat a name, email address, or user ID only as an account lookup lead, not identity verification.
2. Before disclosing nonpublic account or transaction details, submitting a dispute, or correcting rewards, verify the customer with two of the four recorded fields: date of birth, email, phone number, and address. Compare the customer-supplied values to the user record without revealing values first.
3. After two fields match, call `get_current_time`, then call `log_verification` with the complete record and the returned timestamp.
4. Confirm authority and ownership by ensuring the verified user ID owns the relevant card account and each reviewed transaction. Confirm the card type on the account matches the transaction record.
5. Check the transaction is posted/completed and not returned, refunded, or credited. Rewards are calculated after posting. Do not represent an authorization or pending reward as final.
6. Review applicable product eligibility, merchant category, rewards limitations, and any relevant fee, cutoff, balance/credit, recipient, and confirmation requirements before an action. For a rewards review, recipient details are not applicable; for a transaction correction, card type and transaction ownership are the relevant card details. Do not assume a fee, limit, or cutoff is absent if the available policy or tool response does not establish it.
7. A transaction scan is informational. Do not change rewards based solely on a scan or a customer's expectation. A correction requires a resolved and approved cash-back dispute.

If the customer cannot complete verification, do not disclose account-specific results or submit/alter anything. Ask them to return with the required verification information or use an approved support channel.

## Investigation workflow

1. Ask for a transaction ID or statement period if the customer knows it. If they do not, complete verification before retrieving and reviewing their account history.
2. Retrieve the verified user's credit-card accounts and transactions using the normal banking tools. Work only from the returned records. Record the account opening date for each Business Silver transaction.
3. Analyze completed transactions with `scripts/analyze_rewards.py`. Supply the transaction-system category exactly as returned; category is the proxy for the merchant's submitted classification. See the script schema below.
4. Review only rows whose `review_status` is `discrepancy` or `needs_manual_review`. Explain that database rewards are stored as points and that 1 point equals $0.01 in cash back.
5. For a potential merchant miscoding, explain that bonus eligibility depends on how the merchant processed the transaction. Request receipts or invoices if available; do not claim that a merchant qualifies merely from its name.
6. State the calculation transparently: amount × rate × 100 points, rounded down to a whole point. A one-point difference can be explained by truncation only when the independently calculated floor supports it.
7. If the customer wants to dispute a particular transaction, confirm the exact transaction ID, their intent to submit, and the already-verified ownership. Provide the customer-facing tool `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` using `give_discoverable_user_tool`. The customer, not the agent, submits it. Mention that review may request supporting category or promotion documentation.

If no specific transaction can be identified and the customer does not want an authenticated review, provide general reward-rate guidance and ask them to return with a transaction ID or statement period. Do not file a blanket dispute.

## Reward policy encoded by the analyzer

- **Silver Rewards Card:** Eligible posted Travel and Software transactions earn 4.0%. This Skill has no documented standard/nonbonus rate for this card, so it will not calculate an expected value for another category.
- **Business Silver Rewards Card:** Eligible posted Travel and Software transactions earn 10.0%; other documented purchases earn 1.0%.
- **Business Silver exclusions:** Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight earn the standard 1.0%, even if a supplied category says Travel or Software. The analyzer recognizes exact names and documented-name prefixes such as a named merchant followed by a plan/product suffix; verify ambiguous merchant names manually.
- **Business Silver promotion:** An account opened from 2024-11-14 through 2025-11-14 qualifies for double rewards for its first six calendar months from account opening. The multiplier applies to both the 10.0% and 1.0% rates. The account opening date—not the promotion start date—determines the six-month window. The analyzer treats the opening-date anniversary as outside the first six months.
- Travel and software eligibility remains subject to the transaction's merchant category. Eligible travel examples include airlines, lodging, car rentals, rideshare/taxis, passenger rail/buses/ferries, travel-coded parking and tolls, and travel-coded agencies/platforms.
- All calculations floor fractional points. Points should never be rounded to the nearest whole number.

## Analyzer

Run the packaged script with JSON on standard input and consume its JSON standard output:

```sh
python3 scripts/analyze_rewards.py < transactions.json
```

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Silver Rewards Card or Business Silver Rewards Card",
      "merchant_name": "string",
      "transaction_amount": "decimal string or number",
      "transaction_date": "YYYY-MM-DD",
      "category": "transaction-system category",
      "status": "COMPLETED",
      "rewards_earned": "optional whole points or '<whole> points'",
      "account_open_date": "YYYY-MM-DD; required for Business Silver"
    }
  ]
}
```

The output has one result for each supplied transaction. `expected_points` is emitted only when policy supports a calculation. `discrepancy` means the stored whole-point value differs from the independently computed expected value; it is a review lead, not approval to update an account. `needs_manual_review` identifies missing policy inputs, unsupported card/category rules, invalid amounts/dates, or a transaction that is not eligible for final calculation. Preserve the returned calculation inputs and rationale in the case record.

## Approved-dispute correction workflow

Perform this section only after identity/authority checks above and after confirming a dispute is resolved and approved.

1. Look up the user's resolved disputes in the `cash_back_disputes` database and identify the affected transaction IDs. Do not trust an `expected_rewards` field in a dispute record.
2. Re-retrieve the current transaction record and owning card account. Recalculate independently with the analyzer and resolve any merchant-category uncertainty before acting.
3. Recheck applicable product eligibility, ownership, card details, balance/credit relevance, fees, limits, cutoffs, and confirmation requirements. Ensure the dispute resolution authorizes this exact adjustment.
4. Unlock `update_transaction_rewards_3847` using `unlock_discoverable_agent_tool`.
5. Call it through `call_discoverable_agent_tool` with the exact transaction ID and `new_rewards_earned` formatted exactly as `"X points"`, where X is the analyzer's whole-number `expected_points`.
6. Retrieve or otherwise confirm the transaction in `credit_card_transaction_history` after the tool completes. Retain the rate, promotion decision, exclusion decision, arithmetic, dispute ID/status, and confirmation result in the internal case record.

If the dispute is missing, unresolved, denied, ownership cannot be verified, or the analyzer requires manual review, do not update rewards. Escalate through the applicable support process rather than guessing.
