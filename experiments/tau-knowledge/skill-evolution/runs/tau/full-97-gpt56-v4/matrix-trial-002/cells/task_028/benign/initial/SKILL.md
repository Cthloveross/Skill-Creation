---
name: credit-card-rewards-audit
version: 1.0.0
description: Audit posted credit-card transaction rewards against documented earn rates, truncation rules, and known category exceptions; use when a customer thinks cash-back or EcoCard rewards are incorrect.
---

# Credit-card rewards audit

Use this Skill to review a customer's posted credit-card rewards transaction by transaction. It identifies calculation discrepancies supported by the account's recorded card type and merchant category, explains points versus cash-back units correctly, and directs the customer to the required self-service dispute tool. It does **not** submit disputes or alter rewards.

## Required runtime data and tools

1. Obtain a customer identifier from an exact full name, email, or user ID supplied by the customer. Use the corresponding normal lookup tool only as needed.
2. Retrieve the customer's credit-card accounts with `get_credit_card_accounts_by_user(user_id)` and transactions with `get_credit_card_transactions_by_user(user_id)`.
3. Supply the resulting transactions as structured JSON to `scripts/reward_audit.py`. Do not embed current customer data, transaction IDs, or results in this package.

The script requires merchant `category` to represent the merchant's submitted category. If the category is absent or unreliable, do not claim an enhanced rate was owed; explain that merchant coding controls eligibility and offer the dispute route if the customer has supporting documentation.

## Calculation rules implemented

* Database rewards are recorded in points. For cash-back cards, one point represents $0.01; thus a percentage rate is converted to points per dollar (for example, 4% is 4 points per dollar). EcoCard points are sustainability points, but its recorded points also redeem at $0.01 per point.
* Round **each transaction's** calculated points down to a whole number. Never round to nearest or aggregate fractions across purchases.
* Audit only positive-amount `COMPLETED` transactions. Pending, declined, reversed, returned/credit, zero/negative, and unknown-status records are listed as skipped because their net/reversal treatment cannot be confirmed from a simple purchase record.
* Documented excluded transaction types do not earn rewards. If an input category explicitly identifies a fee, interest, cash equivalent, balance transfer, person-to-person payment, gift card, or (for Silver) insurance premium, expected points are zero. Do not infer an exclusion merely from a merchant name.
* The supported card rules are:
  * **Crypto-Cash Back:** 2 points per dollar on eligible purchases.
  * **Business Platinum Rewards Card:** 4 points per dollar for `Travel`, `Software`, or `Media`; otherwise 1.5 points per dollar.
  * **Silver Rewards Card:** 4 points per dollar for `Travel` or `Software`; otherwise 1 point per dollar.
  * **EcoCard:** 5 sustainability points per dollar for qualifying `Green` purchases; otherwise 1 point per dollar. Target, Walmart, Amazon, and ThredUp always receive the standard rate. EV charging is enhanced only when the merchant is Tesla Supercharger, ChargePoint, or EVgo; a provided non-partner EV-charging indication receives the standard rate.

For card types outside this documented set, the script marks transactions unsupported rather than guessing a rate. For an EcoCard merchant merely labelled `Green` but not otherwise verifiable, the recorded category is treated as the available eligibility evidence, except for the documented exclusions above.

## Run the auditor

Invoke the packaged script with JSON on stdin, for example:

```json
{
  "transactions": [
    {
      "transaction_id": "transaction identifier from runtime",
      "credit_card_type": "Silver Rewards Card",
      "merchant_name": "merchant from runtime",
      "transaction_amount": "12.34",
      "category": "Software",
      "status": "COMPLETED",
      "rewards_earned": 49
    }
  ]
}
```

Run:

```text
python3 scripts/reward_audit.py < input.json
```

The script emits one JSON object with these fields:

* `audited`: supported, posted purchase records with expected and recorded points.
* `discrepancies`: the subset where `recorded_points != expected_points`, including signed point and dollar-equivalent differences.
* `skipped`: transactions that cannot safely be evaluated and a reason.
* `summary`: counts and aggregate point differences, separately labelled as cash-back-card points and EcoCard sustainability points.
* `input_errors`: malformed records; correct or retrieve them before relying on the report.

A meaningful validation is that every item in `discrepancies` has an integer expected value computed from the displayed rate and transaction amount using floor truncation, and that no skipped record is presented as an error. Review the merchant/category and status shown in each result against the source transaction before discussing it.

## Customer response and dispute handling

1. Tell the customer which posted transactions matched and which did not, showing merchant, date when available, recorded points, expected points, applicable rate/category basis, and the point difference. Do not expose unrelated account details.
2. State that cash-back-card points are worth $0.01 each; describe EcoCard results as sustainability points (also redeemable at $0.01 each). A positive `points_short` means the customer received fewer points than expected; a negative value means more points were recorded than the calculation expects.
3. Explain the relevant caveat: enhanced rates depend on the merchant's submitted category, and credits/returns affect net rewards. Do not promise a correction.
4. For every transaction the customer wants reviewed, provide the required customer-operated tool using `give_discoverable_user_tool` with tool name `submit_cash_back_dispute_0589`. Tell the customer to execute it with their own `user_id` and that specific `transaction_id`; provide the identifiers only for the customer's own transaction. The agent must not unlock or call this dispute tool as an agent action.
5. If there are no supported discrepancies, say that the posted rewards match the documented calculation based on available category data. The customer may still use the same dispute tool if they believe the merchant was misclassified and can provide receipt/category context.

If identity lookup returns no unique customer, request a different permitted identifier rather than auditing another person's records. If transaction data is unavailable or malformed, state that the review could not be completed and request/retrieve the missing data. Transfer only when the normal support policy independently requires it; a routine rewards discrepancy is handled with the customer-operated dispute tool.
