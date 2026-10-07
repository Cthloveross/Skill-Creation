---
name: credit-card-rewards-audit
description: Audit posted Business Bronze Rewards Card and EcoCard purchase rewards against documented earning rates, exclusions, qualification signals, and whole-point truncation. Use when a customer asks whether transaction rewards were calculated correctly.
---

# Credit Card Rewards Audit

Use this Skill to produce a transparent, transaction-level rewards review. It is read-only: it identifies discrepancies but does not alter an account, issue credits, or assume a correction tool exists.

## Applicable policy

* **Business Bronze Rewards Card:** eligible purchases earn 1.0% cash back. Database rewards are stored as points, where one point represents one cent, so the expected points for an eligible dollar purchase are `floor(amount)`. WeWork, Regus, Industrious, Gusto, ADP, Paychex, and Rippling earn zero. Slack, Zoom, HubSpot, and Salesforce earn zero only after the first 12 months of a subscription; subscription age is required to audit those merchants.
* **EcoCard:** qualifying green purchases earn 5 points per dollar; other purchases earn 1 point per dollar. Target, Walmart, Amazon, and ThredUp always earn the standard rate. Tesla Supercharger, ChargePoint, and EVgo qualify for the green rate for EV charging. A transaction explicitly categorized as a qualifying green category may be treated as green; do not infer certification from a merchant name alone.
* All rewards calculations truncate fractional points down to a whole point.
* Returns and credits reverse rewards at the original rate. This Skill does not recompute negative/return transactions without the original purchase and its original rate.

## Workflow

1. Obtain the account holder's identifying lookup input and use the normal banking read-only tools to locate the customer, card accounts, and transaction history. Do not expose unnecessary personal data in the response.
2. Review posted/completed transactions only. Transcribe the relevant transaction fields into structured JSON: `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `category`, `status`, and `rewards_earned`.
3. Run `scripts/audit_rewards.py`. Supply subscription age when auditing one of the four time-limited Business Bronze SaaS merchants. Supply only categories that the transaction system or applicable records explicitly establish as qualifying green categories; the default recognizes the exact category `Green`.
4. Treat `discrepancy` results as calculation mismatches and `needs_context` results as not auditable from the available evidence. Explain the rate, floor calculation, expected points, posted points, and difference for each discrepancy. Confirm transactions that are correct when helpful.
5. Do not call an account-changing tool merely because the audit finds a mismatch. If an authorized rewards-adjustment process/tool is available in the current environment, follow its stated prerequisites. Otherwise tell the customer that the identified item needs a rewards correction review.

## Running the helper

The script reads one JSON object from standard input and emits one JSON object to standard output:

```sh
python3 scripts/audit_rewards.py <<'JSON'
{"transactions": [...], "eco_qualifying_categories": ["Green"], "eco_certified_merchants": [], "subscription_months_by_merchant": {}}
JSON
```

Input fields:

* `transactions` is a required list of transaction objects. Amounts may be JSON numbers or currency strings. `rewards_earned` may be a number or a string ending in `points`.
* `eco_qualifying_categories` is optional and defaults to `["Green"]`. Only provide labels known to represent qualified green purchases.
* `eco_certified_merchants` is an optional list of additional explicitly confirmed green partners.
* `subscription_months_by_merchant` optionally maps normalized merchant names to subscription age in months. A transaction-level `subscription_age_months` takes precedence.

Output includes each audit result, aggregate expected and posted points for auditable completed transactions, discrepancies, and records needing additional context. `delta_points` is `expected_points - posted_points`; a positive value means the posted reward is short.

## Validation

Before relying on a result, confirm that:

* every reviewed posted transaction has a valid amount, card type, and recorded rewards value;
* all known exclusions override category labels;
* each claimed EcoCard green rate has an explicit qualifying category, confirmed partner, or named certified charging network; and
* expected values use whole-point floor truncation, not conventional rounding.

Unknown card types, malformed records, non-completed transactions, negative amounts, and time-limited SaaS transactions with missing subscription age are deliberately reported rather than guessed.