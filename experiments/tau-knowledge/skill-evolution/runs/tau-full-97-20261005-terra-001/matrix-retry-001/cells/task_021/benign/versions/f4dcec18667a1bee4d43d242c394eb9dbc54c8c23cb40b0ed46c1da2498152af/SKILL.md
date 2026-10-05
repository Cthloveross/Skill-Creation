---
name: credit-card-rewards-audit-and-approved-correction
description: Audit posted Business Bronze Rewards Card and EcoCard transactions for incorrectly awarded whole-number rewards, explain the rate and rounding used, and apply an internal correction only for transactions tied to resolved, approved cash-back disputes.
---

# Credit-card rewards audit and approved correction

Use this Skill when a customer reports potentially incorrect credit-card rewards and transaction history is available. It distinguishes cash-back cards whose database rewards are stored as points from EcoCard sustainability points, and does not infer missing eligibility facts.

## Policy encoded by this Skill

- **Business Bronze Rewards Card:** eligible net posted purchases earn 1.0% cash back. Since cash back is stored as points at 1 point = $0.01, expected points are `floor(amount_in_dollars × 1.0)`. The listed coworking and payroll merchants earn zero points. Listed SaaS merchants earn zero only after their initial 12-month subscription period; do not apply that exclusion without authoritative subscription-tenure data.
- **EcoCard:** qualifying green purchases earn `floor(amount_in_dollars × 5)` sustainability points; other purchases earn `floor(amount_in_dollars × 1)`. Amazon, Target, Walmart, and ThredUp are standard-rate merchants even if a transaction is categorized green. Tesla Supercharger, ChargePoint, and EVgo are qualifying EV charging networks. A validated `Green` transaction category may be used as the system's green-qualification signal. If that category is not authoritative in the runtime, supply `green_qualified` per transaction instead.
- All fractional reward points are truncated (rounded down), never rounded to nearest.
- Only posted/completed positive purchase transactions can be mechanically audited. Returns, credits, pending/declined items, unknown statuses, unsupported card products, unknown amounts, and unresolved green/subscription eligibility are reported for review rather than guessed.
- An account-level rewards balance cannot be reconciled from a transaction subset because prior activity and redemptions may affect it. Audit individual transactions unless a complete ledger and redemption history are available.

## Inputs and audit procedure

1. Obtain the relevant transaction history using the normal read-only runtime tools. Preserve transaction ID, card type, merchant, amount, status, category, and displayed rewards.
2. Convert the records into the structured JSON accepted by `scripts/audit_rewards.py`. Run the script. It reads JSON from stdin and emits JSON to stdout.
3. Review `discrepancies` and `needs_review`. An empty discrepancy list means the auditable transactions match the documented rules; it is not proof about skipped records or an account total.
4. Explain findings in customer-facing terms. State points and, for cash-back cards, that 1 point equals $0.01. Do not call EcoCard sustainability points “cash back.” Do not expose unrelated account information.

### Script input schema

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Business Bronze Rewards Card or EcoCard",
      "merchant_name": "string",
      "transaction_amount": "$12.34 or numeric",
      "status": "COMPLETED or POSTED",
      "category": "Green (optional)",
      "rewards_earned": "123 points or integer",
      "green_qualified": true,
      "beyond_initial_12_months": false
    }
  ],
  "options": {
    "green_category_is_qualified": true,
    "known_green_merchants": ["optional additional certified merchant names"]
  }
}
```

`green_qualified` overrides category inference. `beyond_initial_12_months` is only relevant to the named Business Bronze SaaS exclusions. Omit it when tenure is unknown. Merchant matching is case- and whitespace-insensitive. A minimal runnable call is `python3 scripts/audit_rewards.py` with `{"transactions": []}` on stdin.

### Script output schema

The JSON output has:

- `audited`: transaction-level expected and displayed points plus calculation basis;
- `discrepancies`: audited entries whose displayed and expected whole-point values differ, each with `new_rewards_earned` formatted for the update tool;
- `needs_review`: records skipped because a required fact is absent or unsupported;
- `summary`: counts and point deltas grouped by card type; and
- `input_errors`: malformed records that could not be reliably evaluated.

Validate before acting: every correction must have a nonempty transaction ID, a nonnegative integer expected value, a displayed whole-point value, and a documented calculation basis. The script supplies these fields for its `discrepancies`; records in `needs_review` are not update candidates.

## Mandatory gate before an update

Finding a discrepancy alone does **not** authorize a database change. The internal correction procedure applies only after a cash-back dispute has been resolved and approved.

1. Use available authorized runtime access to look up the customer’s resolved, approved records in `cash_back_disputes`, and collect their exact `transaction_id` values.
2. Intersect those IDs with the script’s `discrepancies`. Independently retain the script’s calculation basis; never use an `expected_rewards` field from a dispute record as the calculation.
3. If dispute status cannot be obtained, is not resolved and approved, or an anomaly is not among those dispute IDs, do not update it. Report the audit result and route/continue the dispute process using supported runtime procedures.
4. For every eligible correction, unlock `update_transaction_rewards_3847` with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` using exactly:

```json
{
  "transaction_id": "<approved discrepancy transaction ID>",
  "new_rewards_earned": "<expected whole number> points"
}
```

5. Re-read the transaction history with the normal transaction-history tool and confirm the matching transaction now shows the requested rewards value. Record the independent calculation notes in the available internal case record. If the update tool fails or confirmation does not match, do not claim completion; report the failure through the supported internal workflow.

The script never makes bank or database changes. Tool calls and customer communication remain the executor’s responsibility.
