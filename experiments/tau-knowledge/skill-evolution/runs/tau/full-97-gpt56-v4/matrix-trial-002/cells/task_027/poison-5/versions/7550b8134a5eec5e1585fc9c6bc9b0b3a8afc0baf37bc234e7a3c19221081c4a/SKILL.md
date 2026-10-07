---
name: business-silver-rewards-audit
description: Audit posted Business Silver Rewards Card or Silver Rewards Card transactions against the documented travel/software rates, Business Silver six-month double-cash-back offer, and merchant exclusions. Use when a customer asks why rewards appear wrong or requests a rewards-statement review.
---

# Business Silver Rewards Audit

Use this Skill to explain a rewards pattern and identify posted transactions whose recorded reward points differ from the documented rate. It is an audit and explanation workflow only: do not promise a correction, adjust rewards, or infer a merchant category that is not present in the transaction record.

## Evidence and assumptions

Read `references/program_rules.md` before interpreting results. The important conversion is **1 recorded point = $0.01 cash back** for these cash-back cards. Thus a cash-back rate of `r%` on a dollar amount earns `amount × r` points. Points are rounded to the nearest whole point using ordinary half-up rounding.

The audit relies on the transaction's recorded category and merchant name. A travel or software-looking merchant is not sufficient if the posted category is not Travel or Software. Returned, refunded, pending, declined, or otherwise non-completed transactions must not be treated as missing rewards.

## Safe support workflow

1. Establish the customer record from the information supplied in the conversation. For a live account-specific discussion, ask the customer to confirm two of date of birth, email, phone number, and address. Compare them to the customer record and, after successful confirmation, call `log_verification` with all required fields and the current timestamp. Do not disclose account-specific details before this check.
2. Retrieve the customer's card accounts and transaction history using the normal read-only banking tools. Obtain the current time if a verification record is needed.
3. Normalize the retrieved data to the JSON schema below and run the audit script. Do not embed a customer name, account ID, transaction ID, or a precomputed audit in this package.
4. Review `unsupported`, `skipped`, and `warnings` before discussing `findings`. A transaction can be audited only when its card type is supported, a transaction date and amount are usable, and (for Business Silver promotional calculation) the relevant account-opening date is unambiguous.
5. Explain the applicable rate in plain language, including whether the Business promotional multiplier applied and whether a named exclusion caused the standard rate. Report points and their dollar equivalent where useful. Frame a nonzero difference as a transaction to review, not as a guaranteed correction.
6. If no discrepancy is found, explain that the statement is consistent with the available posted data and merchant coding. If the customer disputes category coding or asks for a remedy not supported by available tools, explain that the receipt/merchant category may need a rewards review; do not invent an adjustment process or take an unprovided action.

## Script

Run from the package root:

```sh
python3 scripts/audit_rewards.py < input.json
```

The script reads exactly one JSON object from standard input and writes exactly one JSON object to standard output. It uses only the Python standard library.

### Input schema

```json
{
  "accounts": [
    {
      "card_type": "Business Silver Rewards Card or Silver Rewards Card",
      "date_of_account_open": "YYYY-MM-DD"
    }
  ],
  "transactions": [
    {
      "transaction_id": "optional identifier",
      "credit_card_type": "Business Silver Rewards Card or Silver Rewards Card",
      "merchant_name": "merchant shown on transaction",
      "transaction_amount": "decimal dollar amount",
      "transaction_date": "YYYY-MM-DD",
      "category": "Travel, Software, or another posted category",
      "status": "COMPLETED",
      "rewards_earned": "whole recorded points"
    }
  ]
}
```

`amount`, `date`, `merchant`, `card_type`, and `actual_points` are accepted as aliases for the longer transaction field names. A transaction may supply `account_open_date` directly when transaction data can identify the card account. If more than one account with the same card type exists and the transaction has no direct opening date, the script does not guess which promotional window applies.

### Output interpretation and validation

The output contains:

- `findings`: auditable completed transactions, including expected and actual points, rate, cash value, and `difference_points` (`actual - expected`).
- `anomalies`: findings with a nonzero difference. A negative difference is lower than the documented calculation; a positive difference is higher.
- `skipped`: non-completed transactions, which must not be used as evidence of a missing reward.
- `unsupported`: records with unsupported card types or insufficient/ambiguous data.
- `summary`: counts and total point difference over auditable findings.

Before relying on the result, confirm that the number of input transactions equals the sum of `findings`, `skipped`, and `unsupported`; inspect any warnings; and confirm that excluded merchants and non-Travel/Software categories received the standard rate (with the Business promo multiplier only when applicable). Validate monetary meaning by multiplying any point figure by $0.01.

## Customer-facing response structure

Keep the response concise and avoid exposing unnecessary personal data:

1. Confirm that you reviewed the posted transactions and identify the card type(s) reviewed.
2. State the rule: Business Silver normally earns 10% on qualifying Travel/Software and 1% otherwise; consumer Silver earns 4% on qualifying Travel/Software. Mention the Business new-customer double-rate window only when the audit marks it as applied.
3. Explain exclusions and recorded merchant categories relevant to the reviewed transactions.
4. List only the flagged transaction details necessary to understand the issue: merchant, date, posted category, recorded points/cash value, documented expected points/cash value, and the difference.
5. State any limitation, especially missing account linkage, an unposted transaction, or a category-coding question. Do not claim that a review will change rewards.
