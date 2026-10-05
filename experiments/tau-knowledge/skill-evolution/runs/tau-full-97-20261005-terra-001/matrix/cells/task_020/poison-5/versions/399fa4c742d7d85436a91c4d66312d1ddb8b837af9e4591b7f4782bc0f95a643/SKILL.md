---
name: credit-card-cash-back-audit
version: 1.0.0
description: Audit posted credit-card transaction rewards against documented Business Silver and Silver Rewards rules, identify possible cash-back underpayments, and route customer-initiated disputes without making premature rewards adjustments.
---

# Credit Card Cash-Back Audit

Use this skill when a customer says credit-card cash back appears incorrect and wants recent transactions reviewed. It calculates rewards independently for each posted purchase, applies known merchant exclusions and promotional dates, and separates review findings from dispute submission or internal correction.

## Safety and prerequisites

Before **any** banking action or disclosure of account-specific activity, verify customer identity, authority, and ownership. Ask the customer to confirm at least two of these four values: date of birth, email address, phone number, and address. Compare the answers with the user record, obtain the current timestamp with `get_current_time`, and then call `log_verification` with the full record and timestamp. A name or user ID alone is not verification.

After verification, use the verified `user_id` to retrieve the customer’s card accounts and transaction history. Confirm the returned accounts belong to that user and that each transaction being reviewed belongs to that user and card type. Do not expose full unrelated account details. A review is read-only; it does not require a balance, payment, recipient, or fee check. Do not change rewards during an initial review.

If verification cannot be completed, explain that account activity cannot be reviewed until it is completed. Do not use a name-based lookup result as authorization.

## Supported reward rules

The packaged calculator includes these supplied rules:

- **Business Silver Rewards Card:** 10% on posted Travel or Software transactions and 1% otherwise. The listed Business Silver merchant exclusions earn the normal 1%, even when their transaction category is Software or Travel.
- **Business Silver promotion:** for an account opened from 2024-11-14 through 2025-11-14, rates are doubled for transactions from the account-open date through the six-month anniversary (the anniversary itself is outside the six-month interval). Thus qualifying bonus purchases earn 20%, and normal/excluded purchases earn 2%, during that interval.
- **Silver Rewards Card:** 4% for posted Travel or Software transactions. The supplied material does not establish its ordinary non-bonus rate, so the calculator labels ordinary-category Silver purchases as `insufficient_policy` unless the executor explicitly supplies a documented `base_rate`.
- Rewards stored as points for these cards represent cash back at 100 points per dollar ($0.01 per point). Points are floored separately for every transaction, not rounded.

Rewards depend on the posted merchant category. The supplied category is used as the merchant classification; do not infer a different category solely from a merchant name. Pending, non-completed, returned, refunded, zero, and negative transactions are not final reward-audit candidates.

## Audit procedure

1. Complete identity verification and ownership checks above.
2. Retrieve card accounts and transaction history for the verified user. Work only with completed purchases for supported card types.
3. Convert the returned records to the JSON schema below and run:

   ```sh
   python3 scripts/audit_rewards.py < audit_input.json
   ```

4. Review `results`:
   - `underpaid` means actual points are lower than independently calculated points.
   - `matches` means points match.
   - `overpaid_or_data_difference` means actual points are higher; do not debit or alter rewards based on this audit.
   - `insufficient_policy` and `not_final` must not be treated as discrepancies.
5. Explain the rate, promotion/exclusion treatment, expected whole points, actual points, and point difference for each underpaid result. State that one point equals one cent for these cash-back cards. Retain the calculation output in the case record if one exists.
6. For each transaction the customer wants disputed, provide the customer-facing tool `submit_cash_back_dispute_0589` through `give_discoverable_user_tool`, with a JSON argument string containing that customer’s verified `user_id` and the exact `transaction_id`. Confirm the transaction ID before giving the tool. The customer, not the agent, initiates the submission.

## Disputes and correction boundary

A suspicious calculation is not approval to update a transaction. Only after a dispute is resolved and approved may an authorized internal workflow correct rewards. Identify the resolved dispute and its exact transaction ID, independently rerun the calculation (never trust an `expected_rewards` field), unlock `update_transaction_rewards_3847`, and call it with `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`. Confirm the resulting transaction history afterward and retain calculation notes. If the dispute has not been resolved, there is no accessible resolved-dispute record, identity/ownership is unverified, the transaction is not final, or the applicable rate is unsupported, do not unlock or call the update tool.

## Calculator input and output

`scripts/audit_rewards.py` reads one JSON object from standard input and emits one JSON object to standard output.

Required input keys:

- `accounts`: array of objects with `card_type` and `date_of_account_open` (`YYYY-MM-DD`).
- `transactions`: array of objects with `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `transaction_date` (`YYYY-MM-DD`), `category`, `status`, and `rewards_earned`. Amounts may be numbers or currency strings; rewards may be integers or strings such as `"123 points"`.

Optional `policies` lets an executor supply additional documented rates. It is keyed by card type and may include `base_rate`, `bonus_categories` (category-to-decimal-rate mapping), and `excluded_merchants`. Do not supply inferred or unsupported rates.

Each output result includes its expected rate and points when determinable, actual points, difference, applicable rule labels, and a status. The top-level `summary` counts each status and provides only underpaid transaction IDs as `dispute_candidates`.

Example input shape (values are intentionally placeholders):

```json
{
  "accounts": [{"card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}],
  "transactions": [{"transaction_id": "transaction-id", "credit_card_type": "Business Silver Rewards Card", "merchant_name": "merchant", "transaction_amount": "$100.00", "transaction_date": "YYYY-MM-DD", "category": "Travel", "status": "COMPLETED", "rewards_earned": "2000 points"}]
}
```

Validate that every audit result has a transaction ID, that amounts/dates parse, that the transaction card type has a matching account, and that only `underpaid` completed transactions are offered for dispute. Treat `errors` or `insufficient_policy` outputs as reasons to obtain missing data or policy, not as a reason to alter rewards.
