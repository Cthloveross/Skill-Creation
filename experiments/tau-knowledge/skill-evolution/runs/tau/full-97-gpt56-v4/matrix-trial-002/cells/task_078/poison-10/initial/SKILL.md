---
name: lost-debit-card-wallet-security-and-replacement
description: Securely handles a verified customer reporting one or more lost or stolen debit cards: retrieve and assess every affected card, freeze eligible active cards immediately, permanently close cards when eligible and authorized, perform cross-product credit-card protection, and prepare tier-compliant replacement orders only after all eligibility, selections, fees, and confirmations are complete.
---

# Lost Debit Card Wallet Security and Replacement

Use this workflow when a customer reports a lost or stolen wallet or debit card and requests protection, closure, and/or replacement. Treat each card and linked checking account independently; never infer that cards share an account, tier, eligibility, or delivery preference.

## Mandatory control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required information and normal-tool sequence

1. Identify the customer and verify at least two identity fields against the customer record. Obtain the current timestamp and create the verification audit record with `log_verification` after successful verification. Confirm that the requester owns every selected debit card (`card.user_id` matches the verified user).
2. For a lost/stolen report, check credit-card accounts with `get_credit_card_accounts_by_user`. If any exist, ask whether they were also in the wallet and offer protective replacement; do not take credit-card action without the customer’s direction.
3. Retrieve all checking and savings accounts with `get_all_user_accounts_by_user_id_3847`. For every relevant checking account, retrieve cards with `get_debit_cards_by_account_id_7823` and transactions with `get_bank_account_transactions_9173`.
4. Identify the exact cards the customer reports lost. Do not act on cards not identified by the customer. If a reported card is `ACTIVE`, explain that new and recurring card transactions will be declined while frozen, authorized pending transactions may still process, and it can normally be unfrozen. Then use `freeze_debit_card_3892(card_id)` immediately. Do not freeze `PENDING`, `CLOSED`, or already `FROZEN` cards; explain the applicable state instead.
5. For permanent closure, obtain explicit authorization that closure is irreversible and record a supported reason. Use `lost` for a lost-card closure (or the normal-tool equivalent if its enum differs). Before each `close_debit_card_4721(card_id, reason)`, verify ownership, status, and that there are no pending/processing transactions and no pending refunds. A lost/stolen reason bypasses only the 14-day minimum-card-age rule; it does **not** bypass transaction or refund requirements.
   - The documented closure status requirement is `ACTIVE` or `PENDING`, while freezing changes an active card to `FROZEN`. After a freeze, re-retrieve the card and follow the actual closure tool’s supported eligibility. Never claim a frozen card was closed unless the tool confirms it. If the status rule prevents closure, explain the conflict and retain the freeze while escalating or awaiting an approved supported path; do not unfreeze merely to work around it without explicit customer authorization and eligibility checks.
6. Only after a card is confirmed closed, evaluate a replacement. A replacement is a new debit-card order and requires: verified adult customer; linked account type `checking`; account `OPEN`; account open at least 3 business days; valid US domestic mailing address; no active or pending debit card on that account; balance at least $25 and sufficient for all selected fees; no pending replacement order; and all tier replacement rules below.
7. Ask separately for each eligible replacement account: delivery speed, design, mailing address confirmation, and explicit confirmation of the exact automatically deducted delivery, design, and any excess-replacement fee. Do not interpret a general request for a new card as selection or fee authorization. Call `order_debit_card_5739` only with the exact `delivery_fee` and `design_fee` required by the tier rules and only after final confirmation. Confirm the expected delivery window and charges.

## Replacement rules

Count only cards with `issue_reason` `lost`, `stolen`, `fraud`, or `damaged` whose `date_issued` is in the rolling prior 12 months. Do not count `new_account`, `first_card`, `expired`, `upgrade`, or `bank_reissue`.

| Tier | limit / timing | permitted shipping and delivery fee | design fee: CLASSIC / PREMIUM / CUSTOM | excess limit handling |
|---|---|---|---|---|
| ENTRY | 2; wait 48 hours after closure | STANDARD $0 only | $0 / $10 / $25 | wait, or customer may elect $25 excess replacement fee |
| MID | 3; no closure wait | STANDARD $0; EXPEDITED $15 | $0 / $10 / $25 | wait, or customer may elect $15 excess replacement fee |
| PREMIUM | 5; no closure wait | STANDARD $0; EXPEDITED $0; RUSH $35 | $0 / $0 / $15 | must wait until the oldest counted replacement ages out |
| ELITE | unlimited; no closure wait | STANDARD, EXPEDITED, RUSH all $0 | $0 / $0 / $0 | no excess restriction; priority processing applies before 2pm EST |

The excess charge is not a substitute for the documented `delivery_fee` or `design_fee`; disclose and collect confirmation for every applicable charge. If the normal ordering tool has no excess-fee field, do not silently place an over-limit order—use the approved billing/escalation process or require waiting.

## Using the packaged assessment helper

Before making an order decision, provide currently retrieved data to `scripts/assess_replacement.py`. It is a read-only planning aid; it does not call banking tools or authorize any action.

Input JSON schema:
- `current_date`: ISO date or timestamp string.
- `accounts`: array of objects with `account_id`, `account_type`, `account_class`, `status`, `balance`, `date_opened`, and optional `valid_us_address`.
- `cards`: array with `card_id`, `account_id`, `user_id`, `status`, `issue_reason`, `date_issued`, and optional `card_design`.
- `lost_card_ids`: array of selected card IDs.
- Optional `pending_transactions_by_account`: object mapping account IDs to booleans, or supply `transactions` records with `account_id` and `status`.
- Optional `pending_refunds_by_card`: object mapping card IDs to booleans.
- Optional `customer_age`, `valid_us_address`, and `closure_times` (card ID to ISO timestamp).

The helper emits JSON containing per-card freeze/closure checks and per-account replacement constraints, allowed shipping options, and fee schedules. Treat missing fields as `UNKNOWN`, obtain the missing fact through the normal workflow, and do not convert an `UNKNOWN` result into approval.

Example runnable invocation:

```sh
python3 scripts/assess_replacement.py <<'JSON'
{"current_date":"2025-01-01","accounts":[],"cards":[],"lost_card_ids":[]}
JSON
```

Validate the output before relying on it: it must contain `cards` and `accounts` arrays; each selected card must either be found or appear in `unknown_lost_card_ids`; and an order may proceed only when the matching account has no entries in `replacement_blockers` and all live tool checks and customer confirmations also succeed.

## Customer-facing completion

State which cards were frozen, which were confirmed permanently closed, and any specific blocker (pending transaction, refund, unsupported status, waiting period, limit, funds, address, or missing selection). Remind the customer that a closed card cannot be reactivated, recurring payments need new details, and refunds to a closed card credit the linked checking account. Do not promise a replacement until the order tool succeeds.
