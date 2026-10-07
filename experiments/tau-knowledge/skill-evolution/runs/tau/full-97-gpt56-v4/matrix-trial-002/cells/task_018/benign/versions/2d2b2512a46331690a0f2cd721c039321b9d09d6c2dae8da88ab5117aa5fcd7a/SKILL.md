---
name: credit-card-rewards-audit
description: Audit available credit-card transaction rewards against documented EcoCard and Crypto-Cash Back rules, explain points-to-cash conversion and truncation, identify only supportable discrepancies, and route a confirmed transaction-specific cash-back dispute to the customer-operated tool.
---

# Credit-card rewards audit

Use this Skill when a customer asks whether credit-card cash back or rewards on one or more transactions were calculated correctly. It is designed for a read-only review: it does not change rewards, submit disputes, or redeem points.

## Security and scope

1. Before disclosing account-specific transaction results, verify the customer using two of the four identity fields (date of birth, email, phone number, address) against the customer record. Obtain the current time and call `log_verification` with the complete retrieved record once verification succeeds.
2. Locate the customer by the supplied name or email, then retrieve their credit-card accounts and transactions using the declared normal banking tools.
3. Do not request card numbers, CVV values, passwords, or other unnecessary sensitive details.
4. Treat a `COMPLETED` transaction as reviewable. Do not calculate a replacement award for pending, reversed, refunded, disputed, or otherwise nonstandard records unless the required original transaction and program terms are available. Refunds reverse EcoCard points at the original earn rate.
5. Do not infer eligibility from a customer’s desire for a review. Where merchant qualification or purchase eligibility is unknown, provide a conditional calculation and clearly say that the records do not establish a discrepancy.

## Documented rules this Skill may apply

- Stored rewards values are points. On cash-back cards, one point is $0.01 as a statement credit or checking-account credit. EcoCard sustainability points also redeem at $0.01 per point.
- Always truncate calculated rewards down to a whole point; do not round to nearest.
- Crypto-Cash Back earns 2 points per dollar (2.0%) **on eligible purchases**. The 1.25% crypto conversion fee concerns redemption, not points earned on a purchase.
- EcoCard earns 5 points per dollar on qualifying green purchases and 1 point per dollar on other purchases.
- EcoCard always earns the standard rate at Target, Walmart, Amazon, and ThredUp. Tesla Supercharger, ChargePoint, and EVgo are the documented EV charging networks eligible for the green rate. Other EV charging networks do not receive the higher rate.
- A generic `Green` category, a customer’s description, or a merchant’s sustainability branding is not by itself proof of current certified-partner/green qualification. Check directory/badge or other supplied qualification evidence where available. Green qualification can change.
- The available evidence does not define earning schedules for other cash-back card types. State their point value, but do not assert their expected per-transaction earnings without their applicable terms.

## Procedure

1. Parse the transaction records into the JSON schema accepted by `scripts/audit_rewards.py`. Preserve transaction ID, card type, merchant, amount, status, recorded points, category, and any explicit eligibility or qualification evidence.
2. Run the script. It uses decimal arithmetic and produces deterministic findings, conditional estimates, and unsupported items separately.
3. Review only `deterministic_discrepancy` findings as established reward discrepancies. For each, explain the transaction, applicable documented rate, truncation, recorded points, expected points, difference, and dollar equivalent at $0.01 per point.
4. Explain `conditional` findings without calling them errors. For example, an eligible Crypto-Cash Back purchase would have the listed 2% expectation, but eligibility must be confirmed first; an EcoCard green-rate calculation needs qualification evidence unless it is a documented deterministic case.
5. Explain `unsupported_terms` findings concisely: a review occurred, but the available reward terms do not establish the expected rate for that card or status.
6. If a discrepancy is established and the customer wants to dispute it, provide—not execute—the user-operated tool `submit_cash_back_dispute_0589(user_id, transaction_id)` with that customer’s own ID and the specific reviewed transaction ID. Use `give_discoverable_user_tool` to make it available. Never submit a dispute on the customer’s behalf and never offer it for a merely conditional finding.
7. If there are no established discrepancies, say so precisely rather than claiming every reward is correct. Identify any transactions whose eligibility or green qualification prevents a definitive review.

## Script interface

Run:

```text
python scripts/audit_rewards.py < input.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout. Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "card_type": "string",
      "merchant_name": "string",
      "transaction_amount": "decimal string or number",
      "rewards_earned": "integer",
      "status": "COMPLETED",
      "category": "optional string",
      "eligible": true,
      "green_qualified": true
    }
  ]
}
```

`eligible` is optional and applies to Crypto-Cash Back. `green_qualified` is optional and applies to EcoCard. Supply either field only when it is established by an authoritative transaction/merchant record or customer evidence. Omit it when unknown. The output contains an `items` list and a summary count by finding type.

Validate before relying on the result: every reviewed transaction should have a unique ID, a nonnegative monetary amount, integer recorded points, and an explicit status. The script returns input errors for malformed records rather than silently fabricating a result.
