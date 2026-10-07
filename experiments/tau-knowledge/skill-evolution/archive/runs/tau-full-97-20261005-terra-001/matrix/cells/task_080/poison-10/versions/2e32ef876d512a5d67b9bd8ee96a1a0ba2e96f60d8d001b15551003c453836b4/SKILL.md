---
name: secure-stolen-wallet-cards
description: Handle a verified customer's lost or stolen wallet report involving debit cards, including temporary debit-card freezes, later requested debit-card unfreezes, and the required credit-card replacement-protection offer. Use this when supported banking tools and current account/card lookup data are available.
---

# Secure Lost or Stolen Wallet Cards

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety boundary

A debit-card **freeze** is temporary and may later be reversed. A debit-card **closure** is permanent and cannot be reversed. For a reported stolen card, recommend permanent closure as the safer choice, but a verified owner may choose a temporary freeze if the freeze requirements are met.

The supplied workflow documents physical debit-card freeze and unfreeze actions. It does **not** document a physical credit-card temporary-lock action. Never claim that a debit-card action protects a credit card, and never substitute virtual-card management for a physical-card lock. For credit cards in a stolen wallet, perform the required credit-card check and offer replacement protection instead.

Use current conversation facts and current runtime lookups. Do not invent account identifiers, card identifiers, status, ownership, eligibility, confirmation, tool outcomes, or shipping details. The executor must perform banking actions with its normal banking tools and must report only actual successful results.

## Inputs and verification

Collect or use at runtime:

- A profile-locating claim such as name or registered email.
- At least two matching profile fields from date of birth, email, phone number, and address.
- The specific debit accounts/cards the customer wants affected.
- Explicit freeze confirmation after the effects of a freeze are explained.
- For a later unfreeze, an explicit request identifying the frozen card.
- For each optional credit-card replacement: selected credit account, exact replacement reason, confirmed complete shipping address, shipping speed, applicable expedited-fee acknowledgement, eligibility, and affirmative order approval.

A name or email used to locate a profile is not verification by itself. Retrieve the profile with `get_user_information_by_name` or `get_user_information_by_email`; ask for and compare at least two profile fields without disclosing values to solicit confirmation. After two fields match, call `get_current_time`, then call `log_verification` with the retrieved full profile fields and current timestamp. If verification fails, stop without taking or claiming banking action.

A successful verification remains usable for follow-up card actions in the same authenticated interaction unless the runtime requires reverification or facts indicate a security concern.

## Debit-card freeze workflow

1. Retrieve accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. Limit card lookup to the checking accounts the customer selected. Resolve ambiguous account names or card references before proceeding.
2. For each selected checking account, call `get_debit_cards_by_account_id_7823(account_id)`.
3. Match each requested card to the verified user and selected checking account. For a freeze, the card must currently be `ACTIVE`.
4. Before requesting confirmation, explain that new transactions and recurring payments will be declined, already-authorized pending transactions may still process, and the customer can unfreeze later. Explain that freezing does not block ATM access for someone with the PIN; ATM Block is separate in the mobile app.
5. Capture explicit confirmation to freeze the identified cards. Do not interpret a request concerning one card as confirmation for unrelated cards.
6. For each eligible, confirmed card, call `freeze_debit_card_3892` with `card_id`.
7. Read each tool result. Re-query the relevant debit cards when available and confirm `FROZEN` status. Report individual successes and unresolved cards separately.

Do not freeze a card that is `PENDING`, `FROZEN`, or `CLOSED`. A failed tool call or missing post-action evidence is not a successful freeze.

## Debit-card unfreeze workflow

When a verified customer later finds a temporarily frozen debit card and explicitly asks to unfreeze it, process the request rather than transferring merely because it is an unfreeze.

1. Identify the exact requested card. Re-query it with `get_debit_cards_by_account_id_7823(account_id)` when current card status or ownership evidence is unavailable or stale.
2. Confirm all unfreeze prerequisites from current or already-established authenticated-session evidence:
   - the customer is verified;
   - the card `user_id` matches the verified user;
   - the requested card is currently `FROZEN`; and
   - its linked checking account is currently `OPEN`, using `get_all_user_accounts_by_user_id_3847(user_id)` when account status has not already been established.
3. If all prerequisites hold and the customer explicitly requested unfreezing, call `unfreeze_debit_card_3893` with that exact `card_id`. This is a customer-requested action; no new freeze-style warning or replacement choice is required.
4. Read the bank result and re-query the card when available. Confirm only after success that the specific card is `ACTIVE` and ready to use immediately.
5. Leave every other debit card frozen unless the customer separately asks to unfreeze it and its own prerequisites are met.

