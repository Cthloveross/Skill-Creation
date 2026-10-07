---
name: credit-card-rewards-discrepancy-review
description: Safely review a verified cardholder's completed credit-card purchases for documented rewards underpayments, calculate whole-point entitlements consistently, report every supported finding, and provide the cash-back dispute submission option without making an unapproved correction.
---

# Credit-Card Rewards Discrepancy Review

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this Skill when a customer reports missing, low, or incorrect credit-card cash back, including when they cannot identify a specific purchase. A review is read-only. A calculated discrepancy is a potential dispute finding, not authorization to alter rewards, balances, or a transaction.

For cash-back cards, database values called `points` represent cash back at 1 point = $0.01. EcoCard uses sustainability points, also redeemable at $0.01 per point. Calculate documented entitlements in whole points by truncating fractional points down.

## Prerequisites before account review

1. Confirm that the requester is the customer or an authorized account representative.
2. Verify identity by having the requester supply and match two of these record fields: date of birth, email address, phone number, or address. Do not reveal retrieved values as verification prompts.
3. After two fields match, obtain the current time and call `log_verification` with the complete retrieved customer record and timestamp.
4. Retrieve card accounts only after verification. Confirm each reviewed card is owned by the verified user. Confirm each reviewed transaction has that same `user_id` and a card type present among the user's accounts.
5. Confirm the relevant card product is eligible for its documented rewards program. A read-only review does not authorize a correction; recheck balance, limits, fees, cutoffs, recipients, and confirmation requirements if a later banking action makes them relevant.

If identity, authority, ownership, transaction identification, card type, or category eligibility cannot be confirmed, do not submit a dispute or make a correction. Explain what is needed.

## End-to-end review procedure

1. Ask for a relevant statement period, card, merchant, or transaction. If the customer cannot identify one, offer a full review of posted purchases after completing the prerequisites.
2. Retrieve all of the verified user's card accounts and transaction history with the normal banking tools. Preserve the full returned transaction set; do not choose only a suspected purchase or only one card.
3. Send every returned transaction in one JSON batch to `scripts/review_rewards.py` using `run_skill_script` with `relative_path: "scripts/review_rewards.py"`. The script's output is a read-only calculation, not a bank action.
4. Validate the result before responding:
   - `summary.transactions_received` equals the number of retrieved records;
   - the total lengths of `possible_discrepancies`, `matches`, `potential_overpayments`, and `manual_review` equals `transactions_received`;
   - each calculated expected value is a nonnegative integer; and
   - every `possible_discrepancies` item has a positive point difference.
   If validation fails, do not present a completed review; resolve the data issue or explain the limitation.
5. Deliver the script's `customer_report` verbatim or faithfully reproduce all of its itemized findings. Never stop after the first discrepancy. In particular, review every completed transaction with a documented rate, including Crypto-Cash Back eligible purchases; Silver Rewards Travel and Software; Business Platinum Travel, Software, Media, and other purchases; and EcoCard Green/Sustainable and standard-rate purchases.
6. For **every** item in `possible_discrepancies`, state the exact transaction ID, date, merchant, amount, recorded points, expected whole points, and point difference. Describe these as potential underpayments pending dispute review. For cash-back cards, the point difference may also be described at $0.01 per point.
7. Do not describe `potential_overpayments` as cash back owed to the customer. Handle such results internally if needed. Treat `manual_review` as unresolved: explain the stated reason and request receipts or a category review where appropriate.
8. If the customer wants to dispute a listed purchase, reconfirm its exact transaction ID. Call `give_discoverable_user_tool` for `submit_cash_back_dispute_0589`, passing JSON arguments with that customer's `user_id` and the exact `transaction_id`. Tell the customer the tool is submitted using their own user ID and transaction ID. Do not collect card numbers or other sensitive card details.
9. Explain that supporting context, such as receipts and why the purchase should qualify, may be requested during review. Submission does not guarantee approval or an adjustment.

## Documented reward rules

- **Crypto-Cash Back:** eligible purchases earn 2.0%. Fees, cash equivalents, balance transfers, returns, and credits are not treated as eligible purchases.
- **Silver Rewards Card:** Travel and Software purchases earn 4.0% when merchant classification is in the qualifying category. The available policy does not establish a base rate for other Silver purchases; those require manual review.
- **Business Platinum Rewards Card:** Travel, Software, and Media purchases earn 4.0%; other purchases earn 1.5%. Cash equivalents, balance transfers, and fees earn no cash back.
- **EcoCard:** qualifying Green or Sustainable purchases earn 5 points per dollar; other purchases earn 1 point per dollar. Target, Walmart, Amazon, and ThredUp earn the standard rate even if categorized Green. EV charging earns 5 points per dollar only at Tesla Supercharger, ChargePoint, or EVgo; another charging network earns the standard rate.

Merchant-submitted category controls enhanced-rate eligibility. Do not infer an enhanced rate merely because a merchant name sounds travel-, software-, media-, or green-related when the transaction category does not support it.

## Resolution and correction boundary

A dispute submission is not a resolved dispute. Do not unlock or call `update_transaction_rewards_3847`, and do not modify a reward balance, merely because a customer says they received an approval notification.

Only an authorized internal agent acting on independently confirmed resolved-and-approved dispute records may correct rewards. Before that banking action, repeat the applicable mandatory controls; identify the exact transaction from the bank's resolved-disputes records; independently recalculate eligibility and rate; unlock and call `update_transaction_rewards_3847` with `transaction_id` and `new_rewards_earned` formatted exactly as `X points`; confirm the changed transaction history; and retain calculation notes. Never rely on an `expected_rewards` field from a dispute record.

## Script interface

`scripts/review_rewards.py` reads one JSON object from standard input and emits one JSON object on standard output. It has no network, file, banking-tool, or account-modification access.

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

The four boolean flags are optional and default to `false`; provide them whenever source records establish them. Output contains `possible_discrepancies`, `matches`, `potential_overpayments`, `manual_review`, `summary`, and a complete customer-ready `customer_report`. Invalid, incomplete, non-completed, nonpositive, negative-reward, excluded, and unsupported records are placed in `manual_review`; they are never silently omitted.
