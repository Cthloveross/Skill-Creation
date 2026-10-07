---
name: credit-card-rewards-audit
version: 1.0.0
description: Audit completed Gold Rewards Card and EcoCard purchase rewards from transaction records, applying whole-point truncation and EcoCard green-eligibility exclusions. Use when a customer reports potentially missing cash back/rewards or asks for a transaction-level review.
---

# Credit-card rewards audit

Use this Skill to calculate the expected **stored point** award for each completed transaction and compare it to the recorded `rewards_earned` value. It is intended to identify possible discrepancies; it does not itself submit disputes or alter bank records.

## Required handling and identity checks

1. Follow the service's identity-verification process before disclosing account-specific findings or taking account action. A name is a lookup key, not one of the four verification fields.
2. Confirm two of email, phone number, address, and date of birth against the customer record, obtain the current timestamp, and call `log_verification` with all required fields after successful verification.
3. Retrieve the customer's credit-card accounts and transaction history with the normal banking tools. Retain only the fields needed by the audit: transaction ID, card type, merchant, amount, date, category, status, and recorded rewards.
4. Audit completed transactions individually. Do not try to reconcile an account's current reward-points balance against these transactions: prior history, redemptions, reversals, and pending activity can make that comparison invalid.

If identity cannot be verified, explain that account-specific review requires verification and ask for appropriate verification information. Do not disclose transaction details or take action.

## Calculation rules

- The Gold Rewards Card earns 2.5% cash back on every purchase. Transaction systems store this as points at $0.01 per point, so its expected award is `floor(amount_in_dollars * 2.5)` points.
- EcoCard earns 5 points per dollar on qualifying green purchases and 1 point per dollar otherwise. Its expected award is `floor(amount_in_dollars * 5)` or `floor(amount_in_dollars)`, respectively.
- Every award is truncated downward to a whole number of points. Never round to nearest.
- Treat a transaction category of `Green` as the available transaction-record indication of green eligibility unless a supplied boolean `green_eligible` explicitly says otherwise. Override that indication for known exclusions: Target, Walmart, Amazon, and ThredUp are standard-rate purchases even if an eco-friendly product was bought. EV charging earns the high rate only at Tesla Supercharger, ChargePoint, or EVgo; an identified non-partner charging merchant is standard rate.
- If merchant eligibility cannot be established from the record, do not claim that an unsupported merchant qualifies. Mark it for eligibility review rather than changing it.

## Run the calculator

Use `scripts/audit_rewards.py`. It reads one JSON object from standard input and writes one JSON object to standard output. It uses only Python's standard library.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Gold Rewards Card or EcoCard",
      "merchant_name": "string",
      "transaction_amount": "decimal number or $ string",
      "category": "optional string",
      "status": "COMPLETED",
      "rewards_earned": "whole number or '<number> points'",
      "green_eligible": true
    }
  ]
}
```

`green_eligible` is optional. Supply it only when a reliable merchant/category determination exists; it takes precedence over the category except for documented exclusions. The script accepts numeric amounts as JSON numbers but decimal strings are preferred so that source values are exact.

Example invocation:

```sh
python3 scripts/audit_rewards.py <<'JSON'
{"transactions":[{"transaction_id":"txn-example","credit_card_type":"Gold Rewards Card","merchant_name":"Example Store","transaction_amount":"12.34","category":"Shopping","status":"COMPLETED","rewards_earned":"30 points"}]}
JSON
```

The output contains a record for every input transaction, a `summary`, and a `discrepancies` list. Each auditable record has `expected_points`, `recorded_points`, `difference_points`, an outcome (`match`, `possible_discrepancy`, `skipped`, `needs_eligibility_review`, or `unsupported_card`), and an explanation. A positive `difference_points` means the recorded award is lower than the independently calculated expected award.

## Validate the audit before communicating it

- Confirm the script returned `ok: true` and `summary.input_count` equals the number of records supplied.
- Confirm every relevant completed Gold Rewards Card and EcoCard record has an auditable outcome. Investigate `invalid_record` output rather than silently omitting it.
- Manually spot-check the rate logic: Gold is 2.5 points per dollar; qualifying EcoCard is 5; standard EcoCard is 1; all values are floored.
- Check named EcoCard exclusions and the EV-network rule against merchant names before describing a transaction as a high-rate green purchase.
- State rewards as points and, when useful, clarify that each point is worth $0.01 as statement-credit or checking-account cash value. Do not represent points as cash dollars without the conversion.

## Customer-facing resolution

Explain the transactions that match and the possible discrepancies, including the expected and recorded points and the $0.01-per-point conversion. Be clear that an audit identifies a possible rewards discrepancy, not an automatic approval.

For every transaction the customer wants formally reviewed, provide the documented customer-operated tool `submit_cash_back_dispute_0589` through `give_discoverable_user_tool`, with the customer's own user ID and that exact transaction ID. Do not collect card numbers or submit the dispute internally. If the customer declines or cannot identify which finding to dispute, provide the findings and let them return when ready.

Do **not** use `update_transaction_rewards_3847` based merely on this audit or a customer allegation. That internal update is permitted only after a cash-back dispute has been resolved and approved. When the runtime supplies access to resolved-dispute records, independently recalculate the transaction, unlock the tool, submit `new_rewards_earned` exactly as `"X points"`, and confirm the resulting transaction-history update. Never rely on an `expected_rewards` field from a dispute record.

If a required transaction record, merchant eligibility fact, or resolved-dispute status is unavailable, say what could not be confirmed and avoid an adjustment. Escalate only when the issue actually requires a specialized or complex billing resolution under the available transfer policy.
