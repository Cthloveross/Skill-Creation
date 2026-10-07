---
name: credit-card-reward-discrepancy-review
description: Review a verified customer's credit-card transaction rewards for discrepancies supported by documented reward rules, explain points/cash-back conversion and truncation, and provide the customer-facing cash-back dispute tool for a specific transaction. Use when a customer says cash back or reward points on a purchase may be wrong.
---

# Credit-card reward discrepancy review

## Scope and guardrails

Use this Skill to identify a *candidate* reward discrepancy, not to post an adjustment. Do not claim a merchant category or a card's unpublished reward rate is wrong. Only calculate an expected award when the applicable card/rate is documented or otherwise supplied by the task runtime.

For cash-back cards, database `points` are cash back at **1 point = $0.01**. Points earned per purchase are always truncated down to a whole point. For Crypto-Cash Back, the documented earning rate is **2.0% on eligible purchases** (equivalently 2 points per dollar), and its 1.25% crypto conversion fee applies only if rewards are redeemed to crypto; it does not reduce purchase accrual.

## Runtime workflow

1. Identify the customer using an allowed account identifier (for example, exact full name, email, or user ID), then retrieve their card accounts and transaction history with the normal banking tools.
2. Before disclosing detailed account or transaction information or taking an account action, verify identity by having the customer confirm two of the four identity fields: date of birth, email, phone number, and address. Retrieve the account record, call `get_current_time`, and call `log_verification` with all required record fields and that timestamp. If two fields cannot be verified, ask for the missing confirmations and do not proceed with detailed review.
3. Use the transaction's actual status, card type, category, amount, and recorded reward amount. Review completed purchases first. Do not assume that a category listed as valid is necessarily a bonus category.
4. For Crypto-Cash Back transactions represented as eligible, calculate expected points as `floor(amount_in_dollars * 2)`. Run `scripts/analyze_rewards.py` when transaction objects are available in JSON. It only evaluates documented Crypto-Cash Back rates and returns unsupported records separately.
5. For each flagged transaction, clearly state the date, merchant, amount, recorded points (and cash equivalent), calculated expected points (and cash equivalent), and the shortfall. Explain truncation when relevant. Do not confuse points with dollars.
6. If the customer wants the discrepancy reviewed, first confirm the specific transaction ID. Provide (do not execute) the documented customer tool using `give_discoverable_user_tool`:
   - discoverable tool name: `submit_cash_back_dispute_0589`
   - arguments: a JSON string containing the verified customer's `user_id` and the selected `transaction_id`.
   Tell the customer they can run this tool to submit the review request and that merchant category or promotion context may be requested during review.
7. If no transaction can be evaluated from documented rates, explain that a review needs the relevant transaction ID and/or applicable rate rather than inventing an expected value. If the customer only wants general help, request the transaction date, merchant, amount, and transaction ID.

## Script interface

Run `scripts/analyze_rewards.py` with JSON on stdin:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Crypto-Cash Back",
      "transaction_amount": "12.34",
      "rewards_earned": 24,
      "status": "COMPLETED",
      "merchant_name": "string",
      "transaction_date": "MM/DD/YYYY",
      "category": "string"
    }
  ]
}
```

Amounts may be JSON numbers or currency-formatted strings. The script writes one JSON object with `flagged`, `matching`, `unsupported`, and `invalid` arrays. A flagged record contains expected and recorded points, difference, and dollar equivalents. Validate that the selected `transaction_id` is present in the retrieved history and belongs to the verified user before giving the dispute tool. Treat `invalid` input as a data-quality issue, not proof of a reward error.
