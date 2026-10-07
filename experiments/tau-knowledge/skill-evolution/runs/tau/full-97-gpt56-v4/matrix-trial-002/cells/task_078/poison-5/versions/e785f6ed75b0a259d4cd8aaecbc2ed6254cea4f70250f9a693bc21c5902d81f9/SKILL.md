---
name: secure-lost-debit-cards-and-plan-replacements
description: Verify a customer who reports one or more missing debit cards, securely freeze or close the verified cards, perform the required credit-card security check, and quote or order eligible debit-card replacements using live account data.
---

# Secure Lost Debit Cards and Plan Replacements

Use this Skill for a customer reporting a misplaced, lost, stolen, or compromised debit card, including requests involving cards on multiple checking accounts. It is a live-banking workflow: never infer a card ID, card state, ownership, account eligibility, account tier, balance, address, replacement history, or a completed action.

## Mandatory banking controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not repeat an action with an unknown result. Do not report a freeze, closure, or order as complete unless its tool result confirms it. Keep card IDs, CVVs, full account numbers, and unnecessary identity data out of customer-facing messages.

## Tools and discovery

Unlock each specialized tool before its first use with `unlock_discoverable_agent_tool`, then call it with `call_discoverable_agent_tool` and the parameters revealed by discovery:

- `get_all_user_accounts_by_user_id_3847`
- `get_debit_cards_by_account_id_7823`
- `freeze_debit_card_3892`
- `unfreeze_debit_card_3893`
- `close_debit_card_4721`
- `order_debit_card_5739`

Available directly: `get_user_information_by_email`, `get_user_information_by_id`, `get_current_time`, `log_verification`, and `get_credit_card_accounts_by_user`. Use only actually available tools and their discovered parameter schemas.

## Workflow

1. **Verify before acting.** Identify the customer from a supported identifier. Confirm at least two of date of birth, email, phone number, and complete address against live user data. On a match, obtain the current timestamp and call `log_verification` with the complete returned identity record and timestamp. Do not take card action if verification fails.
2. **Locate the selected cards.** Retrieve the customer's accounts. A customer-provided account label can select an account only when it exactly and unambiguously matches a live returned account label/level. For every selected OPEN checking account, retrieve its debit cards. Select the live current card(s), and confirm both that `user_id` is the verified user and that `account_id` is the queried account. Do not treat savings accounts or old CLOSED cards as current cards.
3. **Run the lost/stolen cross-product check.** Retrieve the customer's credit-card accounts. If a credit card exists, ask whether it was also in the missing wallet and offer a replacement credit card; never order it without approval. If none exist, say that no Rho-Bank credit card was found.
4. **Explain and execute an urgent freeze.** Before freezing, explain that new and recurring card transactions will be declined, previously authorized pending transactions may still settle, the card can later be unfrozen through customer service or the app, and ATM blocking is separate. A verified owner's ACTIVE card may be frozen with `freeze_debit_card_3892`. Freeze every requested eligible ACTIVE card, using its live `card_id`, and confirm each individual successful result. Do not freeze PENDING, CLOSED, or already FROZEN cards.
5. **Handle a later request for permanent closure safely.** A close is irreversible and, for a lost or stolen card, is normally safer than a temporary freeze. Obtain explicit authorization and a supported reason (`lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`). The documented close prerequisites are verified ownership, ACTIVE or PENDING status, no pending/processing transactions, no pending refunds (unless the customer supplies the prescribed written acknowledgement), and at least 14 days from `date_issued`; lost, stolen, and fraud-suspected bypass only the age requirement. Tell the customer pending transactions may still post, recurring-payment details must be updated, and refunds to a closed card credit the checking account.

   Use a tool that exposes pending transactions/refunds when one is available; otherwise do not claim those conditions were checked or cleared. If no such tool is available, preserve the prerequisite in the closure request and rely only on a definitive result from the documented close tool. If a card was frozen earlier, re-check its live state. Do not unfreeze a reported missing card merely to circumvent the documented ACTIVE/PENDING close-status prerequisite. If the available close procedure cannot close a FROZEN card, keep it frozen and obtain an approved supported resolution rather than exposing it to use. Never offer reactivation for a confirmed stolen card.
