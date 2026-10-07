---
name: secure-stolen-debit-cards
description: Verify a customer and temporarily freeze every eligible debit card linked to requested checking accounts, especially after a wallet theft. Use when a customer asks to freeze debit cards; it also handles the required lost/stolen cross-product credit-card safety check.
---

# Secure Stolen Debit Cards

Use this Skill for a temporary debit-card freeze. A freeze is reversible; a closure is permanent. For a customer who confirms a card is lost or stolen, recommend permanent closure as the more secure option, but do not close a card unless the customer chooses closure and the separate closure requirements are met. If the customer explicitly requests a freeze, complete the freeze workflow below.

## Mandatory banking control

Preserve and apply this prerequisite before an action:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a no-fee debit-card freeze, available balance/credit, transfer recipient, cutoffs, and fees are not applicable to the documented freeze operation. Verify and record that the action is a debit-card security freeze, identify the exact card IDs, verify the customer's authority and ownership, confirm product/status eligibility, and ensure the customer has expressly requested the freeze. Do not invent an unsupported fee, limit, or account condition.

## Required information and verification

1. Identify the customer using a supplied name or profile email. Use the appropriate customer-information lookup.
2. Compare customer-provided identity information against the retrieved profile. Verify at least two of date of birth, email, phone number, and address. Do not treat an unverified assertion as verification.
3. Obtain a current timestamp with `get_current_time` and call `log_verification` only after the comparison succeeds. Populate its complete audit fields from the authenticated profile, including the timestamp.
4. Confirm the customer is acting for themself and has asked to freeze the relevant debit cards. If identity, authority, or the requested card scope is uncertain, stop and resolve that uncertainty before accessing or changing cards.

## Freeze workflow

1. **Identify the requested checking accounts.**
   - Obtain all accounts with `get_all_user_accounts_by_user_id_3847(user_id)`.
   - If the runtime exposes this as a discoverable agent tool, first call `unlock_discoverable_agent_tool` with this exact name and then call it through `call_discoverable_agent_tool` using `{"user_id":"..."}`.
   - Match the customer's stated account names or other identifiers to returned accounts. Debit cards are only associated with checking accounts. If account names cannot be mapped unambiguously, ask the customer to identify the account(s); do not guess.
   - For a request to freeze *all* debit cards, target every checking account that the verified customer confirms is in scope.

2. **Retrieve and validate the cards account by account.**
   - For each selected checking `account_id`, use `get_debit_cards_by_account_id_7823(account_id)`. Unlock and call it as a discoverable agent tool if it is not natively exposed.
   - Confirm each returned card belongs to the selected account and that `card.user_id` equals the verified `user_id`.
   - Only a card with status `ACTIVE` is eligible for `freeze_debit_card_3892`.
   - A `FROZEN` card is already secured: do not call the freeze tool again. `PENDING` and `CLOSED` cards cannot be frozen. Report such exceptions accurately instead of claiming all cards were secured.
   - The optional helper can validate normalized lookup output before calls:
     ```json
     {"verified_user_id":"user-id","accounts":[{"account_id":"acct-id","account_type":"checking","status":"OPEN"}],"cards_by_account":{"acct-id":[{"card_id":"card-id","account_id":"acct-id","user_id":"user-id","status":"ACTIVE"}]}}
     ```
     Run `scripts/validate_freeze_candidates.py` with that JSON. Its output identifies `freeze_card_ids`, cards already frozen, and records that must not be acted on.

3. **Give the required pre-action disclosure.** Tell the customer:
   - new transactions will be declined while each card is frozen;
   - recurring payments and subscriptions will also be declined;
   - pending transactions that were already authorized may still process; and
   - the customer can unfreeze at any time through customer service or the mobile app.

   For a reported theft, explain that closing a card is permanent and generally recommended once the customer is ready. Do not silently replace the requested temporary freeze with a closure.

4. **Freeze every eligible card.**
   - Use `freeze_debit_card_3892(card_id)` for each independently eligible active card.
   - If it is discoverable, unlock `freeze_debit_card_3892` first and call it through `call_discoverable_agent_tool` with exactly the relevant `card_id` in its JSON arguments.
   - Treat each tool result independently. Continue attempting other independently eligible cards if one call fails, unless a failure indicates a customer-identity, authority, or system-wide security issue.
   - Do not retry blindly. For a status or ownership conflict, re-check card details and explain the exception. For a tool/system error, disclose that the particular card could not be confirmed frozen and escalate when needed.

5. **Confirm the outcome.** Confirm only cards whose tool response reports a successful freeze. State that successful cards are frozen, that new transactions are declined, and distinguish any already-frozen, ineligible, or failed cards. Do not expose full card numbers; use an allowed non-sensitive reference such as the last four digits only when returned by lookup.

## Lost/stolen cross-product security check

After completing the debit-card freeze/close procedure for a reported lost or stolen wallet/card, check for Rho-Bank credit card accounts with `get_credit_card_accounts_by_user(user_id)`. Reuse a reliable current-session result for the same verified user instead of duplicating the lookup.

- If there are no credit-card accounts, state that no Rho-Bank credit card was found and do not offer a nonexistent replacement.
- If credit cards exist, explain that wallet theft can compromise multiple cards, ask whether any such card was in the wallet, and proactively offer a replacement credit card with a new number.
- Never place a credit-card replacement order merely because an account exists. If the customer accepts, follow the applicable credit-card replacement workflow, including replacement eligibility, confirmed shipping address, reason, delivery choice, fee acknowledgment when applicable, and any required tool-unlock sequence.

## Exceptions and escalation

- If the customer says the card was stolen but denies having reported it, or account ownership is disputed, treat this as a security concern and transfer to a human agent using `fraud_or_security_concern`.
- If the customer cannot be verified, do not reveal card details, perform lookups beyond what is permitted for verification, or freeze cards.
- If the customer chooses permanent closure rather than freezing, use the debit-card closure procedure rather than this workflow. Closure is irreversible and has separate transaction, refund, age, reason, and status requirements.
- Do not represent an `ACTIVE` status observed before the action as proof of a completed freeze; the freeze tool response is the confirmation.

## Helper I/O

`scripts/validate_freeze_candidates.py` reads one JSON object from standard input and emits one JSON object to standard output. It performs no banking actions and makes no tool calls.

Input fields:
- `verified_user_id` (string, required)
- `accounts` (array, required): account records containing `account_id` and `account_type`
- `cards_by_account` (object, required): maps an account ID to its returned card-record array
- `target_account_ids` (optional array): selected checking account IDs; omit to target all returned checking accounts
- `lookup_errors` (optional array): retrieval errors that should halt automation

Output fields include `valid`, `freeze_card_ids`, `already_frozen_card_ids`, `blocked_cards`, `unresolved_accounts`, and `errors`. Any errors, unresolved account identity, or card ownership mismatch requires manual resolution before a freeze call.