If the card is not frozen, ownership does not match, the linked checking account is not open, or a tool action fails, do not claim it was reactivated. Explain the blocking condition and use normal escalation only if no supported resolution remains.

## Debit-card closure branch

If the customer chooses permanent closure instead of a freeze, before calling `close_debit_card_4721(card_id, reason)` verify ownership, that status is `ACTIVE` or `PENDING`, the selected reason, no pending/processing transactions, and no pending refunds unless the required written acknowledgement is supplied. Lost, stolen, and fraud-suspected reasons bypass only the 14-day card-age condition.

Explain that closure is irreversible, recurring payments need updated payment details, and pending authorized transactions may still process. Do not close unrelated cards or treat a freeze request as closure authorization.

## Required credit-card security check

For every lost/stolen debit-card or wallet report, after verification call `get_credit_card_accounts_by_user(user_id)`.

If credit cards exist:

1. Explain that a stolen wallet can expose multiple cards and ask whether the relevant credit cards were in the wallet.
2. State that this workflow has no documented physical-credit-card temporary-lock action. Offer a replacement card with a new number as the supported precaution.
3. If suspicious transactions are reported, advise review and normal dispute channels. Do not label transactions fraudulent without a customer report or completed investigation.
4. If replacement is declined, document that the offer was made through the normal record process if available. Do not order a replacement.

## Optional credit-card replacement

Order a replacement only after the customer affirmatively requests it for a specific looked-up credit account and all prerequisites are present:

- verified identity, ownership, and replacement eligibility;
- exactly one reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`;
- confirmed complete shipping address, including unit or suite where applicable;
- shipping speed `standard` (7–10 business days, free) or `expedited` (2–3 business days);
- expedited-fee acknowledgement when a fee applies.

Expedited fees: entry tier including EcoCard is $15; mid tier is $10; premium tier and above including Gold Rewards is $0. For stolen or suspected-fraud replacements, strongly recommend expedited shipping and remind the customer to review transactions.

Only after eligibility and all customer choices are confirmed, call `unlock_discoverable_agent_tool` for `order_replacement_credit_card_7291`, then call `call_discoverable_agent_tool` using that tool name and arguments containing the looked-up account identifier, reason, shipping address, shipping speed, expedited-fee acknowledgement, and relevant notes. Following a successful order, communicate delivery timing and that the old card is cancelled for new purchases.

## Plan-validation helper

Use `scripts/validate_card_security_plan.py` to validate structured data before dispatching proposed freeze, unfreeze, or replacement actions. It performs no banking action and never changes state.

The script reads one JSON object from stdin and writes one JSON object to stdout. Its principal fields are:

```json
{
  "verified": true,
  "user_id": "verified-user-id",
  "freeze_confirmed": true,
  "selected_debit_card_ids": ["card-to-freeze"],
  "requested_unfreeze_card_ids": ["card-to-unfreeze"],
  "debit_cards": [
    {"card_id": "card-to-freeze", "account_id": "checking-id", "user_id": "verified-user-id", "status": "ACTIVE"},
    {"card_id": "card-to-unfreeze", "account_id": "checking-id", "user_id": "verified-user-id", "status": "FROZEN"}
  ],
  "checking_accounts": [
    {"account_id": "checking-id", "user_id": "verified-user-id", "status": "OPEN"}
  ],
  "credit_replacements": []
}
```

Output fields `freeze_actions`, `unfreeze_actions`, and `replacement_actions` are candidates only. Dispatch each only after checking live facts. `blockers` explains withheld operations. For example, run it through `run_skill_script` with `relative_path` `scripts/validate_card_security_plan.py` and the transformed lookup records as `input_json`.

## Completion checklist

- Verification was completed and logged before banking actions.
- Each debit action was matched to the verified owner, exact card, linked account, and required current status.
- Freeze effects and explicit confirmation preceded every freeze.
- Each completed freeze was confirmed as `FROZEN`.
- Each requested unfreeze had a verified owner, `FROZEN` card, `OPEN` linked checking account, successful `unfreeze_debit_card_3893` result, and `ACTIVE` confirmation.
- Other frozen cards remain frozen unless separately requested.
- Credit cards were checked and replacement protection was offered, but no unsupported physical-card lock or unapproved replacement was claimed.
