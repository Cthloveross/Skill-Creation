---
name: business-silver-cash-back-review
description: Review a Business Silver Rewards Card cash-back concern, safely verify the customer before account-specific actions, calculate policy-based expected rewards from transaction data, distinguish confirmed discrepancies from merchant-coding questions, and guide the customer to the required self-service dispute tool.
---

# Business Silver Rewards Card Cash-Back Review

Use this Skill when a customer says that cash back on a Business Silver Rewards Card appears incorrect.

## Policy facts used

- Eligible travel and software purchases earn 10% cash back; other purchases earn 1%.
- Eligibility depends on how the merchant processes and codes the transaction. A displayed category or a merchant's general line of business alone is not conclusive proof of qualifying coding.
- Corporate expense platforms (Concur, SAP Concur, Expensify, Navan), hardware/electronics merchants (Apple, Microsoft, Dell), gaming subscriptions (Xbox Game Pass, PlayStation Plus, Nintendo Switch Online), and online-learning platforms (Coursera, Udemy, LinkedIn Learning, Skillshare, Pluralsight) earn the standard rate, even if a transaction appears related to travel or software.
- A customer who opened the card during the offer period receives double the otherwise applicable rate for the first six months after opening. The offer does not override exclusions.
- Stored reward “points” on this cash-back card mean cash back at 100 points per dollar ($0.01 per point).

## Safe workflow

1. Treat the supplied opening statement as a request for assistance, not as authorization to disclose or change account information.
2. Before any new banking action, verify identity and authority. Obtain and confirm two of the four identity fields (date of birth, email, phone number, and address) against the located customer record. Do not reveal stored values to solicit confirmation. After two fields match, use the current timestamp and call `log_verification` with the complete required record.
   - A full name may be used to locate a possible record, but is not itself sufficient verification.
   - If identity cannot be verified, do not access additional account information, disclose transaction details, or submit/offer an account-specific dispute. Explain that two verification fields are needed.
   - If multiple customer records match, ask for a non-sensitive distinguishing identifier or use the normal supported lookup; do not guess.
3. Once verified, retrieve the customer’s credit-card accounts and transaction history using the normal banking tools. Confirm the relevant card type, account-opening date, transaction status, merchant, transaction date, amount, recorded category/coding information, and recorded rewards.
4. Analyze transactions with `scripts/review_rewards.py`. Supply only runtime-obtained data; never place a customer’s IDs, transaction IDs, or expected results into this package.
5. Explain results in dollars and points. For a clear mismatch, state the recorded amount, the policy calculation, and why it differs. For travel/software records without confirmed processing coding, describe the result as a potential discrepancy rather than promising an adjustment. State that exclusions remain standard-rate purchases.
6. If the customer wants review of a specific transaction, first confirm the transaction ID belongs to their verified account. Then provide the customer the discoverable tool named `submit_cash_back_dispute_0589` with arguments containing their own `user_id` and that specific `transaction_id`. The customer, not the agent, initiates this tool. Do not submit the dispute on the customer’s behalf.
7. Tell the customer that review can check merchant coding, the applicable reward rate, promotion eligibility, and any adjustment. Supporting receipts or billing confirmation may help, but do not request card numbers or other unnecessary sensitive data.

## Calculating the expected reward

For each completed transaction:

1. Establish whether the account opened within the offer window and whether the transaction falls during its first six months. If either is not established, do not apply the multiplier.
2. Determine the base rate: 1% for an exclusion or non-bonus category; 10% only for confirmed qualifying travel/software processing.
3. Apply the 2x multiplier only when the promotional conditions are met.
4. Convert cash back to stored points: `amount × rate × 100`; round to the nearest whole point using half-up rounding.
5. Compare the calculated points with recorded points. A rate cannot be confirmed from a generic category label alone, so these records should be reviewed as conditional unless merchant coding is independently confirmed.

## Script interface

Run:

```sh
python3 scripts/review_rewards.py < review_input.json
```

The script reads one JSON object from standard input and writes one JSON object to standard output.

Required input fields:

- `account_open_date`: ISO date string.
- `review_date`: ISO date string for the review.
- `transactions`: list of objects with `transaction_id`, `merchant_name`, `transaction_amount`, `transaction_date`, `category`, `status`, and either `rewards_earned` or `reward_points`.

Optional input fields:

- `promo`: object with `start_date`, `end_date`, and `months` (default 6). Set `enabled` false to disable it.
- `merchant_category_confirmed`: boolean per transaction. Set true only when the processing/coding is actually confirmed.
- `excluded_merchants`: replacement or additional exclusion merchant names. The script includes the documented exclusions by default.

Output contains a per-transaction assessment, expected points where determinable, the promotion status, and a `review_candidates` list. `confirmed_mismatch` requires a confirmed coding basis; `conditional_mismatch` means coding must be reviewed before concluding that rewards were short. `consistent` does not guarantee a later adjustment is impossible.

## Validation and interpretation

Before relying on output, ensure every reviewed record has a valid ISO date, nonnegative monetary amount, integer point total, and `COMPLETED` status. The script returns input errors rather than silently inventing values. Manually verify that the card product and account-opening date belong to the verified customer. Confirm any merchant coding through available records or the subsequent dispute review before representing a conditional finding as a definite error.

If the customer only asks a general question, explain the rates, coding requirement, exclusions, and promotion timing without retrieving or disclosing account-specific information.