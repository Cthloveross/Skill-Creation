---
name: credit-card-cashback-discrepancy-audit
description: Securely investigate reported cash-back discrepancies on Silver Rewards Card and Business Silver Rewards Card accounts, calculate supported expected earnings from posted transaction data, and identify transactions requiring review or adjustment.
---

# Credit-Card Cash-Back Discrepancy Audit

Use this Skill when a cardholder reports missing, incorrect, or unclear cash-back earnings on a Silver Rewards Card or Business Silver Rewards Card. It supports a read-only investigation and produces a transaction-level calculation. It does not itself post rewards adjustments, change accounts, or expose account data before verification.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required prerequisites and scope

1. **Identity:** Do not inspect or disclose card accounts, transactions, balances, or rewards until the customer independently confirms at least two of the following account fields: date of birth, email, phone number, or address. A name is only a lookup locator, not one of the two verification fields.
2. **Audit record:** After the two fields match the account record, obtain the current time and call `log_verification` with the complete account identity record and the timestamp.
3. **Authority and ownership:** Retrieve credit-card accounts for the verified user and confirm that each investigated account belongs to that user and is one of the card products they asked to review. Do not investigate an unrequested account.
4. **Applicability:** This procedure is read-only. Balance/credit availability, fees, limits, cutoffs, recipients, and payment confirmations do not apply to calculating posted rewards. If an adjustment, redemption, payment, dispute, or account change is later requested, separately verify all prerequisites applicable to that action before proceeding.
5. **Status:** Audit completed transactions only. Pending, reversed, refunded, disputed, or otherwise non-completed transactions require manual review rather than an expected-reward calculation.

If verification cannot be completed, explain that account-specific investigation must wait until the customer can provide two verification fields. Do not use a retrieved address, email, phone number, or date of birth as though the customer supplied it.

## Investigation workflow

1. Ask what transaction(s), statement period, card, expected reward, and received reward are at issue if the customer knows them. A broad recent-activity review may be performed after verification and ownership confirmation.
2. Verify identity as above, record the verification, then use `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user` for the verified user ID.
3. Send the account opening dates and transaction records to `scripts/reward_audit.py`. Use the current date only to report whether a promotional period is already over; each transaction’s own date controls its calculation.
4. Review the script output:
   - `confirmed_mismatch` means the expected points can be derived from supplied terms and differ from recorded points.
   - `matches_expected` means the recorded points agree after whole-point rounding.
   - `indeterminate` means available terms do not establish a required rate or the record cannot be safely classified; do not call it an error.
   - `manual_review` means transaction status or required input prevents an automated conclusion.
5. Explain that database “points” on cash-back cards are cash back at **1 point = $0.01**. State the expected, recorded, and difference in points and dollars for each confirmed discrepancy.
6. Explain category and merchant-exclusion reasoning in plain language. A merchant category controls the bonus rate; a merchant name alone cannot override a supplied category.
7. If internal tooling explicitly documented for a rewards correction is available, follow that tooling’s prerequisites and confirmation requirements before using it. Otherwise, document the confirmed discrepancy and direct the customer to customer service for a rewards investigation; do not invent an adjustment tool or claim a correction was posted.

## Supported reward rules

### Business Silver Rewards Card

- Standard rate: 10.0% on eligible **Travel** and **Software** categories; 1.0% on other categories.
- The following merchants are excluded from the 10.0% bonus and use the standard rate: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight.
- A customer who opened the account during 2024-11-14 through 2025-11-14 receives double cash back for the first six months after account opening: 20.0% on otherwise eligible Travel/Software purchases and 2.0% on all other purchases. The script treats the six-month anniversary as the first non-promotional day.
- Eligible Travel and Software status requires the supplied transaction category to be Travel or Software and, for online transactions, depends on the merchant/authorized platform being categorized that way. The audit cannot establish an unrecorded merchant classification.

### Silver Rewards Card

- The available terms establish 4.0% for eligible posted Travel and Software transactions.
- The available terms do **not** establish a numeric standard rate for non-Travel/non-Software purchases. Mark those transactions `indeterminate`, not incorrect, unless an applicable card term supplies the base rate.
- Gift cards, person-to-person payments, fees, interest, insurance premiums, returns, and refunds are not automated bonus-earning determinations. Treat them as manual review when apparent from the supplied data.

## Script interface

Run with JSON on standard input and read JSON from standard output:

```json
{
  "accounts": [
    {"account_id": "...", "card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {"transaction_id": "...", "credit_card_type": "Business Silver Rewards Card", "merchant_name": "...", "transaction_amount": 0.0, "transaction_date": "YYYY-MM-DD", "category": "Travel", "status": "COMPLETED", "rewards_earned": 0}
  ],
  "as_of_date": "YYYY-MM-DD"
}
```

`accounts` and `transactions` must be arrays. Amounts may be JSON numbers or currency-formatted strings. `rewards_earned` is a whole-point quantity. The output contains `transactions`, `summary`, and `input_errors`. It uses Decimal arithmetic and rounds calculated rewards to the nearest whole point using half-up rounding.

Example invocation in a compatible runtime:

```sh
python3 scripts/reward_audit.py < audit_input.json
```

## Validation before communicating results

- Confirm every output transaction ID came from the retrieved verified user’s transaction history.
- Confirm each calculated Business Silver promotion decision uses both account opening date and transaction date.
- Confirm exclusions override Travel/Software category bonus treatment.
- Confirm Silver non-bonus transactions remain indeterminate unless a sourced base rate is supplied.
- Confirm dollar values equal points multiplied by $0.01 and that no adjustment is represented as completed without a successful documented banking action.
- Do not disclose unrelated transactions or account balances in the final customer response.
