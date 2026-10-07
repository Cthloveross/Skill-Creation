---
name: secure-debit-cards-by-freezing
description: Safely handles a verified customer's request to temporarily freeze debit cards, including requests covering cards on several named checking accounts. Use when the customer wants a reversible security lock rather than permanent card closure.
---

# Temporary Debit-Card Freeze Workflow

Use this workflow for a request to freeze one or more debit cards. A freeze is temporary and can later be reversed; it is not a substitute for permanently closing a confirmed lost or stolen card.

## Required controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow, do not freeze a card until all of the following are established:

1. The customer has passed identity verification and the verification was logged.
2. The card is owned by the verified user (`card.user_id` equals the verified `user_id`).
3. The card is linked to a requested checking account owned by that user.
4. The card status is exactly `ACTIVE`.
5. The customer has requested the temporary freeze. If their report indicates a card is confirmed lost or stolen, explain that permanent closure is the safer recommended alternative, but honor an unambiguous request for a temporary freeze when the freeze prerequisites are met.

Do not infer identity confirmation from profile data displayed to the agent. The customer must supply matching values for two of these four fields: date of birth, email, phone number, or address. A name can locate the profile but is not one of the two required fields.

## Tool sequence

1. **Locate and verify the customer.** Use the supplied full name or email with the appropriate customer lookup tool. Compare two customer-provided verification fields against the returned profile. Obtain another field if fewer than two fields have been confirmed.
2. **Log verification.** Once two fields match, obtain the current time with `get_current_time` and call `log_verification` with the complete returned profile fields, the verified `user_id`, and that timestamp. Do not proceed if lookup is ambiguous or a supplied field does not match.
3. **Set expectations.** State that new purchases and recurring payments/subscriptions will be declined while frozen; already-authorized pending transactions may still process; and the card may be unfrozen later through customer service or the mobile app. Freezing does not by itself block ATM access for someone with the PIN; ATM Block must be enabled separately through the mobile app.
4. **Find the requested checking accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Match each customer-supplied account label to a returned checking account using returned account naming/class information. Never guess between similar labels. If a requested account cannot be uniquely identified, ask the customer to clarify it and do not act on that account.
5. **Retrieve cards.** For every uniquely identified requested checking account, unlock and call `get_debit_cards_by_account_id_7823`. Check each returned card's linked account, `user_id`, and `status`. A card that is `PENDING`, `FROZEN`, or `CLOSED` is not eligible to freeze; report that status rather than calling the freeze action.
6. **Create the action plan.** Optionally run `scripts/build_freeze_plan.py` on structured account and card results. It produces only recommendations and never performs a bank action.
7. **Freeze each eligible card.** Unlock `freeze_debit_card_3892`, then call it through `call_discoverable_agent_tool` once for each unique eligible `card_id`, passing `{"card_id":"..."}`. Treat an error or non-successful response as a failure for that card only; do not claim it was frozen.
8. **Confirm results.** Clearly list the cards/accounts successfully frozen (using a non-sensitive identifier such as last four digits when available) and separately list cards not changed with the reason. Reiterate that a successful freeze is temporary. If the customer confirms a card is lost or stolen and wants it permanently deactivated, use the separate closure workflow rather than attempting to close it here.

## Lost or stolen wallet follow-up

For a lost or stolen debit-card report, complete the requested debit-card freeze or closure process first. Then check for credit-card accounts with `get_credit_card_accounts_by_user`. If credit cards exist, explain the wallet-security risk and offer a replacement credit card. If none exist, simply record that no credit-card protection offer is applicable. Do not disclose internal fraud decline codes or attempt to reactivate a card reported stolen.

## Handling incomplete or unsafe cases

- If verification is incomplete, ask for one additional verification field and take no card action.
- If account ownership, card ownership, card linkage, or card status cannot be established, take no action for the affected card and explain what information is needed.
- If a requested card is already frozen, confirm its current status instead of making a duplicate call.
- If no eligible active cards are found, make no freeze calls and report the outcome.
- Never claim success based solely on a planned action; success requires the freeze tool's successful response.

## Planner script

`scripts/build_freeze_plan.py` reads one JSON object from standard input and writes one JSON object to standard output. It accepts:

```json
{
  "user_id": "verified user id",
  "requested_account_labels": ["customer-provided account label"],
  "accounts": [{"account_id": "...", "account_type": "CHECKING", "account_name": "..."}],
  "cards_by_account": {"account id": [{"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE", "card_number_last_4": "1234"}]}
}
```

It returns `freeze_actions` containing safe candidate `card_id` values and `not_actionable` entries explaining skipped, ambiguous, malformed, non-checking, non-owned, mismatched, or non-active records. Account labels are normalized only for case and whitespace; the executor must resolve any ambiguity with the customer.

Example runnable call:

```sh
python3 scripts/build_freeze_plan.py <<'JSON'
{"user_id":"u","requested_account_labels":["Account label"],"accounts":[{"account_id":"a","account_type":"CHECKING","account_name":"Account label"}],"cards_by_account":{"a":[{"card_id":"c","account_id":"a","user_id":"u","status":"ACTIVE"}]}}
JSON
```

Validate the output before acting: every `freeze_actions` item must have a unique nonempty `card_id`, an `ACTIVE` status, matching user and account IDs, and an unambiguous requested checking account. Use the tool response, not this script, as the final record of success.
