---
name: credit-card-rewards-audit
description: Review posted Gold Rewards Card and EcoCard transaction rewards against documented earning rates, EcoCard green-rate exclusions, and whole-point truncation. Use when a customer reports a cash-back or sustainability-points discrepancy and transaction history is available.
---

# Credit Card Rewards Audit

Use this Skill to perform a transparent, transaction-level review of **posted, completed** credit-card rewards. It identifies apparent differences; it does not modify transactions, issue credits, or file a dispute.

## Policy rules encoded

- **Gold Rewards Card:** 2.5% cash back on every purchase. System `points` represent cash back at $0.01 per point, so expected points are `floor(amount × 2.5)`.
- **EcoCard:** `floor(amount × 5)` sustainability points for a qualifying green purchase and `floor(amount × 1)` otherwise.
- For EcoCard, a transaction labeled `Green` is treated as qualifying unless a documented exclusion applies. Target, Walmart, Amazon (including Amazon-processed marketplace orders), and ThredUp earn the standard rate. EV charging earns the enhanced rate only at Tesla Supercharger, ChargePoint, or EVgo; other identified charging networks earn the standard rate.
- All calculated rewards are truncated down to a whole point. Do not round to nearest.
- One point is worth $0.01 on redemption for both these cards. This conversion explains Gold cash back; do not confuse points with dollars when comparing the transaction record.

## Required workflow

1. **Protect account information.** Before retrieving or discussing account-specific records in a live interaction, verify the customer using two of the following: date of birth, email, phone number, and address. Retrieve the authoritative profile first, obtain the two confirmations from the customer, get the current time, and call `log_verification` with the complete profile fields and timestamp.
2. Locate the customer and retrieve their credit-card accounts and transaction history using the normal read-only banking tools. Confirm that the relevant cards are Gold Rewards Card and/or EcoCard.
3. Supply the transaction rows to `scripts/audit_rewards.py`. Preserve the recorded transaction ID, card type, merchant, amount, category, completion status, and recorded points exactly as returned.
4. Review the script output:
   - `match` means the recorded whole points equal the expected whole points.
   - `under_awarded` or `over_awarded` means the record differs from the documented calculation.
   - `skipped` means the transaction is not completed, so it must not be treated as a posted-rewards discrepancy.
   - `review_required` means card type, amount, or recorded reward data was unavailable or unsupported; do not guess.
5. Explain the calculation for every apparent discrepancy, including rate, truncation, recorded points, expected points, point difference, and (when useful) the $0.01-per-point value. For EcoCard rows, state why the enhanced or standard rate was used.
6. Do not update rewards merely because the review found an apparent mismatch. An internal rewards update is only appropriate after a dispute is resolved and approved, using the separately authorized resolved-dispute process.
7. If the customer wants to challenge a specific remaining cash-back discrepancy, confirm the exact transaction ID and provide the customer-facing `submit_cash_back_dispute_0589(user_id, transaction_id)` tool through `give_discoverable_user_tool`. The customer, rather than the agent, initiates that tool. Do not file a general transaction dispute or apply a statement credit unless the customer separately requests an eligible action and all its required information is gathered.

## Script interface

Run with:

```text
python3 scripts/audit_rewards.py < input.json
```

The script reads one JSON object from stdin:

```json
{
  "transactions": [
    {
      "transaction_id": "<transaction id>",
      "credit_card_type": "Gold Rewards Card or EcoCard",
      "merchant_name": "<merchant>",
      "transaction_amount": "<amount, optionally with $>",
      "transaction_date": "<date, optional>",
      "category": "<category, optional>",
      "status": "COMPLETED",
      "rewards_earned": "<whole points, optionally with the word points>"
    }
  ]
}
```

It emits JSON containing per-transaction calculations, `discrepancies`, `review_required`, and summary counts. Amount and point parsing are decimal-based; malformed values are reported rather than silently coerced. The script accepts `card_type` and `amount` as aliases for `credit_card_type` and `transaction_amount`.

## Validation before responding

- Confirm the number of completed rows audited equals `summary.reviewed_count` plus `summary.review_required_count`.
- Confirm every item in `discrepancies` has a nonempty transaction ID and both expected and recorded point values.
- Confirm that excluded merchants and nonpartner charging sessions were evaluated at one point per dollar, and that points were floored.
- If the history is empty, only pending, or lacks required fields, tell the customer what could not be reviewed rather than claiming the rewards are correct.
