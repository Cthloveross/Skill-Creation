---
name: secure-debit-card-freeze
version: 1.1.0
description: Safely verify a customer and temporarily freeze one or more eligible debit cards after a misplaced wallet/card report, while performing the required credit-card security check for lost or stolen cards.
---

# Secure Debit Card Freeze

Use this Skill when a verified customer asks to temporarily freeze a debit card, especially after misplacing a wallet. A freeze is reversible; do not substitute a permanent closure unless the customer confirms the card is lost/stolen or requests cancellation.

## Controls that apply before every banking action

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, establish and record all applicable prerequisites before freezing:

1. **Intent and scope:** Confirm whether the customer wants a temporary freeze or a permanent close. Confirm exactly which cards/accounts are in scope.
2. **Identity:** Match at least two of date of birth, email, phone number, and address against a retrieved customer record. Obtain the current time and call `log_verification` with the complete retrieved record and timestamp after a successful match.
3. **Authority and ownership:** Retrieve the customer’s accounts and cards. Verify that each selected card’s `user_id` is the verified user and its `account_id` is one of the customer’s selected checking accounts.
4. **Eligibility:** The linked checking account must be open and the card must be `ACTIVE`. A `PENDING`, `FROZEN`, or `CLOSED` card is not eligible to freeze.
5. **Card detail and confirmation:** Use only returned card IDs and last four digits; never ask for or expose a full card number or PIN. If more than one eligible card could fit the request, obtain a safe disambiguation (such as account name/account identifier or last four digits) before action. A customer who clearly requests *all* debit cards attached to identified accounts may authorize each uniquely identified active card.

## Procedure

1. Determine whether the report is a misplaced-card scenario (freeze) or confirmed lost/stolen scenario (recommend closure rather than freeze). Do not perform a closure under this Skill.
2. Locate the customer with an available identity lookup, then collect and compare at least two identity fields. Do not treat a name alone as verification.
3. Call `get_current_time`, then call `log_verification` using the retrieved name, user ID, address, email, phone number, date of birth, and current timestamp.
4. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Identify the requested checking account(s), and retain only open checking accounts.
5. For each selected checking account, unlock and call `get_debit_cards_by_account_id_7823` with its `account_id`.
6. Select only cards whose returned `account_id` and `user_id` match the verified customer and whose status is `ACTIVE`. The optional helper `scripts/select_freezable_cards.py` can validate a structured copy of these results, but it does not execute bank actions.
7. Before freezing, tell the customer that new transactions and recurring payments/subscriptions will be declined, while already-authorized pending transactions may still process. Tell them they can unfreeze through customer service or the mobile app. Freezing does not affect ATM access when they have their PIN; ATM blocking must be enabled separately in the mobile app.
8. For every confirmed eligible card, unlock `freeze_debit_card_3892` and call it with the returned `card_id`. Do not call it for an ineligible or ambiguous card. Check the tool response and report only successful freezes as completed. If a freeze outcome is unknown or the tool fails, do **not** repeat that action; tell the customer that its status needs confirmation through the appropriate support path.
9. Confirm that each successfully frozen card is frozen. Mention that a reminder notification is sent if it remains frozen for 90 days.
10. After the debit-card result is known, perform the separate credit-card check below before ending the lost/stolen-wallet interaction. Do not treat account retrieval that happens to display a credit-card record as a substitute for the required dedicated credit-card lookup.

## Lost/stolen wallet cross-product check

A report that a wallet or debit card is lost/stolen requires a credit-card check even if the customer elects a temporary debit freeze.

1. Call `get_credit_card_accounts_by_user` with the verified `user_id` after the debit-card procedure, even when another account lookup displayed credit-card information.
2. If one or more credit cards are found, tell the customer that a Rho-Bank credit card is on file, ask whether it was also in the missing wallet, and explain that wallet theft can compromise multiple cards.
3. If it was in the wallet, recommend replacing it promptly and proactively ask a clear yes/no question: whether they want a replacement credit card with a new number as a precaution against unauthorized charges. Saying that the card was in the wallet is not itself authorization to replace it.
4. Do not order, close, replace, or otherwise modify a credit card merely because the customer says it was present. Obtain an explicit request and follow the separate supported credit-card replacement workflow. If no such workflow/tool is available, explain that limitation and offer an appropriate human handoff rather than claiming a replacement was ordered.
5. If the customer declines replacement, make any note only if an authorized, available note-taking workflow exists; do not invent a record or tool call.

## Exceptions and safe responses

- If identity cannot be verified, do not access or change cards; request the needed identity fields or use the appropriate secure support path.
- If account ownership, account status, or card status fails validation, do not freeze that card. Explain the specific non-sensitive eligibility issue.
- If no card is returned for an account, do not assume a card exists.
- If a card is already frozen, report that it is already protected rather than attempting another freeze.
- When the customer identifies every debit card on specifically named checking accounts (for example, “both cards” on two named accounts), the returned active card for each such account is sufficiently scoped even if the customer does not know its last four digits. Do not delay urgent protection solely to obtain digits that they cannot safely provide.
- If a customer confirms loss/theft and wants permanent replacement/closure, pause this freeze workflow and use the applicable loss/stolen closure procedure.
- Never imply that a freeze prevents pending authorized transactions, blocks ATM usage, or protects a credit card automatically.

## Tool discovery and execution

Names documented in this Skill may be discoverable agent tools. Before calling a discoverable tool, call `unlock_discoverable_agent_tool` with that exact name, then call `call_discoverable_agent_tool` with JSON-encoded arguments. Use normal banking tools for actual actions; the helper script only returns recommendations and never triggers bank actions.

## Helper input/output

Run the helper as `scripts/select_freezable_cards.py`. It reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "user_id": "verified customer ID",
  "selected_account_ids": ["checking account ID"],
  "open_checking_account_ids": ["checking account ID"],
  "cards": [
    {"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE"}
  ]
}
```

Output contains `eligible_cards`, `ineligible_cards`, and `errors`. Execute freeze actions only for entries in `eligible_cards` after confirming the customer’s requested scope and completing the customer disclosures.
