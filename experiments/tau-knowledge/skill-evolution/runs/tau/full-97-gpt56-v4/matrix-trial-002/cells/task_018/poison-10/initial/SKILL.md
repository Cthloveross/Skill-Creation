---
name: credit-card-rewards-review
description: Review posted credit-card reward transactions against documented earning rules, identify mathematically supported discrepancies, explain assumptions and rounding, and direct a verified customer to the required cash-back-dispute tool for selected transactions. Use for read-only rewards or cash-back discrepancy reviews; do not use it to redeem rewards or change an account.
---

# Credit-Card Rewards Review

Use this Skill to perform a conservative, transaction-level review. It distinguishes confirmed calculation mismatches from cases where eligibility, merchant coding, or terms are not available. It does **not** alter rewards, balances, transactions, or dispute status.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this read-only review:

1. Obtain and verify identity using two of the supported identity fields (date of birth, email, phone number, or address), look up the customer, and call `log_verification` after successful verification. A name alone is not sufficient.
2. Confirm the customer owns the card accounts being reviewed and confirm the requested card scope and transaction period. If the customer requests all cards, state the included card types.
3. Retrieve the card accounts and transaction history only after the above checks. Review posted/completed purchase transactions. Do not treat pending, reversed, refunded, returned, fee, interest, cash-equivalent, gift-card, person-to-person, or otherwise excluded transactions as ordinary eligible purchases.
4. This review does not require a redemption, payment, transfer, account change, or balance movement. Do not take any such action.

If verification, ownership, transaction details, or necessary terms cannot be established, explain the limitation and request the missing information rather than making a definitive finding.

## Supported rules

Use the transaction's submitted category; merchant classification controls category-based earning. Compute every transaction independently and truncate fractional points downward.

- **Silver Rewards Card:** Travel and Software earn 4.0%. The supplied evidence does not establish a default rate for other categories. Therefore, calculate a definitive expectation only for travel/software records (unless a reliable, current card disclosure separately supplies the default rate).
- **Business Platinum Rewards Card:** Travel, Software, and Media earn 4.0%; other eligible purchases earn 1.5%.
- **EcoCard:** Qualifying Green/Sustainable purchases earn 5 points per dollar and other purchases earn 1 point per dollar. Target, Walmart, Amazon, and nonpartner EV charging earn the standard rate. Tesla Supercharger, ChargePoint, and EVgo charging qualify at the enhanced rate. A Green category is treated as evidence of a qualifying green classification unless the transaction identifies an exclusion; if qualification is unclear, mark it for merchant-category review instead of asserting an error.
- **Crypto-Cash Back:** The documented rate is 2.0% on eligible purchases. The available evidence does not define all eligibility/exclusion rules. Calculate the 2.0% comparison only when eligibility is explicitly confirmed; otherwise present it as a potential discrepancy requiring eligibility confirmation.
- One recorded point is worth $0.01 when redeemed as statement credit or checking-account credit for cash-back cards. EcoCard sustainability points also redeem at $0.01 per point. This conversion explains variance in dollars but does not change points calculations.

Do not infer a missing rate from a transaction's prior award. Do not promise that a flagged transaction will be adjusted.

## Analysis procedure

1. Gather records in a structured JSON array using the fields accepted by `scripts/review_rewards.py`.
2. Run the helper once, passing only the requested transactions and any known per-transaction eligibility facts.
3. Validate that the returned `errors` array is empty. If it is not, correct the source fields or explain that the affected record cannot be reviewed.
4. Separate results as follows:
   - `match`: documented calculation matches recorded points.
   - `mismatch`: a documented, applicable rate produces a different whole-point result.
   - `potential_mismatch`: arithmetic differs, but a required fact such as Crypto eligibility is unknown.
   - `indeterminate`: the evidence does not establish the applicable rate or green qualification.
   - `skipped`: record is not a completed posted purchase or has an excluded/reversal status.
5. For each mismatch, show transaction date, merchant, transaction ID, recorded points, expected points, point difference, and dollar equivalent. For potential/indeterminate records, state precisely what must be confirmed (for example merchant category, green eligibility, or Crypto purchase eligibility).
6. Provide totals only for mathematically supported `mismatch` records. Keep potential discrepancies separate; never add them to confirmed totals.
7. Explain that truncation is applied per purchase, not after summing purchases.

## Dispute handling

A review is not a dispute submission. If the verified customer wants to dispute a specific transaction after reviewing the results:

1. Reconfirm the customer owns the relevant account and confirm the exact transaction ID and the customer's intent to submit that individual dispute.
2. Provide the customer-facing tool `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` via `give_discoverable_user_tool`. The customer, not the agent, executes it. Supply the verified customer ID and the confirmed transaction ID only for that specific dispute.
3. Tell the customer that merchant/category or promotion documentation may be requested during review. Do not collect card numbers or sensitive card details.
4. Do not submit, retry, or claim completion of a dispute on the customer's behalf.

If the customer needs a review beyond available terms or a complex billing resolution that cannot be handled by the dispute tool, explain the limitation and use the approved human-transfer process when applicable.

## Helper interface

Run `scripts/review_rewards.py` with JSON on standard input. It emits one JSON object on standard output.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Silver Rewards Card | Business Platinum Rewards Card | EcoCard | Crypto-Cash Back",
      "merchant_name": "string",
      "transaction_amount": "decimal number or currency string",
      "transaction_date": "optional string",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": "whole number or string",
      "crypto_eligible": true,
      "green_qualification": "qualified | excluded | unknown"
    }
  ]
}
```

`crypto_eligible` and `green_qualification` are optional. Do not set them from guesswork. `green_qualification` takes precedence when supplied. The output contains per-transaction expected points, review status, rationale, and separate confirmed and potential summaries.

Example runnable call (using only synthetic placeholders):

```sh
printf '%s' '{"transactions":[{"transaction_id":"example","credit_card_type":"Business Platinum Rewards Card","merchant_name":"Example Travel","transaction_amount":"100.25","category":"Travel","status":"COMPLETED","rewards_earned":401}]}' | python3 scripts/review_rewards.py
```

A valid helper result has an empty `errors` list, exactly one `results` entry per accepted input record, and only integer `expected_points`, `recorded_points`, and `difference_points` values where an expectation is available.
