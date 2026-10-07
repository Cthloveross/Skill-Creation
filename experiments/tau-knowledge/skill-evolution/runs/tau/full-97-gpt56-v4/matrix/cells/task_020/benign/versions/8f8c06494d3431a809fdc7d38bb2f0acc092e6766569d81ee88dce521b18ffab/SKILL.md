---
name: rewards-statement-investigator
description: Investigate whether posted cash-back rewards on Silver Rewards Card or Business Silver Rewards Card purchases match the documented rate, merchant exclusions, and Business Silver promotional period. Use for a customer asking why reward earnings look incorrect.
---

# Rewards Statement Investigator

Use this Skill to perform a transparent, transaction-level rewards review. It distinguishes the similarly named consumer and business cards, converts database `points` to cash-back dollars, and identifies postings whose recorded points do not match the documented expected rate.

## Product rules encoded by the analyzer

- **Silver Rewards Card:** 4% on transactions categorized as Travel or Software; 1% otherwise. Gift cards, person-to-person payments, bank fees, interest, and bank-charged insurance premiums do not qualify. Returned or refunded purchases reverse rewards when the credit posts. The qualifying rate depends on the merchant category submitted at posting.
- **Business Silver Rewards Card:** 10% on eligible Travel or Software transactions; 1% otherwise.
- Business Silver named-merchant exclusions receive the 1% standard rate even when categorized as Travel or Software: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. The merchant must be that listed merchant (or its named service), not merely contain a similar word.
- A Business Silver account opened during the offer dates (2024-11-14 through 2025-11-14) receives double its otherwise applicable rate from opening through the matching calendar date six months later. The published offer end controls whether the account opening qualifies, not the end of that customer’s six-month window. Exclusions remain exclusions, so their standard 1% rate is doubled during that window.
- Database points on these cash-back cards equal cash back at **100 points per dollar** (1 point = $0.01).
- The analyzer treats Travel and Software category labels as evidence of eligibility, but a real statement's merchant coding controls. If the category is absent, unclear, or does not match the claimed service, do not assert that a bonus rate is owed; recommend a category review with receipt/invoice.

## Workflow

1. Identify the account(s), card type, account-open date, and relevant posted transactions. Keep the Business Silver and Silver records separate.
2. Supply normalized data to `scripts/analyze_rewards.py`. The script only analyzes records; it cannot modify rewards, open disputes, or contact the bank.
3. Review `findings`:
   - `match` means the posted points agree with the expected amount after normal whole-point rounding.
   - `mismatch` identifies an apparent under- or over-credit and reports expected, posted, and difference points and cash-back dollars.
   - `unreviewable` means needed information is missing or the transaction is not a completed purchase.
4. Explain the result in plain language. State the applicable card, rate, promotion status, exception status, and point/dollar conversion. Do not imply a transaction is definitely eligible when merchant classification is uncertain.
5. For apparent mismatches, keep receipts and invoices and offer the normal rewards review. If the customer asks to have a review or correction submitted, treat that as an account action: obtain the required customer-confirmed identity fields, verify two of the four fields (date of birth, email, phone, address), then log verification with the current timestamp. Use a declared rewards-review tool only when one exists and is authorized. If no such tool is declared, transfer to the specialized department with the verified request and transaction details; do not claim an adjustment was made.
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

`date_of_account_open` and `transaction_date` accept either `YYYY-MM-DD` or the `MM/DD/YYYY` dates commonly returned by the banking tools. `transaction_amount` may also be a JSON number or a dollar-formatted string. `rewards_earned` may be a number or a string such as `"123 points"`. A missing posted category is unreviewable rather than assumed to be standard-rate. For the consumer Silver card, an unequivocal posted category of gift card, person-to-person/P2P, fee, interest, or insurance premium is analyzed at 0%; other categories are analyzed at the documented standard rate unless they are Travel, Software, or SaaS. Account matching uses `account_id` when provided; otherwise it requires exactly one supplied account of the transaction's card type.

Output contains a per-transaction `findings` list and aggregate totals. Validate that every relevant completed transaction appears once, that its account mapping is not `unreviewable`, and that the number of mismatches in `summary.mismatch_count` matches the findings before communicating results.

## Customer-response outline

- Acknowledge the concern and identify which card was reviewed.
- Explain that points on this cash-back card represent cents (100 points = $1.00).
- For each relevant apparent mismatch: name the merchant/date, documented expected rate and points, posted points, and difference. Explain whether a six-month business promotion or named exclusion was applied.
- For matching exceptions, explain why the standard rate applies rather than describing it as an error.
- If a merchant-code question remains, say that rewards are based on the posted merchant category and offer a review with supporting documentation.
