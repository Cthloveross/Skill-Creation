---
name: credit-card-rewards-audit
description: Audit posted credit-card transaction rewards for a customer who reports incorrect cash back or EcoCard sustainability points. Use this for a read-only review that compares recorded points with applicable per-transaction earn rules and identifies discrepancies or eligibility questions; do not use it to post a correction or redeem rewards.
---

# Credit-card rewards audit

Use this workflow to investigate reported rewards discrepancies across cash-back cards and the EcoCard. It produces a transparent, transaction-level comparison without taking a financial action.

## Safety and access prerequisites

Before reviewing or disclosing customer-specific account or transaction information, verify customer identity and authority under the available banking procedure. For any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Use only records returned by the authorized banking tools for the identified customer. Do not infer ownership from a name alone when the runtime requires stronger verification. This Skill is read-only: do not redeem points, change an account, or claim an adjustment was made. If a correction is needed but no authorized correction process/tool is available, explain the finding and route it through the supported dispute or specialist process.

## Rules applied

1. Audit only posted/completed purchase transactions. Set aside pending, reversed, refunded, disputed, missing, or non-positive transactions for manual review unless the system explicitly supplies their reward-reversal rule.
2. Compute each transaction separately, never from a statement total.
3. Rewards points are always whole points: truncate fractional calculated points downward.
4. For a configured cash-back card, points equal `floor(purchase_amount × cash_back_rate_percent)`. This works because one stored point represents $0.01 of cash back. For example, a 2.5% rate earns 2.5 points per dollar.
5. For EcoCard, qualifying green purchases earn 5 points per dollar; other purchases earn 1 point per dollar. The expected result is again truncated per transaction.
6. EcoCard exclusions override a Green category: Target, Walmart, Amazon, and ThredUp earn the standard rate. EV charging earns the green rate only on Tesla Supercharger, ChargePoint, or EVgo. Do not treat a merchant as eligible merely because its name sounds sustainable.
7. A transaction explicitly marked `green_qualified: true` is green, and `false` is standard. If that flag is unavailable, this Skill may use a system-provided `category: "Green"` as a conditional classification, clearly label it as inferred, and ask for merchant eligibility confirmation for a disputed result. A transaction lacking either source is `needs_eligibility_review`, not a calculated discrepancy.

## Input preparation

Obtain the customer’s authorized card accounts and transaction history from the runtime. Convert tool records to the JSON schema accepted by `scripts/audit_rewards.py`; do not place customer data in this package.

The script reads one JSON object from standard input and writes one JSON report to standard output:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "card_type": "Gold Rewards Card",
      "merchant_name": "string",
      "amount": "12.34",
      "category": "Green",
      "status": "COMPLETED",
      "rewards_earned": 30,
      "green_qualified": true
    }
  ],
  "cash_back_rate_percent": {
    "Gold Rewards Card": "2.5"
  }
}
```

`amount` may also be named `transaction_amount`; dollar signs and commas are accepted. `rewards_earned` may be a number or a string such as `"30 points"`. `green_qualified` is optional and must be a JSON boolean when supplied. Cash-back rates must be supplied for every non-EcoCard card being audited; the Skill does not invent rates for other products.

Run it through the packaged script runtime, or equivalently:

```sh
python3 scripts/audit_rewards.py < audit_input.json
```

## Interpret the report

- `match`: recorded and calculated points agree.
- `mismatch`: `point_difference` is `recorded - expected`; a negative value means fewer points were recorded than expected, conditional on the stated eligibility source.
- `needs_eligibility_review`: green eligibility was unavailable, so do not call it an error.
- `unsupported_card`: provide the product’s documented rate before auditing it.
- `not_a_posted_purchase` or `invalid_transaction`: exclude it from discrepancy totals and investigate separately.

Review every `mismatch` with its `eligibility_source`, merchant, amount, recorded points, expected points, and truncation policy. Explain stored-point value accurately: for cash-back cards, one point is $0.01 when redeemed as a statement credit or eligible checking credit; EcoCard sustainability points also redeem at $0.01 per point. Do not promise a particular redemption option, adjustment, or monetary value without checking its eligibility and minimum requirements.

The report’s `summary` totals include only rows with a calculated expected value and are an audit aid, not an account adjustment. For an inferred Green classification or a merchant eligibility dispute, obtain receipt/merchant evidence or refer for review rather than changing the rate based on guesswork.

## Validation checklist

Before communicating the result, confirm that:

- all included rows belong to the verified customer and are completed purchases;
- every cash-back card has an explicit rate in the input;
- each expected value was calculated per transaction and truncated down;
- EcoCard exclusions and EV-network conditions were applied before a Green-category inference;
- rows with unknown eligibility were described as review items, not discrepancies; and
- no rewards redemption or account change was performed.
