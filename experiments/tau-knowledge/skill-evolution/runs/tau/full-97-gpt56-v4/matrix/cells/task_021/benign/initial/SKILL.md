---
name: credit-card-rewards-audit
description: Review posted Business Bronze Rewards Card and EcoCard transactions for reward-point calculation discrepancies, using the documented merchant exceptions, green rate, and floor-rounding rule. Use when a customer asks why recent card rewards or cash back appear incorrect.
---

# Credit-card rewards audit

Use this Skill to produce a transparent, transaction-level rewards review. It calculates the *expected* stored reward points; it does not change rewards, account balances, or transaction records.

## Customer handling and access

1. Identify the account holder from an identifier the customer supplies. Do not expose transaction or account details merely because an email was used as a lookup key.
2. Before discussing account-specific results or taking any account action, confirm two of the four identity fields (date of birth, email, phone, address). After two fields are confirmed, get the current time and call `log_verification` with the complete profile values and timestamp.
3. Retrieve the customer's credit-card accounts and transaction history with the normal banking tools. Limit the review to the relevant customer and the requested/recent period. Treat the tool data as the source for posted amount, status, merchant, displayed rewards, and category.
4. Convert the relevant tool records to the JSON input described below and run `scripts/audit_rewards.py`. Do not invent subscription ages, merchant certification, missing statuses, or points.

## Rules implemented

- Stored points have a redemption value of $0.01 each for both supported cards. Thus Business Bronze's 1.0% cash back is one stored point per eligible dollar.
- All point computations are truncated down to whole points, per transaction.
- **Business Bronze Rewards Card:** eligible purchases earn `floor(amount)` points. WeWork, Regus, Industrious, Gusto, ADP, Paychex, and Rippling earn zero. Slack, Zoom, HubSpot, and Salesforce earn zero only after the first 12 months of that particular subscription; if its age is absent, the result is intentionally `manual_review`, not an assumed error.
- **EcoCard:** qualifying green purchases earn `floor(amount * 5)` points; other purchases earn `floor(amount)` points. Amazon, Target, Walmart, and ThredUp are always standard-rate. Tesla Supercharger, ChargePoint, and EVgo qualify for the green rate. A supplied `green_qualified: true` takes precedence; otherwise, by default a normalized transaction category of `Green` is treated as the system's green qualification. Set `green_category_means_qualified` to `false` when that category is only descriptive and no eligibility flag/directory evidence is available.
- Only completed, positive purchases are automatically audited. Returns, credits, reversals, declined/pending transactions, malformed amounts, unsupported cards, and transactions missing policy-critical facts are reported for manual review. A return must be tied to its original transaction and original earn rate before judging its reversal.

## Run the calculator

The script accepts one JSON object on stdin and emits one JSON object on stdout. It uses only Python's standard library.

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Business Bronze Rewards Card or EcoCard",
      "merchant_name": "string",
      "transaction_amount": "decimal currency amount",
      "status": "COMPLETED",
      "rewards_earned": "integer points",
      "category": "Green",
      "green_qualified": true,
      "subscription_months": 4
    }
  ],
  "green_category_means_qualified": true
}
```

`green_qualified` and `subscription_months` are optional and should be included only if supported by transaction or merchant-directory data. `rewards_earned` may be a number or a string such as `"123 points"`. For example, execute `python3 scripts/audit_rewards.py` and pass the JSON object on standard input.

The output contains:

- `audited_transactions`: completed transactions with policy basis, expected and posted points, point difference (`expected - posted`), cash equivalent, and `match`/`discrepancy` result;
- `manual_review`: transactions that cannot safely be adjudicated and the missing fact or reason;
- `summary`: counts and aggregate expected-versus-posted point difference across auditable records.

Validate that every included completed supported transaction appears exactly once in either `audited_transactions` or `manual_review`, and that each discrepancy has a nonzero `difference_points`. Do not use a current rewards balance to reconcile this limited transaction list, because it may include older activity, redemptions, adjustments, or reversals outside the review period.

## Customer response

After verification, state the reviewed period and distinguish cash-back wording from the database's point representation: one point equals $0.01. For each discrepancy, identify the date/merchant (and transaction ID only if useful), posted points, expected points, point difference, and dollar equivalent. Briefly name the applicable rule and explain floor rounding where relevant. Also say which examined transactions matched and disclose anything placed in manual review.

Do not claim that a reward was corrected or that a merchant is certified without evidence. This Skill has no documented adjustment tool. If the customer asks for a correction after the review, explain that the review found the discrepancy and follow the supported escalation process available in the active environment; do not fabricate a correction or repeat an action whose outcome is unknown.
