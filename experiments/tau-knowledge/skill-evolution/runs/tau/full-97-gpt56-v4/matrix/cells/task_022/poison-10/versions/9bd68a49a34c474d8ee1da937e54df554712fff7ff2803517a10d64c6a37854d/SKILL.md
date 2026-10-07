---
name: credit-card-rewards-audit
description: Audit posted credit-card reward transactions against documented Diamond Elite, Business Platinum, Business Silver, and EcoCard earning rules; identify supported discrepancies while preserving uncertainty where merchant qualification cannot be verified.
---

# Credit-card rewards audit

Use this Skill when a customer asks to review credit-card rewards, identify apparently incorrect reward amounts, or explain the applicable earning rate. It supports a read-only audit and does **not** make reward adjustments, redemptions, or account changes.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safe banking workflow

1. Establish the requester using a supported lookup identifier (full case-sensitive name, email, or user ID). A name lookup locates a record but is not sufficient authentication.
2. Before disclosing transaction details or acting on the audit, obtain the customer's confirmation of at least two of these four fields: date of birth, email, phone number, and address. Do not treat data merely returned from a lookup as customer confirmation.
3. Once two fields match the located record, obtain the current timestamp with `get_current_time`, retrieve the complete record by user ID if necessary, and call `log_verification` with all required record fields and that timestamp. Confirm that the requester is the account owner and is authorized to request the review.
4. Retrieve credit-card accounts with `get_credit_card_accounts_by_user` and transactions with `get_credit_card_transactions_by_user`. Restrict the review to the verified user's transactions. Confirm the product/card type on each transaction before applying a rule.
5. Convert the retrieved transaction records to the structured JSON input described below and run `scripts/audit_rewards.py`.
6. Report every `confirmed` discrepancy with transaction ID, merchant, recorded points, expected points, and point difference. Explain that cash-back-card database points are worth $0.01 per point; EcoCard points are sustainability points and also redeem at $0.01 each. Do not represent points as dollars unless using this conversion.
7. Clearly separate `indeterminate` transactions from confirmed errors. For EcoCard green-category purchases without qualifying proof, request an official merchant-directory result, a receipt/statement green indicator, or support confirmation. Do not infer certification from merchant name, a sustainability claim, or the `Green` category alone.
8. Do not adjust rewards or balances based solely on this audit. If an authorized correction workflow/tool is available in the runtime, first verify its prerequisites and obtain any required confirmation; otherwise document the discrepancy and route through the applicable supported review process. If a needed merchant-directory lookup is unavailable, say so and escalate only through an available, authorized process.

## Earning rules encoded by the helper

All calculations truncate fractional points downward per transaction; never round to nearest.

* **Diamond Elite Card:** 5.0% cash back on eligible purchases, represented as points. Expected points are `floor(amount × 5)`.
* **Business Platinum Rewards Card:** 4.0% on travel, software, and media purchases submitted under qualifying merchant codes; 1.5% otherwise. Expected points are `floor(amount × 4)` or `floor(amount × 1.5)`.
* **Business Silver Rewards Card:** 10.0% on qualifying travel or software purchases; 1.0% otherwise. Expected points are `floor(amount × 10)` or `floor(amount)`. The documented exclusions receive 1.0% even when their category appears qualifying: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. Qualifying travel includes airlines, lodging, car rentals, rideshare/taxi/limousine, passenger rail/bus/ferry, travel-coded parking/tolls, and travel agencies/platforms, when travel-coded.
* **EcoCard:** qualifying green purchases earn 5 sustainability points per dollar; other purchases earn 1 point per dollar. Target, Walmart, Amazon, and ThredUp earn the standard rate even for eco-friendly goods. EV charging earns the high rate only at Tesla Supercharger, ChargePoint, or EVgo. A non-excluded merchant marked `Green` still needs qualifying evidence from the directory, statement/receipt indicator, or support confirmation; it is indeterminate without it. The helper treats supplied non-Green categories as standard-rate records.

Only completed, positive purchase records can be fully recalculated. Pending, reversed, refunded, chargeback, zero/negative, malformed, or unsupported-card records are not silently treated as clean; they are returned as `unsupported` or `indeterminate` for manual review. Do not reconcile an account's aggregate reward balance to the listed transaction history unless the opening balance, redemption history, and all adjustments are available.

## Helper usage

Run the packaged helper with JSON on stdin, for example:

```sh
python3 scripts/audit_rewards.py <<'JSON'
{"transactions":[{"transaction_id":"...","credit_card_type":"Diamond Elite Card","merchant_name":"...","transaction_amount":"123.45","category":"Shopping","status":"COMPLETED","rewards_earned":617}]}
JSON
```

Input schema:

* `transactions` is a JSON array of transaction objects.
* Each object should supply `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `category`, `status`, and `rewards_earned`.
* Amounts may be decimal numbers or currency strings. `rewards_earned` must be an integer or integer-like string.

Output schema:

* `results` has one result per input transaction in the same order.
* `disposition` is `confirmed`, `indeterminate`, or `unsupported`.
* A determinable record includes `expected_points`, `recorded_points`, `difference_points` (`expected - recorded`), `rate`, and `finding` (`correct`, `under_awarded`, or `over_awarded`).
* An uncertain or unsupported record includes an explanatory `reason`; an uncertain EcoCard green record may include `possible_expected_points` for its standard and high-rate alternatives.
* `summary` counts each disposition and confirmed findings.

Validate the output before using it: it must have exactly one result per supplied transaction, each result must retain the input transaction ID, and only `confirmed` records with a nonzero `difference_points` should be presented as identified reward errors. A zero difference is correct only where the rule was determinable.
