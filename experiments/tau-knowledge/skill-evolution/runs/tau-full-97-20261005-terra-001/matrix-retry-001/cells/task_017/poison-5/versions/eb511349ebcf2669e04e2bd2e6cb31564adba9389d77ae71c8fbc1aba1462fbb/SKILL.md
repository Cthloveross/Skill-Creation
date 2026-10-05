---
name: review-and-correct-credit-card-cash-back
description: Review posted credit-card rewards for a verified account, independently calculate supported Silver Rewards Card travel/software earnings, identify discrepancies, and apply a correction only for transactions tied to a resolved cash-back dispute.
---

# Review and Correct Credit-Card Cash Back

Use this skill when a customer believes credit-card cash back is missing or incorrect and the runtime can retrieve card accounts and transactions. It supports review of the **Silver Rewards Card** where the applicable documented bonus rate is 4.0% on eligible **Travel** and **Software** purchases. It does not invent undocumented base rates, promotions, merchant recategorizations, dispute statuses, or account ownership.

## Mandatory banking controls

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow:

1. Before retrieving or discussing account-specific transactions, identify the customer using an allowed lookup and have them confirm at least two of the profile fields: date of birth, email, phone number, or address.
2. Match the supplied factors against the retrieved customer profile. Do not reveal profile values merely to solicit confirmation.
3. On a successful two-factor match, obtain the current time and call `log_verification` with the complete matched profile and timestamp. Treat the verified customer as authorized only for that customer's account.
4. If identity, authority, or account ownership cannot be confirmed, do not retrieve additional account information, disclose transaction details, or make a rewards change. Ask for acceptable verification information or use the applicable support/escalation path.
5. Before any rewards update, additionally verify that the transaction belongs to the verified customer and card, is posted/completed, the card and category are eligible under documented terms, the dispute is resolved, the proposed point value is independently calculated, and any runtime-required confirmation is satisfied. Balance, fees, limits, cutoffs, recipient, and card-detail checks must be performed when applicable; they do not substitute for the resolved-dispute requirement.

## Review procedure

1. Ask what period or transactions concern the customer. If they cannot identify any, explain that you can review the available posted recent history after identity verification.
2. Retrieve the verified customer's credit-card account(s), then their transaction history. Confirm the relevant card type and that every transaction evaluated is for the verified customer.
3. Evaluate only posted/completed transactions. Pending/authorization-only transactions must be reported as not yet final rather than treated as an error.
4. Supply the relevant card type and transaction records to `scripts/review_rewards.py`. The script accepts amounts as strings or JSON numbers, but preserving displayed decimal amounts as strings is preferred.
5. Interpret the results:
   - For a Silver Rewards Card, Travel and Software are supported bonus categories at 4.0%.
   - Database “points” on cash-back cards mean cash back at 1 point = $0.01. Thus 4.0% produces `purchase amount × 4` points before truncation.
   - Fractional rewards are always rounded down to a whole point **per purchase**.
   - A transaction marked as a known gift card, person-to-person payment, fee, interest, bank-charged insurance premium, or returned/refunded purchase is not a qualifying earning transaction. Returned/refunded purchase rewards are reversed when the credit posts.
   - Do not conclude that Shopping, Dining, or any other non-bonus Silver category is incorrect: the supplied policy does not state the Silver base rate. Mark these as `unsupported_rate` and explain that their applicable rate needs authoritative card terms or a case review.
   - Do not infer eligibility from merchant name. Use the posted merchant category. If the customer disputes that category, document the receipt/invoice and route it for category review.
6. Clearly tell the customer which supported transactions match the documented calculation, which have a discrepancy, and which cannot be conclusively evaluated with the available rates. Do not claim an adjustment has occurred unless the update and post-update confirmation both succeed.

## Correction procedure (restricted)

A detected discrepancy is not sufficient to change rewards.

1. Locate the customer’s **resolved** cash-back disputes in the `cash_back_disputes` data source and obtain the exact `transaction_id` values. Never use an `expected_rewards` field as the calculation source.
2. If the runtime does not expose a way to verify a resolved dispute, or no resolved dispute covers the transaction, do **not** unlock or call an update tool. Explain that the discrepancy needs the normal cash-back dispute/review process; collect the transaction date, merchant, amount, received versus expected rewards, and receipts where available.
3. Independently recompute the whole-point result using the documented rate and category. Run the helper with only transaction IDs confirmed by the resolved-dispute records in `resolved_dispute_transaction_ids`.
4. Only for an `approved_corrections` item produced by the helper and independently matched to the resolved dispute, unlock `update_transaction_rewards_3847`, then call it with exactly:
   - `transaction_id`: the confirmed transaction ID
   - `new_rewards_earned`: the helper's exact `"X points"` string
5. Retrieve `credit_card_transaction_history` again and confirm the stored reward value equals the requested whole-point value. Retain the transaction, category, formula, old value, new value, dispute reference, and confirmation outcome in the internal case record.
6. If the update fails or post-update value differs, do not retry blindly or represent success. Preserve the error and escalate through the available internal support path.

## Helper interface

Run:

```text
run_skill_script(relative_path="scripts/review_rewards.py", input_json={...})
```

Input JSON schema:

```json
{
  "card_type": "Silver Rewards Card",
  "transactions": [
    {
      "transaction_id": "string",
      "transaction_amount": "decimal amount",
      "category": "Travel|Software|other category",
      "status": "COMPLETED",
      "rewards_earned": "whole points or 'N points'",
      "returned_or_refunded": false,
      "is_gift_card": false,
      "is_p2p": false,
      "is_fee": false,
      "is_interest": false,
      "is_insurance_premium": false
    }
  ],
  "resolved_dispute_transaction_ids": ["IDs obtained from resolved dispute records"]
}
```

All transaction fields other than `transaction_id`, `transaction_amount`, `category`, `status`, and `rewards_earned` are optional boolean flags and default to false. `resolved_dispute_transaction_ids` defaults to an empty list. The script emits JSON with a `reviews` entry for every submitted transaction and `approved_corrections` only where a supported, completed, non-excluded transaction has a mismatch **and** its ID was supplied from a resolved dispute record.

Validate before using an output: `expected_points` must be an integer, `new_rewards_earned` must exactly match `"<expected_points> points"`, the card type must be Silver Rewards Card, category must be Travel or Software, status must be completed, no exclusion flag may be true, and the transaction ID must match both the account history and resolved dispute record. An empty `approved_corrections` list means no update is authorized.
