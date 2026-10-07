---
name: rewards-statement-investigator
description: Investigate whether posted cash-back rewards on Silver Rewards Card or Business Silver Rewards Card purchases match the documented rate, merchant exclusions, and Business Silver promotional period. Use for a customer asking why reward earnings look incorrect.
---

# Rewards Statement Investigator

Use this Skill to perform a transparent, transaction-level rewards review. It distinguishes the similarly named consumer and business cards, converts database `points` to cash-back dollars, and identifies postings whose recorded points do not match the documented expected rate.

## Product rules encoded by the analyzer

- **Silver Rewards Card:** 4% on transactions categorized as Travel or Software; 1% otherwise. The qualifying rate depends on the merchant category submitted at posting.
- **Business Silver Rewards Card:** 10% on eligible Travel or Software transactions; 1% otherwise.
- Business Silver exclusions receive the 1% standard rate even when categorized as Travel or Software: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight.
- A Business Silver account opened during the offer dates (2024-11-14 through 2025-11-14) receives double its otherwise applicable rate for its first six calendar months. Exclusions remain exclusions, so their standard 1% rate is doubled during that window.
- Database points on these cash-back cards equal cash back at **100 points per dollar** (1 point = $0.01).
- The analyzer treats Travel and Software category labels as evidence of eligibility, but a real statement's merchant coding controls. If the category is absent, unclear, or does not match the claimed service, do not assert that a bonus rate is owed; recommend a category review with receipt/invoice.

## Workflow

1. Identify the account(s), card type, account-open date, and relevant posted transactions. Keep the Business Silver and Silver records separate.
2. Supply normalized data to `scripts/analyze_rewards.py`. The script only analyzes records; it cannot modify rewards, open disputes, or contact the bank.
3. Review `findings`:
   - `match` means the posted points agree with the expected amount after normal whole-point rounding.
   - `mismatch` identifies an apparent under- or over-credit and reports expected, posted, and difference points.
   - `unreviewable` means needed information is missing or the transaction is not a completed purchase.
4. Explain the result in plain language. State the applicable card, rate, promotion status, exception status, and point/dollar conversion. Do not imply a transaction is definitely eligible when merchant classification is uncertain.
5. For apparent mismatches, offer to submit the normal rewards-review/dispute process if an appropriate banking tool and authorization are available. Keep receipts and invoices. Do not claim an adjustment was made unless the declared banking tool confirms it.
6. If the customer asks about only one charge, focus the response on that charge but disclose any material account/card distinction needed to prevent confusion.

## Identity and privacy

Only retrieve account data through declared tools and according to the applicable authentication procedure. A name lookup alone is not confirmation of identity. If policy requires identity verification for the requested account action, obtain the required customer-confirmed fields and log verification only after successful verification. An informational calculation does not itself change an account.

## Script interface

Run:

```text
python3 scripts/analyze_rewards.py < input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "accounts": [
    {"account_id": "optional", "card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {
      "transaction_id": "optional", "account_id": "optional",
      "credit_card_type": "Business Silver Rewards Card",
      "merchant_name": "merchant", "transaction_amount": "12.34",
      "transaction_date": "YYYY-MM-DD", "category": "Travel",
      "status": "COMPLETED", "rewards_earned": 123
    }
  ]
}
```

`transaction_amount` may also be a JSON number or a dollar-formatted string. `rewards_earned` may be a number or a string such as `"123 points"`. Account matching uses `account_id` when provided; otherwise it requires exactly one supplied account of the transaction's card type.

Output contains a per-transaction `findings` list and aggregate totals. Validate that every relevant completed transaction appears once, that its account mapping is not `unreviewable`, and that the number of mismatches in `summary.mismatch_count` matches the findings before communicating results.

## Customer-response outline

- Acknowledge the concern and identify which card was reviewed.
- Explain that points on this cash-back card represent cents (100 points = $1.00).
- For each relevant apparent mismatch: name the merchant/date, documented expected rate and points, posted points, and difference. Explain whether a six-month business promotion or named exclusion was applied.
- For matching exceptions, explain why the standard rate applies rather than describing it as an error.
- If a merchant-code question remains, say that rewards are based on the posted merchant category and offer a review with supporting documentation.
