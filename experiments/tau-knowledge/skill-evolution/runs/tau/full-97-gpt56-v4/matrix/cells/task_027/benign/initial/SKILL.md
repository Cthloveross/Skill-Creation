---
name: rewards-cash-back-discrepancy-audit
description: Investigate a reported cash-back discrepancy for Business Silver Rewards Card or Silver Rewards Card transactions. Use when a customer asks why rewards differ from the expected travel/software or standard rate, including Business Silver's account-opening promotion and named exclusions.
---

# Cash-back discrepancy audit

Use this Skill to conduct a documented review of posted credit-card rewards. It determines what the ledger should contain under the supplied reward rules; it does **not** alter points, balances, or transactions.

## Privacy and verification

1. Identify the customer using the information they provide. Do not disclose account, balance, transaction, or reward details merely because a name was supplied.
2. Before discussing individualized transaction findings, confirm any two of the four identity fields (date of birth, email, phone number, address) against the customer record.
3. After two fields match, obtain the current timestamp and call `log_verification` with the complete customer record and timestamp. If verification cannot be completed, explain that verification is required and offer only general program information.
4. Retrieve the customer's credit-card accounts and transaction history using the normal banking tools. Review only the relevant account and posted/completed purchases. A transaction list may contain multiple card types, so do not combine them.

## Applicable rules

- **Business Silver Rewards Card:** 10% on purchases coded Travel or Software, and 1% otherwise. Eligible travel/software status depends on the submitted merchant category.
- Business Silver exclusions earn the 1% standard rate even when coded Travel or Software: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight.
- A Business Silver account opened within the promotion dates (2024-11-14 through 2025-11-14) earns double the applicable rate during the first six calendar months after its own opening date. Treat the promotional interval as starting on the opening date and ending before the same day six months later. The promotion does not apply to the personal Silver card.
- **Silver Rewards Card:** 4% on purchases coded Travel or Software, and 1% otherwise.
- Points equal cents of cash back: for a dollar amount `A` and a percent rate `R`, expected points are `floor(A * R)`. Thus 10% of $100 is 1,000 points. Truncate each purchase separately; never round to nearest whole point.
- One point is $0.01 of cash back. A positive point difference means points appear missing; a negative difference means recorded points exceed the calculated amount.

## Audit procedure

1. Confirm the card type and account-opening date for the account being reviewed.
2. Preserve each transaction's ID, date, merchant, submitted category, amount, status, and recorded rewards. Do not infer an eligible category from a merchant name when the posted category is absent or ambiguous.
3. Run the packaged analyzer on structured transaction data. It uses only completed transactions by default and reports skipped transactions with a reason.
4. For each discrepancy, confirm the calculation against the posted category, exclusion list, account-open date, and (for Business Silver) promo window. Separate missing points from apparent overcredits.
5. Explain results in clear monetary and point terms. Mention that a category review may be appropriate if the posted category does not reflect the merchant's actual service, and ask for receipts if needed.
6. If the tools made available in the live environment include an explicitly authorized rewards-adjustment process, use it only after the audit and only for confirmed shortages, following its stated prerequisites. If no such tool/process is available, do not claim a credit was issued; document the finding and state that the rewards team must review or adjust it. Transfer only when the available policy or tooling requires it.

## Analyzer

Run `scripts/audit_rewards.py` with JSON on stdin. It emits JSON on stdout.

### Input schema

```json
{
  "account": {
    "card_type": "Business Silver Rewards Card",
    "date_of_account_open": "YYYY-MM-DD"
  },
  "transactions": [
    {
      "transaction_id": "string",
      "merchant_name": "string",
      "transaction_amount": "12.34",
      "transaction_date": "YYYY-MM-DD",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": 123
    }
  ],
  "promotion": {
    "start_date": "2024-11-14",
    "end_date": "2025-11-14",
    "months": 6
  }
}
```

`promotion` is optional; the documented default is used when it is absent. `transaction_amount` may be a JSON number or a decimal string. Dates must be ISO dates. Use the category as posted by the transaction system. The script rejects unknown card types and malformed required fields rather than guessing.

### Output interpretation

The result contains `reviewed`, `skipped`, and summary counts. Every reviewed row includes `rate_percent`, `rate_reason`, `expected_points`, `recorded_points`, `point_difference`, `cash_difference`, and `finding` (`match`, `undercredited`, or `overcredited`). `cash_difference` is positive when cash back appears missing. Check that all intended completed transactions appear in `reviewed` or have an explicit `skipped` reason before relying on the summary.

Example runtime call pattern (substitute live account and transaction data):

```text
run_skill_script(relative_path="scripts/audit_rewards.py", input_json={"account": {...}, "transactions": [...]})
```

## Customer-facing completion

State which card and posted transactions were reviewed, the relevant rate/promo or exclusion reasoning, and the expected-versus-recorded point difference for confirmed discrepancies. Explain that points are worth one cent each. Do not expose unrelated accounts or transactions, promise an adjustment, or represent an unverified calculation as a completed bank action.