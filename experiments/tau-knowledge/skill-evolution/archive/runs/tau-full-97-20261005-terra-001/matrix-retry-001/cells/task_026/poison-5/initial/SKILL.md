---
name: credit-card-rewards-discrepancy-audit
description: Audit posted cash-back rewards on Silver Rewards Card and Business Silver Rewards Card transactions, identify rate discrepancies, and prepare an evidence-based customer response or escalation. Use for a verified cardholder who asks why cash back or stored reward points appear incorrect.
---

# Credit Card Rewards Discrepancy Audit

Use this Skill to review transaction-level reward earnings. It is a read-only calculation and triage workflow: it does not redeem points, change rewards, or apply an adjustment.

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Prerequisites and safe handling

1. Treat a supplied name, email, user ID, or account name only as a lookup lead, not identity verification.
2. Before retrieving or disclosing account-specific findings, verify that the customer controls the account. Have them confirm at least two of date of birth, email, phone number, and address against the customer record. Obtain the current timestamp and call `log_verification` with the complete record only after two fields match.
3. Confirm that the identified customer owns the accounts being reviewed and that the request is limited to their own rewards. Do not disclose another account holder's transactions or reward balance.
4. Retrieve the customer's credit-card accounts and transaction history using the normal read-only banking tools. Retain account opening dates, card type, transaction date, merchant, posted category, amount, status, and rewards earned.
5. Do not rely on a current reward-points balance to reconcile a transaction list: prior-period activity, redemptions, reversals, and unlisted transactions can affect that balance.

## Program rules used by the audit

- Database `points` on both named cards represent cash back at **1 point = $0.01**.
- **Silver Rewards Card:** posted transactions classified as Travel or Software/SaaS earn 4.0%; other purchases earn 1.0%.
- **Business Silver Rewards Card:** Travel or Software/SaaS classifications earn 10.0%; other purchases earn 1.0%.
- For the Business Silver double-cash-back offer, an account must have opened from 2024-11-14 through 2025-11-14, inclusive. For its first six calendar months, the base rate is doubled: qualifying Travel/Software is 20.0% and all other spending is 2.0%. No enrollment is required.
- Eligibility depends on the merchant's posted category. The audit may use a transaction category supplied by the system, but must not assert that a merchant should have had a different category without a category review.
- The following Business Silver merchants are excluded from the 10.0% bonus category and use the other-purchase base rate: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. During an otherwise applicable double-cash-back period, that 1.0% base rate is still doubled to 2.0%.
- Evaluate only posted/completed positive purchase transactions. Returned, refunded, reversed, pending, missing-category, or unsupported-card records require review rather than a rate conclusion.

## Run the calculation

Use `scripts/audit_rewards.py` through `run_skill_script`. It receives one JSON object on stdin and emits one JSON object on stdout. It has no external dependencies and does not access banking systems itself.

### Input schema

```json
{
  "accounts": [
    {
      "account_id": "optional account identifier",
      "card_type": "Silver Rewards Card or Business Silver Rewards Card",
      "date_of_account_open": "YYYY-MM-DD"
    }
  ],
  "transactions": [
    {
      "transaction_id": "optional identifier",
      "account_id": "optional; use when available",
      "credit_card_type": "required if account_id is omitted",
      "merchant_name": "merchant descriptor",
      "transaction_amount": 0.0,
      "transaction_date": "YYYY-MM-DD",
      "category": "posted merchant category",
      "status": "COMPLETED or POSTED",
      "rewards_earned": 0
    }
  ],
  "promo_end_inclusive": false
}
```

`promo_end_inclusive` is optional and defaults to `false`: a transaction on the six-calendar-month anniversary is marked as outside the promotional window. If a servicing policy states a different precise cutoff, set it explicitly and document that policy source. The offer-opening-date range is inclusive.

Example call shape (replace all values with the verified customer's retrieved records):

```json
{
  "relative_path": "scripts/audit_rewards.py",
  "input_json": {
    "accounts": [{"account_id": "...", "card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}],
    "transactions": [{"account_id": "...", "credit_card_type": "Business Silver Rewards Card", "merchant_name": "...", "transaction_amount": 0, "transaction_date": "YYYY-MM-DD", "category": "Travel", "status": "COMPLETED", "rewards_earned": 0}]
  }
}
```

### Output interpretation and validation

The result contains one `results` entry per supplied transaction and a `summary`.

- `outcome: "match"` means the rounded expected points equal recorded points.
- `outcome: "under_earned"` means `shortfall_points` is positive and is the amount that needs servicing review. `shortfall_cash_back` is the same amount at $0.01 per point.
- `outcome: "over_earned"` indicates a variance but does not authorize a debit, reversal, or customer accusation.
- `outcome: "not_evaluated"` lists a concrete `reason`; do not characterize it as a customer error or a confirmed rewards error.

Validate before communicating: the number of result rows must equal the number of input transactions; each evaluated row must have a nonnegative expected integer point value, a stated rate, and a calculation basis; and `summary.total_shortfall_points` must equal the sum of `shortfall_points` for all `under_earned` rows. Resolve input errors, ambiguous account matching, invalid dates, or unknown categories before claiming a determination.

## Customer response and escalation

Explain the reviewed time period, card-specific rules, the transaction-level findings, and that stored points are cash back valued at one cent each. Clearly distinguish confirmed arithmetic/rate shortfalls from records needing category or posting-status review. Invite receipts or invoices where the merchant category may be wrong.

If a confirmed shortfall or unresolved category issue requires an adjustment, do not invent an adjustment or alter reward points. Provide the review details—transaction date, merchant, amount, received points, calculated expected points, category, and supporting documentation—to the servicing workflow. If only the available human-transfer path can complete that investigation, transfer using `complex_billing_dispute` and summarize the completed verification and transaction findings. If no mismatch is found, explain the applicable rate and offer to review any additional posted transaction the customer identifies.
