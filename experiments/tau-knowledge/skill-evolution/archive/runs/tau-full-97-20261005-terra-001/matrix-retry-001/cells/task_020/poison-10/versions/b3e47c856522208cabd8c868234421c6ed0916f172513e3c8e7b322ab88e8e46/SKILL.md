---
name: cash-back-discrepancy-audit
version: 1.1.0
description: Audit posted Silver Rewards Card and Business Silver Rewards Card transactions against documented cash-back rates, Business Silver promotion timing, and Business Silver merchant exclusions; guide verified customers through dispute submission and approved-dispute corrections.
---

# Cash-Back Discrepancy Audit

Use this Skill when a customer reports missing or incorrect cash back and the relevant card accounts and transaction history can be obtained through the normal banking tools. It supports only **Silver Rewards Card** and **Business Silver Rewards Card** rules documented here. Do not infer rates for other cards.

## Preconditions and privacy

Do not expose transaction details, account balances, account identifiers, or initiate a dispute or adjustment based only on a name or an unverified identifier. Establish that the requester is the account holder or otherwise authorized, then verify any two of date of birth, email, phone number, and address against the user record. Obtain the current time with `get_current_time` and call `log_verification` with the complete retrieved customer record and timestamp after successful verification.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A name alone, an account number alone, or information volunteered without comparison to the record is not two-factor identity verification. If verification cannot be completed, provide only general rate information and ask the customer to return with the needed information.

## Rate rules encoded by this Skill

All calculated values are whole **points**. For these cash-back cards, 1 point equals $0.01 cash back.

- **Silver Rewards Card:** 4.0% for posted Travel and Software transactions; 1.0% for all other categories.
- **Business Silver Rewards Card:** 10.0% for posted Travel and Software transactions; 1.0% otherwise.
- Business Silver excluded merchants earn the standard 1.0% instead of 10.0%: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. A Business Silver promotion can still double that otherwise applicable 1.0% rate.
- Business Silver double-cash-back offer: an account opened from 2024-11-14 through 2025-11-14 qualifies. It doubles the otherwise applicable rate for transactions in the first six calendar months from account opening. The script treats the six-month anniversary as exclusive: a transaction on or after that date is outside the window. If operations defines a different boundary for a particular account, do not silently override it; mark it for review.
- Eligibility is determined by the posted transaction category and applicable exclusion. Transactions that are not posted/completed, are refunded/returned, have unknown category coding, or lack a trustworthy date/amount must be reviewed rather than automatically adjusted.

## Workflow

1. **Verify before account-specific work or any action.** Complete the prerequisite and verification process above. Confirm that each card account belongs to the verified user and that the requester is authorized for it.
2. **Collect authoritative records.** Use `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user`. Retain the card type, account opening date, transaction ID, amount, date, status, category, merchant, and recorded rewards. Obtain transaction/merchant documentation if category coding is disputed.
3. **Normalize observed records.** Supply account opening dates as `YYYY-MM-DD`. Supply transaction dates as either the `MM/DD/YYYY` format returned by the normal transaction-history tool or `YYYY-MM-DD`; the helper explicitly accepts both formats. Put the normalized records into the input schema below and run `scripts/reward_audit.py`. Inspect `discrepancies`, `audited`, and `review_required`.
4. **Explain every result clearly.** For every entry in `discrepancies`, identify its transaction ID and state both the recorded and independently calculated point amounts (and dollar equivalents), including over-credits as well as shortfalls. State how many remaining audited transactions matched exactly. Say that the result is **evidence for review, not an automatic adjustment**. Explain the applicable category rate, promotion, and exclusion where relevant. Do not omit a discrepancy merely because the customer did not initially identify that transaction.
5. **Submit a customer dispute.** For every transaction the verified customer elects to dispute, reconfirm the exact transaction ID and the customer's confirmation to initiate it. Provide `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` to the customer using `give_discoverable_user_tool`, with only that verified user's ID and the selected transaction ID in its JSON arguments. The customer, not the agent, initiates this tool. Do not submit a vague, account-wide dispute. If the customer reports an access problem with a provided action, re-provide that same documented user-operated tool with the same verified user ID and exact transaction ID; do not claim the dispute was submitted.
6. **Correct only an approved dispute.** After resolution, locate the user's resolved and approved cash-back dispute record to obtain the affected transaction ID. Independently rerun the calculation; never rely on an `expected_rewards` field in the dispute record. Reconfirm the mandatory control, the verified user, ownership, exact transaction, approval status, and the final whole-point value. Unlock `update_transaction_rewards_3847`, then call it with `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`. Confirm the updated value in credit-card transaction history and retain the calculation notes in the internal case record. If an approved-dispute lookup, approval, required tool, or post-update confirmation is unavailable, do not attempt a substitute adjustment; escalate through the normal internal process.

Do not use a generic statement credit to replace the approved cash-back correction workflow.

## Script interface

Run with JSON on standard input and receive one JSON object on standard output:

```sh
python3 scripts/reward_audit.py <<'JSON'
{
  "accounts": [
    {"account_id": "...", "card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {
      "transaction_id": "...",
      "account_id": "...",
      "credit_card_type": "Business Silver Rewards Card",
      "merchant_name": "...",
      "transaction_amount": "$123.45",
      "transaction_date": "MM/DD/YYYY",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": "1234 points"
    }
  ]
}
JSON
```

`account_id` is optional only when there is exactly one supplied account for the transaction's card type. Amounts may be JSON numbers or decimal strings, with or without a dollar sign. Transaction dates may be `MM/DD/YYYY` or ISO `YYYY-MM-DD`; account dates use ISO `YYYY-MM-DD`. The script returns `audited`, `discrepancies`, `review_required`, and summary counts. A discrepancy contains the independently calculated whole points, recorded whole points, point delta, dollar delta, applied rate, and explanation. It never performs banking actions.

Validation: before relying on a result, confirm `input_errors` is empty; confirm every transaction expected to be assessed appears in either `audited` or `review_required`; ensure each reported transaction has a matching verified-user transaction record; and manually review all `review_required` records. Confirm that `summary.matching_count` plus `summary.discrepancy_count` equals `summary.audited_count`. For an approved correction, require that the script's `expected_rewards_points` is an integer and format it as `X points` exactly.
