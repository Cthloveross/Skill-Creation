---
name: secure-lost-debit-cards-and-plan-replacements
description: Secure one or more debit cards reported lost, misplaced, or stolen; verify the customer, locate eligible checking accounts and cards, freeze or close cards as appropriate, perform the lost/stolen cross-product check, and prepare compliant replacement-card orders.
---

# Secure Lost Debit Cards and Plan Replacements

Use this Skill when a verified customer reports one or more debit cards missing or requests card freezes, closures, or replacement debit cards. It supports multiple checking accounts and must use live runtime data; never infer a card ID, account tier, balance, status, ownership, or replacement history.

## Mandatory banking controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not perform an action merely because it was requested. Obtain explicit confirmation when required, make only actions supported by the available banking tools, and report tool failures rather than guessing that an action completed. Never repeat an action whose result is unknown.

## Runtime tools to discover

Before calling a named specialized banking tool, unlock it with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` using the documented JSON arguments. The relevant tool names are:

- `get_all_user_accounts_by_user_id_3847` — list the user's accounts.
- `get_debit_cards_by_account_id_7823` — list cards for one checking account.
- `freeze_debit_card_3892` — freeze an ACTIVE debit card.
- `unfreeze_debit_card_3893` — unfreeze an eligible FROZEN debit card.
- `close_debit_card_4721` — permanently close an eligible card.
- `order_debit_card_5739` — order a debit card with selected fees and delivery/design details.

Use only tools that are available after discovery. The normal tools `get_user_information_by_email`, `get_user_information_by_id`, `get_credit_card_accounts_by_user`, `get_current_time`, and `log_verification` are available directly.

## End-to-end workflow

1. **Identify and verify the customer.** Locate the user from a supplied account email, user ID, or other supported identifier. Compare at least two of date of birth, email, phone number, and full address against live user information. After successful verification, get the current timestamp and call `log_verification` with all returned identity fields and that timestamp. Do not expose unnecessary sensitive values in the response.
2. **Locate every requested card.** Retrieve all accounts for the verified `user_id`. Match any customer-provided account nickname/color only if live account data makes the match unambiguous; otherwise ask for account IDs or card last four digits. For each relevant checking account, retrieve debit cards. Savings accounts are not debit-card eligible. Confirm every selected card's `user_id` equals the verified user and its `account_id` matches the queried account.
3. **Perform the lost/stolen security check.** For a reported lost or stolen debit card, retrieve the customer's credit-card accounts. If credit cards exist, explain the wallet-security concern and offer a replacement credit card; do not order one without the customer's approval. If none exist, record that no cross-product offer is needed in the response.
4. **Choose freeze versus permanent closure.** A freeze is temporary and requires verified ownership and an `ACTIVE` card. Explain that new and recurring transactions will be declined, already authorized pending transactions may settle, and the customer can later unfreeze; ATM blocking is separate. A lost or stolen card is normally safer to close permanently. Do not close a card unless the customer requests/authorizes closure and supplies or confirms the applicable reason.
5. **Freeze immediately when eligible.** For each requested card that is ACTIVE and owned by the verified customer, call `freeze_debit_card_3892` with its `card_id` and confirm the returned result. Do not attempt to freeze PENDING, CLOSED, or already FROZEN cards; explain its current state instead. A freeze does not satisfy a request to permanently cancel a card.
6. **If closure is requested, check closure prerequisites first.** Confirm ownership and ACTIVE/PENDING status; check for pending/processing transactions and pending refunds; and calculate the 14-day minimum age from `date_issued`. Lost, stolen, and fraud-suspected reasons bypass only the minimum-age rule, not the other stated prerequisites. Use `close_debit_card_4721` with `card_id` and the approved reason only after checks pass. Explain that closure is irreversible, recurring payment details need updating, and refunds go to the checking account.
7. **Gather replacement choices before ordering.** For each desired replacement, obtain the linked checking account, explicit delivery speed, design, and a confirmed valid US domestic mailing address. State the exact delivery and design fees and that all applicable fees are automatically deducted from the linked checking-account balance before ordering. If the customer only asks to freeze, finish the freezes and ask these questions; do not choose shipping or design on their behalf.
8. **Validate replacement eligibility and calculate fees.** The account must be a verified customer's OPEN checking account, open at least three business days, with balance at least $25, a valid domestic address, and no conflicting active/pending card order under the applicable ordering rules. Retrieve all card history and count cards issued within the previous rolling 12 months whose `issue_reason` is `lost`, `stolen`, `fraud`, or `damaged`; exclude `new_account`, `first_card`, `expired`, `upgrade`, and `bank_reissue`. Use `scripts/replacement_quote.py` to consistently evaluate tier fees and replacement limits, supplying live values.
9. **Order only after confirmation.** After the customer confirms the selected per-card delivery/design choices and fees, call `order_debit_card_5739` with the live account/card-order information and the exact `delivery_fee` and `design_fee` required by tier. If the tool requires additional documented fields, collect them before calling. Confirm only orders whose tool calls succeed, including delivery estimate and charged fees.
10. **Summarize accurately.** List each selected card only by last four digits when available, the completed freeze/closure state, any cards not acted on and why, security-check outcome, and replacement status. Clearly separate completed actions from options requiring customer information or confirmation.

## Tier replacement rules

Use the linked checking account's live `account_class`/tier. Do not guess a tier from an account nickname.

- **ENTRY:** maximum 2 replacements in 12 months; after card closure, wait 48 hours before ordering. STANDARD only ($0). At/over limit, customer may wait or choose the $25 excess-replacement fee if supported by the order flow. Design: CLASSIC $0, PREMIUM $10, CUSTOM $25.
- **MID:** maximum 3; no closure wait. STANDARD $0 or EXPEDITED $15. At/over limit, wait or $15 excess fee. Design: CLASSIC $0, PREMIUM $10, CUSTOM $25.
- **PREMIUM:** maximum 5; no closure wait. STANDARD/EXPEDITED $0, RUSH $35. At/over limit, customer must wait. Design: CLASSIC/PREMIUM $0, CUSTOM $15.
- **ELITE:** unlimited; no closure wait. STANDARD/EXPEDITED/RUSH $0. Design: all designs $0. Priority processing applies only when the live current time and applicable cutoff support it.

Do not silently add an excess-replacement fee. Explain the option and obtain confirmation first. If an ENTRY replacement requires the 48-hour post-closure wait, do not order it until elapsed.

## Special cases

- If the card is confirmed stolen or a stolen-card security condition is present, do not offer reactivation. Follow enhanced verification requirements where applicable and transfer to a human agent for a major account-compromise concern.
- If a customer says a card reported stolen was never reported by them, transfer to a human agent with reason `fraud_or_security_concern`; do not attempt to resolve it.
- Do not disclose internal fraud decline codes or fraud-security reasons.
- If unauthorized transactions are reported, offer the applicable debit-card dispute/Regulation E support separately; freezing or replacement does not itself resolve a dispute.

## Helper script

`scripts/replacement_quote.py` is deterministic advisory logic only. It reads JSON from standard input and emits one JSON object to standard output. It never contacts banking systems and does not place orders.

Input schema:

```json
{
  "tier": "ENTRY|MID|PREMIUM|ELITE",
  "delivery": "STANDARD|EXPEDITED|RUSH",
  "design": "CLASSIC|PREMIUM|CUSTOM",
  "replacement_issue_dates": ["YYYY-MM-DD"],
  "as_of": "YYYY-MM-DD",
  "closed_at": "YYYY-MM-DDTHH:MM:SS",
  "excess_fee_confirmed": false
}
```

`closed_at` may be omitted when no ENTRY waiting-period evaluation is needed. Dates in `replacement_issue_dates` must already have been filtered to qualifying replacement reasons from live card history. The output provides eligibility, exact delivery/design fees, whether an excess fee is an available and confirmed option, and blocking reasons. Validate that output against live account status, balance, age, address, card conflict, and customer confirmation before ordering.

Example runtime invocation: send the constructed live-data JSON to `run_skill_script` with `relative_path` set to `scripts/replacement_quote.py`, then use its JSON result to explain the quote and decide whether an order can proceed.
