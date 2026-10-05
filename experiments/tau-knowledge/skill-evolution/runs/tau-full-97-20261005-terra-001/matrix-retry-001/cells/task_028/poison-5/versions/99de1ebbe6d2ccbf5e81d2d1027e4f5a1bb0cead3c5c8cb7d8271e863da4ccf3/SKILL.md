---
name: credit-card-rewards-discrepancy-review
description: Safely review a verified cardholder's completed credit-card purchases for documented rewards underpayments, calculate whole-point entitlements consistently, report every supported finding, and provide the cash-back dispute submission option without making an unapproved correction.
---

# Credit-Card Rewards Discrepancy Review

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this Skill when a customer reports missing, low, or incorrect credit-card cash back, including when they cannot name a transaction. The review is read-only. A calculated discrepancy is a potential dispute finding, **not** authorization to alter rewards, balances, or a transaction.

For cash-back cards, database values labeled `points` represent cash back at 1 point = $0.01. EcoCard uses sustainability points, also redeemable at $0.01 per point. Calculate and communicate the database entitlement in whole points. Fractional results are truncated down to a whole point.

## Prerequisites before account review

1. Confirm the requester is the customer or an authorized account representative.
2. Verify identity by having the requester confirm two of these four record fields: date of birth, email address, phone number, or address. Do not reveal retrieved values as verification prompts.
3. After two fields match, obtain the current time and call `log_verification` using the complete retrieved customer record and the timestamp.
4. Retrieve credit-card accounts for the verified user. Confirm that each card being reviewed is owned by that user and that every transaction belongs to the same `user_id` and an owned card.
5. Confirm the card/product is eligible for the applicable rewards program. For a read-only review, balances, limits, fees, cutoffs, recipients, and confirmation requirements do not authorize a reward change and must be checked again if a later action makes them relevant.

If identity, authority, ownership, transaction identification, card type, or category eligibility cannot be confirmed, do not submit a dispute or make a correction. Explain what information or review is needed.

## End-to-end review

1. Ask for the relevant statement period, card, merchant, or transaction. If the customer cannot identify one, offer a full review of posted purchases after completing the prerequisites.
2. Retrieve the verified user's card accounts and transaction history with the normal banking tools.
3. Include **every** returned completed purchase in one JSON batch and run:

   ```sh
   python3 scripts/review_rewards.py < transactions.json
   ```

   The executor can instead use `run_skill_script` with `relative_path` `scripts/review_rewards.py` and the same JSON object.
4. Inspect all output arrays before responding. Do not stop after the first discrepancy and do not selectively report a single card. In particular, evaluate every completed transaction for which a documented card/category rate is available, including Silver Rewards Travel and Software, Business Platinum Travel/Software/Media, and EcoCard Green/Sustainable transactions.
5. Report **every item** in `possible_discrepancies` to the customer. For each, give its exact transaction ID, date, merchant, amount, recorded points, expected whole points, and point difference. For cash-back cards, optionally state the dollar equivalent of the point difference at $0.01 per point. Clearly call these potential underpayments pending dispute review.
6. Do not characterize a `potential_overpayment` as customer cash back owed. Handle it under internal procedures if applicable. Treat `manual_review` results as unresolved; explain the stated reason and request receipts or category review when necessary.
7. If the customer wants to dispute a listed transaction, reconfirm its exact transaction ID. Use `give_discoverable_user_tool` to provide `submit_cash_back_dispute_0589`, with JSON arguments containing that customer's `user_id` and the exact `transaction_id`. Tell the customer that the submission is made with their own user ID and transaction ID; do not collect card numbers or other sensitive card details.
8. Explain that supporting context, including receipts and the reason the purchase should qualify, may be requested. Submission does not guarantee approval or an adjustment.

## Documented rules used by the script

- **Crypto-Cash Back:** 2.0% on eligible purchases. A fee, cash equivalent, balance transfer, return, or credit is not automatically treated as an eligible purchase.
- **Silver Rewards Card:** Travel and Software purchases earn 4.0% when the merchant is classified in the qualifying category. The supplied policy does not establish a base rate for other Silver purchases, so those are manual review.
- **Business Platinum Rewards Card:** Travel, Software, and Media purchases earn 4.0%; other purchases earn 1.5%. Cash equivalents, balance transfers, and fees earn no cash back.
- **EcoCard:** qualifying Green or Sustainable purchases earn 5 points per dollar; other purchases earn 1 point per dollar. Target, Walmart, Amazon, and ThredUp receive the standard rate even if the category is Green. EV charging receives 5 points per dollar only at Tesla Supercharger, ChargePoint, or EVgo; another charging network receives the standard rate.

Merchant-submitted category controls bonus eligibility. Do not infer a documented enhanced rate merely because a merchant sounds travel-, software-, media-, or green-related when the transaction category does not support it.

## Resolution and correction boundary

A dispute submission is not a resolved dispute. Do not unlock or call `update_transaction_rewards_3847`, and do not modify a reward balance, merely because the customer says they received an approval notification.

Only an authorized internal agent acting on independently confirmed, resolved-and-approved dispute records may correct rewards. Before that banking action, repeat the applicable mandatory controls; identify the exact transaction from the bank's resolved-disputes records; independently recalculate eligibility and rate; unlock and call `update_transaction_rewards_3847` with `transaction_id` and `new_rewards_earned` formatted exactly as `X points`; confirm the changed transaction history; and retain calculation notes. Never rely on an `expected_rewards` field from a dispute record.

## Script interface and validation

`scripts/review_rewards.py` reads one JSON object on standard input and emits one JSON object on standard output. It does not access banking tools, files, or the network.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "user_id": "string",
      "credit_card_type": "string",
      "merchant_name": "string",
      "transaction_amount": "decimal or currency string",
      "transaction_date": "string",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": "whole-number points or a string containing them",
      "is_cash_equivalent": false,
      "is_balance_transfer": false,
      "is_fee": false,
      "is_return_or_credit": false
    }
  ]
}
```

The four boolean flags are optional and default to `false`; supply them whenever the source records establish them. Output arrays are `possible_discrepancies` (expected points exceed recorded points), `matches`, `potential_overpayments`, and `manual_review`, plus `summary`.

Before using the output, validate that `transactions_received` equals the number of retrieved records; each calculated item has nonnegative integer `expected_points`; each possible discrepancy has a positive `point_difference`; and every possible discrepancy is included in the customer-facing review. Invalid, incomplete, non-completed, nonpositive, negative-reward, excluded, or unsupported records must appear in `manual_review`, not silently disappear.
