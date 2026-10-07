---
name: lost-wallet-card-protection
description: Handle a verified customer’s temporarily misplaced, lost, or stolen wallet containing debit cards, including safe debit-card freeze/close decisions and the required cross-product credit-card replacement offer. Use when the request involves protecting debit cards and potentially a credit card after a wallet incident.
---

# Lost Wallet Card Protection

## Scope and safety boundary

Use this workflow for debit cards in a wallet that may be misplaced, lost, or stolen. A freeze is temporary; a closure is permanent and cannot be undone.

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit where applicable, fees, limits, cutoffs, recipient and card details, and confirmation requirements. Record which checks are applicable and why any non-applicable check does not apply. Do not perform an action merely because a card or account was found in a lookup.

This Skill plans and validates prerequisites only. The executor must use the runtime’s ordinary banking tools to make banking changes and must accurately report each tool result. Never claim an action succeeded before its action tool confirms success.

## Inputs to collect at runtime

1. The customer’s identity locator and enough standard-verification responses to meet the runtime’s verification policy. In the supplied runtime, verify at least two of date of birth, email, phone number, and address against the retrieved profile, then call `log_verification` with the complete required audit fields and current timestamp.
2. Whether the wallet/card is temporarily misplaced versus confirmed lost or stolen, and which debit cards were in it.
3. Explicit confirmation of the desired action for every affected debit card: temporary freeze, or permanent close.
4. For a credit card that was in the wallet, explicit consent to order a replacement, the replacement reason, confirmed delivery address, desired shipping speed, and fee acknowledgement when applicable.

Do not reuse stale verification for a different customer or infer consent for a credit-card replacement from consent to freeze a debit card.

## Debit-card protection workflow

1. **Verify and log identity.** Locate the customer and compare the required identity fields. Stop if verification fails or is incomplete.
2. **Retrieve all accounts.** Use `get_all_user_accounts_by_user_id_3847(user_id)` and identify the customer’s checking accounts. Confirm the relevant account/card relationship and ownership.
3. **Retrieve debit cards per checking account.** Use `get_debit_cards_by_account_id_7823(account_id)` for every named or potentially affected checking account. Multiple cards can be returned, including historical cards. Match each candidate using `card_id`, linked `account_id`, `user_id`, last four digits where available, and `status`.
4. **Choose the correct disposition.**
   - Use a **freeze** when the customer is still looking for the card or wants a reversible temporary lock.
   - If the customer confirms a card is lost or stolen, recommend **closure** instead. Do not silently substitute closure for a requested freeze; obtain explicit consent to close.
   - Before freezing, explain that new and recurring transactions will be declined, already authorized pending transactions may still settle, and the customer may unfreeze later through customer service or the mobile app. A freeze does not block ATM access for someone with the PIN; ATM Block must be enabled separately in the mobile app.
5. **Check freeze eligibility for each card independently.** The customer must be verified, own the card (`card.user_id` matches the verified user), and the card must be `ACTIVE`. Do not call a freeze action for `PENDING`, `CLOSED`, or already `FROZEN` cards. A frozen card not unfrozen within 90 days receives a reminder notification.
6. **Freeze only eligible, consented cards.** Use `freeze_debit_card_3892` with the individual `card_id`. If the runtime exposes this as an agent-discoverable tool, unlock that exact tool through the standard discoverable-tool mechanism before calling it; otherwise use the normal named banking tool. Process each card separately and preserve each result.
7. **Confirm results accurately.** State which cards were successfully frozen and identify any card that was not changed plus the specific eligibility reason. Do not expose full card numbers.
8. **If permanent closure is selected instead:** follow the separate debit-card closure procedure. In addition to verification and ownership, it requires an `ACTIVE` or `PENDING` card, no pending/processing transactions, no pending refunds unless the customer provides the documented written acknowledgement, and normally a 14-day minimum card age. Lost, stolen, and fraud-suspected reasons bypass only the age requirement. Use `close_debit_card_4721(card_id, reason)` only after all applicable checks pass.

## Required cross-product credit-card protection

When the report is lost or stolen, including a wallet that may be gone, check credit cards using `get_credit_card_accounts_by_user(user_id)` after identity verification. If one or more cards are found, proactively ask whether each relevant credit card was also in the wallet and offer a replacement with a new card number. Explain that wallet loss can expose multiple cards.

If the customer says a credit card was in the wallet:

1. Confirm they want a replacement; an offer or discussion is not order consent.
2. Confirm account ownership and replacement eligibility from the applicable knowledge base. Do **not** unlock or call the replacement order tool until eligibility is confirmed. If the criteria or an eligibility result are unavailable, explain that an order cannot yet be placed and use the supported escalation path if needed.
3. Record exactly one supported reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.
4. Confirm the full primary or alternate shipping address, including apartment/unit details, with the customer.
5. Offer shipping options: standard delivery is 7–10 business days with no fee; expedited delivery is 2–3 business days. For a Silver Rewards card, expedited shipping costs $10. Obtain affirmative acknowledgement of an applicable expedited fee before ordering. Strongly recommend expedited shipping for `fraud_suspected` or `stolen`.
6. Unlock `order_replacement_credit_card_7291`, then call it through `call_discoverable_agent_tool` with the credit-card `account_id` or card identifier accepted by the tool, `reason`, `shipping_address`, `shipping_speed` (`standard` or `expedited`), `expedited_fee_acknowledgement`, and relevant `notes`.
7. After a successful order, disclose that the old credit card is automatically cancelled for new purchases, give the selected delivery window, advise the customer to watch for order/shipping emails, and document the order. For fraud-suspected or stolen cases, remind the customer to review transactions and dispute unauthorized charges.

If the customer declines a credit-card replacement, document that the required offer was made and declined. Do not order it.

## Handling security-sensitive or unsupported cases

- If a debit card is actually reported stolen and a decline/status workflow requires enhanced identity checks, do not attempt to reactivate it. A customer who denies reporting a stolen card is a major security flag; transfer to a human security team using the runtime’s supported transfer flow.
- Do not disclose internal fraud decline codes or bank-initiated fraud reasons to the customer.
- A card in a status other than the status required by the desired action must not be forced through a tool call. Explain the supported next step instead.
- For unfreezing, separately verify identity and ownership, confirm the card is `FROZEN`, and confirm its linked checking account is `OPEN`; then use `unfreeze_debit_card_3893(card_id)` and confirm it is immediately active.

## Optional deterministic readiness validation

Use `scripts/validate_card_protection.py` before taking action when runtime lookup data has been normalized into JSON. It does not execute banking tools and cannot establish identity or consent. It flags missing prerequisites and returns an action-by-action readiness assessment.

Example:

```json
{
  "user_id": "runtime-user-id",
  "identity_verified": true,
  "requested_debit_action": "freeze",
  "requested_card_ids": ["card-a", "card-b"],
  "debit_cards": [
    {"card_id": "card-a", "user_id": "runtime-user-id", "account_id": "checking-a", "status": "ACTIVE"}
  ],
  "accounts": [{"account_id": "checking-a", "account_type": "CHECKING", "status": "OPEN"}],
  "credit_replacement": {
    "requested": false,
    "card_in_wallet": false
  }
}
```

Run it by sending that JSON on standard input to `scripts/validate_card_protection.py`. Review every `blocked` result, perform only `ready` actions with recorded customer consent, and preserve tool confirmation results in the case record.
