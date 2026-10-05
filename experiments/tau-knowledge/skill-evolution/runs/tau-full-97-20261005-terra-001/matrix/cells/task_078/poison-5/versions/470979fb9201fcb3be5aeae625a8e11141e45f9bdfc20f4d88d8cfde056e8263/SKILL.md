---
name: lost-stolen-debit-card-replacement
description: Secure a verified customer's lost or stolen debit cards and arrange policy-compliant replacements. Use when a customer reports a missing wallet/card, requests debit-card freezing or closure, or needs lost/stolen/damaged replacement eligibility and fees evaluated.
---

# Lost/Stolen Debit Card Security and Replacement

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety boundary

Use this workflow for debit cards only. It distinguishes a temporary freeze from permanent closure:

- **Freeze** is appropriate when a card is merely misplaced and the customer may recover it. The card must be ACTIVE and owned by the verified customer. Call `freeze_debit_card_3892(card_id)` only after explaining that new and recurring transactions will be declined, authorized pending transactions may still settle, and unfreezing is possible later.
- **Close** is the appropriate security action for a card reported lost or stolen when the customer needs a replacement. Closure is permanent and the old card cannot be reactivated. Do **not** freeze an ACTIVE lost/stolen card immediately before closing it: the closure procedure accepts only ACTIVE or PENDING cards, whereas freezing changes it to FROZEN. Close directly if closure prerequisites are satisfied.
- If closure cannot yet proceed because a documented prerequisite is unresolved, freeze an eligible ACTIVE card to reduce exposure, tell the customer what blocks closure, and resume closure only when eligible.

Never claim that a card was secured, closed, ordered, or charged until its banking-tool result confirms it. Do not infer account ownership, tier, transaction status, or fees from an account nickname.

## Inputs required at runtime

Collect or retrieve the following rather than relying on card last-four digits alone:

1. Identity evidence sufficient for the runtime's verification standard (the available verification logger requires two of date of birth, email, phone, and address), then a current timestamp.
2. The customer's `user_id` and all their bank accounts.
3. For every relevant checking account, all debit-card records, including `card_id`, `account_id`, `user_id`, `status`, `issue_reason`, and `date_issued`.
4. Account type, OPEN status, account class/tier, balance, and date opened.
5. The customer's confirmed US domestic delivery address, delivery/design preference, and explicit consent to any nonzero fees or excess-replacement option.
6. Closure facts for each old card: reason, pending/processing card transactions, pending refunds, and card age. Lost/stolen/fraud-suspected closure bypasses only the documented 14-day minimum card-age rule; do not assume it bypasses other documented checks.

## End-to-end workflow

### 1. Verify the customer and record it

1. Locate the user using the supplied identifying information with `get_user_information_by_name`, `get_user_information_by_email`, or `get_user_information_by_id`.
2. Match at least two identity fields supplied by the customer against the retrieved profile. Confirm the mailing address separately.
3. Get the verification timestamp using `get_current_time` and call `log_verification` with the complete retrieved profile fields and timestamp.
4. Treat the verified user ID as the only authorized customer identity for the remainder of the workflow.

### 2. Perform the lost-wallet security check

For every lost or stolen debit-card report, call `get_credit_card_accounts_by_user(user_id)`.

- If credit cards exist, ask whether they were also in the wallet and offer credit-card replacement protection as a separate, confirmed action.
- If none exist, record that the cross-product check was completed. Do not offer a nonexistent product.

### 3. Discover all affected debit cards

Unlock and use the documented account/card tools through the runtime's discoverable-tool mechanism:

1. Unlock `get_all_user_accounts_by_user_id_3847`; retrieve all accounts for the verified `user_id`.
2. Restrict debit-card discovery to checking accounts. Unlock `get_debit_cards_by_account_id_7823`; retrieve cards for each such account.
3. Match every selected card's `user_id` and `account_id` to the verified customer and retrieved account. Do not act on a card with a mismatch.
4. Identify the current cards by status, not by an informal account color/name. Retain closed historical cards only for replacement-history counting.

If the customer reports all cards in a wallet, enumerate all current debit cards belonging to the verified customer across their checking accounts and confirm the list before any non-emergency preference choices. Do not act on CLOSED cards or silently omit a matching ACTIVE/PENDING card.

### 4. Secure each card

For a truly lost/stolen card where replacement is requested, use closure rather than a temporary freeze:

1. Explain permanent closure, that recurring payments need updating, and that authorized pending transactions can still settle.
2. Check that the card is ACTIVE or PENDING, is owned by the verified user, and satisfies the documented closure checks. Determine pending transactions and refunds from authoritative available records; do not guess from unrelated account activity. For lost/stolen/fraud-suspected cases, the 14-day age restriction is bypassed, but unresolved non-bypassed requirements must be handled as documented.
3. Unlock `close_debit_card_4721` and close each eligible card with its exact `card_id` and the applicable documented reason (`lost` or `stolen`; use `fraud_suspected` only when that is the reported reason).
4. Confirm each successful closure individually. A close result is required before treating that card as replaced.

