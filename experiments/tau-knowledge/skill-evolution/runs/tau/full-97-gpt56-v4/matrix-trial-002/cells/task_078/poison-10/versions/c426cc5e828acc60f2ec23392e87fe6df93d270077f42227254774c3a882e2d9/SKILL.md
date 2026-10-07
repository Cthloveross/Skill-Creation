---
name: lost-or-stolen-debit-card-security-and-replacement
description: Use for a verified customer reporting lost or stolen debit cards or a wallet, including immediate temporary protection, permanent closure, replacement eligibility, tier fees, and related credit-card security checks.
---

# Lost or Stolen Debit Cards and Replacement

Use this workflow for one or more debit cards reported lost or stolen. Work card-by-card and account-by-account. A card identifier, account, tier, eligibility, fee, address, or customer preference for one card must never be assumed for another.

## Mandatory control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## 1. Verify, establish scope, and inspect

1. Identify the customer and confirm at least two of date of birth, email, phone number, and address against the user record. Obtain the current timestamp and call `log_verification` with the verified record and timestamp before any state-changing banking action.
2. Confirm the requester owns every selected card by matching `card.user_id` to the verified user. Determine the scope precisely. If the customer says all debit cards in their lost wallet, list the active cards found and confirm which are affected; do not affect historical closed cards or an unmentioned active card.
3. For every lost/stolen report, use `get_credit_card_accounts_by_user`. If any credit card exists, ask whether it was also in the wallet and offer a protective replacement. Do not take credit-card action without direction.
4. Use `get_all_user_accounts_by_user_id_3847`, then `get_debit_cards_by_account_id_7823` for each relevant checking account. Before closure also retrieve `get_bank_account_transactions_9173` for each linked account. Check for pending or processing transactions and any available pending-refund information. If a required fact cannot be retrieved with a declared normal tool, do not invent it; explain the limitation and use only a closure result that explicitly confirms the prerequisite.

## 2. Protect and close the lost cards

A confirmed lost or stolen card should be **permanently closed**, not merely frozen. Closing is irreversible; a freeze is only a temporary lock.

- If the customer is still looking for the card or wants temporary protection while deciding, and the card is `ACTIVE`, explain that new and recurring transactions will be declined, authorized pending transactions may still process, and the card can be unfrozen. Then use `freeze_debit_card_3892(card_id)`. Do not freeze cards that are PENDING, CLOSED, or already FROZEN.
- If the customer confirms the card is lost/stolen and explicitly authorizes irreversible closure, do **not** freeze it first merely because the initial request mentioned a freeze. Verify closure prerequisites and use `close_debit_card_4721(card_id, reason)` with `lost` or `stolen`. This gives the requested security without creating a frozen-status conflict.
- A closure requires verified ownership; card status `ACTIVE` or `PENDING`; no pending/processing transactions; and no pending refund unless the customer provides the documented written acknowledgement that it will credit to the linked checking account. Lost/stolen bypasses only the 14-day card-age requirement, not the transaction or refund checks.
- If a card was already frozen while the customer decided, the documented close tool accepts only ACTIVE or PENDING. Explain this before acting. To use the documented path, obtain explicit consent to unfreeze that specific card solely to close it, verify its linked checking account remains OPEN, call `unfreeze_debit_card_3893(card_id)`, immediately recheck applicable live eligibility, and close it. Never unfreeze a card simply as a workaround without that consent. If the card has pending/processing activity or refunds, keep it frozen and do not close it yet.
- Record only tool-confirmed outcomes. Tell the customer that a closed card cannot be reactivated, recurring merchants require updated payment details, and refunds to a closed card credit the linked checking account.

## 3. Evaluate each replacement only after confirmed closure

A replacement is a new debit-card order. For each closed lost/stolen card, independently verify all of the following before ordering:

- verified customer is at least 18;
- linked account is a checking account, OPEN, and at least 3 business days old;
- valid US domestic shipping address is confirmed;
- balance is at least $25 and sufficient for the selected automatically charged fees;
- no ACTIVE debit card and no PENDING debit-card order remains on that account;
- required post-closure waiting period and rolling 12-month replacement limit are satisfied.

Count only cards issued within the prior rolling 12 months whose `issue_reason` is `lost`, `stolen`, `fraud`, or `damaged`. Do not count `new_account`, `first_card`, `expired`, `upgrade`, or `bank_reissue`.

| Tier | replacement rule | permitted delivery fee | Classic / Premium / Custom design fee | over-limit handling |
|---|---|---|---|---|
| ENTRY | maximum 2; wait 48 hours after closure | STANDARD $0 | $0 / $10 / $25 | wait for aging out, or customer may elect $25 excess fee |
| MID | maximum 3; no closure wait | STANDARD $0; EXPEDITED $15 | $0 / $10 / $25 | wait for aging out, or customer may elect $15 excess fee |
| PREMIUM | maximum 5; no closure wait | STANDARD $0; EXPEDITED $0; RUSH $35 | $0 / $0 / $15 | must wait for aging out; no fee alternative |
| ELITE | unlimited; no closure wait | STANDARD, EXPEDITED, RUSH $0 | $0 / $0 / $0 | none; priority processing applies before 2pm EST |

Do not translate an unfamiliar account label into a tier without a supported account mapping. Obtain the actual tier/classification from the normal account workflow or treat it as unknown.

Before `order_debit_card_5739`, ask separately for each eligible account for: delivery option, design, confirmed mailing address, and explicit authorization for the exact total of delivery, design, and (if applicable) excess-replacement fee. Explain that those fees are automatically deducted from the linked checking account. A general request for a replacement or a preference for “the free option” is not fee authorization; it may select the no-cost CLASSIC design only after the customer also authorizes any remaining delivery/excess charge. Supply the tool with the exact `delivery_fee`, `design_fee`, and, when applicable, `excess_replacement_fee`. Do not promise a replacement until the order tool confirms it.

## Optional read-only assessment helper

Run `scripts/assess_replacement.py` before an order decision when normalized retrieved data is available. It does not call banking tools or authorize any action.

It reads one JSON object from stdin and writes one JSON object to stdout. Required keys are `current_date`, `accounts`, `cards`, and `lost_card_ids`. Account objects accept documented keys (`account_type`, `account_class`, `balance`) and common retrieval aliases (`class`, `level`, `current_holdings`); aliases are reported rather than silently mapped to a tier. Optional keys are `transactions`, `pending_transactions_by_account`, `pending_refunds_by_card`, `customer_age`, `valid_us_address`, and `closure_times`.

```sh
python3 scripts/assess_replacement.py <<'JSON'
{"current_date":"2025-01-01","accounts":[],"cards":[],"lost_card_ids":[]}
JSON
```

Validate that stdout has `cards`, `accounts`, and `unknown_lost_card_ids`. A missing fact is `UNKNOWN`, never approval. Use its fee schedule only when its tier is known, and still require live tool checks and the customer's final selections and authorization.

## Completion message

Clearly distinguish cards frozen, cards confirmed closed, and cards blocked pending settlement/refunds. State any waiting date or limit restriction, every confirmed order and fee, and expected delivery only after success. If action cannot proceed, state the specific blocker and the next safe step.
