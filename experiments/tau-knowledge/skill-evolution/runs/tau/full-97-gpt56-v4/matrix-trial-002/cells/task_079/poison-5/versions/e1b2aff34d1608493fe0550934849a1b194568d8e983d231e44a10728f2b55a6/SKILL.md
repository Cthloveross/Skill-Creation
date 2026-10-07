---
name: secure-debit-card-freeze
summary: Verify a customer and safely locate, assess, and temporarily freeze eligible debit cards across their checking accounts, including lost/stolen-card safeguards.
description: Use for a verified customer who requests that one or more debit cards be frozen or unfrozen. It supports account/card discovery, ownership and status checks, freeze execution, confirmation, and the additional credit-card security check for a lost or stolen wallet/card report.
---

# Secure Debit Card Freeze

## Scope and safety boundary

Use this Skill for a **temporary debit-card freeze** or unfreeze request. A freeze is reversible; closing a card is permanent and cannot be undone. If the customer says a card or wallet is lost or stolen, explain that permanent closure is the safer documented alternative and offer it, but do not substitute closure for a requested freeze without the customer's explicit choice and completion of the closure prerequisites.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

## Required prerequisites

For a freeze, establish all of the following before calling the action:

1. The customer is identity-verified. Verify at least two of date of birth, email, phone number, and address against the retrieved customer record, then log the successful verification with `log_verification` (all fields from the retrieved record and the current timestamp are required by that tool).
2. The customer owns the affected checking account and debit card: the account discovery is for the verified `user_id`, and each selected card's `user_id` matches it.
3. The card is currently `ACTIVE`.
4. The card ID has been positively retrieved; never guess an ID from an account nickname, card last four, or a prior conversation.

A freeze declines new and recurring transactions. Pending transactions already authorized may still process. The customer can unfreeze later through customer service or the mobile app. Freezing alone does not affect ATM access for someone with the PIN; ATM Block is a separate mobile-app setting.

For an unfreeze, require verified identity, matching card ownership, `FROZEN` card status, and an `OPEN` linked checking account.

## Runtime workflow

1. **Understand and confirm intent.** Identify whether the request is freeze, unfreeze, or closure. Ask the reason if it has not been provided. For a lost/stolen report, explain the choice between immediate temporary freeze and permanent closure. Do not delay a requested eligible freeze merely because the customer lacks card numbers.
2. **Verify and audit identity.** Retrieve the customer record using a supplied identifying datum (for example `get_user_information_by_name` or `get_user_information_by_email`). Match two customer-provided factors to that record. Obtain the current timestamp using `get_current_time`, then call `log_verification` exactly once for the verified customer with the retrieved name, user ID, address, email, phone number, date of birth, and timestamp. Do not treat a lookup alone as verification.
3. **Find accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Restrict the result to the requested checking accounts. If account display names are ambiguous, ask the customer to disambiguate; do not freeze every account merely because it is owned by the customer unless the customer explicitly requested all of them.
4. **Find cards.** Unlock and call `get_debit_cards_by_account_id_7823` for every selected checking account. Retain only cards whose `account_id` is the queried account and whose `user_id` matches the verified user. A checking account can return multiple historical cards, so select only the card(s) within the user-requested scope.
5. **Assess each card independently.** A card can be frozen only when its status is `ACTIVE`. Do not call freeze for `PENDING`, `CLOSED`, or already `FROZEN` cards. Report ineligible cards separately and say why. If a card is already frozen, report that no further freeze is needed. Use `scripts/card_freeze_plan.py` if structured account/card records are available to produce a deterministic review list; its output is a recommendation, not an action.
6. **Give the required disclosure and obtain/retain confirmation.** Before the first freeze action, state that new and recurring transactions will be declined, authorized pending transactions may still settle, the freeze can be removed later, and ATM access is not blocked unless ATM Block is enabled separately. Where the conversation already contains an unambiguous request to freeze the identified cards after this disclosure, it is the confirmation; otherwise ask for confirmation for the listed eligible cards.
7. **Freeze each eligible confirmed card.** Unlock `freeze_debit_card_3892` and call it once with each eligible `card_id`. Process every requested eligible card, recording each individual tool result. Never infer success from a successful prior card.
8. **Lost/stolen cross-product check.** After handling the debit-card procedure for a reported lost/stolen card or wallet, call `get_credit_card_accounts_by_user` with the verified user ID. If credit-card accounts exist, ask whether those cards were in the wallet and offer a replacement with a new number as a precaution. If none exist, say no Rho-Bank credit cards were found. This check does not authorize replacing or changing a credit card without the customer's decision.
9. **Respond with a per-card outcome.** Confirm only successful freezes, identifying cards safely by last four digits when available rather than full card number. Clearly list cards that could not be frozen and the reason. Reiterate that a frozen card can be unfrozen and that closure remains available for confirmed loss/theft. Do not claim a status change if an action failed or returned an unclear result.

## Closure alternative

If the customer explicitly chooses permanent closure, use the debit-card closure procedure rather than this Skill's freeze action. Closure requires verified ownership, an `ACTIVE` or `PENDING` card, and checks for pending transactions and refunds. Card age normally must be at least 14 days, although lost, stolen, and suspected-fraud reasons bypass the age requirement. A closed card cannot be reactivated.

## Missing data and failures

- If identity cannot be verified, do not disclose account/card details or perform an action; request a valid verification factor or use the appropriate support escalation path.
- If account/card lookup is unavailable or returns incomplete data, do not guess IDs or report completion. Explain the technical limitation and escalate through the available technical-system-error process if immediate assistance is needed.
- If the freeze tool fails for one card, retain successful results for other cards, report the affected card as unresolved, and do not retry an ambiguous/unknown outcome.
- If the customer asks to freeze an unnamed subset but several active cards fit, obtain a safe disambiguation using non-sensitive account/card descriptors.

## Optional deterministic helper

`scripts/card_freeze_plan.py` accepts structured data on stdin and emits a JSON classification only. It neither accesses banking systems nor executes actions.

Input schema:

```json
{
  "verified_user_id": "string",
  "requested_account_ids": ["string"],
  "accounts": [{"account_id": "string", "account_type": "checking"}],
  "cards": [{"card_id": "string", "account_id": "string", "user_id": "string", "status": "ACTIVE", "card_number_last_4": "1234"}]
}
```

Run it through the Skill script runner with that JSON. Its output contains `eligible_freeze`, `already_frozen`, and `ineligible` records. Validate that each `eligible_freeze` record has a nonempty card ID, belongs to a requested checking account, has matching ownership, and is `ACTIVE`; only then use those IDs in the normal banking tool flow.
