---
name: recent-credit-card-activity
version: 1.0.0
description: Retrieve and clearly summarize recent posted transactions for a specified credit card, including the current balance and cautious review of Silver Rewards Card enhanced-category rewards. Use when a customer asks what was charged, wants to review a balance, or asks for recent card activity.
---

# Recent Credit Card Activity

## Purpose
Provide an accurate, readable view of activity for the requested card without mixing it with the customer's other cards. This Skill is read-only: it does not dispute, reverse, or otherwise alter transactions.

For a Silver Rewards Card, it can also flag a completed transaction categorized as `Travel` or `Software` whose recorded rewards appear materially below the documented 4% enhanced rate. Rewards in the transaction data are stored as points; for cash-back cards, 1 point represents $0.01 in cash back.

## Required runtime data
Obtain fresh data using the normal banking tools:

1. Identify the customer using the information they provided.
2. Retrieve the customer's credit-card accounts and select the account whose `card_type` exactly matches the requested card.
3. Retrieve the customer's credit-card transactions.
4. Obtain the current time when a recency cutoff is needed.

Do not expose account activity to someone who has not met any authentication requirements applicable to the active support workflow. A name used for lookup is not itself proof of verification. If the workflow requires two identity fields, confirm them and create the required verification log using the normal tools before disclosing account-specific details.

Never use account, transaction, balance, or customer values embedded in an earlier conversation as a substitute for fresh runtime data.

## Procedure

1. **Confirm scope.** Identify the card the customer named. If they did not specify one and have multiple accounts, ask which card they mean. If the requested card is absent, say that it could not be found; do not substitute another card.
2. **Define “recent.”** Honor an explicit requested date range or number of transactions. Otherwise, use the 10 most recent posted/completed transactions and state the date range shown. Offer to show older activity or a particular statement period. Do not call a limited list a complete statement.
3. **Keep only posted activity.** The supplied reporting guidance says transaction reports contain items once they post. The helper accepts `COMPLETED` and `POSTED` by default. Mention pending activity only if it was separately retrieved; do not call it posted or include it in the posted total.
4. **Prepare the report.** Run `scripts/summarize_card_activity.py` with normalized tool results. It selects only the requested card, sorts newest first, calculates the displayed-charge total, and produces any eligible rewards-review flags.
5. **Respond concisely.** Include:
   - the card name and currently reported balance, if supplied;
   - each displayed transaction’s date, merchant, amount, category, and posted/completed status;
   - the displayed-list total and its date range;
   - a note that this total is only the displayed activity and is not expected to equal the full balance, which can include older purchases, payments, credits, fees, and statement timing.
6. **Handle a rewards flag carefully.** A flag is a review cue, not proof that a merchant was misclassified or that money is owed. Explain that Travel and Software transactions normally earn 4% when the merchant’s submitted category qualifies, that rewards are calculated after posting, and that merchant coding or later adjustments can affect the final amount. Offer the customer a category/rewards review and retain receipts or invoices if they want to pursue it.
7. **Do not initiate a dispute solely because the balance seems high.** Ask the customer to identify any unrecognized transaction if they want to dispute one. A balance concern alone does not establish fraud or an erroneous charge.

## Helper input and output

Run from the package root:

```sh
python3 scripts/summarize_card_activity.py < runtime_input.json
```

The script reads one JSON object from standard input and emits one JSON object on standard output. No third-party dependencies are required.

Input schema:

```text
{
  "card_type": string,                         # required exact requested card type
  "accounts": [                                # required; normalized account records
    {"card_type": string, "current_balance": number|string, "reward_points": integer|string}
  ],
  "transactions": [                            # required; normalized transaction records
    {
      "credit_card_type": string,
      "transaction_id": string (optional),
      "merchant_name": string,
      "transaction_amount": number|string,
      "transaction_date": "MM/DD/YYYY" | "YYYY-MM-DD",
      "category": string (optional),
      "status": string,
      "rewards_earned": integer|string (optional)
    }
  ],
  "recent_count": integer,                     # optional, default 10
  "start_date": date string,                   # optional inclusive filter
  "end_date": date string,                     # optional inclusive filter
  "posted_statuses": [string]                  # optional, default COMPLETED and POSTED
}
```

Amounts may be decimal numbers or currency-formatted strings. `start_date` and `end_date` accept the same two date formats. If a date range is provided it takes precedence over `recent_count`; the script returns every matching posted transaction in that range.

Successful output has `ok: true`, a selected `account`, `transactions` ordered newest first, a `displayed_total`, inclusive `date_range`, and `rewards_review_flags`. Monetary values are strings formatted to two decimals to avoid floating-point ambiguity. If input is missing, an account is absent or ambiguous, or records cannot be normalized, output has `ok: false` with a readable `error`; correct the runtime data or ask a targeted clarification rather than guessing.

## Validation before sending

- Verify the selected account and every displayed transaction exactly match the requested card type.
- Verify the list is newest-first and only includes allowed posted statuses.
- Ensure displayed total equals the sum of the displayed transaction amounts, not the account balance.
- If a rewards flag appears, describe it as a possible review item and do not promise an adjustment.
- Avoid revealing unrelated accounts, unnecessary personal information, or internal identifiers unless the customer needs a specific transaction reference.
