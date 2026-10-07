---
name: credit-card-cash-back-review
summary: Verify a cardholder, audit posted cash-back transactions against documented Silver and Business Silver reward rules, identify explainable discrepancies, and route any correction through the required dispute-and-approval workflow.
---

# Credit Card Cash-Back Review

Use this skill when a cardholder reports missing, incorrect, or unclear cash back on a credit-card transaction, or asks for a review of recent rewards activity. It supports the Silver Rewards Card and Business Silver Rewards Card rules documented with this package. It does not authorize an adjustment merely because an audit detects a mismatch.

## Banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Treat account-specific transaction lookup, disclosure, dispute submission, and reward modification as banking activity. Do not rely on a name lookup, a prior conversation claim, or an existing record as identity verification.

## Required inputs

Obtain or retrieve at runtime only after verification:

- The customer’s full name and two confirmations matching two of: date of birth, email, phone number, or address.
- The current timestamp for the verification audit record.
- The customer record, card accounts (including card type and opening date), and relevant transaction history.
- For a targeted review, the transaction identifier(s). For a broad review, use the customer’s posted transactions and clearly state the reviewed period.
- For a correction, an approved cash-back-dispute record identifying the exact transaction(s). An audit result or a customer allegation is not approval.

Do not request or collect full card numbers, CVVs, passwords, or unnecessary sensitive details.

## Workflow

1. **Verify identity and authority.** Ask the customer to provide two identity fields; do not recite values from the customer record. Compare them against the record, confirm the requester is the cardholder or otherwise authorized, obtain the current time, then call `log_verification` with the complete retrieved customer record and timestamp. If verification or authority cannot be established, do not access or discuss account-specific rewards.
2. **Retrieve and scope the review.** Retrieve accounts and transaction history for the verified user. Match every transaction to its account, not solely to a similarly named card type. Review only posted/completed purchases. Returned, refunded, reversed, pending, fee, interest, insurance-premium, gift-card, and person-to-person items require their documented treatment and should not be represented as ordinary bonus-earning purchases.
3. **Calculate independently.** Run `scripts/audit_rewards.py` using runtime account and transaction data. The script calculates only rates established by this skill and labels an item `indeterminate` when essential facts or an applicable non-bonus rate are not supplied. Never use an `expected_rewards` value in a dispute record as the calculation source.
4. **Review classifications.** Confirm the merchant category is the category processed by the merchant; merchant names alone cannot override it. Explain that rewards are stored as points even for cash-back cards, and that 1 point equals $0.01. Distinguish a transaction that is correct, a likely shortfall, an apparent excess, and an indeterminate item. A likely shortfall is a review candidate, not a final entitlement.
5. **Handle a customer-requested dispute.** Confirm the exact transaction ID with the customer. Provide the customer the documented self-service tool `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` through `give_discoverable_user_tool` when available, for one confirmed transaction at a time. Explain that category or promotion documentation may be requested during review. Do not submit it as the agent and do not promise approval.
6. **Apply a correction only after approval.** First locate the customer’s *resolved and approved* dispute record in `cash_back_disputes` and verify its transaction ID, ownership, and approval status. If the runtime does not provide a way to obtain that record, do not unlock or invoke an update tool; retain the audit result and use the available support/escalation path. For each approved transaction, independently recalculate rewards, unlock `update_transaction_rewards_3847`, and call it with the exact `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`, where `X` is a nonnegative whole-number point value. Then retrieve transaction history and confirm the posted value. Retain calculation notes in the internal case record.
7. **Communicate the outcome.** Give a concise transaction-level explanation: posted amount, processed category, applicable rate, expected points/cash value where determinable, recorded points, and next step. Never expose unrelated transaction details or account data.

## Reward rules used by the calculator

### Business Silver Rewards Card

- Eligible travel and software purchases earn **10.0%**; other purchases earn **1.0%**.
- The processed merchant category controls eligibility. Travel and software categories are eligible only when the transaction is actually categorized accordingly.
- The following named merchants are exceptions and earn the standard 1.0% rather than the 10.0% bonus: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. A merchant label that clearly extends one of these names (for example, a product/service suffix) is treated as that exception; ambiguous names must be reviewed manually.
- A qualifying new-account promotion doubles the otherwise applicable rate for the first six months after account opening, provided the account was opened from 2024-11-14 through 2025-11-14. The calculator uses a half-open promotional interval: opening date inclusive through, but not including, the date six calendar months later. If the operational program supplies a different boundary convention, pass it explicitly through `promo_end_inclusive`.

### Silver Rewards Card

- Eligible transactions processed in travel or software/SaaS categories earn **4.0%** after posting.
- Gift cards, person-to-person payments, bank fees, interest, insurance premiums, and returned/refunded purchases do not qualify for the enhanced rate; credits reverse applicable rewards.
- The supplied rules do not state the ordinary/non-bonus rate. The calculator intentionally marks non-travel/non-software Silver transactions as indeterminate unless the runtime supplies an authorized `silver_other_rate_percent`. Do not infer a rate from prior transaction outcomes.

### Points and rounding

For these cash-back cards, database “points” represent cash back at 1 point = $0.01. Therefore points equal the cash-back dollar amount divided by $0.01. Calculate from the transaction amount and rate, then round to a whole point using decimal `ROUND_HALF_UP`. Do not calculate from displayed account reward balances.

## Calculator

Run from the package root:

```sh
python scripts/audit_rewards.py < audit_input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "accounts": [
    {"account_id": "string", "card_type": "Business Silver Rewards Card|Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {
      "transaction_id": "string",
      "account_id": "string (preferred)",
      "credit_card_type": "string (used only if uniquely matched)",
      "merchant_name": "string",
      "transaction_amount": "decimal amount",
      "transaction_date": "YYYY-MM-DD",
      "category": "Travel|Software|...",
      "status": "COMPLETED",
      "rewards_earned": "integer or '<integer> points'"
    }
  ],
  "silver_other_rate_percent": "optional decimal authorized rate",
  "promo_end_inclusive": false
}
```

The output contains `assessments`, one per input transaction, and totals for determinate transactions. Each assessment includes the independent rate, expected whole points when computable, recorded points, point difference, status, and a reason. `shortfall` is a candidate for review; it is not an approved correction. The script emits a structured `error` object for malformed dates, amounts, reward values, missing account matches, or unsupported card types.

Before relying on output, verify that each assessment has the intended account and transaction ID, that its expected points are a nonnegative integer when determinate, and that the totals match the sum of determinate assessment values. Check excluded merchants and promotion boundaries manually when the transaction category or merchant identity is uncertain.

## Failure handling

- If identity, authority, account ownership, card type, posting status, category, date, amount, or recorded rewards are missing or ambiguous, do not claim a final reward calculation. Request the missing non-sensitive information or mark the item for review.
- If a customer only wants an explanation, do not create a dispute or make any update.
- If no approved dispute record exists, do not unlock or call `update_transaction_rewards_3847`.
- If an eligible customer-facing dispute tool cannot be made available due to a runtime failure, explain the limitation and use the normal support/escalation path; do not substitute an unapproved reward update.
