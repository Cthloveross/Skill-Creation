---
name: stolen-wallet-card-protection
version: 1.2.0
description: Handle a verified report that a wallet, debit card, or credit card was lost or stolen. Use to protect affected debit cards through the documented closure workflow and to offer documented credit-card replacement protection without inventing a credit-card freeze action.
---

# Stolen Wallet Card Protection

A confirmed stolen or lost debit card is a permanent-closure case, not a temporary debit-card freeze. This workflow separates the debit-card closure action from the credit-card replacement offer, and never represents one as protection for the other product.

## Safety and tool-access rules

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

- Before every banking action verify identity, authority, ownership, relevant account/card status, product eligibility, and the customer's required confirmation. Never claim success until the action response says it succeeded.
- Compare at least two of date of birth, email, phone number, and mailing address to a retrieved customer profile. Obtain `get_current_time` and then call `log_verification` with the retrieved profile fields and timestamp.
- The named card/account operations may be agent-discoverable in a runtime. Before using one in that case, call `unlock_discoverable_agent_tool` with its exact name, then use `call_discoverable_agent_tool` with a JSON-string arguments object. Unlocking is not a banking action.
- Use only retrieved IDs. Do not expose sensitive returned fields or invent card, transaction, refund, freeze, replacement, or dispute results.
- If a required fact is unavailable, say what prevents the action. Do not substitute a freeze for authorized permanent closure or repeat an action with an unknown outcome.

## 1. Establish the affected debit-card scope

1. Confirm which debit cards were in the lost/stolen wallet and obtain explicit authorization to close each affected debit card with reason `lost` or `stolen`.
2. Explain that closure is permanent, recurring payments need updating, authorized pending transactions can still settle, and refunds to a closed debit card credit the linked checking account. Offer debit replacement only if a supported replacement process is available.
3. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Match the customer-named checking accounts to retrieved open checking accounts.
4. Unlock and call `get_debit_cards_by_account_id_7823` for each matching account. For each selected card, verify its `user_id`, linked `account_id`, and `ACTIVE` or `PENDING` status.

## 2. Evaluate and close debit cards

A debit closure additionally requires no pending/processing transaction and no pending refund (unless the customer gives the documented written refund acknowledgement). A 14-day minimum age applies except for `lost`, `stolen`, and `fraud_suspected`.

1. Use `scripts/evaluate_debit_closure.py` with current, structured preflight facts to identify missing facts and blockers. Its output is advisory and does not perform banking actions.
2. Obtain pending-transaction and pending-refund eligibility from a supported current record or closure service response; never infer either from a debit-card lookup that omits it. If the available closure service is the runtime's eligibility-enforcing operation, submit the single authorized closure request and treat its result as authoritative for the remaining service-side eligibility checks. If it rejects or reports a pending transaction/refund, do not retry; explain the stated blocker. If no supported way can establish or enforce those checks exists, do not close the card.
3. For an eligible, explicitly authorized card, unlock `close_debit_card_4721` and call it with exactly `{"card_id": retrieved_id, "reason": "lost"}` or `"stolen"` as applicable.
4. A success response confirms only that card. Confirm permanent deactivation, the recurring-payment and refund information, and that pending authorized transactions may still process. For each failure/ambiguous response, do not say the card was closed and escalate only when supported and necessary.

For non-security reasons, provide `earliest_eligible_date` if the helper reports the age blocker. The age rule is bypassed for lost/stolen/fraud-suspected reports, not the transaction/refund rules.

### Later correction or recovery report

If a customer later says that a card reported lost or stolen was found, retrieve its current status. A card whose closure succeeded is permanently closed and cannot be unfrozen or reactivated, even if it was not actually stolen. State that result plainly and offer the supported standard replacement route; do not call an unfreeze tool. A card that was only frozen and remains `FROZEN` follows the separate unfreeze procedure, including its own ownership and open-linked-account checks.

### Debit-card replacement availability

Closing a debit card does not itself order a replacement. If the customer requests one, use a documented debit-card replacement procedure/tool only if it is available and its prerequisites can be met. If the only documented instruction is that replacement occurs through a standard process and no safe tool or procedure is available, do not invent an order; explain this and transfer to the appropriate supported specialized team with the verified customer, affected account(s), closure result(s), and requested replacement scope.

## 3. Credit-card protection

For a wallet theft/lost debit-card report, unlock and call `get_credit_card_accounts_by_user` with the verified user ID. If credit cards exist, explain that they may also have been compromised, ask whether each was in the wallet, and offer a replacement with a new card number. There is no documented credit-card freeze operation in this workflow: do not claim the card was frozen, cancelled, or replaced merely because the customer requested it.

If the customer accepts replacement for a particular credit card, before unlocking any order tool:

1. Reconfirm identity, retrieve the selected account, confirm complete shipping address, record exactly one reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), choose standard or expedited shipping, and confirm eligibility.
2. State standard delivery is 7–10 business days and free. Expedited delivery is 2–3 business days; it costs $15 for EcoCard/entry tier, $10 for mid-tier, and is complimentary for Gold/premium tier. Obtain explicit fee consent whenever a fee applies.
3. Unlock `order_replacement_credit_card_7291`; call it with the retrieved account/card identifier, reason, confirmed `shipping_address`, `shipping_speed`, applicable expedited-fee acknowledgement, and notes.
4. Only after success, say the old card is cancelled, give the selected delivery window, mention email notifications, and for stolen/fraud cases remind the customer to review and dispute unauthorized charges.

Do not order a credit replacement from a request to freeze alone: obtain the replacement authorization and all shipping prerequisites first. If immediate credit-card security action is requested but no documented eligible action can be completed, clearly explain the limitation and use a supported security escalation only when warranted.

## Helper interface

Run `scripts/evaluate_debit_closure.py` with one JSON object on stdin and consume one JSON object on stdout. It accepts:

```json
{"as_of_date":"YYYY-MM-DD","customer_user_id":"string","reason":"stolen","cards":[{"card_id":"string","user_id":"string","status":"ACTIVE","date_issued":"YYYY-MM-DD","pending_transactions":false,"pending_refunds":false,"refund_acknowledgement_in_writing":false}]}
```

The result has `reason`, `results` (per-card `eligible_to_close`, `blockers`, `earliest_eligible_date`, and `minimum_age_bypassed`) and `all_cards_eligible`. The helper rejects an absent or unsupported closure reason with a blocker. Missing facts are blockers. Example: `python3 scripts/evaluate_debit_closure.py < input.json`. Validate that the result count equals the supplied card count and that each action is limited to a result with no preflight blocker, unless the documented closure service itself returns the authoritative eligibility decision as described above.
