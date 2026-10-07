---
name: credit-card-cash-back-audit
version: 1.1.0
description: Review a verified cardholder's completed credit-card transactions over a customer-selected calendar period, calculate only documented and evidenced reward rates with per-transaction flooring, identify supported discrepancies, and route them through the documented dispute and approved-resolution process.
---

# Credit-Card Cash-Back Audit

Use this Skill when a cardholder asks to review earned rewards, identify potentially incorrect cash back, or understand a transaction-level reward calculation. It supports multi-card, date-bounded reviews and separates supported calculations from transactions whose rate or eligibility is not established by the available evidence.

## Controls and prerequisites

**Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.**

Before retrieving or discussing nonpublic account, transaction, or rewards information:

1. Obtain two of the four identity fields: date of birth, email, phone number, and address. A name alone does not verify identity.
2. Locate the asserted customer record using the supplied lookup capability and compare the two customer-provided fields to the record. Do not disclose record values to help the customer answer.
3. Confirm the requested cards and transactions belong to the verified `user_id` using returned account and transaction ownership fields.
4. Get the current timestamp and call `log_verification` with the complete record fields and timestamp only after the two-field comparison succeeds.
5. Confirm the review scope: cards, dates, and that only completed/posted transactions are to be reviewed.

For a request stated as a sequence of calendar months (for example, “September through November”), use the inclusive calendar range beginning on day 1 of the first named month and ending on the final day of the last named month, clipped to the available/current transaction-history date when the final month is still in progress. Do not silently substitute a later statement period or omit earlier requested months. Every in-scope completed transaction must be reported once, including transactions whose result is indeterminate.

For an action that submits a dispute or changes rewards, additionally confirm customer authority, the exact transaction identifier and card, the applicable product/rate, any promotion, and customer confirmation of the requested action. Do not bypass these prerequisites.

## Runtime workflow

1. Retrieve the verified customer's card accounts with `get_credit_card_accounts_by_user` and transactions with `get_credit_card_transactions_by_user`.
2. Filter records to the full customer-approved date range and `COMPLETED` status. Preserve transaction ID, amount, date, merchant, card type, category, status, recorded rewards, and ownership.
3. Build the audit input for **every** in-scope completed record. Do not drop a record because its expected reward cannot be determined.
4. Establish rates only from documented card rules, the merchant-submitted category where relevant, and transaction/merchant eligibility evidence. Never infer a missing rate from the posted points.
5. For EcoCard, a `Green` or `Sustainable` category label alone is not proof of the 5-points-per-dollar rate. Mark it `green_eligibility: "eligible"` only when the available record independently provides a qualifying green indicator, certified-partner confirmation, or documented qualifying green criteria. Use `unknown` when that evidence is absent. The explicitly documented named exceptions may be classified from their documented exception rule. Do not treat a merchant's reputation, name, product type, or category label as partner evidence.
6. Run `scripts/audit_rewards.py` with the normalized records, period, and `include_statuses: ["COMPLETED"]`.
7. Communicate results transaction by transaction or in an unambiguous grouped list that names every indeterminate transaction. The final review must state the complete requested month range, number reviewed, supported matches, supported discrepancies, and pending-evidence/indeterminate cases with their reasons. Specifically, identify missing Silver standard-rate information separately from missing EcoCard green-eligibility evidence.
8. Treat only an `mismatch` with positive `difference_points` as a supported potential underpayment. `insufficient_information` is not a supported discrepancy and must not be described as an expected amount, shortfall, or dispute candidate.
9. For a supported potential underpayment the customer confirms they want to pursue, provide `submit_cash_back_dispute_0589` via `give_discoverable_user_tool`. Its arguments must contain exactly the verified `user_id` and selected `transaction_id`. The customer, not the agent, submits the tool. Do not provide this tool for an eligibility-dependent or otherwise indeterminate calculation.
10. Do **not** update rewards merely because the review finds a mismatch or because the customer reports an approval. Correction requires a verifiable resolved-and-approved dispute record. At that later stage, independently recalculate the supported amount, unlock `update_transaction_rewards_3847`, call it with the exact transaction ID and `new_rewards_earned` formatted as `X points`, re-read transaction history to confirm the update, and retain calculation notes in the authorized internal case record. If the formal resolution record or case-record facility is unavailable, stop after documenting the review/dispute route.

## Supported earning rules

Calculate points per dollar and floor each transaction independently to a whole number. Never round to nearest, aggregate fractions across transactions, or rely on an `expected_rewards` field from a dispute record.

| Card | Supported documented calculation |
|---|---|
| Business Platinum Rewards Card | 4 points/$ on Travel, Software, and Media purchases; 1.5 points/$ on other eligible purchases. |
| Silver Rewards Card | 4 points/$ on merchant-classified Travel and Software purchases. Available terms do not establish a standard rate outside those categories; those purchases are indeterminate unless a verified applicable term is available. |
| Crypto-Cash Back | 2 points/$ on eligible purchases. A crypto redemption fee is not an earning-rate adjustment. |
| EcoCard | 5 sustainability points/$ only for evidenced qualifying green purchases; 1 point/$ for other eligible purchases. Target, Walmart, Amazon, and ThredUp are documented standard-rate exceptions. Tesla Supercharger, ChargePoint, and EVgo EV-charging sessions are documented high-rate exceptions. |

Cash equivalents, balance transfers, and fees do not earn rewards. Returns and credits reverse rewards at their original rate, but a standalone return or credit cannot be independently recalculated without its original-purchase linkage. Cash-back-card rewards stored as points represent cash back at 1 point = $0.01; EcoCard points also redeem at $0.01 per point. Reporting this conversion does not change a balance.

## Script interface

Run `scripts/audit_rewards.py` with JSON on stdin; it writes JSON only to stdout.

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
      "green_eligibility_evidence": "certified_partner|green_indicator|qualifying_criteria|null",
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

`green_eligibility` defaults to `unknown`. Set it to `eligible` only with one of the listed independent evidence values; a category label is not evidence. `applicable_points_per_dollar` may be used only for a documented, verified term or promotion applicable on the purchase date. It overrides the ordinary rate only for that transaction. Exclusion flags default to false; `is_eligible_purchase` defaults to true.

Example executor call:

```text
run_skill_script(relative_path="scripts/audit_rewards.py", input_json={"transactions": [...], "period": {"start": "2025-09-01", "end": "2025-11-30"}, "include_statuses": ["COMPLETED"]})
```

Validate output before communicating it: each in-scope completed record appears once; every calculated `expected_points` is a nonnegative integer floor of amount × rate; every mismatch belongs to the verified user and approved scope; and every null expected amount has a stated reason. Do not claim that an unresolved or indeterminate transaction is incorrect.

## Ambiguous and unsupported cases

Use an indeterminate result, request qualifying evidence, or transfer to a human specialist as appropriate when merchant classification, EcoCard green qualification, transaction status, refund linkage, Silver non-bonus rate, promotion eligibility, ownership, or identity verification cannot be established. If the customer requests a human after review, use `transfer_to_human_agents` with an accurate summary and applicable reason.
