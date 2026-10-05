---
name: credit-card-cash-back-audit
version: 1.0.0
description: Review a verified cardholder's completed credit-card transactions for documented cash-back or rewards-point discrepancies, calculate only supported expected rewards with per-transaction flooring, and route possible corrections through the documented customer dispute and approved-resolution process.
---

# Credit-Card Cash-Back Audit

Use this Skill when a cardholder asks to review earned rewards, identify possibly incorrect cash back, or understand a transaction-level reward calculation. It supports a multi-card, date-bounded review and deliberately distinguishes documented calculations from transactions whose eligibility or standard rate is not established by available evidence.

## Controls and prerequisites

**Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.**

Before retrieving or discussing nonpublic account, transaction, or rewards information:

1. Obtain two of the four identity fields: date of birth, email, phone number, and address. A name alone does not verify identity.
2. Locate the asserted customer record using the supplied lookup capability and compare the two customer-provided fields to the record. Do not disclose the record's values to help the customer answer.
3. Confirm the requested cards and transactions belong to the verified `user_id` by checking the returned account and transaction ownership fields.
4. Get the current timestamp and call `log_verification` with the complete record fields and timestamp only after the two-field comparison succeeds.
5. Confirm the request scope (cards, dates, and completed/posted transactions). Do not treat authorizations, refunds, credits, fees, cash equivalents, balance transfers, or transactions outside scope as ordinary eligible purchases.

For any action that changes rewards or submits a dispute, additionally confirm the customer is authorized, the exact transaction identifier and card are correct, the applicable product/rate is supported, any promotion is verified, and the customer has confirmed the requested action. There is no available basis in this Skill to bypass these prerequisites.

## Runtime workflow

1. Retrieve the verified customer's card accounts with `get_credit_card_accounts_by_user` and transactions with `get_credit_card_transactions_by_user`.
2. Filter to the customer-approved date range and `COMPLETED` transactions. Preserve returned transaction IDs, amount, date, merchant, card type, merchant category, status, and recorded reward points.
3. Establish eligibility from the merchant-submitted category and any available transaction/merchant eligibility evidence. Merchant names alone do not override an actual submitted category.
4. Supply the normalized transactions to `scripts/audit_rewards.py`. Include an explicit `green_eligibility` value when available and a documented approved promotion rate only when the promotion applies at the purchase date.
5. Review each result:
   - `match` means the recorded whole points equal a calculation supported by the supplied evidence.
   - `mismatch` means the supported expected whole-point amount differs from the recorded amount; it is a potential discrepancy, not a permission to edit.
   - `insufficient_information` means a required rate, eligible classification, promotion, or refund linkage is missing. Do not infer a rate from the points that happened to be posted.
   - `excluded` means the supplied record identifies a non-earning transaction type.
6. Explain that cash-back-card rewards are stored as points and are redeemable at 1 point = $0.01. EcoCard sustainability points also redeem at $0.01 per point. Report both points and, where helpful, the cash value, without implying a balance change.
7. For a potential underpayment the customer wishes to pursue, provide the documented customer tool `submit_cash_back_dispute_0589` using `give_discoverable_user_tool`. Its arguments must be exactly the verified customer's `user_id` and the selected `transaction_id`. The customer, not the agent, submits this tool.
8. Do **not** update transaction rewards merely because this review finds a mismatch. The internal correction flow applies only after a dispute is resolved and approved. At that later stage, independently recalculate the supported amount, unlock `update_transaction_rewards_3847`, call it with the exact transaction ID and `new_rewards_earned` formatted as `X points`, then re-read transaction history to confirm the update. Retain calculation notes in the authorized internal case record. If no dispute-resolution record or case-record facility is available, stop after documenting the review/dispute route.

## Supported earning rules

Use points per dollar, then floor each transaction separately to a whole number. Never round to nearest, aggregate fractions across transactions, or rely on an `expected_rewards` field in a dispute record.

| Card | Supported documented calculation |
|---|---|
| Business Platinum Rewards Card | 4 points/$ on eligible Travel, Software, and Media purchases; 1.5 points/$ on other eligible purchases. |
| Silver Rewards Card | 4 points/$ on merchant-classified Travel and Software purchases. The supplied policy does not establish its standard rate outside those categories, so such transactions are indeterminate unless a verified term supplies it. |
| Crypto-Cash Back | 2 points/$ on eligible purchases. The crypto redemption fee is not an earning-rate adjustment and must not be applied to purchase rewards. |
| EcoCard | 5 sustainability points/$ for verified qualifying green purchases; 1 point/$ for other eligible purchases. Target, Walmart, Amazon, and ThredUp are standard-rate exceptions. Tesla Supercharger, ChargePoint, and EVgo EV-charging sessions qualify for the high rate. |

Cash equivalents, balance transfers, and fees do not earn rewards. Returns and credits reverse rewards at their original rate, but a standalone refund cannot be independently recalculated unless it is linked to its original purchase. A merchant category or known merchant name can be insufficient for EcoCard green qualification: use explicit qualifying/partner evidence where the classification is uncertain.

## Script interface

Run `scripts/audit_rewards.py` with JSON on stdin. It emits JSON only.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "string",
      "merchant_name": "string",
      "transaction_amount": "decimal or currency string",
      "transaction_date": "YYYY-MM-DD or MM/DD/YYYY",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": "integer or 'integer points'",
      "green_eligibility": "eligible|ineligible|unknown",
      "is_eligible_purchase": true,
      "is_cash_equivalent": false,
      "is_balance_transfer": false,
      "is_fee": false,
      "applicable_points_per_dollar": null
    }
  ],
  "period": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
  "include_statuses": ["COMPLETED"]
}
```

`green_eligibility` is optional and defaults to `unknown`; set it to `eligible` only from available qualifying green-category, green-indicator, or certified-partner evidence. `applicable_points_per_dollar` is optional and may be used only for a documented, verified promotion or product term that applies to that transaction. It overrides the normal computed rate for that transaction. Boolean exclusion fields default to false and `is_eligible_purchase` defaults to true.

Output contains one result per input transaction plus totals and a summary. An expected amount is `null` when the information is insufficient. The script validates required fields, money/point formats, dates, rate values, and range ordering; it returns an `error` JSON object for invalid input.

Example invocation in the executor runtime:

```text
run_skill_script(relative_path="scripts/audit_rewards.py", input_json={"transactions": [...], "period": {"start": "2025-01-01", "end": "2025-01-31"}})
```

Validate the output before communicating it: every in-scope completed transaction must appear once; every calculated `expected_points` must be a nonnegative integer floor of amount × rate; all mismatch transaction IDs must belong to the verified user and approved review scope; and every null expected amount must have a stated reason. Do not claim that an unresolved or indeterminate transaction is incorrect.

## Unsupported or ambiguous cases

Escalate or use the customer dispute path rather than fabricating an answer when the merchant classification, green qualification, transaction status, refund linkage, non-bonus Silver rate, promotion eligibility, transaction ownership, or identity verification cannot be established. If the customer requests a human after the review or a specialized review is needed, use `transfer_to_human_agents` with an accurate summary and the applicable reason.
