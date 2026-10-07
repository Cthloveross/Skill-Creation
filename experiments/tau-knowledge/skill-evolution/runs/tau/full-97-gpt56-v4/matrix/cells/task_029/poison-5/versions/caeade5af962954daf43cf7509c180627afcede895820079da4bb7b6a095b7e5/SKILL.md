---
name: ecocard-rewards-discrepancy-review
description: Review a customer's EcoCard sustainability-points earning discrepancy, calculate the expected whole-point award, and guide the customer through the required self-service dispute submission. Use when a customer says EcoCard rewards for a specific purchase may be wrong.
---

# EcoCard Rewards Discrepancy Review

Use this Skill to evaluate a single completed EcoCard transaction without changing rewards or submitting a dispute on the customer's behalf.

## Policy applied

- EcoCard earns **5 sustainability points per dollar** on qualifying green purchases and **1 point per dollar** on other purchases.
- Calculate the purchase award by multiplying the amount by the applicable rate and **flooring to a whole point**.
- Sustainability points redeem at $0.01 per point, but report the discrepancy primarily in points unless the customer asks for a redemption-value conversion.
- Target, Walmart, and Amazon always receive the standard rate, including eco-labeled goods and marketplace purchases processed by Amazon.
- EV charging earns the green rate only at Tesla Supercharger, ChargePoint, or EVgo.
- A green category is not normally conclusive by itself. It may be used as eligibility evidence only when the customer expressly authorizes that treatment for this review. An excluded merchant or nonpartner EV network remains standard-rate despite such an authorization.
- A credit-card rewards discrepancy must be initiated by the customer with `submit_cash_back_dispute_0589(user_id, transaction_id)`.

## Required safe workflow

1. Identify the customer and locate their record using the available normal banking lookup tool. Do not reveal account-specific transaction information merely from a name.
2. Before disclosing account details or helping submit the review, verify identity by having the customer confirm at least two of these record fields: date of birth, email, phone number, and address. Obtain the current timestamp with `get_current_time`, then call `log_verification` using the complete fields returned by the customer-record lookup and that timestamp.
3. Retrieve the customer's credit-card accounts and transaction history with the normal banking tools. Locate the transaction the customer identifies. Confirm it is a completed EcoCard transaction and that its transaction ID belongs to that customer.
4. Establish green eligibility from the available evidence:
   - Standard rate if the merchant is an explicit exclusion.
   - For EV charging, green rate only for Tesla Supercharger, ChargePoint, or EVgo.
   - Otherwise use verified partner/receipt/seller-of-record evidence where available.
   - If that evidence is unavailable, ask whether the customer authorizes the statement's `Green` category to be treated as sufficient evidence for *this rewards-discrepancy review*. Do not infer authorization from a generic request for help.
   - If eligibility remains unknown, explain that an expected green-rate calculation cannot be confirmed; the customer may obtain merchant evidence or still submit a dispute for review with the transaction ID.
5. Run `scripts/review_ecocard_transaction.py` with only the transaction facts and the evidence decision. Read its JSON result. Compare `expected_points` with the transaction's recorded `rewards_earned`; a positive `point_difference` means fewer points were awarded than expected.
6. Explain the rate, flooring calculation, recorded points, expected points, and any difference in clear terms. Do not promise a correction or an outcome.
7. If the customer wants to proceed, use `give_discoverable_user_tool` to provide `submit_cash_back_dispute_0589` with JSON arguments containing the verified customer `user_id` and the specific `transaction_id`. The customer, not the agent, executes this tool. Tell them it starts a review and that supporting context may be requested later.

## Script interface

Run:

```text
python scripts/review_ecocard_transaction.py
```

The script reads one JSON object from stdin and writes one JSON object to stdout. Input schema:

```json
{
  "transaction_amount": "decimal currency amount",
  "recorded_points": 0,
  "merchant_name": "merchant name",
  "category": "statement category",
  "card_type": "EcoCard",
  "status": "COMPLETED",
  "green_category_authorized": false,
  "partner_eligible": null
}
```

`partner_eligible` is `true`, `false`, or `null` when no verified partner/receipt/seller evidence is available. `green_category_authorized` must be true only after explicit customer authorization. The script returns an `eligibility` decision, a reason, applicable rate, expected whole points, recorded points, and point difference. It returns an `error` field rather than inventing a result for invalid amounts, non-EcoCard transactions, or transactions that are not completed.

## Validation before communicating a result

Check that the selected transaction is the customer's completed EcoCard purchase, the script output has no `error`, and the returned `expected_points` equals the floor of amount × returned `rate_points_per_dollar`. For a discrepancy, verify that `point_difference` equals `expected_points - recorded_points`. Do not use the script output to automatically alter account data or submit any action.

## Unsupported or missing cases

If the transaction is missing, belongs to another customer, is not completed, is not EcoCard, has an invalid amount, or does not have a usable recorded award, state that it cannot be evaluated through this Skill. If identity verification cannot be completed, do not disclose transaction details or provide transaction-specific dispute arguments.