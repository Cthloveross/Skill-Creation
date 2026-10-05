---
name: cash-back-rewards-audit
version: 1.0.0
description: Audit posted Business Silver Rewards Card and Silver Rewards Card transactions for cash-back discrepancies, explain qualifying rates and exclusions, guide a customer to file transaction-specific disputes, and apply corrections only after an approved resolved dispute.
---

# Cash Back Rewards Audit

Use this skill when a customer reports missing, unexpected, or potentially incorrect cash back on one or more posted credit-card transactions. It supports review of the Business Silver Rewards Card and personal Silver Rewards Card policies documented in this package. It does not infer a merchant category from the merchant name when the posted category is absent or questionable.

## Safety and access prerequisites

Before accessing account-specific data, discussing nonpublic transaction details, submitting a dispute, or changing rewards:

1. Verify the customer using **two of four** independent fields: date of birth, email, phone number, and address. Compare supplied values to the customer record, obtain current time, and create the required verification log after successful verification.
2. Confirm the customer is authorized for each card being reviewed and that each account and transaction belongs to the verified user. Do not use a name match alone as identity verification.
3. Confirm the relevant card type, posted transaction status, merchant/category details, account ownership, and applicable promotion eligibility. For an adjustment, also confirm the dispute is resolved and approved, the transaction has not been refunded, and the transaction identifier exactly matches the approved dispute.
4. Never request full card numbers, CVV, passwords, or other unnecessary sensitive data. If verification, authority, ownership, category evidence, or a required tool is unavailable, do not disclose details or make a change; explain what is needed or escalate through the normal support process.

Reading a rewards history can be used to investigate the request after verification. An audit result alone is not authorization to alter rewards.

## Policy used for the audit

Rewards stored in the transaction system are points. For these cash-back cards, **1 point = $0.01** cash back. A purchase amount of `A` dollars at a rate of `R%` earns `floor(A × R)` whole points. Always truncate fractional points; do not round to nearest.

### Personal Silver Rewards Card

* Eligible posted Travel and Software transactions earn 4.0% (4 points per dollar).
* Other eligible purchases earn the standard 1.0% (1 point per dollar).
* The Business Silver promotion does not apply to this personal card.

### Business Silver Rewards Card

* Eligible posted Travel and Software transactions earn 10.0% (10 points per dollar).
* Other eligible purchases earn 1.0% (1 point per dollar).
* The documented new-customer offer doubles both rates for an account opened from 2024-11-14 through 2025-11-14, during its first six months after opening. The calculator treats the six-month anniversary as the end boundary unless an explicit boundary convention is supplied. Flag a transaction exactly on that anniversary for manual policy review if the convention is unknown.
* The following named merchant families receive the standard 1.0% rather than the 10.0% bonus rate: Concur/SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. If the double-cash-back offer is active, their standard rate is doubled to 2.0%.
* Merchant display names are evidence, not conclusive processor/category proof. If a result depends on a merchant-family exclusion or the posted category conflicts with the receipt, label it for category/merchant review rather than treating the display name as definitive.

Gift cards, person-to-person payments, fees, interest, bank-charged insurance premiums, returned purchases, and refunded purchases do not qualify for ordinary bonus treatment; refunds reverse rewards. A transaction that is not posted/completed, lacks a category, has an unsupported card type, or has a return/refund condition must be marked for manual review instead of calculated as a normal purchase.

## Workflow

1. Complete the prerequisites above. Ask which statement period or transactions concern the customer; if they cannot identify them, agree on the available review range before reviewing all available posted transactions for each authorized card.
2. Retrieve the authorized customer’s credit-card accounts and transaction history using the normal banking tools. Preserve the raw posted amount, date, category, status, earned points, card type, and transaction ID. Do not assume that a transaction belongs to a card merely because its type has a similar name.
3. Assemble the retrieved records into the JSON schema below and run `scripts/audit_rewards.py`. The script is deterministic and does not contact a bank or change data.
4. Review only `undercredited` findings as potential missing-cash-back disputes. Explain matches and known exclusion outcomes clearly. Treat `overcredited`, boundary, merchant/category, and unsupported-status findings as internal/manual review items; do not tell a customer they are owed an overcredit.
5. Give the customer a concise list of the affected transaction IDs, dates, merchants, amount, displayed points, independently calculated points, and the reason. Explain that category coding and refunds can change a final result.
6. For each potential undercredit the customer chooses to dispute, provide the customer-facing tool `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` using the verified user ID and that exact transaction ID. The customer must run the tool themselves; do not submit it on their behalf. Confirm the ID before offering it and advise that receipts or category/promotion context may be requested during review.
7. Do **not** update rewards at this stage. Only after a cash-back dispute is resolved and approved, locate the approved dispute/transaction through the supported dispute-history source, independently rerun the calculation (never rely on an `expected_rewards` field), unlock `update_transaction_rewards_3847`, and call it with `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`. Confirm the result in transaction history and retain calculation notes in the internal case record. If the approved dispute, ownership, amount, category, promotion, or tool availability cannot be confirmed, do not update.

## Calculator interface

Run:

```sh
python3 scripts/audit_rewards.py <<'JSON'
{
  "accounts": [
    {
      "account_id": "optional-account-id",
      "card_type": "Business Silver Rewards Card",
      "date_of_account_open": "YYYY-MM-DD"
    }
  ],
  "transactions": [
    {
      "transaction_id": "transaction-id",
      "account_id": "optional-account-id",
      "credit_card_type": "Business Silver Rewards Card",
      "merchant_name": "merchant display name",
      "transaction_amount": "0.00",
      "transaction_date": "YYYY-MM-DD",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": "0 points"
    }
  ],
  "promotion": {
    "offer_start": "2024-11-14",
    "offer_end": "2025-11-14",
    "end_inclusive": false
  }
}
JSON
```

`accounts` and `transactions` are required arrays. A transaction can be mapped by `account_id`; otherwise its card type must identify exactly one supplied account. Amounts may be numeric or decimal strings. `promotion` is optional and defaults to the documented offer dates; supply current, approved policy data if it differs. Set `end_inclusive` only if the governing offer terms explicitly define the exact six-month anniversary as included.

The script emits JSON with a `results` entry per transaction and a `summary`. A calculable result includes `expected_points`, `actual_points`, `finding` (`match`, `undercredited`, or `overcredited`), the applied rate, and explanatory flags. A `manual_review` result has `expected_points: null` and must not be used to make an adjustment. Validate that every requested transaction appears exactly once, all calculated point values are integers, and the summary counts match the result entries.