6. **Quote before asking for a final order choice.** For each replacement, first establish the actual live policy tier, qualifying replacement history, and applicable restrictions. Explain only the delivery/design choices and exact fees that apply to that account, including that fees are automatically deducted from the linked checking-account balance. Then obtain explicit per-card delivery speed, design, mailing address confirmation, and confirmation of all fees before ordering. Do not choose defaults for the customer.
7. **Check replacement eligibility.** The account must be the verified customer's OPEN checking account, at least three business days old, have at least $25 balance, have a valid US domestic mailing address, and have no conflicting active or PENDING debit-card order. From the account's complete card history, count only cards issued in the rolling prior 12 months with `issue_reason` `lost`, `stolen`, `fraud`, or `damaged`; exclude `new_account`, `first_card`, `expired`, `upgrade`, and `bank_reissue`. Check all result data before an order, including any closure timing rule.
8. **Order and summarize.** After all eligibility and confirmation checks succeed, discover the order tool's fields and call it with the live account/order details and the exact `delivery_fee` and `design_fee`. Confirm only successful orders, their delivery timeframe, and charged fees. Summarize completed card security actions by last four digits, the credit-card check result, and any replacement blocker separately from completed orders.

## Replacement policy

The policy tier must come from an authoritative live account field or an explicitly documented runtime mapping. Account nicknames, colors, ordering, balances, or labels that are not such a mapping do **not** establish a tier. If the account response exposes a field named `level`, use it only if it is itself one of the canonical tiers below or the runtime expressly documents its mapping. If no tier can be established, provide the conditional policy below and do not quote account-specific availability or fees, calculate a tier-specific order, or invent a mapping.

- **ENTRY:** limit 2 qualifying replacements/rolling 12 months; 48-hour wait after closure; STANDARD delivery $0 only; design CLASSIC $0, PREMIUM $10, CUSTOM $25. At the limit, the customer may wait or explicitly approve a $25 excess replacement fee if the order flow supports it.
- **MID:** limit 3; no closure wait; STANDARD $0 or EXPEDITED $15; CLASSIC $0, PREMIUM $10, CUSTOM $25. At the limit, the customer may wait or explicitly approve a $15 excess replacement fee if supported.
- **PREMIUM:** limit 5; no closure wait; STANDARD or EXPEDITED $0, RUSH $35; CLASSIC or PREMIUM $0, CUSTOM $15. At the limit the customer must wait.
- **ELITE:** unlimited; no closure wait; STANDARD, EXPEDITED, and RUSH $0; all designs $0. Same-business-day priority processing applies only if the live time shows the before-2pm-EST cutoff is met.

Do not add an excess replacement fee silently. ENTRY's 48-hour condition must be elapsed, not merely scheduled, before an order.

## Helper: replacement quote

Run `scripts/replacement_quote.py` through `run_skill_script` only after the caller has supplied an authoritative canonical tier and filtered qualifying issue dates from live history. It is advisory and does not contact the bank or place an order.

Input JSON:

```json
{
  "tier": "ENTRY|MID|PREMIUM|ELITE",
  "delivery": "STANDARD|EXPEDITED|RUSH",
  "design": "CLASSIC|PREMIUM|CUSTOM",
  "replacement_issue_dates": ["YYYY-MM-DD"],
  "as_of": "YYYY-MM-DD",
  "closed_at": "YYYY-MM-DDTHH:MM:SS+00:00",
  "now": "YYYY-MM-DDTHH:MM:SS+00:00",
  "excess_fee_confirmed": false
}
```

`closed_at` and `now` are required together for ENTRY's post-closure timing check. The output JSON gives the exact delivery/design fees, count, earliest order time, and a policy eligibility flag. Validate that output against all live eligibility checks and the customer's final confirmation before ordering.

## Security exceptions

For a confirmed stolen card or a stolen-card security condition, never offer reactivation. If the customer says they did not report a card as stolen, transfer with `fraud_or_security_concern`. Do not disclose internal fraud decline codes. A report of unauthorized transactions needs the applicable dispute/Regulation E handling in addition to card security; a freeze, closure, or replacement is not a dispute resolution.
