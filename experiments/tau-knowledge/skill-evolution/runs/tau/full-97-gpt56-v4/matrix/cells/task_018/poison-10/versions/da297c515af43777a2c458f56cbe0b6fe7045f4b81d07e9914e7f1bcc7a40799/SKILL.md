---
name: cash-back-reward-discrepancy-review
description: Review a customer's credit-card cash-back rewards for a suspected transaction-level discrepancy, calculate expected whole-point rewards from documented rates, explain findings, and guide the customer to the required self-service dispute submission when appropriate.
---

# Cash-Back Reward Discrepancy Review

Use this Skill when a customer says that cash back for one or more credit-card purchases is missing, lower than expected, or based on an incorrect merchant category. It supports investigation and customer guidance; it does **not** change rewards, submit disputes, or make any bank action automatically.

## Required controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For account-specific investigation, obtain an account lookup identifier (exact account name, email address, or user ID). Confirm identity with two of the four identity fields—date of birth, email, phone number, and address—then log verification using `log_verification` with the complete returned user record and the current timestamp before taking a rewards/dispute action. Do not request or collect full card numbers or other unnecessary sensitive card details.

## Workflow

1. **Establish the scope.** Ask which purchase(s) appear wrong if the customer has not identified them. Request or retrieve the transaction date, merchant, amount, card product, category shown, transaction status, rewards awarded, and transaction ID. Confirm the transaction ID with the customer before offering a dispute tool.
2. **Locate and validate records.** Use normal banking lookup tools only after the applicable identity and ownership checks. Ensure the transaction belongs to the verified user and relevant card, and distinguish pending, reversed, declined, or incomplete records from completed purchases.
3. **Determine the applicable rate from supplied policy.** Do not infer undocumented bonus rates from merchant names. For Crypto-Cash Back, eligible purchases earn 2.0% (equivalent to 2 points per dollar because one cash-back point represents $0.01). Treat `Other` and unclear merchant classifications as possible exclusions or categorization issues requiring review rather than asserting they earn the standard rate.
4. **Calculate expected points per transaction.** Cash-back records may label rewards as “points.” For cash-back cards, convert the cash-back rate to points and truncate fractional points down:
   
   `expected_points = floor(purchase_amount × cash_back_rate / 0.01)`
   
   At a 2.0% rate, this is `floor(purchase_amount × 2)`. Compare expected and awarded points transaction-by-transaction; do not round to nearest point or aggregate purchases before truncation. Use `scripts/analyze_cash_back.py` for deterministic calculations when structured transaction data is available.
5. **Explain the result clearly.** State the displayed category, applicable documented rate, awarded points, expected points, point difference, and dollar equivalent for cash-back cards (1 point = $0.01). Explain that a verified mismatch or a potentially wrong category can be reviewed, while an exact match does not establish a reward shortfall.
6. **Offer the prescribed dispute path when needed.** For a suspected cash-back discrepancy, provide `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` to the customer via `give_discoverable_user_tool`. Tell the customer to run it using their own verified user ID and the confirmed transaction ID. Include only the relevant transaction; do not submit it on the customer's behalf. Advise that review may later request supporting context such as category or promotion expectations.
7. **Handle uncertainty.** If the rate, eligibility, category, transaction status, owner, or transaction ID cannot be established, say what is missing and do not claim an adjustment is due. A categorization concern can still be directed to the customer-service review path once the transaction ID is confirmed.

## Calculator interface

Run:

```sh
python3 scripts/analyze_cash_back.py <<'JSON'
{"cash_back_rate_percent":"2.0","transactions":[{"transaction_id":"...","amount":"12.34","awarded_points":24,"status":"COMPLETED","category":"Dining"}]}
JSON
```

Input is a JSON object containing a decimal `cash_back_rate_percent` and a `transactions` array. Each transaction requires `transaction_id`, `amount`, and `awarded_points`; `status` and `category` are optional. Amounts must be non-negative decimal strings or JSON numbers. The script emits JSON containing each calculation, only completed-transaction mismatches, and validation errors. A record with an unrecognized/non-completed status is reported but not treated as a rewards mismatch.

Validate the output before communicating it: there must be no `errors`; compare the returned transaction IDs to the retrieved records; and verify that each reported mismatch is a completed transaction with the documented rate applicable. The calculator is advisory and cannot establish merchant eligibility, authorize an account action, or submit a dispute.
