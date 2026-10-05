---
name: review-and-correct-silver-rewards
version: 1.0.0
description: Review posted Silver Rewards Card transaction rewards, calculate independently verifiable expected points, identify discrepancies, and—only after identity verification and an approved cash-back dispute—apply and verify authorized transaction-reward corrections.
---

# Review and Correct Silver Rewards

Use this Skill when a cardholder says that cash back on a Silver Rewards Card may be incorrect, or when an approved cash-back dispute requires correcting one or more transaction rewards. It supports review and calculation; it does not treat a calculation alone as authorization to alter account records.

## Banking-control prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow:

1. Obtain and compare at least two of date of birth, email, phone number, and address against the customer record. A name alone is not identity verification.
2. Get the current timestamp and call `log_verification` only after two fields match. Include the complete retrieved identity record and timestamp required by that tool.
3. Confirm the verified customer owns the selected credit-card account and that it is a Silver Rewards Card before discussing account-specific transactions or acting on them.
4. For a correction, confirm the transaction belongs to that account, the transaction is posted/completed rather than pending or refunded, and the customer has authority for the request. Determine and obtain any required confirmation before a state-changing action.
5. Do not expose account information or update rewards if verification, ownership, status, dispute approval, or a required confirmation is absent or contradictory. Explain the missing prerequisite and use the normal support process.

## Reward rules used by this Skill

- A Silver Rewards Card earns 4.0% cash back on eligible **Travel** and **Software** transactions when the posted merchant category is the applicable category.
- Points stored for this cash-back card represent cash back at **1 point = $0.01**. Thus expected points are `floor(amount × applicable cash-back percent × 100)`.
- Reward points are truncated down to a whole point **for each transaction**; never round to nearest or aggregate fractional rewards across transactions.
- Travel and Software eligibility depends on the merchant's posted category. A purchase routed through a third party, a non-travel-coded travel merchant, or a non-software-coded subscription may not qualify for the 4% rate.
- Non-category purchases earn at least 1.0% according to the available card material, but the exact applicable non-category rate must be independently verified before proposing an exact correction. Supply that verified rate to the calculator rather than assuming a promotion or rate not in evidence.
- Gift cards, person-to-person payments, bank fees, interest, insurance premiums, and returned/refunded purchases are not qualifying rewards purchases. Rewards can change after a merchant update or credit posts.

## Review procedure

1. After verification, use `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user` for the verified user. Select only the owned Silver Rewards Card.
2. Use the posted category, transaction amount, status, stored `rewards_earned`, and independently verified applicable rates or promotions. Do not rely on an `expected_rewards` field from a dispute record.
3. Put normalized transaction data into the JSON schema below and run `scripts/reconcile_rewards.py`. The script calculates points deterministically and identifies differences; it does not call banking tools or mutate data.
4. Review each reported candidate. Confirm the category and whether a credit, return, merchant recategorization, or active promotion changes the result. For a potentially miscategorized merchant, request or retain the receipt/invoice and route it for category review rather than assuming the merchant category.
5. Clearly tell the customer which posted transactions appear correct, which require investigation, and that points are displayed as cash-back equivalents at $0.01 each. A discrepancy in a non-category transaction is a minimum-rate or rate-verification issue unless an exact applicable rate has been verified.

## Correction procedure: approved disputes only

A direct update is permitted only when there is a resolved, approved cash-back dispute covering the exact transaction. A customer report or calculator discrepancy alone is not an approved dispute.

1. Look up the customer’s resolved disputes in the `cash_back_disputes` data source and identify the exact `transaction_id` values with approved corrections. If this lookup is not available in the current runtime, do not attempt an update; record or route the case through the ordinary cash-back dispute process.
2. Recalculate the reward independently using the transaction's card type, posted category, verified rate, and applicable promotion. Do not use an `expected_rewards` value from the dispute record as the calculation source.
3. Recheck all banking-control prerequisites, including account ownership, product eligibility, card and transaction details, required approval, and any required confirmation.
4. Unlock `update_transaction_rewards_3847` with `unlock_discoverable_agent_tool`.
5. For each approved transaction, call `update_transaction_rewards_3847` through `call_discoverable_agent_tool` with exactly:
   - `transaction_id`: the verified exact transaction identifier
   - `new_rewards_earned`: the calculated whole-point value formatted as `"X points"`
6. Re-query `credit_card_transaction_history` and confirm the returned reward value equals the requested whole-point value. Preserve the rate, formula, category/status evidence, approval reference, and verification result in the internal case record.
7. If the update tool fails or post-update data does not match, do not retry speculatively or claim success. Keep the calculation/audit notes and route the technical or dispute issue through the normal support process.

## Calculator

Run from the package root with a runtime-supplied JSON file:

```sh
python3 scripts/reconcile_rewards.py < request.json
```

The script reads one JSON object from standard input and writes one JSON object to standard output. It uses only the Python standard library and makes no external calls.

### Input schema

```json
{
  "card_type": "Silver Rewards Card",
  "base_rate_percent": "verified optional standard rate",
  "category_rates_percent": {"category name": "verified percent"},
  "promotion_rates_percent_by_transaction": {"transaction id": "verified percent"},
  "transactions": [
    {
      "transaction_id": "runtime transaction id",
      "transaction_amount": "currency amount",
      "category": "posted category",
      "status": "COMPLETED, POSTED, or another source status",
      "rewards_earned": "stored whole points"
    }
  ]
}
```

`card_type` and `transactions` are required. `base_rate_percent`, category rates, and transaction promotion rates are optional. A verified transaction-specific promotion takes precedence over a verified category rate, which takes precedence over Silver's Travel/Software 4% rate, which takes precedence over a provided base rate. Only provide a promotion or non-category rate after independently verifying it for the transaction date.

### Output and validation

On valid input, the output has `ok: true`, a `reviews` entry per transaction, and `candidates` containing calculated transactions whose stored whole points differ from the independent result. A review entry can instead be `not_final` (not posted), `excluded` (returned/refunded/void), or `needs_rate` (no verified applicable rate). These are not correction candidates.

Before using a calculated candidate, validate that:

- its amount is nonnegative currency and stored rewards are nonnegative whole points;
- the transaction is posted/completed and belongs to the verified account;
- the category is the posted merchant category, not a guessed description;
- each supplied rate or promotion is independently verified for the transaction; and
- an approved dispute and all update prerequisites exist before any mutation.

Malformed JSON, malformed amounts/rates, missing required transaction fields, or an unsupported card type produce `ok: false` with actionable errors. Do not update from an error result.
