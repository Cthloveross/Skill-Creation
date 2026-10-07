---
name: credit-card-rewards-discrepancy-review
description: Review posted credit-card reward transactions for supported card programs, identify rate/rounding discrepancies or unresolved eligibility questions, and guide a verified customer to the documented cash-back dispute submission tool.
---

# Credit-Card Rewards Discrepancy Review

Use this Skill when a customer believes credit-card rewards or cash back were calculated incorrectly and wants a transaction-level review. It supports a transparent audit of posted transactions; it does not change rewards, submit a dispute on the customer's behalf, or infer missing merchant facts.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and prerequisites

1. Treat account lookup, transaction review, reward disclosure, and dispute initiation as banking actions. Before those actions, verify the customer using **two of four** account fields: date of birth, email, phone number, and address.
2. Use a supplied full name or email only to locate a possible record. Do not treat it as identity verification.
3. Once two fields match the located record, call `get_current_time` and then `log_verification` with the complete record fields and returned timestamp. Do not disclose transaction or balance details until verification is logged.
4. Confirm that the customer owns the identified account and that the transaction belongs to that customer before discussing it. Do not request card numbers, CVVs, or other unnecessary sensitive card details.
5. Obtain or retrieve the relevant transaction IDs. If the customer cannot identify a period, review the available posted history after verification and report only auditable findings. Do not claim an unverified merchant should have received a bonus.

## Review method

1. Retrieve the verified customer's credit-card accounts with `get_credit_card_accounts_by_user`, then retrieve transactions with `get_credit_card_transactions_by_user`.
2. Audit only `COMPLETED`/posted purchase transactions. Pending, refunded, reversed, or non-purchase activity must be labeled out of scope or unresolved because rewards can change or reverse.
3. Run the normalized transaction data through `scripts/audit_rewards.py`. The script produces transaction-level expected points, status, variance, and review notes.
4. Interpret reward units correctly:
   - Database `points` for cash-back cards represent cash back at **100 points per dollar** (one point = $0.01).
   - EcoCard points are sustainability points, but also redeem at $0.01 per point.
   - Every calculation floors fractional points, separately for each purchase. Never round to nearest or aggregate fractional points across transactions.
5. Use only documented rates:
   - **Silver Rewards Card:** 4% (4 points per dollar) for posted `Travel` and `Software` categories; the baseline supported by this audit is 1 point per dollar for other ordinary purchases.
   - **Crypto-Cash Back:** 2% (2 points per dollar) for eligible purchases. Gift cards, person-to-person payments, fees, interest, insurance premiums, and returns/refunds are not eligible. If eligibility is not known from transaction data, label it `needs_eligibility_review`, not an error.
   - **EcoCard:** 5 sustainability points per dollar for a qualifying green purchase and 1 point per dollar otherwise. Treat the categories/merchant evidence supplied at runtime as the basis for qualification. Target, Walmart, Amazon, ThredUp, and nonpartner EV charging earn the standard rate. Only Tesla Supercharger, ChargePoint, and EVgo qualify for the higher EV-charging rate. When the merchant qualification cannot be established, label it `needs_green_qualification`.
6. For a transaction marked `mismatch`, report the posted category, documented expected points, actual points, and shortfall/excess both in points and (where meaningful) dollar value. State that category/eligibility may be reviewed by support. For `needs_*` results, explain what receipt, merchant-of-record, item, or eligibility information would resolve the issue.
7. Do not extrapolate rates for unsupported card types or undocumented promotions. Return `unsupported_card` and explain that a rate source or specialist review is necessary.

## Dispute handoff

If a verified customer wants to dispute a specific cash-back transaction, confirm the exact transaction ID and provide the customer this user-executed tool:

`submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

Use `give_discoverable_user_tool` with `discoverable_tool_name` set to `submit_cash_back_dispute_0589` and JSON arguments containing the verified user's own `user_id` and the confirmed `transaction_id`. Tell the customer that support may later request receipts or the basis for the category expectation. Do not call this tool as the agent and do not submit speculative disputes where no transaction ID is confirmed.

If no mismatch is determinable, explain the calculations and any unresolved classification facts. If the customer demands a human review after the available audit, transfer using the applicable supported transfer reason.

## Script interface

Run:

```sh
python3 scripts/audit_rewards.py <<'JSON'
{"transactions":[{"transaction_id":"...","credit_card_type":"Silver Rewards Card","merchant_name":"...","transaction_amount":"123.45","category":"Travel","status":"COMPLETED","rewards_earned":493}]}
JSON
```

Input is a JSON object with a `transactions` list. Each transaction needs `transaction_id`, `credit_card_type`, `transaction_amount`, `category`, `status`, and `rewards_earned`; `merchant_name` is optional but needed for EcoCard exclusions. Amounts may be JSON numbers or decimal strings. Output is JSON containing `results` and a `summary` count by result status.

Validate the output before using it: every input transaction must yield exactly one result; `expected_points` must be an integer or null; a `mismatch` must have integer `variance_points = expected_points - actual_points`; and any unverified eligibility must be reported as a `needs_*` status rather than as a mismatch.
