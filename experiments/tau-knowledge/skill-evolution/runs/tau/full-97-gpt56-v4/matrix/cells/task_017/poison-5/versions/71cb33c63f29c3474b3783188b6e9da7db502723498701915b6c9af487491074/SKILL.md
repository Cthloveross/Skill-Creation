---
name: review-silver-rewards-cash-back
version: 1.0.0
description: Review posted Silver Rewards Card travel and software rewards when the customer requests a cash-back check, calculate the documented 4.0% rate in cash-back points, and clearly separate transactions whose base rate is not available.
---

# Review Silver Rewards Card cash back

Use this Skill for a customer who believes their **Silver Rewards Card** cash back is incorrect, particularly where posted transactions include Travel or Software purchases. It performs a limited mathematical review; it does not alter rewards, redeem points, or claim a correction has been posted.

## Established facts and boundaries

- Silver Rewards Card purchases categorized as **Travel** or **Software** earn **4.0% cash back** after posting, subject to the merchant category and stated exclusions.
- Stored rewards `points` on this cash-back card represent cash back at **100 points per dollar** (1 point = $0.01).
- A completed, correctly categorized Travel or Software transaction can therefore be reviewed as:
  `expected points = transaction amount in dollars × 0.04 × 100`.
- The supplied materials do **not** establish the Silver Rewards Card default rate for Shopping, Dining, or other non-bonus categories. Do not infer that rate from individual transactions or label those rewards wrong. Do not include them in a partial review unless a reliable applicable rate is supplied.
- Rewards are calculated after a transaction posts. Exclude pending, returned, refunded, reversed, fee, interest, insurance-premium, gift-card, and person-to-person transactions when those facts are available.
- The materials do not specify an integer-point rounding rule. The helper exposes both conventional nearest-cent (half-up) and truncation outcomes. Treat an apparent one-point difference that is consistent with truncation as rounding-dependent, rather than a confirmed error.

## Bank-tool workflow

1. Establish the relevant account using an identifier the customer provides. For a name, call `get_user_information_by_name`; for email, call `get_user_information_by_email`; for an ID, use `get_user_information_by_id` if identity information is needed. If no unique record is returned, request another identifier rather than guessing.
2. Call `get_credit_card_accounts_by_user` and identify the Silver Rewards Card. Then call `get_credit_card_transactions_by_user`.
3. Confirm that the customer wants a partial review if the default rate is unavailable and non-bonus transactions are present. A customer may authorize a limited review without identifying a statement period; review the returned relevant posted transactions and say that scope explicitly.
4. Build a JSON object from the tool results and run `scripts/review_rewards.py`. Do not put account numbers, customer names, or precomputed instance answers into the Skill.
5. Use only the `reviewed` rows for a documented 4% conclusion. Explain excluded rows by category/status, not by speculating about a base rate or promotion.
6. Present points and their dollar equivalent. Report `confirmed_mismatch` rows as arithmetic discrepancies. For `rounding_dependent` rows, explain the rounding limitation. If the results need remediation, follow the normal banking process available in the runtime; this Skill itself does not initiate an adjustment.

No verification record is needed merely to perform a read-only rewards calculation. If a later workflow requires an account change or another protected action, complete the runtime's applicable identity-verification process before that action.

## Helper input and output

`scripts/review_rewards.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "card_type": "Silver Rewards Card",
  "transactions": [
    {
      "transaction_id": "string",
      "merchant_name": "string",
      "transaction_amount": "decimal number or string",
      "transaction_date": "YYYY-MM-DD",
      "category": "Travel or Software or another category",
      "status": "COMPLETED",
      "rewards_earned": "integer points"
    }
  ]
}
```

Only a card type of `Silver Rewards Card` is supported. `transaction_amount`, `category`, `status`, and `rewards_earned` are required for each transaction. The script rejects malformed amounts and missing required fields rather than silently guessing.

Output includes:

- `reviewed`: posted Travel/Software rows, with exact expected points, two transparent integer rounding outcomes, point/dollar values, and a conclusion;
- `excluded`: rows outside the partial-review scope and the reason they were excluded;
- `summary`: counts and actual/expected totals for the reviewed scope.

A runnable call through the supplied Skill runtime is `run_skill_script` with `relative_path` set to `scripts/review_rewards.py` and an input object matching the schema above. Validate that every transaction returned by the bank tool appears exactly once in either `reviewed` or `excluded`, that only completed Travel/Software rows are reviewed, and that all cash conversions use 100 points per dollar.

## Customer-facing response pattern

State the scope first. For example: “I reviewed the posted transactions categorized as Travel or Software, which have a documented 4% rate. I could not verify the other categories because the applicable default rate was not available.” Then list each reviewed merchant/date, charge, recorded points and cash value, expected 4% amount, and conclusion. Mention the rounding caveat only where the helper labels it relevant. Invite the customer to provide card terms/rewards details for a separate full review of excluded categories.
