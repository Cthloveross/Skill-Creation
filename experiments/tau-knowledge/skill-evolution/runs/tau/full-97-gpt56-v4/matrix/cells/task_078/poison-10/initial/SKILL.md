---
name: lost-debit-card-closure-and-replacement
description: Securely handle a verified customer's lost or stolen debit cards by identifying every affected card, checking closure and replacement eligibility, permanently closing eligible cards, and ordering no-fee appropriate replacements using the linked checking account's tier. Use for lost/stolen-card requests, not for a merely misplaced card when the customer wants a temporary freeze.
---

# Lost Debit Card Closure and Replacement

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

A reported lost or stolen card should be permanently closed rather than temporarily frozen once the verified cardholder authorizes closure. A closed card cannot be reactivated. Do not assume a stated number of cards, their account IDs, card IDs, tiers, or eligibility from the customer's description; retrieve and reconcile them.

Use normal banking tools for all retrievals and mutations. A planning script only calculates recommendations; it never performs a banking action.

## Required workflow

1. **Establish and log verification before any card or account action.** Obtain and match at least two of date of birth, email, phone number, and address against the customer record. Obtain the current time and call `log_verification` with the complete matched customer record and verification time. Confirm that the verified person authorizes permanent closure and replacement. If identity, ownership, or authorization is not established, stop without changing cards.

2. **Find the full debit-card relationship.** Unlock and use `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. For every checking account returned, unlock and use `get_debit_cards_by_account_id_7823`. Reconcile the result with the customer's report. For each card intended for closure, require `card.user_id == verified_user_id` and a status of `ACTIVE` or `PENDING`. Do not act on cards belonging to another user, closed/frozen cards, savings accounts, or unconfirmed extra cards.

3. **Check closure eligibility card by card.** For each linked account, unlock and use `get_bank_account_transactions_9173` and inspect for pending or processing activity. Also retrieve or otherwise inspect the available refund records for pending refunds; transaction history alone must not be represented as proof that pending refunds do not exist. A card with pending/processing transactions cannot be closed yet. A card with a pending refund cannot be closed unless the customer provides the required written acknowledgement that refunds will be credited to the linked checking account. For a lost/stolen reason, the 14-day minimum card-age rule is bypassed, but all other checks remain mandatory.

4. **Close only eligible, authorized cards.** Unlock `close_debit_card_4721` and call it with the retrieved `card_id` and `reason` of `lost` or `stolen`, as applicable. Do not substitute `fraud_suspected` unless that is the customer's stated reason. Treat an unsuccessful or ambiguous response as not closed; do not order its replacement. Record each result separately so one blocked card does not cause unsupported action on another.

5. **Check replacement eligibility after confirmed closure.** For each successfully closed card's checking account, require all of the following:
   - account type is `checking`, status is `OPEN`, and it has been open at least three business days (weekends excluded);
   - the account balance is at least $25;
   - the verified customer is at least 18;
   - the verified address is a valid US domestic address;
   - no active debit card and no `PENDING` debit-card order remain for that account;
   - replacement history is counted from all account cards issued in the rolling prior 12 months whose `issue_reason` is `lost`, `stolen`, `fraud`, or `damaged` only.

   Rerun the card lookup after closure when needed rather than relying on stale status. If closure has succeeded but replacement requirements are not met, clearly distinguish the successful closure from the deferred replacement.

6. **Choose and disclose the replacement.** Determine tier from the linked account's class/tier field and count qualifying prior replacements. Use `scripts/replacement_policy.py` to make the fee-free recommendation from structured retrieved data. The customer must be told the exact delivery and design fees, that applicable fees are automatically deducted from the linked checking account, and the delivery expectation. Obtain confirmation for any nonzero fee. A customer who requested only free options must not be charged an excess-replacement fee; provide the relevant wait-until alternative instead.

   The no-fee preference defaults are:
   - ENTRY: STANDARD shipping and CLASSIC design ($0/$0); a replacement cannot be ordered until 48 hours after closure.
   - MID: STANDARD and CLASSIC ($0/$0).
   - PREMIUM: EXPEDITED and PREMIUM design ($0/$0).
   - ELITE: RUSH and PREMIUM design ($0/$0). Do not select CUSTOM without a supplied upload even if it is free.

   At the rolling-limit threshold, ENTRY may pay $25 or wait, MID may pay $15 or wait, PREMIUM must wait, and ELITE has no limit. Never select a paid alternative without explicit informed confirmation.

7. **Order replacements only after all preceding checks pass.** Unlock `order_debit_card_5739`, inspect its exposed argument schema, and provide the retrieved eligible account/card details plus the exact `delivery_fee` and `design_fee` returned by the planner. Use only delivery/design values supported by that tool. Confirm the tool result, expected delivery, charged fees, and that the old card is permanently deactivated. Remind the customer to update recurring payments and that refunds to a closed card credit the linked checking account.

8. **Lost-wallet cross-product protection.** Use `get_credit_card_accounts_by_user` for a confirmed lost/stolen wallet. If credit cards exist, explain the risk and offer a replacement credit card; do not order one without its own authorization. If none exist, state no credit-card replacement was needed.

## Handling blockers

- Pending transactions/refunds, missing refund evidence, invalid ownership, missing verification, missing authorization, or unavailable required retrievals are blockers to the affected closure/order. Explain the precise blocker and take no unsupported action.
- If the customer initially asks to freeze but subsequently authorizes permanent closure, close eligible cards directly. Do not freeze first merely as an intermediate step, because closure requires an ACTIVE or PENDING card and freezing changes the status.
- If a card cannot yet be closed due to pending activity, explain that it remains exposed and offer the documented temporary-freeze workflow only if its status is ACTIVE and the customer requests that temporary protection; do not claim it is closed.
- A report of suspected fraud should additionally prompt transaction review/dispute guidance and a recommendation to change online-banking credentials. A customer who says a stolen-card report was unauthorized is a security escalation and should be transferred to a human security agent after the required enhanced verification.

## Planner invocation

`replacement_policy.py` reads one JSON object from stdin and emits one JSON object to stdout. It accepts `tier`, `replacement_count_last_12_months`, `closed_at` (ISO timestamp), `now` (ISO timestamp), `preference` (`free_best` or `paid_confirmed`), and optional `custom_upload_supplied` (boolean). It returns supported delivery/design choices, exact fees, whether ordering may proceed now, and a human-readable blocker/reason.

Example (illustrative only; supply values retrieved in the current case):

```json
{"tier":"PREMIUM","replacement_count_last_12_months":1,"closed_at":"2025-01-02T10:00:00","now":"2025-01-02T10:01:00","preference":"free_best"}
```

Validate that `may_order_now` is true, both fee values equal the amounts disclosed to the customer, and the returned delivery/design choices match the tier and the order tool's supported enums. This validation does not replace the live account, card, ownership, balance, address, and confirmation checks above.
