---
name: secure-lost-wallet-card-protection
description: Handle a verified customer's misplaced, lost, or stolen debit card(s), including identifying eligible debit cards, temporarily freezing active cards, and offering/ordering a credit-card replacement when a lost wallet also contained an Rho-Bank credit card.
---

# Secure Lost-Wallet Card Protection

Use this workflow when a customer reports a misplaced, lost, or stolen wallet or debit card and needs protection for one or more cards. A freeze is temporary; a closure is permanent and is appropriate only when the card is confirmed lost/stolen or the customer asks to cancel it.

## Preconditions and safety controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

1. Identify the customer with a supplied profile field (such as email or name), then retrieve the profile using the corresponding lookup tool.
2. Verify at least two of the profile fields: date of birth, email, phone number, and address. Do not treat an unverified assertion as verification. Obtain the current time and call `log_verification` with the complete retrieved profile and timestamp after successful verification.
3. Establish that the requester owns each affected product: the returned debit-card or credit-card record must belong to the verified `user_id`.
4. Confirm the requested protection choice. Clearly distinguish temporary freezing from permanent closure. Do not close a card merely because it is missing if the customer selected a freeze.
5. Never perform a freeze, replacement, or other state-changing action if identity, ownership, required confirmation, or eligibility cannot be established. Explain the missing prerequisite or transfer to a human agent for a security concern when appropriate.

## Debit-card temporary freeze

### Inform before acting

For each requested debit-card freeze, explain before submission that:

- new transactions and recurring payments/subscriptions will be declined while the card is frozen;
- already-authorized pending transactions can still process;
- the card can be unfrozen later through customer service or the mobile app; and
- freezing does not block ATM access for a customer who has the PIN; ATM blocking must be enabled separately in the mobile app.

### Discover and validate cards

1. Call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
2. Retain only the customer's checking accounts. For each requested checking account, call `get_debit_cards_by_account_id_7823(account_id)`.
3. Match each returned card's `user_id` and `account_id` to the verified customer and selected open checking account. A card is eligible for freezing only if its current status is `ACTIVE`.
4. Do not freeze `PENDING`, `CLOSED`, or already `FROZEN` cards. Report such a card accurately; do not retry a prior action solely because status has changed.
5. Unlock `freeze_debit_card_3892`, then call it once for every eligible, customer-selected debit `card_id`. Treat the tool result as the authoritative outcome. Confirm only successful freezes.

If a card is confirmed lost or stolen and the customer requests permanent deactivation instead, use the applicable close-card workflow rather than this temporary-freeze workflow.

## Cross-product wallet protection

When the report is lost or stolen (including a wallet that may be lost), after handling the debit-card request call `get_credit_card_accounts_by_user` for the verified user. If there are credit cards, tell the customer that a lost wallet can expose multiple cards, ask whether each relevant credit card was in the wallet, and offer a replacement with a new number. Record a declined offer according to the available customer-record process; do not order a replacement without the customer's agreement.

## Credit-card replacement

Use this section only after the customer confirms that an Rho-Bank credit card was in the missing wallet and explicitly requests a replacement.

1. Reconfirm that the returned credit-card account belongs to the verified user and is eligible for replacement. If eligibility cannot be confirmed from the available account information or policy, do not unlock or call the order tool; explain the limitation and seek the appropriate support path.
2. Confirm the full shipping address, including unit/suite information where applicable.
3. Record exactly one permitted reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`. Use the customer's report; do not invent fraud.
4. Confirm shipping selection:
   - `standard`: 7–10 business days, no fee.
   - `expedited`: 2–3 business days. Fee is $15 for entry tier, $10 for mid tier, and $0 for premium tier and above. Obtain explicit fee acknowledgement whenever an expedited fee applies.
   - Strongly recommend expedited delivery for `fraud_suspected` or `stolen`, but honor a confirmed standard selection.
5. Unlock `order_replacement_credit_card_7291`, then call it with the credit-card account identifier, `reason`, confirmed `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and relevant `notes`. Use `false` for fee acknowledgement only when no fee applies; otherwise submit the customer's affirmative acknowledgement.
6. On success, tell the customer that the old credit card is automatically cancelled for new purchases, state the selected delivery window, and advise them to watch for order/shipment email. For fraud or theft, remind them to review transactions and dispute unauthorized charges.

## Tool-use sequence for a typical multi-card case

1. Retrieve profile, verify two fields, obtain current time, and log verification.
2. Retrieve checking accounts; retrieve debit cards for each relevant checking account; verify ownership/status; disclose freeze effects; unlock and freeze every eligible selected debit card.
3. Retrieve credit-card accounts. If the customer confirms a credit card was in the wallet and requests replacement, confirm address, reason, speed, fee consent if needed, eligibility, then unlock and submit the replacement order.
4. Give a concise completion summary identifying only actions whose tools reported success, plus any card that was ineligible or could not be processed.

## Validation checklist

Before finalizing, verify all of the following from live tool results:

- Verification was logged only after two matching identity fields were confirmed.
- Each frozen debit card belonged to the verified user, was linked to the selected checking account, and was `ACTIVE` before submission.
- Every requested eligible debit card was submitted exactly once, and each reported completion has a successful tool result.
- The credit-card offer was made for a reported missing wallet when credit cards existed.
- A replacement order, if any, has customer confirmation, a matching account owner, one allowed reason, a confirmed address, shipping selection, and applicable expedited-fee consent.
- The final response does not claim an unavailable action, does not expose full card numbers, and accurately states remaining limitations.

## Failure handling

If account lookup returns no matching checking account or debit card, state that no matching eligible card was found and do not guess a card ID. If a state-changing tool fails or returns an uncertain result, do not repeat the operation; communicate that the requested protection could not be confirmed and escalate for security assistance. If the customer asks to unfreeze later, require a verified customer, card ownership, `FROZEN` status, and an open linked checking account before using `unfreeze_debit_card_3893`.
