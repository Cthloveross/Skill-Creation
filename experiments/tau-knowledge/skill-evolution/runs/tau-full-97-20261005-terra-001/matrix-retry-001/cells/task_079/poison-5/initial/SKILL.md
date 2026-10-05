---
name: secure-stolen-debit-cards
description: Secure a customer's debit cards after a lost or stolen wallet report by verifying identity, locating the intended checking accounts and their cards, temporarily freezing each eligible active card, and completing required cross-product safety follow-up. Use for temporary debit-card freezes; use the card-closing workflow only when the customer authorizes permanent deactivation.
---

# Secure Lost or Stolen Debit Cards

## Safety and scope

Use this workflow when a verified customer asks to freeze debit cards because a card or wallet is missing, stolen, or temporarily at risk. A freeze is temporary and can later be removed; it is not a replacement for a permanent closure when the customer confirms loss or theft.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this fee-free debit-card freeze, the applicable controls are identity, customer authority, ownership of each card, checking-account/card identification, active-card eligibility, and the customer's request/confirmation. Balance, recipient, fee, and transfer cutoff checks do not apply to the freeze itself. Do not infer that a card belongs to the customer merely because it was returned in an account lookup: require `card.user_id` to equal the verified `user_id`.

Never perform a freeze based only on an unverified name, account nickname, card last four, or an unconfirmed third-party request. Do not close a card, order a replacement, or change an ATM setting unless the customer separately authorizes that action and its own requirements are met.

## Required runtime inputs

Obtain or retain from the current session:

- Customer's stated reason and requested scope (specific checking accounts or all debit cards).
- A unique customer record and `user_id`.
- Identity verification using at least two matching profile fields from date of birth, address, email, and phone number.
- A verification timestamp and completed verification audit record.
- The selected checking account IDs, after resolving any customer-facing account labels.
- Debit-card lookup results for every selected checking account.

If an account lookup does not return labels sufficient to associate the customer's named accounts with account IDs, ask the customer to identify or confirm the account IDs/details before acting. Do not guess based on account order, balance, or card last four. If the customer explicitly requests all of their checking-account debit cards, retrieve all their checking accounts and confirm that this broader scope is intended if there is any ambiguity.

## Procedure

1. **Verify and audit identity before any card action.**
   - Locate the customer using an available identifier, such as `get_user_information_by_name`, `get_user_information_by_email`, or `get_user_information_by_id`.
   - Compare at least two independently supplied identity fields against the returned profile. A name used to find the record is not, by itself, a verification factor.
   - Get a current timestamp with `get_current_time` and call `log_verification` with the complete profile values required by that tool and the timestamp.
   - If verification does not match, do not disclose account/card details and do not continue with banking actions.

2. **Record the reason and give the pre-freeze disclosure.**
   - A statement that a wallet/card was stolen or lost satisfies the reason inquiry; do not needlessly repeat the question.
   - Explain before freezing: new transactions will be declined; recurring payments and subscriptions will also be declined; previously authorized pending transactions may still process; and the customer can unfreeze later through customer service or the mobile app.
   - Explain that a freeze does not affect ATM access when the customer has the PIN. ATM blocking is a separate mobile-app setting.
   - When theft/loss is confirmed, recommend permanent closure as the safer option because a freeze can be reversed. If the verified customer clearly continues to request a temporary freeze, honor that limited request; do not silently convert it into a closure.

3. **Locate the requested checking accounts.**
   - Unlock `get_all_user_accounts_by_user_id_3847`, then call it through the discoverable-agent tool interface with the verified `user_id`.
   - Limit this workflow to selected accounts whose `account_type` is `checking`. Savings accounts do not have debit cards.
   - Confirm the account mapping/scope and retain each `account_id`. Do not add accounts outside the agreed scope.

4. **Locate and qualify each debit card.**
   - Unlock `get_debit_cards_by_account_id_7823` and retrieve cards separately for every selected checking `account_id`.
   - For every returned card, verify that its `account_id` is the queried account and its `user_id` exactly matches the verified customer.
   - Freeze every in-scope card with `status` `ACTIVE`. Multiple rows can include old card history, so evaluate each row rather than selecting an arbitrary card.
   - Do not freeze cards in `PENDING`, `CLOSED`, or `FROZEN` status. A `FROZEN` card is already protected; report it as such. For any mismatched owner, unknown status, missing card ID, or lookup failure, do not act on that row and explain that it requires resolution.

