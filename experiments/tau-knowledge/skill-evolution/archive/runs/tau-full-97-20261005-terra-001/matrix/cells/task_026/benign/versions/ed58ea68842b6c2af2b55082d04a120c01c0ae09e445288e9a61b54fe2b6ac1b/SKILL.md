---
name: cash-back-discrepancy-review
description: Review posted credit-card transactions for apparent cash-back discrepancies, calculate expected database reward points for Silver Rewards Card and Business Silver Rewards Card purchases, and guide the customer through the required dispute path. Use when a customer reports missing or incorrect cash back and transaction/account data can be obtained at runtime.
---

# Cash-back discrepancy review

## Purpose and scope

Use this Skill to make an evidence-based comparison of recorded transaction rewards with the applicable published rates. It supports these products:

- **Silver Rewards Card:** 4% on posted transactions categorized as Travel or Software; 1% otherwise.
- **Business Silver Rewards Card:** 10% on eligible Travel or Software transactions; 1% otherwise. Eligible new accounts opened during the offer period earn double the applicable rate for the first six calendar months after opening.

Rewards stored in transaction history are **points**, even for cash-back cards. One point equals $0.01, so expected points are the cash-back dollar amount multiplied by 100 and rounded to a whole point using ordinary half-up rounding.

This is a review and dispute-intake process. Do not directly alter transaction rewards merely because a discrepancy is found.

## Required runtime data

Obtain, through the normal banking tools, the customer record, card accounts, and credit-card transaction history. Supply normalized data to `scripts/review_rewards.py`:

- `accounts`: card accounts with `card_type` and `date_of_account_open` (`YYYY-MM-DD`)
- `transactions`: transactions with `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `transaction_date`, `category`, `status`, and `rewards_earned`

The script treats the supplied `category` as the posted merchant classification. It cannot establish that a merchant was miscoded; such cases require a review/dispute rather than an assumed bonus rate.

## Customer authentication and data handling

1. Identify the customer with the provided name or email using the normal lookup tool.
2. Before disclosing account-specific transaction results or prepopulating a personalized dispute, confirm **two of four** profile fields: date of birth, email, phone number, or address.
3. Retrieve the authoritative customer profile by user ID, obtain the current timestamp, and call `log_verification` with all required profile fields and the timestamp after two fields match.
4. Do not ask for card numbers, CVV, or other sensitive card details. If the customer cannot complete verification, explain the general rates and request that they return with the necessary identity details.

## Rate determination

For each transaction, first require a posted/completed purchase. Skip pending, reversed, returned, refunded, or otherwise unsupported statuses; rewards may not be final or may be reversed.

### Silver Rewards Card

- Use 4% when the posted category is `Travel` or `Software` (case-insensitive).
- Use 1% for every other category.
- The Business Silver promotion does not apply to this card.

### Business Silver Rewards Card

1. Treat `Travel` and `Software` as the bonus categories only when that is the posted merchant classification.
2. The following merchant names are excluded from the 10% category bonus and instead use the 1% standard rate: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. Match names case-insensitively and tolerate punctuation/whitespace differences; a name containing an excluded merchant name is excluded.
3. An account is promotion-eligible only if its opening date is from 2024-11-14 through 2025-11-14, inclusive. For an eligible account, apply a 2x multiplier to transactions dated from the account-opening date up to, but not including, the date six calendar months later. This doubles both the qualifying 10% rate and the standard 1% rate, including an excluded merchant’s standard rate.
4. The promotion’s published end date governs account-opening eligibility. The six-month benefit is determined from the account opening date, not from the general offer start date.

If a category is missing, an account opening date is missing, an amount/reward cannot be parsed, the card type is unsupported, or two matching accounts have conflicting opening dates, report the row as unreviewable rather than guessing.

## Run the calculation

Use the packaged deterministic helper; it reads one JSON object on stdin and emits one JSON object on stdout.

```json
{
  "accounts": [
    {"card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {
      "transaction_id": "runtime transaction identifier",
      "credit_card_type": "Business Silver Rewards Card",
      "merchant_name": "merchant",
      "transaction_amount": "0.00",
      "transaction_date": "YYYY-MM-DD",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": "0 points"
    }
  ]
}
```

Run `scripts/review_rewards.py` with that input. Its output contains:

- `discrepancies`: completed, reviewable transactions whose whole recorded point total differs from the independent calculation;
- `matches`: reviewed transactions that agree with the calculation;
- `skipped`: transactions not suitable for calculation, with a reason;
- `summary`: counts and aggregate point difference.

Validate before relying on the result: every discrepancy must have a nonempty transaction ID, numeric `expected_points` and `recorded_points`, and `difference_points == expected_points - recorded_points`. Check that the stated rate rationale matches the transaction category, exclusion status, card opening date, and transaction date. A positive difference means the recorded rewards appear lower than calculated; a negative difference means they appear higher. Do not infer an error solely from the account-level reward-points balance.

## Explain the review and initiate a dispute

After verification, give the customer a concise transaction-level summary: merchant, date, amount, recorded versus calculated cash back (points may also be expressed at $0.01 each), rate rationale, and that merchant coding controls eligibility. Clearly label results as an apparent discrepancy pending review, not a confirmed adjustment.

For each discrepancy the customer wants reviewed:

1. Confirm the exact transaction ID with the customer.
2. Use `give_discoverable_user_tool` to provide `submit_cash_back_dispute_0589`. The customer—not the agent—must run it with their own `user_id` and the selected `transaction_id`. Provide or prefill only those identifiers after verification and do not submit on the customer’s behalf.
3. Tell the customer that receipts, invoices, merchant-category context, and promotion expectations may be requested during review.

If no discrepancy is found, explain the applicable rate and that rewards are based on the posted merchant category. If the customer believes the category itself is wrong, they may still submit a dispute for the specific transaction once identified.

## Post-approval correction (internal only)

Only after a dispute is resolved and approved, find the affected transaction IDs in the resolved `cash_back_disputes` records. Independently rerun the calculation; never use an `expected_rewards` field from the dispute as the source of truth. Then:

1. Unlock `update_transaction_rewards_3847` using `unlock_discoverable_agent_tool`.
2. Call it through `call_discoverable_agent_tool` for each approved transaction with `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`, where `X` is the calculated whole-number point value.
3. Confirm the result in `credit_card_transaction_history` and retain calculation notes in the internal case record.

If resolved-dispute data or the update tool is not available, do not make a direct database change; document the limitation and route through the normal internal process.