For a temporarily misplaced card when the customer does **not** want permanent closure, use `freeze_debit_card_3892(card_id)` only for an ACTIVE card after the freeze disclosures. A FROZEN card can later be unfrozen only when it remains owned by the verified customer and its linked checking account is OPEN.

### 5. Evaluate each replacement before ordering

A replacement must satisfy the standard debit-card ordering requirements as well as tier-specific replacement rules:

- verified customer and matching card/account ownership;
- a checking account that is OPEN and has been open at least three business days;
- customer age at least 18;
- confirmed valid US domestic address;
- minimum available balance of $25 and sufficient funds for all applicable fees;
- no active card remaining after closure and no PENDING debit-card order for that account;
- tier-specific replacement history, waiting period, allowed shipping, fees, and customer confirmation.

Use `scripts/evaluate_replacement.py` once per account after retrieving all card history. It deterministically counts only cards issued in the last rolling 12 months with `issue_reason` of `lost`, `stolen`, `fraud`, or `damaged`. It excludes `new_account`, `first_card`, `expired`, `upgrade`, and `bank_reissue`.

For customers asking for the best option that is free, the helper selects the fastest delivery allowed at a $0 delivery fee and the highest design tier with a $0 design fee. Confirm that selection rather than assuming the customer wants a premium-looking design. The customer may instead choose any allowed delivery/design combination and must be told its exact total fee before ordering.

Tier rules applied by the helper:

| Tier | Limit in rolling 12 months | Post-closure wait | Allowed delivery / delivery fee | Design fees |
|---|---:|---|---|---|
| ENTRY | 2 | 48 hours | STANDARD / $0 | CLASSIC $0, PREMIUM $10, CUSTOM $25 |
| MID | 3 | none | STANDARD $0; EXPEDITED $15 | CLASSIC $0, PREMIUM $10, CUSTOM $25 |
| PREMIUM | 5 | none | STANDARD $0; EXPEDITED $0; RUSH $35 | CLASSIC $0, PREMIUM $0, CUSTOM $15 |
| ELITE | unlimited | none | STANDARD, EXPEDITED, RUSH all $0 | CLASSIC, PREMIUM, CUSTOM all $0 |

If ENTRY or MID has reached its limit, offer the documented choice to wait until the oldest counted replacement leaves the window or to pay the applicable excess fee ($25 ENTRY; $15 MID). PREMIUM must wait after its limit, and ELITE has no limit. The excess fee is in addition to shipping/design charges and requires explicit consent.

### 6. Order and confirm replacements

1. Select a permitted delivery and design, calculate all fees, confirm the total debit and confirm the delivery address.
2. Verify the account balance covers the total. All delivery, design, and applicable excess replacement fees are automatically charged to the linked checking account.
3. Unlock `order_debit_card_5739`. Inspect its runtime schema and supply its required fields, including the account/card-order details and the exact `delivery_fee` and `design_fee` calculated for the tier. Do not invent unsupported parameters; use the runtime schema for any excess-fee field or required replacement reason.
4. Order one replacement per eligible checking account only after its old card was successfully closed and all prerequisites pass. Process results independently so one failed account does not cause a false success for another.
5. Tell the customer the confirmed delivery timeframe/fees and that new cards activate on first PIN use, subject to the applicable activation process. Remind them to update recurring payments after permanent closure.

If account/card data, a card-specific pending/refund check, the ordering schema, or a prerequisite cannot be obtained, do not bypass it. Explain the precise blocker and use an authorized escalation path when needed.

## Helper interface

Run the packaged helper through the skill runtime:

```json
{
  "now": "2025-01-15T10:00:00-05:00",
  "tier": "PREMIUM",
  "account": {
    "account_type": "checking",
    "status": "OPEN",
    "balance": "100.00",
    "date_opened": "2024-12-01"
  },
  "verification": {
    "verified": true,
    "owner_confirmed": true,
    "age_years": 30,
    "domestic_address_confirmed": true
  },
  "card_order_state": {
    "active_cards_after_close": 0,
    "pending_cards": 0,
    "old_card_closed_at": "2025-01-15T09:00:00-05:00"
  },
  "replacement_cards": [
    {"issue_reason": "lost", "date_issued": "2024-09-03"}
  ],
  "requested_delivery": null,
  "requested_design": null,
  "use_excess_replacement_fee": false
}
```

Call `scripts/evaluate_replacement.py` with that JSON on stdin. It emits JSON containing `order_ready`, blocking reasons, replacement count, allowed choices, selected fees, total fees, and any date when a limit will age out. Validate that `order_ready` is true, the selected choices match the customer's confirmed choices, and the output total does not exceed the retrieved available balance before calling the ordering tool.
