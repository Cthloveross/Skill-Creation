---
name: credit-card-rewards-audit
description: Review posted EcoCard and Business Bronze Rewards Card transactions against documented reward rates, exclusions, and transaction-record points. Use for an authenticated customer asking whether recent rewards appear correctly calculated. Produces a reproducible transaction-level discrepancy report; it does not redeem, adjust, or dispute rewards.
---

# Credit Card Rewards Audit

Use this Skill to explain rewards calculation for **EcoCard** and **Business Bronze Rewards Card** activity and to identify transaction rows whose stored rewards differ from the documented rate.

## Controls and scope

This workflow is a read-only rewards review. It must not be used to make a redemption, statement-credit, account, or transaction adjustment.

Before accessing or discussing account-specific transactions, satisfy the banking control: verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements applicable to the requested banking action. For this read-only review:

1. Verify identity by confirming at least two of date of birth, email, phone number, and address against the user record.
2. Obtain the current timestamp and call `log_verification` with the matched record values and timestamp.
3. Retrieve the user's card accounts and ensure each reviewed account has that user's `user_id`; review only the selected owned card(s).
4. This review has no redemption, transfer, merchant payment, fee, recipient, or cutoff action. Do not infer that a customer is eligible to redeem merely from a rewards balance. A separate redemption request requires its own eligibility and confirmation checks.

If identity is not verified, request the additional verification information rather than revealing transactions, account balances, or rewards.

## Policy used in the audit

### Business Bronze Rewards Card

- Eligible posted purchases earn **1.0% cash back**, represented in the transaction database as **1 point per dollar spent**. One point equals **$0.01** when redeemed.
- Rewards are based on the net transaction amount after credits or returns; a return or credit reverses rewards at its original earn rate.
- The following merchants earn 0 points: **WeWork, Regus, Industrious, Gusto, ADP, Paychex, Rippling**.
- **Slack, Zoom, HubSpot, and Salesforce** earn the ordinary rate only during the first 12 months of the subscription. At 12 months or later, continued subscription payments earn 0 points. Subscription age must be supplied to determine these rows.

### EcoCard

- A qualifying green purchase earns **5 sustainability points per dollar**; other purchases earn **1 point per dollar**. One sustainability point equals **$0.01** when redeemed.
- **Amazon, Target, Walmart, and ThredUp** always earn the standard 1-point rate, including eco-labeled items and any purchase channel.
- EV charging earns the 5-point rate only at **Tesla Supercharger, ChargePoint, or EVgo**.
- A transaction explicitly classified as category `Green` can be treated as a qualifying green transaction unless an exclusion overrides it. Do not infer green eligibility merely from a merchant's name, product description, or a generic retail category.
- For ordinary non-green rows, use the standard 1-point rate.

## Procedure

1. Complete the identity and ownership checks above. Retrieve transactions for the verified owner; filter them to the card type(s) the customer wants reviewed.
2. Convert the relevant tool output into the structured input schema below. Preserve transaction ID, merchant, amount, status, category, card type, and recorded `rewards_earned`.
3. Run the deterministic reviewer:

   ```sh
   python3 scripts/review_rewards.py <<'JSON'
   {"transactions": [{"transaction_id": "...", "credit_card_type": "EcoCard", "merchant_name": "...", "transaction_amount": "12.34", "category": "Green", "status": "COMPLETED", "rewards_earned": 61}]}
   JSON
   ```

4. Inspect `reviews`:
   - `match` means the integer points recorded agree with the expected stored points.
   - `possible_undercredit` or `possible_overcredit` identifies a row needing explanation or correction review.
   - `indeterminate` means key evidence is missing, such as an unlinked return/credit or the age of a SaaS subscription.
   - `not_reviewed` means the row is not posted/completed, has an unsupported card, or lacks essential data.
5. Explain the result in plain language, including the card, merchant, documented rate/basis, expected points, recorded points, and dollar equivalent of any difference. A positive `difference_points` is a potential undercredit; a negative value is a potential overcredit.
6. Do not claim that the current account `reward_points` balance should equal the sum of the supplied rows. Balances can include other activity, redemptions, and adjustments. Do not promise an adjustment: no adjustment tool is supplied. If a confirmed correction or a disputed eligibility determination is requested, follow the applicable supported escalation process.

## Input and output schema

`review_rewards.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input:

- `transactions` (required): array of objects with `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `status`, and `rewards_earned`. `category` is optional but needed to establish an ordinary EcoCard green transaction.
- `subscription_months` (optional per transaction): numeric age of a Slack, Zoom, HubSpot, or Salesforce subscription. Values under 12 receive the ordinary Business Bronze rate; 12 or greater receive 0 points.
- `rounding` (optional): `truncate_toward_zero` (default), `floor`, or `half_up`.

Amounts and recorded points can be JSON numbers or strings such as `$12.34` and `61 points`. The output includes `expected_points_exact`, `expected_points`, recorded `actual_points`, rate `basis`, and a signed `difference_points` for every usable row, plus an `anomalies` list and summary totals.

The database stores whole points. The default conversion truncates fractional points toward zero, matching the integer transaction-record representation. If an authoritative system specifies another posting convention, provide the supported `rounding` option and describe it in the customer response.

## Meaningful validation

Before relying on an output, confirm that:

- `input_errors` is empty;
- all intended posted transactions appear in `reviews`;
- known exclusions override a `Green` category;
- SaaS rows without subscription age are `indeterminate`, not called errors;
- return/credit rows are `indeterminate` unless an original transaction/rate is supplied; and
- every listed anomaly has a nonzero `difference_points` and an explicit policy basis.

Treat missing fields and unrecognized cards as unsupported rather than guessing.