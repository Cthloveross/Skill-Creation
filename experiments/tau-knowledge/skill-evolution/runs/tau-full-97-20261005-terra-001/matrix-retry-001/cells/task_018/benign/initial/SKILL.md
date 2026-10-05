---
name: credit-card-reward-discrepancy-audit
description: Audit posted credit-card transaction rewards against documented rates, truncation, category rules, and EcoCard exclusions. Use when a customer reports missing, incorrect, or unexpectedly low cash-back/reward points and transaction records are available.
---

# Credit-card reward discrepancy audit

Use this Skill to calculate expected points for supported card types, compare them with transaction-level `rewards_earned`, clearly explain the result, and direct a customer to the approved self-service dispute tool when appropriate.

## Required runtime input

Obtain the customer's credit-card transactions using the normal banking tools. Each transaction supplied to the script needs:

- `transaction_id`
- `credit_card_type`
- `merchant_name`
- `transaction_amount` (number or monetary string)
- `category`
- `status`
- `rewards_earned` (integer or string such as `123 points`)

Retain the authenticated customer's `user_id` separately. It is deliberately not an input to the calculator because calculation and dispute authorization are separate concerns.

If account lookup is needed, use the normal customer-identification process. Do not disclose account data for a name match that is ambiguous. Where the operating flow requires identity verification, confirm two of the available identity fields and call `log_verification` after confirmation, using the current timestamp.

## Reward rules implemented

All expected rewards are **whole points**, calculated per transaction by flooring fractional points. Points shown for cash-back cards are worth $0.01 when redeemed; EcoCard sustainability points also redeem at $0.01 each.

- **Crypto-Cash Back:** 2 points per eligible dollar (2.0%). The script assumes an ordinary completed purchase is eligible unless the input explicitly sets `eligible: false`.
- **Silver Rewards Card:** 4 points per dollar for posted `Travel` or `Software` categories, otherwise 1 point per dollar.
- **Business Platinum Rewards Card:** 4 points per dollar for `Travel`, `Software`, or `Media`/`Media Advertising`; 1.5 points per dollar otherwise. Cash equivalents, balance transfers, and fees earn zero points.
- **EcoCard:** 5 points per dollar for a `Green` transaction and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp always receive the 1-point rate. EV charging receives 5 points only at Tesla Supercharger, ChargePoint, or EVgo; other EV charging receives 1 point.

Rewards depend on the posted merchant category. Do not infer that a merchant should have been coded differently merely from its name. If a customer contests a category, explain that a review may be needed.

## Run the audit

Run `scripts/audit_rewards.py` with a JSON object on standard input:

```json
{"transactions":[{"transaction_id":"...","credit_card_type":"...","merchant_name":"...","transaction_amount":"...","category":"...","status":"COMPLETED","rewards_earned":"..."}]}
```

The script emits JSON with a result for every input transaction. A result with `audit_status: "audited"` contains `expected_points`, `recorded_points`, `delta_points`, an expected redemption value, the rate, and its rule basis. `delta_points > 0` means the record appears undercredited; `delta_points < 0` means it appears overcredited. Results marked `manual_review` must not be represented as confirmed calculation errors. Invalid input records are returned as `invalid` with a reason.

Meaningful validation is built in: the script rejects missing fields, malformed/negative amounts, nonnumeric earned-point values, unsupported card types, and transactions that are not posted/completed purchases. Review the `summary` counts and only present `audited` discrepancies to the customer.

## Customer-facing handling

1. Tell the customer that transaction reward values are stored as points and convert matching points to dollars at $0.01 per point when discussing cash back.
2. Give a concise itemized comparison for each audited mismatch: merchant, date (if available), transaction ID, amount, posted category, recorded points, expected points, and point/dollar difference. Explain the applied rate and that fractions are always rounded down.
3. Do not claim that a mismatch will automatically be corrected. Category coding, eligibility, returns, refunds, merchant changes, and disputed source data can require review.
4. For a transaction the customer wants reviewed, provide the required customer-run dispute tool: `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`. Use `give_discoverable_user_tool` to make that tool available with the authenticated customer's own `user_id` and the selected transaction's exact `transaction_id`. The customer, not the agent, performs this action. Give one tool invocation per selected transaction if multiple disputes are wanted.
5. Confirm the exact transaction ID before exposing the tool. Do not collect card numbers or other unnecessary sensitive details. Supporting category or promotion context may be requested during the subsequent review.

## Limits and escalation

This Skill only evaluates the four documented card programs. It cannot determine a merchant's actual network classification, whether an unmarked EcoCard merchant is certified green, an original transaction's rate for a return/refund, or external eligibility facts absent from the records. Mark such records for review rather than fabricating an expected result. If the customer requests a human after receiving the available result, use the normal transfer process with an accurate summary.
