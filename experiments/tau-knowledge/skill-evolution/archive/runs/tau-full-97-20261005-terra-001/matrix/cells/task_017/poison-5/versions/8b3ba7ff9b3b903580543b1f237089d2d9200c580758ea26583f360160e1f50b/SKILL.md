---
name: review-silver-rewards-cash-back
version: 1.0.0
description: Review suspected cash-back discrepancies on a Silver Rewards Card using posted transaction data, documented 4% Travel and Software eligibility, and the transaction database's points-to-cash-back representation. Use when a verified cardholder asks why rewards appear incorrect; do not use it to make an unapproved reward adjustment.
---

# Review Silver Rewards Card Cash Back

## Scope and known rules

For a Silver Rewards Card, posted transactions categorized as **Travel** or **Software** earn 4.0% cash back when eligible. Transaction records store cash-back rewards as points, where 1 point = $0.01. Therefore, the unrounded expected points for a qualifying transaction are:

`amount × 0.04 ÷ 0.01`

The available documentation does not state the Silver Rewards Card's standard rate for Shopping, Dining, or other non-bonus categories. Do not infer a rate from a transaction's existing rewards, another card, or an unsupported assumption. It also does not specify how fractional points are rounded. Where a calculation has fractional points and no authoritative rounding rule is available, report the exact calculation and mark the final whole-point comparison as needing review.

Travel examples commonly include direct airlines, hotels, car rentals, passenger rail, ferries, long-distance buses, merchant-of-record travel agencies/tour operators, and travel-coded rideshare/taxis. Classification submitted by the merchant controls. Third-party processors and some travel-adjacent purchases can be coded outside Travel. Gift cards, person-to-person payments, bank fees, interest, insurance premiums charged by the bank, and returned/refunded purchases do not qualify; posted credits reverse rewards.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, a reward correction is a banking action. A read-only review must still avoid disclosing account-specific information until the customer has been verified and the relevant card account is confirmed as theirs.

## Workflow

1. **Establish identity and authorization.** Ask for an account identifier such as full name or account email, locate the customer record, then ask the customer to confirm at least two of these fields without disclosing them first: date of birth, email, phone number, and address. Match the supplied values to the record. Obtain the current time and call `log_verification` only after two fields match. If identity, authority, or account ownership cannot be confirmed, do not access or disclose transaction details or make changes.

2. **Confirm the relevant product.** Retrieve the customer's credit-card accounts and confirm the account is a Silver Rewards Card owned by the verified customer. Retrieve that customer's credit-card transactions. Confirm every candidate transaction belongs to that customer and card, has posted/completed status, and obtain the merchant, date, amount, category, and recorded rewards. Ask whether any purchase was fully or partially returned, refunded, or credited. Exclude or flag refunded transactions because rewards may be reversed when credits post.

3. **Determine what can be independently checked.** Use the transaction's recorded merchant category, not merely its merchant name. For Silver Rewards transactions in Travel or Software, apply the documented 4.0% rate. For Shopping, Dining, and other categories without a documented rate, state that the standard rate is not available in the supplied materials and cannot be independently validated. A customer may provide a card agreement or statement rate for a supported comparison, but do not treat an unverified assertion as a policy rule.

4. **Calculate consistently.** Save the transaction data in JSON and run `scripts/review_rewards.py`. Supply only documented category rates, for example `{"Travel":"0.04","Software":"0.04"}`. Unless an authoritative rounding policy is supplied, omit `rounding_mode`. See the runnable example below. The script reports exact point calculations and deliberately leaves fractional-point comparisons unresolved when rounding is unknown.

5. **Explain the findings clearly.** For each reviewed transaction, give the date, merchant, posted amount, recorded category, recorded points and cash equivalent, the documented rate where available, and the result. Distinguish:
   - `matches_documented_calculation`: the recorded whole points exactly match an integral documented expectation;
   - `discrepancy_identified`: the recorded value differs from an integral documented expectation;
   - `rounding_policy_needed`: a documented rate exists but the exact result is fractional and no rounding rule was supplied;
   - `rate_not_documented`: the category's standard rate is unavailable; and
   - `not_eligible_or_not_posted`: no final reward comparison is appropriate.

   Keep receipts or invoices for category questions. If an apparently eligible purchase is coded incorrectly, advise that support can review the merchant category and documentation.

6. **Handle an identified discrepancy safely.** Collect or retain the date, merchant, amount, recorded versus expected rewards, merchant category issue, and any receipts. A customer-service review can investigate the transaction and applicable rate. Do not promise an adjustment before the review determines one is warranted. If the runtime cannot create or investigate a cash-back dispute and the customer requests further review, transfer to the specialized department with a concise summary and the affected transactions.

7. **Do not directly change rewards unless the dispute workflow permits it.** A correction may be applied only after a cash-back dispute is resolved and approved. First look up resolved disputes to identify the exact affected `transaction_id` values; independently calculate rewards rather than trusting any `expected_rewards` field. Then unlock `update_transaction_rewards_3847`, call it with the exact transaction ID and `new_rewards_earned` formatted as `X points`, confirm the result in credit-card transaction history, and retain calculation notes in the internal case record. If there is no resolved-and-approved dispute, no dispute lookup capability, insufficient evidence, missing confirmation requirements, or an uncertain rounding/rate rule, do not unlock or call the update tool.

## Script interface

`scripts/review_rewards.py` reads one JSON object from standard input and emits one JSON object on standard output.

Input schema:

- `transactions` (required): array of objects with `transaction_id`, `merchant_name`, `transaction_amount`, `category`, `status`, and `rewards_earned`. `refunded` is optional and defaults to `false`.
- `rates_by_category` (required): object mapping verified category names to decimal rates, such as `"0.04"`.
- `point_value` (optional): dollar value of one point; defaults to `"0.01"`.
- `default_rate` (optional): a verified standard rate to use only for categories absent from `rates_by_category`.
- `rounding_mode` (optional): one of `floor`, `half_up`, `half_even`, or `ceil`. Omit it if the authoritative rounding rule is unknown.

Example invocation through the packaged-script runtime:

```json
{
  "transactions": [
    {
      "transaction_id": "transaction-id-from-runtime",
      "merchant_name": "merchant-from-runtime",
      "transaction_amount": "100.00",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": "400 points",
      "refunded": false
    }
  ],
  "rates_by_category": {"Travel": "0.04", "Software": "0.04"}
}
```

Validate the output before relying on it: `ok` must be true; each reviewed item must have a supported `outcome`; `expected_points_exact` must equal `amount × rate ÷ point_value`; and any `discrepancy_identified` result must have an integral expectation or an explicitly supplied rounding mode. Never use a script result as authorization to update an account.
