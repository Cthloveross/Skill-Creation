---
name: credit-card-rewards-audit
description: Perform a verified, read-only audit of credit-card transaction rewards under the documented EcoCard and Crypto-Cash Back rules; distinguish confirmed discrepancies from missing eligibility evidence and route a customer-requested, transaction-specific cash-back dispute to the customer-operated tool.
---

# Credit-card rewards audit

Use this Skill when a customer asks whether credit-card cash back or transaction rewards were calculated correctly. It does not change rewards, redeem points, or submit a dispute.

## Secure workflow

1. Ask for the account name or email solely to locate the customer record. Do not disclose the lookup result yet.
2. Ask the customer to confirm **two** of date of birth, email, phone number, or address. Compare both values to the located record. Do not ask for card number, CVV, password, or other unnecessary sensitive data.
3. After two fields match, obtain the current time and call `log_verification` with the full retrieved customer record and timestamp. Only then disclose or discuss account-specific information.
4. Retrieve the verified customer’s credit-card accounts and transaction history with the declared normal banking tools. Preserve the transaction ID, card type, merchant, amount, date, category, status, recorded points, and any authoritative eligibility/green-qualification evidence.
5. Limit calculation to `COMPLETED` transactions. Do not invent a replacement award for refunds, reversals, disputes, pending records, cash equivalents, bill payments, or other nonstandard activity. An EcoCard refund reverses points at its original rate.

## Rules available for the audit

- Database reward values are points. For cash-back cards, including the named cash-back card types, 1 point is **$0.01** as a statement credit or checking-account credit. EcoCard sustainability points also have that redemption value.
- Truncate every calculated award down to a whole point; never round to nearest.
- **Crypto-Cash Back:** an *eligible purchase* earns 2 points per dollar (2.0%). The 1.25% fee applies to a crypto redemption, not reward earning. Do not assume that a transaction is eligible without authoritative transaction evidence.
- **EcoCard:** qualifying green purchases earn 5 points per dollar; other purchases earn 1 point per dollar. Target, Walmart, Amazon, and ThredUp always receive the standard rate. Tesla Supercharger, ChargePoint, and EVgo are documented qualifying EV networks. A generic `Green` category or sustainable branding alone does not prove current green qualification; use a directory/badge, receipt, or authoritative merchant/transaction evidence. A known non-green category or explicit non-qualification supports the standard rate.
- No per-transaction earning schedules are available here for other card types. Their stored points can be valued at $0.01 each, but their expected awards must be `unsupported_terms` rather than guessed.

## Run and interpret the auditor

Normalize tool records into the script schema and run:

```text
python scripts/audit_rewards.py < input.json
```

The script reads one JSON object from standard input and writes one JSON object to standard output:

```json
{
  "transactions": [{
    "transaction_id": "string",
    "card_type": "string",
    "merchant_name": "string",
    "transaction_amount": "decimal string or number",
    "transaction_date": "optional display date",
    "rewards_earned": 0,
    "status": "COMPLETED",
    "category": "optional string",
    "eligible": true,
    "green_qualified": true
  }]
}
```

`eligible` and `green_qualified` are optional. Include either only if established by authoritative records or supplied evidence; omission means unknown. The program uses decimal arithmetic and returns `items` plus a count by finding type. It rejects malformed, duplicate, negative, or incomplete calculation records rather than silently guessing. Confirm each transaction ID is unique, amounts are nonnegative, recorded points are nonnegative integers, and status is present before relying on a result.

Interpret findings as follows:

- `match`: the recorded award agrees with a fully documented rate.
- `deterministic_discrepancy`: explain the transaction date/merchant, governing rate, truncation, recorded and expected points, point difference, and dollar difference. This is the only type that establishes an error.
- `conditional`: give the conditional calculation, identify exactly what eligibility/qualification fact is missing, and do **not** call it an error.
- `unsupported_terms`: say a review was performed but the available terms do not establish that card/status’s expected earning rate.
- `input_error`: correct or obtain the missing record data before presenting an audit conclusion.

When no `deterministic_discrepancy` exists, say precisely that no established discrepancy was found; do not claim every reward is correct. Mention conditional and unsupported items that prevent a definitive conclusion.

## Disputes

A `deterministic_discrepancy` establishes an audit error, but the customer-operated dispute process can also review a **suspected** discrepancy. When a customer believes a specific completed purchase received the wrong cash back and asks to dispute it, confirm its transaction ID and make the customer-operated tool available with `give_discoverable_user_tool`:

```text
submit_cash_back_dispute_0589(user_id, transaction_id)
```

Confirm the transaction ID first. Do not invoke the dispute on the customer’s behalf and do not collect sensitive card details. After successful identity verification, the customer may be told their own user ID and the confirmed transaction ID if needed to operate the provided tool. If the customer reports that the user-operated tool is unavailable, provide it again with the same confirmed identifiers, but do not execute it. Explain when the audit remains conditional and that supporting category or qualification context may be requested during review; do not falsely represent the suspected issue as established. If no specific transaction is identified, ask the customer to identify one before making the tool available.
