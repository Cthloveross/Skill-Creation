---
name: credit-card-rewards-audit
description: Audit supplied credit-card transactions against documented Diamond Elite, Business Platinum, Business Silver, and EcoCard reward rules. Use when a customer or internal reviewer needs a transaction-level explanation of rewards that appear too high or too low. Produces deterministic expected-point calculations and discrepancy summaries without making account changes.
---

# Credit-card rewards audit

Use this Skill to calculate the documented rewards for every supplied transaction, compare them with recorded `rewards_earned`, and explain only supported discrepancies.

## Privacy and access prerequisite

An account name lookup or a statement that the customer owns the account is not identity verification. Before disclosing an account-specific audit to a live customer, obtain confirmation of any two of date of birth, email, phone number, and address; then call `log_verification` with all required fields and the current timestamp. Do not log a verification merely because account data was retrieved.

The calculator is read-only. It does not change points, file a dispute, or invoke banking tools. If a correction is desired after the audit, follow the runtime's authorized rewards-correction process; do not infer or invent an adjustment tool.

## Method

1. Obtain the customer's authorized transaction list and, when promotions may matter, their card accounts and account-opening dates.
2. Convert the records to the JSON schema below. Preserve the recorded merchant, category, status, amount, card type, transaction ID, date, and reward value exactly.
3. Run `scripts/audit_rewards.py`. It loads the documented rules from `references/rewards_rules.json`, applies the relevant merchant exceptions, then truncates points **for each transaction**.
4. Review `input_issues` and `skipped_transactions` before relying on totals. Unknown card types, missing numeric fields, and non-final statuses are intentionally not silently treated as correct.
5. Present the `discrepancies` list. A positive `point_delta` means the recorded amount is too low; a negative value means it is too high. State expected and recorded points, the applicable rate/reason, and the transaction identifier for each discrepancy. The result includes all reviewed transactions, so the audit covers both matching and mismatching records.

## Rule interpretation implemented

- Database rewards are points. One point has a redemption value of $0.01 for the covered cash-back cards and EcoCard.
- Diamond Elite earns 5 points per purchase dollar (5% cash back).
- Business Platinum earns 4 points per dollar for Travel, Software, and Media and 1.5 points per dollar otherwise. Its documented cash-equivalent, balance-transfer, and fee types earn zero.
- Business Silver earns 10 points per dollar for Travel and Software and 1 point per dollar otherwise. Its named corporate-expense, hardware/electronics, gaming-subscription, and online-learning exceptions use the 1-point rate. The limited double-rewards offer is applied only when an account opening date and transaction date establish that the account opened in the offer window and the transaction is in its first six months.
- EcoCard earns 5 points per dollar for Green/Sustainable transactions and 1 point per dollar otherwise. Target, Amazon, and ThredUp are standard-rate exceptions even if categorized Green. Tesla Supercharger, ChargePoint, and EVgo are recognized EV charging partners; an identified charging merchant outside that list receives the standard rate.
- All point calculations are `floor(amount × points-per-dollar)` per transaction, not rounded to nearest and not rounded only after aggregation.

The transaction category is used as supplied. A category alone cannot prove an unobserved merchant-category-code dispute or an unrecognized green merchant; flag such concerns for manual review rather than changing a rate based on assumptions.

## Script interface

Run:

```text
python scripts/audit_rewards.py < input.json
```

Input is one JSON object:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Diamond Elite Card | Business Platinum Rewards Card | Business Silver Rewards Card | EcoCard",
      "merchant_name": "string",
      "transaction_amount": "$123.45 or 123.45",
      "transaction_date": "MM/DD/YYYY or YYYY-MM-DD",
      "category": "Travel",
      "status": "COMPLETED or POSTED",
      "rewards_earned": "123 points or 123",
      "account_id": "optional"
    }
  ],
  "accounts": [
    {
      "account_id": "optional string",
      "card_type": "string",
      "date_of_account_open": "MM/DD/YYYY or YYYY-MM-DD"
    }
  ]
}
```

`accounts` is optional except for evaluating the Business Silver promotion. If one account of a card type is supplied, it is associated with that card type; where multiple such accounts exist, provide `account_id` on the transaction. Optional transaction fields `is_reward_eligible: false` and `transaction_type` can explicitly mark non-earning Business Platinum transactions.

The script emits one JSON object with `summary`, `reviewed_transactions`, `discrepancies`, `skipped_transactions`, and `input_issues`. `expected_points` and `recorded_points` are per-transaction values; `point_delta = expected - recorded`.

## Validation checklist

Before communicating results, ensure that the number in `summary.reviewed_count` plus `summary.skipped_count` equals the supplied transaction count, every discrepancy has a transaction ID and rate reason, and each expected amount is an integer produced by per-purchase truncation. Do not reconcile an account's current reward balance to only this extract unless the extract is known to contain the entire account history and all adjustments/redemptions.
