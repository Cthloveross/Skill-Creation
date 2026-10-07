---
name: recent-credit-card-activity
version: 1.1.0
description: Retrieve and clearly summarize recent posted transactions for a specified credit card, including its current balance, Silver Rewards cash-back representation, and safe escalation of suspected unauthorized-card activity. Use when a customer asks what was charged, wants to review a card balance or rewards, or identifies an unrecognized card charge.
---

# Recent Credit Card Activity

## Purpose
Provide an accurate, readable view of activity for the requested card without mixing it with the customer's other cards. This Skill is read-only: it does not dispute, reverse, secure, cancel, replace, or otherwise alter a card or transaction.

For a Silver Rewards Card, completed Travel or Software transactions can be reviewed against the documented 4% cash-back rate. The transaction database labels rewards as `points`, but Silver Rewards is a cash-back card: **1 stored point = $0.01 in cash back** when redeemed as a statement credit or checking-account credit.

## Required runtime data
Obtain fresh data with the normal banking tools:

1. Identify the customer from information they provide.
2. Complete any identity-verification requirements in the active workflow before revealing account-specific information. If two identity fields and a verification log are required, obtain them, confirm them, obtain the current timestamp, and create the required log.
3. Retrieve the customer's credit-card accounts and select the account whose `card_type` exactly matches the requested card.
4. Retrieve the customer's credit-card transactions.
5. Obtain current time only when a recency cutoff or verification timestamp requires it.

A name lookup is not itself verification. Never use values from an earlier conversation instead of fresh runtime data, and do not disclose unrelated accounts or unnecessary personal information.

## Procedure

1. **Confirm scope.** Use the card the customer named. If they have not named one and have multiple cards, ask which card they mean. If an exact requested card is absent, say it could not be found; never substitute another card.
2. **Define “recent.”** Honor an explicit date range or requested count. Otherwise show the 10 most recent posted/completed transactions, state the displayed date range, and offer older activity or a statement period. If the customer asks for more, retrieve or present the next older card-scoped posted records in newest-to-oldest order; do not repeat records already shown.
3. **Keep only posted activity.** Reports contain items once they post. Use `COMPLETED` and `POSTED` only unless the customer specifically requests separately retrieved pending activity. Do not include pending items in posted totals.
4. **Prepare a deterministic report.** Normalize tool output and run `scripts/summarize_card_activity.py`. It exact-matches the card type, sorts newest first, calculates the displayed-charge total, and generates Silver rewards-review cues.
5. **Give the customer a clear report.** Include the card name, currently reported balance if available, and for every displayed transaction: date, merchant, amount, category, and posted/completed status. Include the displayed-list total and date range.
6. **Explain balance versus activity.** State that the displayed activity total is not expected to equal the current balance. A balance may include older purchases, payments, credits, fees, and statement timing.
7. **Represent Silver rewards correctly.** Whenever discussing Silver Rewards earnings or a possible rewards discrepancy, explicitly say that stored points represent cash back at **1 point = $0.01**. Show both units when useful: `N points ($X.XX cash back)`. For a four-percent comparison, describe the reference in points and cash-back dollars. For example, a transaction's recorded and expected values must be computed from the runtime transaction amount; do not invent an adjustment. A review flag is only a cue, not proof of misclassification or money owed.
8. **Explain qualified-rate limits.** Travel and Software purchases normally earn 4% only when the merchant's submitted category qualifies. Rewards are calculated after posting, and merchant coding, changes, refunds, or later adjustments can affect final rewards. Offer a category/rewards review and advise the customer to retain receipts or invoices.
9. **Handle suspected fraud safely.** If the customer identifies a charge as unrecognized or asks to secure, cancel, or replace their card:
   - acknowledge the urgency and concern;
   - clearly state: **“I cannot secure or cancel the card, issue a replacement, or file a dispute from this chat.”** Adapt wording only if a completed action is actually established by an available tool result;
   - say that a specialist transfer is needed to protect the card and address the suspected unauthorized charge;
   - call `transfer_to_human_agents` with reason `fraud_or_security_concern` and a concise factual summary after the customer accepts or requests the handoff;
   - only after a successful transfer result, tell the customer they have been transferred to a human agent. Do not claim that a cancellation, replacement, security hold, or dispute has been completed.
10. **Do not initiate a dispute from a balance concern alone.** Ask the customer to identify any unrecognized transaction. A higher-than-expected balance is not itself proof of fraud or error.

## Helper input and output

From the package root:

```sh
python3 scripts/summarize_card_activity.py < runtime_input.json
```

The script reads one JSON object from standard input and writes one JSON object to standard output. It uses only the Python standard library.

Input schema:

```text
{
  "card_type": string,                         # required exact requested card type
  "accounts": [
    {"card_type": string, "current_balance": number|string, "reward_points": integer|string}
  ],
  "transactions": [
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
  "recent_count": integer,                     # optional; default 10
  "start_date": date string,                   # optional inclusive filter
  "end_date": date string,                     # optional inclusive filter
  "posted_statuses": [string]                  # optional; default COMPLETED and POSTED
}
```

Currency values may be decimal numbers or currency-formatted strings. A date range takes precedence over `recent_count` and returns every matching posted transaction in that range.

On success the output has `ok: true`, the selected `account`, card-scoped `transactions` in newest-first order, `displayed_total`, inclusive `date_range`, and `rewards_review_flags`. Monetary values are strings with two decimals. Silver account and review fields include cash-back equivalents where applicable. On malformed input, an absent or ambiguous account, or an unnormalizable record, the output has `ok: false` and an `error`; correct the data or ask a targeted clarification rather than guessing.

## Validation before sending

- Confirm the selected account and every disclosed transaction exactly match the requested card type.
- Confirm transactions are newest first, have allowed posted statuses, and the displayed total equals their amounts rather than the current balance.
- Do not characterize a limited display as a complete statement.
- For any Silver points or rewards analysis, include the $0.01-per-point cash-back meaning, not points alone.
- Treat a rewards flag as a possible review item, never a promised adjustment.
- For fraud/security requests, perform the transfer workflow and make no unsupported completion claim.
