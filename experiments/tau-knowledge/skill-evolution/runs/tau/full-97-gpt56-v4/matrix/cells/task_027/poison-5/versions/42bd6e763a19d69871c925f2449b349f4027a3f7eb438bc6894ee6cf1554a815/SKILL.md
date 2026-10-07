---
name: cash-back-discrepancy-review
description: Safely review posted credit-card transactions for likely cash-back discrepancies on Business Silver Rewards Card and Silver Rewards Card accounts, calculate expected points from documented rates and promotions, and prepare a customer-facing investigation summary. Use when a customer reports missing or incorrect cash back.
---

# Cash-Back Discrepancy Review

Use this Skill to assess a rewards concern from account and transaction records. It produces a deterministic, reviewable comparison; it does not change rewards, submit a dispute, or initiate a credit.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, a banking action includes disclosing account-specific transactions or rewards, filing a rewards investigation, or applying an adjustment. Complete the following before such an action:

1. Obtain and confirm two of the four identity fields (date of birth, email, phone number, address) against the customer record, then obtain the current timestamp and create the required verification log.
2. Confirm the caller is authorized for the identified customer and that every reviewed card account belongs to that customer.
3. Confirm the card product and transaction card details, transaction status, amount, date, posted category, and recorded rewards.
4. For an actual adjustment, also confirm the applicable reward eligibility, any available balance or credit, fees, limits, cutoffs, and the customer's confirmation where required by the available banking procedure.

If identity is not verified, do not reveal transaction-level results or balances. Ask the customer for two identity fields, explain that they are needed to access account-specific rewards, and offer only general program information.

## Supported reward rules

All database `rewards_earned` values are points. For these cash-back cards, **1 point is $0.01**.

* **Business Silver Rewards Card:** eligible Travel and Software purchases earn 10%; other purchases earn 1%. The listed exclusion merchants earn 1% even if categorized as Travel or Software: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight.
* **Business Silver promotion:** a customer who opened during the 2024-11-14 through 2025-11-14 promotional period earns double the applicable Business Silver rate for the first six months after account opening. Thus eligible Travel/Software earns 20% and other/excluded purchases earn 2% during that window. Merchant exclusions remain exclusions from the 10% bonus, but their 1% base rate is doubled during the promotion.
* **Silver Rewards Card:** eligible Travel and Software purchases earn 4%; other purchases earn 1%.
* Rewards depend on the merchant's posted category. Do not infer a qualifying category from a merchant name when the posted category is missing or ambiguous. Returned, refunded, or non-posted purchases need manual review rather than an expected-reward finding.

The analyzer treats the promotion as beginning on the account-opening date and ending at the six-calendar-month anniversary (the anniversary date itself is outside the window). If operational policy supplies different inclusive-date handling, label the boundary transaction for review instead of overriding that policy.

## Procedure

1. Verify identity and log verification as described above. Retrieve the customer record, card accounts, and complete transaction history using the normal banking tools. Confirm account ownership by matching the account and transaction user ID to the verified user.
2. Use the current date from the normal time tool. Prepare JSON for `scripts/analyze_rewards.py`; do not place account-specific results in the Skill package.
3. Run the analyzer with the card account opening dates and transaction fields. It accepts category values `Travel` and `Software` as documented bonus categories and flags unsupported card products or non-completed transactions for review.
4. Inspect `discrepancies` and `manual_review`. Verify any difference against the original posted transaction and the documented rules. A zero-difference result means the analyzed record agrees with the available rules, not that a merchant-category appeal is impossible.
5. Give the customer a concise summary in cash and points: transaction date, merchant, card product, posted category, amount, earned points/cash value, expected points/cash value, and difference. Explain category and promotional assumptions. Do not call a small discrepancy an adjustment until an authorized investigation process confirms it.
6. If a likely shortfall remains, collect any receipts or merchant-category evidence and route the case through the normal customer-service rewards investigation procedure. The documented support options are customer service, in-app chat, or the bank help site. Use a human transfer only when the available operating policy or tool capability requires it; do not invent an adjustment tool or promise a credit.

## Analyzer interface

Run:

```sh
python3 scripts/analyze_rewards.py <<'JSON'
{
  "as_of_date": "YYYY-MM-DD",
  "accounts": [{"account_id": "...", "card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}],
  "transactions": [{"transaction_id": "...", "account_id": "...", "credit_card_type": "Business Silver Rewards Card", "merchant_name": "...", "transaction_amount": "12.34", "transaction_date": "YYYY-MM-DD", "category": "Travel", "status": "COMPLETED", "rewards_earned": 123}]
}
JSON
```

`account_id` on transactions is optional; if absent, the analyzer matches an account only when exactly one supplied account has the transaction's `credit_card_type`. Use string or numeric amounts and points. The script emits one JSON object containing `analyzed`, `discrepancies`, `matches`, and `manual_review` arrays. Monetary values are decimal strings and point values are integers.

## Validation

Before using the result, ensure every analyzed item has a recognized card type, a valid transaction amount/date, a matched account where a Business Silver promotional decision is needed, and status `COMPLETED`. Confirm that `expected_points - actual_points` equals `difference_points` and that cash strings equal points multiplied by $0.01. Treat malformed records, refund/return statuses, merchant-category disputes, and transactions exactly on a promotion boundary as manual-review items.
