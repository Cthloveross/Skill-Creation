---
name: credit-card-rewards-discrepancy-review
description: Review posted Business Bronze Rewards Card and EcoCard transactions for likely rewards discrepancies, explain the applicable earning rules, and provide the customer-facing cash-back dispute tool for transactions that need investigation. Use when a customer asks to check missing, incorrect, or unexpectedly low credit-card rewards.
---

# Credit-Card Rewards Discrepancy Review

Use this Skill to make a read-only, transaction-by-transaction rewards assessment. It does not change rewards, redeem rewards, or submit a dispute for the customer.

## Mandatory banking controls

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Before accessing or discussing account-specific results:

1. Verify the customer using two of the four identity fields: date of birth, email, phone number, and address. A database lookup is not a customer confirmation.
2. Match the customer-provided factors against the user record, obtain the current timestamp with `get_current_time`, and call `log_verification` with the complete user record and timestamp.
3. Retrieve the customer's card accounts and confirm each reviewed account belongs to the verified user and has a supported card type.
4. Use only that verified user's transactions. Do not disclose transactions, balances, or account details before verification.

If identity, authority, ownership, or card type cannot be established, stop the account-specific review and request the missing information. Do not take any rewards, dispute, redemption, or account-changing action.

## Supported rules

### Business Bronze Rewards Card

- Eligible net posted purchases earn 1.0% cash back.
- In the transaction database, rewards are stored as points; for this cash-back card, 1 point is worth $0.01. Therefore 1.0% corresponds to **1 point per dollar spent**, with a whole-point transaction record using a truncated fractional point.
- The following merchants earn 0 points: WeWork, Regus, Industrious, Gusto, ADP, Paychex, and Rippling.
- Slack, Zoom, HubSpot, and Salesforce earn the normal rate only during the first 12 months of the subscription. Payments after that earn 0 points. If the subscription age is not available, label the transaction as requiring review rather than assuming either rate.
- Returns and credits reduce the net eligible amount and reverse associated rewards.

### EcoCard

- Qualifying green purchases earn 5 sustainability points per dollar; other purchases earn 1 point per dollar. Points redeem at $0.01 per point.
- A transaction classified as `Green` by the transaction source is treated as qualifying green evidence unless an exclusion overrides it. Explicit `qualifies_as_green` input, when present, takes precedence.
- Amazon, Walmart, Target, and ThredUp always earn the standard 1 point per dollar, including eco-labeled purchases.
- EV charging earns the higher rate only for Tesla Supercharger, ChargePoint, and EVgo. Those named networks qualify; other charging networks earn the standard rate.
- Where neither a qualifying classification nor sufficient merchant/category evidence exists, apply the standard rate; do not infer green eligibility merely from a merchant name or product claim.
- Returns and refunds reverse points at the original rate. Pending or otherwise unposted transactions are not final rewards determinations.

## Review workflow

1. Complete the mandatory banking controls above.
2. Retrieve all transactions for the verified user with `get_credit_card_transactions_by_user` and limit the review to the supported card accounts confirmed for that user. If the customer named a date range or transactions, honor that scope; otherwise state the scope used (for example, all available recent posted activity).
3. Convert the retrieved records to the JSON schema accepted by `scripts/review_rewards.py`, run the script, and inspect its results. The script performs rule-based calculation only; it does not query systems or make account changes.
4. For each `evaluated` transaction, compare `recorded_rewards_points` with `expected_rewards_points`:
   - `difference_points > 0`: the transaction appears under-rewarded.
   - `difference_points < 0`: the recorded reward is higher than this rules-based estimate; do not propose an adjustment because an unobserved promotion or data issue may apply.
   - `difference_points = 0`: it matches the applicable rule.
5. Clearly distinguish confirmed matching transactions, likely discrepancies, and `needs_review`/`not_posted` results. Explain the rate and exclusion that led to each conclusion. Do not represent a calculation as an approved correction.
6. For each likely discrepancy the customer wants investigated, provide the customer with the documented submission mechanism using `give_discoverable_user_tool`:
   - `discoverable_tool_name`: `submit_cash_back_dispute_0589`
   - `arguments`: a JSON string containing the verified user's `user_id` and that specific `transaction_id`.

   Tell the customer to run the provided tool for the specific transaction. Confirm the transaction ID with them before offering it. The tool initiates review; it does not guarantee an adjustment.
7. Do not unlock or call internal reward-update tools during this workflow. Rewards may only be corrected after a dispute is resolved and approved under the applicable internal process.

If the customer asks for a human instead of using the dispute tool, transfer them with `transfer_to_human_agents` and a factual summary. If the request cannot be reviewed due to an unresolved data ambiguity or system error, explain the limitation and offer the dispute mechanism or an appropriate human transfer.

## Script interface

Run `scripts/review_rewards.py` with JSON on stdin:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Business Bronze Rewards Card or EcoCard",
      "merchant_name": "string",
      "transaction_amount": "decimal number or string",
      "rewards_earned": "integer, numeric string, or 'N points'",
      "category": "optional string",
      "status": "COMPLETED, POSTED, PENDING, REFUNDED, etc.",
      "qualifies_as_green": true,
      "subscription_months": 3
    }
  ]
}
```

`qualifies_as_green` and `subscription_months` are optional. Do not manufacture them when they are unavailable. The script emits JSON with per-transaction expected whole points, recorded points, the signed difference (`expected - recorded`), rate rationale, and an aggregate summary. Invalid records are returned as `needs_review` with an explanatory reason rather than guessed.

Example runnable call:

```sh
python3 scripts/review_rewards.py <<'JSON'
{"transactions": []}
JSON
```

Validate that every retrieved, in-scope transaction appears exactly once in `results`, that no `error` is returned, and that every `evaluated` result has an integer expected value, recorded value, and signed difference. Reconcile the number of results with the number of supplied transaction records before discussing conclusions.