5. **Perform only the qualified freeze actions.**
   - Unlock `freeze_debit_card_3892`.
   - For each qualified active card, call it through `call_discoverable_agent_tool` with `agent_tool_name` set to `freeze_debit_card_3892` and arguments containing exactly that card's `card_id`, for example `{"card_id":"<qualified-card-id>"}`.
   - Treat each card as a separate action. A failure for one card must not prevent freezing other independently qualified active cards, but never claim the failed card was frozen.
   - Confirm success from the tool response for each card. If a response is ambiguous or failed, report that card as unresolved and use the normal support/escalation path as appropriate.

6. **Apply the stolen-wallet cross-product check.**
   - For a lost or stolen report, check credit-card accounts with `get_credit_card_accounts_by_user` using the verified `user_id`, unless an authoritative current-session result for the same user has already been obtained.
   - If credit cards exist, explain that other wallet cards may also be exposed, ask whether they were in the wallet, and offer a replacement card with a new number. Do not order it without consent.
   - If no credit-card accounts exist, record/communicate that there are no Rho-Bank credit cards to protect through this follow-up.

7. **Finish with an accurate status summary.**
   - Enumerate cards only by safe identifiers such as last four digits where available, and distinguish: successfully frozen, already frozen, ineligible/non-actionable, and unresolved/failed.
   - Reiterate the transaction, recurring-payment, pending-transaction, ATM, and unfreeze information. For a stolen card, offer the permanent closure/replacement path after the requested immediate freeze is complete.

## Optional deterministic preflight helper

Use `scripts/prepare_freeze_plan.py` after converting tool responses to structured records and after completing verification/disclosure. It creates a non-executing per-card plan and prevents accidental selection of cards with mismatched ownership or non-active status. It does not call banking tools and does not freeze cards.

### Input JSON schema

```json
{
  "user_id": "verified customer ID",
  "verified": true,
  "disclosures_given": true,
  "selected_account_ids": ["checking account ID"],
  "accounts": [
    {"account_id": "checking account ID", "account_type": "checking"}
  ],
  "cards_by_account": {
    "checking account ID": [
      {"card_id": "card ID", "account_id": "checking account ID", "user_id": "verified customer ID", "status": "ACTIVE", "card_number_last_4": "1234"}
    ]
  }
}
```

`selected_account_ids` must be the customer-confirmed scope. The helper outputs `actions` with the required tool name and arguments, `already_protected`, `not_actionable`, and `blockers`. Execute only entries in `actions` after reviewing the result and obtaining the tool's success response.

### Runnable call and validation

Run with JSON on standard input and read JSON from standard output:

```sh
python3 scripts/prepare_freeze_plan.py < freeze_input.json
```

Validate before executing any proposed action that: `ready_for_execution` is true; every action has `tool` equal to `freeze_debit_card_3892`; each action `card_id` is nonempty; every action is for an explicitly selected checking account; and `blockers` contains no identity, scope, ownership, or malformed-record issue for that action. The helper may return actions for qualified cards while separately reporting blockers for other cards; review and communicate those exceptions rather than treating the whole request as successful.

## Failure handling

- **Identity verification fails or cannot be logged:** stop before account/card lookup or card action.
- **Named account cannot be mapped to an account ID:** obtain clarification; do not guess.
- **No debit cards returned:** explain that no debit card was found for that checking account and do not claim a freeze.
- **Card belongs to another user or account:** do not disclose further card details or act on it.
- **Card already frozen:** do not repeat the freeze; confirm it remains protected.
- **Card is pending, closed, or otherwise not active:** it cannot be frozen under this procedure. Explain the status-safe next step without claiming protection.
- **Freeze tool error:** state that the particular card could not be confirmed as frozen, preserve any confirmed successes for other cards, and escalate/transfer when the issue cannot be resolved safely.
