---
name: credit-card-rewards-audit
description: Audit posted Business Bronze Rewards Card and EcoCard transactions for reward-calculation discrepancies, applying documented merchant exclusions, green-purchase rules, cash-back point representation, and truncation. Use for an account holder asking why recent rewards or cash back appear incorrect.
---

# Credit Card Rewards Audit

Use this skill to explain whether posted transaction rewards match the published rules. It performs an audit only: it does not alter reward balances, issue credits, redeem rewards, or initiate disputes.

## Safety and prerequisite checks

Before accessing or discussing account-specific information, verify the requester is the account holder using two of the four identity fields (date of birth, email, phone number, address). Do not reveal stored values while asking for verification. After two fields match, obtain the current time and call `log_verification` with the complete returned identity record and timestamp.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. This audit has no monetary action. Do not claim that a rewards correction has been made. If the customer asks for a correction, use only a documented available resolution workflow; otherwise explain that the discrepancy should be reviewed by the appropriate rewards/billing support process.

If identity cannot be verified, provide only general published rewards information and do not disclose transactions, balances, or account-specific conclusions.

## Runtime inputs and information gathering

1. Identify the account holder and retrieve their credit-card accounts and transaction history using the normal banking tools.
2. Restrict the review to posted/completed transactions for the relevant card. Pending, declined, reversed, refunded, disputed, or unrecognized statuses need separate handling and must not be judged with the ordinary purchase formula.
3. Convert the relevant records into the JSON input described below and run `scripts/audit_rewards.py` with `run_skill_script`.
4. Review every `mismatch` and `needs_review` result. A mismatch is an arithmetic/rule discrepancy; it is not proof that the customer is owed money until the transaction and merchant classification are investigated.
5. Give a concise customer-facing result: transaction date, merchant, amount, recorded and expected points, and point difference. Explain that 1 point equals $0.01 when redeemed for both of these cards. Do not expose internal record IDs unless the customer needs them for follow-up.

## Reward rules applied

### Business Bronze Rewards Card

- Eligible net posted purchases earn 1.0% cash back. In the transaction system, this is represented as 1 point per dollar; 1 point is $0.01.
- WeWork, Regus, Industrious, Gusto, ADP, Paychex, and Rippling earn 0 points.
- Slack, Zoom, HubSpot, and Salesforce earn 0 points only after the first 12 months of the subscription. Do not infer that condition from merchant name alone. Supply `saas_after_first_12_months: true` or `false`; otherwise the script returns `needs_review`.

### EcoCard

- Qualifying green purchases earn 5 sustainability points per dollar; other purchases earn 1 point per dollar.
- Target, Walmart, Amazon, and ThredUp always earn the standard 1-point rate, even if a category or item appears green.
- EV charging earns the 5-point rate only at Tesla Supercharger, ChargePoint, or EVgo. Mark an EV charge through `is_ev_charging`; an unidentified EV network is treated as standard unless the supplied merchant name is one of those partners.
- Use `qualifies_green` when merchant eligibility was confirmed. When it is absent, a transaction classified `category: "Green"` is treated as provisionally qualifying, except for the fixed exclusions and nonpartner EV rule. Clearly describe that assumption in the explanation.

### Rounding and returns

For an ordinary positive purchase, calculate points from the whole transaction amount and truncate fractional points down, never round to nearest. This is applied per transaction, not after summing transactions. A credit, return, or reversal requires the original transaction/reward relationship, so send it to review rather than guessing a reversal amount.

## Script interface

Run `scripts/audit_rewards.py`. It reads one JSON object from stdin and writes one JSON report to stdout.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "optional reference",
      "credit_card_type": "Business Bronze Rewards Card or EcoCard",
      "merchant_name": "merchant",
      "transaction_amount": "decimal dollar amount",
      "transaction_date": "optional ISO date",
      "category": "optional category",
      "status": "COMPLETED or POSTED",
      "rewards_earned": "recorded integer points",
      "qualifies_green": true,
      "is_ev_charging": false,
      "saas_after_first_12_months": false
    }
  ]
}
```

`qualifies_green`, `is_ev_charging`, and `saas_after_first_12_months` are optional. The last field is required only to resolve a Business Bronze transaction at one of the listed SaaS merchants. Amounts may be JSON numbers or decimal strings, but decimal strings avoid floating-point ambiguity.

Output contains `items`, `mismatches`, `needs_review`, and aggregate point/value differences. Each item reports the applied rule, expected points when determinable, recorded points, and a difference calculated as `expected - recorded`. A positive difference means fewer points were recorded than expected; a negative difference means more were recorded.

## Validation

Before relying on the result, confirm that:

- every reviewed record is for Business Bronze or EcoCard and has a parseable nonnegative amount and integer recorded reward;
- every transaction marked as a mismatch has a determinate expected value rather than `needs_review`;
- merchant spelling and card type are copied from the transaction record;
- SaaS tenure and uncertain green/EV eligibility are not silently assumed; and
- all calculations use the script's per-transaction truncation result.

If the input has malformed records, unsupported card types, non-posted statuses, negative amounts, missing recorded points, or unresolved SaaS tenure, the report identifies them for review instead of manufacturing a conclusion.
