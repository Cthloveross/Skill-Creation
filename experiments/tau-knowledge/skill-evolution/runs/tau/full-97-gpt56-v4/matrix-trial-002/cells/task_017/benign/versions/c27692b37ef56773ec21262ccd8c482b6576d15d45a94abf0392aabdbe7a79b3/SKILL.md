---
name: review-and-submit-cash-back-dispute
description: Review posted Silver Rewards Card transactions for potential cash-back discrepancies, explain points-to-cash-back conversion and known rates, and give the customer the required self-service cash-back-dispute tool for a confirmed transaction. Use when a customer says their credit-card cash back looks wrong.
---

# Review and submit a cash-back dispute

## Scope and assumptions

Use this Skill for a customer who believes cash back on one or more credit-card purchases is incorrect. It supports a preliminary comparison, not a final adjudication. Merchant category, posting status, exclusions, promotions, and rounding can affect the final result.

For the Silver Rewards Card:

- Eligible posted travel and software/SaaS purchases earn **4.0%** cash back.
- Purchases outside top categories earn **1.0%** cash back.
- In transaction records, rewards labeled `points` are cash back at **100 points = $1.00**.
- The merchant's submitted category controls eligibility. Third-party processors can alter it.
- Gift cards, person-to-person payments, fees, interest, insurance premiums, and returned/refunded purchases generally do not qualify.

Do not collect card numbers, CVVs, or other sensitive card details.

## Runtime inputs and lookup

1. Identify the customer using the normal supported account lookup flow. If the customer is not yet identifiable, ask only for a supported account identifier such as their full name, email address, or user ID.
2. Retrieve the customer's credit-card account(s) and transaction history with the declared read-only banking tools.
3. Confirm the relevant account is a Silver Rewards Card before applying the rate comparison in this Skill. For another card type, do not infer its rates from this Skill; explain that its reward rules must be checked separately.
4. Focus on transactions that are posted/completed. Pending or non-posted transactions should be described as not final yet.
5. Confirm the exact `transaction_id` with the customer before offering a dispute action. If several transactions look unusual, list merchant, date, amount, category, recorded rewards, and transaction ID so the customer can select the purchase(s).

## Preliminary comparison

Use `scripts/review_cashback.py` for deterministic arithmetic after converting the retrieved transaction records into its JSON input schema. The script:

- uses 4% for `Travel` and `Software` categories and 1% for other supplied categories;
- calculates cash back to cents using decimal half-up rounding, then represents cents as whole points;
- reports comparisons as **estimates**, because an active promotion, an exclusion, or the official merchant classification may change the final outcome.

Run it as a packaged script with JSON on standard input. It emits JSON on standard output.

Example input shape (illustrative values only):

```json
{
  "card_type": "Silver Rewards Card",
  "transactions": [
    {
      "transaction_id": "transaction identifier from the account",
      "merchant_name": "merchant",
      "transaction_amount": "$12.34",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": "49 points"
    }
  ]
}
```

Interpretation:

- `reviewed` contains posted entries where an estimate could be produced.
- `potential_discrepancies` contains only entries whose recorded whole-point amount differs from the estimate.
- `not_final_or_unsupported` identifies skipped entries and why.
- An empty `potential_discrepancies` list does not prove there is no issue; it only means the supplied record agrees with the documented base-rate estimate.

Validate that each proposed dispute has a nonempty user ID and the transaction ID exactly as returned by the transaction-history tool. Never manufacture or shorten either identifier.

## Customer response and required action

Explain the results plainly, including that points are cash back (100 points equals $1.00). State the relevant documented rate only when the account and posted merchant category support it. For a potentially eligible transaction that received a lower rate, mention that merchant classification and promotions are reviewed and that a receipt or invoice may later be requested.

A cash-back discrepancy must be initiated by the customer, not by the agent. Once the customer confirms the exact transaction to dispute, call:

`give_discoverable_user_tool` with:

- `discoverable_tool_name`: `submit_cash_back_dispute_0589`
- `arguments`: a JSON string containing the confirmed customer's `user_id` and the exact confirmed `transaction_id`, for example `{"user_id":"<user-id>","transaction_id":"<transaction-id>"}`.

Tell the customer to run the provided tool for that specific purchase. Give a separate tool invocation only for each transaction the customer confirms they want to dispute. The submission may later request supporting context such as the expected category or promotion and receipts.

Do **not** call `submit_cash_back_dispute_0589` yourself, and do not directly edit transaction rewards. Reward correction is an internal follow-up only after a dispute has been resolved and approved.

## Suggested customer-facing wording

"I reviewed the posted rewards using the card's published base rates. Transaction rewards are shown as points, where 100 points equals $1.00 in cash back. The comparison is preliminary because the merchant's submitted category, exclusions, and any promotion are confirmed during review. If the transaction ID above is the purchase you want reviewed, please use the dispute tool I provided. Keep your receipt or invoice in case the review team requests it."

If no specific transaction has been selected, ask the customer which listed transaction ID they want reviewed or disputed rather than submitting every transaction automatically.
