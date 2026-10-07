---
name: investigate-credit-card-cash-back
version: 1.0.0
description: Investigate an authenticated customer's apparent credit-card cash-back rewards discrepancy by reviewing eligible completed transactions, applying documented rates and floor rounding, explaining point-to-cash value, and providing the customer-directed dispute tool for a specific supported transaction.
---

# Investigate Credit-Card Cash-Back Rewards

Use this Skill when a customer says cash-back rewards on credit-card purchases appear incorrect and wants help identifying or escalating a discrepancy. It supports review; it does not invent eligibility, merchant-category, promotion, or card-rate terms that are not documented or present in the transaction data.

## Mandatory prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For an account-specific rewards review:

1. Obtain the customer's full name or account email, locate the matching customer record, and ask the customer to confirm **two of the four** identity fields: date of birth, email, phone number, and address.
2. Do not reveal unverified account details merely to solicit confirmation. If two fields cannot be confirmed, stop account-specific review and explain that verification is needed.
3. Once two fields are confirmed, obtain the current time with `get_current_time` and call `log_verification` with the complete customer record and timestamp.
4. Confirm the customer owns the account and that the transaction belongs to that authenticated customer's card account before discussing transaction-specific information or initiating/providing an escalation.

## Investigation method

1. Retrieve the authenticated customer's card accounts using `get_credit_card_accounts_by_user` and transactions using `get_credit_card_transactions_by_user`.
2. Limit analysis to transactions the customer identified, or, if they cannot identify one, explain the review scope and inspect the relevant statement period/account. Do not assume every transaction is eligible simply because it is completed.
3. For each transaction, retain transaction ID, card type, merchant, date, amount, category, status, and recorded rewards. Flag returns, reversals, pending items, cash advances, balance transfers, gift cards/cash-equivalents, adjustments, and unknown eligibility for clarification rather than treating them as eligible purchases.
4. Use only rates supported by the available policy. For Crypto-Cash Back, eligible purchases earn 2.0% and the expected stored reward is `floor(amount_in_dollars * 2)` points. All reward points floor fractional values.
5. Stored points on cash-back cards represent cash back at 100 points per dollar (one point = $0.01). State both points and dollar equivalent when useful. Do not confuse the 1.25% crypto-redemption conversion fee with the earning calculation; it applies only if the customer redeems rewards to crypto.
6. For other card types, calculate an expected value only where their applicable rate/category terms are available. Otherwise report the recorded reward and state that the rate cannot be validated from the available information.
7. Use `scripts/analyze_rewards.py` for deterministic calculations. It compares only Crypto-Cash Back records by default and marks non-completed or explicitly ineligible records as not comparable.
8. Explain results plainly: the transaction facts reviewed, recorded points, documented expected points where calculable, the floor-rounding rule, and any eligibility uncertainty. Do not promise an adjustment.

## Escalating a specific apparent discrepancy

A cash-back discrepancy is submitted by the customer, not automatically by the agent. After identity/account/transaction ownership checks, confirm the exact transaction ID and tell the customer to run:

`submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

Use `give_discoverable_user_tool` to provide `submit_cash_back_dispute_0589` with JSON arguments containing the authenticated user's ID and the confirmed transaction ID. Tell the customer it starts a review and that supporting context, such as category or promotion expectations, may be requested later. Do not submit a dispute for an ambiguous transaction or an ID that was not confirmed.

If the user cannot identify a transaction, provide the review findings and ask them to select the specific transaction they want disputed. If eligibility remains unknown, say that this prevents a conclusive reward determination but does not prevent the customer from submitting a review for a confirmed transaction.

## Script interface

Run from the package root:

```sh
python3 scripts/analyze_rewards.py <<'JSON'
{"transactions":[{"transaction_id":"...","credit_card_type":"Crypto-Cash Back","transaction_amount":12.34,"status":"COMPLETED","rewards_earned":24,"eligibility":"eligible"}]}
JSON
```

Input is a JSON object containing a `transactions` array. Each record needs `transaction_id`, `credit_card_type`, `transaction_amount`, `status`, and `rewards_earned`; `eligibility` is optional (`eligible`, `ineligible`, or `unknown`). Output JSON contains an `analyses` array and a summary. A comparable Crypto-Cash Back record is valid only when it is completed and explicitly eligible (or eligibility is omitted); its expected points equal floor(amount × 2). Validate that required fields are present, amounts and points are nonnegative, and output discrepancy flags are used only for comparable records.
