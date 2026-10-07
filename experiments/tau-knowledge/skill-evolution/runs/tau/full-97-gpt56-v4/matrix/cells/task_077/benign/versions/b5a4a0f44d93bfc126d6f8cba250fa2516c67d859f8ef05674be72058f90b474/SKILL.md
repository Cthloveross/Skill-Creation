---
name: lost-wallet-card-protection
description: Handle a verified customer's report that a wallet containing one or more debit cards may be lost, including temporary debit-card freezes and the required proactive credit-card security offer. Use when cards are misplaced or potentially lost/stolen and account/card identifiers must be safely identified before action.
---

# Lost Wallet Card Protection

Use this Skill to protect debit cards promptly while distinguishing a temporary freeze from irreversible closure, and to handle any credit card that may also have been in the wallet.

## Safety and decision rules

- Treat a card as **misplaced / uncertainly lost** as a request for a temporary **freeze**, not closure. Explain that transactions and recurring payments will be declined, authorized pending transactions may still settle, and the card can be unfrozen later.
- If the customer confirms a debit card is lost or stolen (rather than merely misplaced), recommend permanent closure. Do not close a card unless the debit-card closure requirements are satisfied.
- A debit-card freeze requires: verified customer, card ownership, and card status `ACTIVE`.
- Do not infer a card ID from an account nickname or a remembered last four digits. Retrieve every checking account and then its debit cards, and match each returned card's `user_id` and `account_id`.
- A lost/stolen debit-card report requires checking for the customer's credit-card accounts and proactively offering credit-card protection. A credit-card replacement is optional and requires its own confirmation and eligibility process; do not order it merely because the card was present.
- Never claim an action succeeded until its banking tool returns success. If a lookup or action fails, explain the limitation and do not retry an operation whose result is `UNKNOWN`.

## Identity verification and audit

1. Locate the customer with a supplied name or email using the appropriate user-information tool.
2. Verify at least two of the four identity fields: date of birth, email, phone number, and address. The customer must provide/confirm the fields; do not treat fields returned from the profile lookup as customer confirmation.
3. Obtain the current timestamp with `get_current_time` and call `log_verification` with the complete profile fields, the user ID, and that timestamp.
4. If two fields are not confirmed, ask for another verification field and do not perform card actions yet. If identity cannot be verified, do not disclose account/card details or make changes.

## Debit-card protection workflow

1. Confirm whether the customer wants temporary protection because the wallet might be found, or confirms a lost/stolen card. Ask the reason if it has not already been stated.
2. Retrieve all bank accounts with `get_all_user_accounts_by_user_id_3847(user_id)`.
3. Select only checking accounts. For each checking account, retrieve cards with `get_debit_cards_by_account_id_7823(account_id)`.
4. Build the actionable set only from cards for which:
   - returned `user_id` equals the verified customer ID;
   - returned `account_id` equals the checking account queried; and
   - status is `ACTIVE` for a requested freeze.
   Mention cards that are not eligible and their status without attempting an unsupported action.
5. Before freezing, state the consequences: new and recurring transactions will decline, already-authorized pending transactions can still process, and the customer may unfreeze later through customer service or the app. For a customer who cannot identify card digits, it is acceptable to identify all active, owned cards on the checking accounts they identified.
6. Unlock `freeze_debit_card_3892` with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` once per eligible card, passing the retrieved `card_id` in the arguments JSON.
7. Record each individual result. Confirm only successful freezes. Tell the customer that ATM use is not affected by the card freeze if they know their PIN; an ATM block must be enabled separately in the mobile app.

### If permanent debit-card closure is requested

Use the closure procedure rather than the freeze tool. Before calling `close_debit_card_4721`, verify owner, `ACTIVE` or `PENDING` status, transaction/refund requirements, and card age. Lost, stolen, and fraud-suspected reasons bypass the minimum-age restriction but not the other stated safeguards. Closure is permanent; advise that recurring payments need updating and refunds credit the linked checking account. Do not use an unfreeze action for a card reported stolen.

## Cross-product credit-card workflow

After or while securing the debit cards, call `get_credit_card_accounts_by_user(user_id)`. If the customer has a credit card, say that it too may be at risk if it was in the wallet and offer a replacement with a new card number. Do not disclose unnecessary account information.

If the customer wants a replacement:

1. Confirm standard verification is complete.
2. Identify the credit-card account and confirm it is eligible before ordering.
3. Obtain and confirm the shipping address, including unit/suite where applicable.
4. Record exactly one reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.
5. Ask the customer to select standard (7–10 business days, no fee) or expedited (2–3 business days). For expedited shipping, disclose the applicable tier fee and obtain acknowledgement/consent if a fee applies. Strongly recommend expedited shipping for fraud-suspected or stolen cards.
6. Only after those confirmations, unlock `order_replacement_credit_card_7291` and call it with the credit-card account identifier, reason, confirmed shipping address, shipping speed, required fee acknowledgement, and relevant notes.
7. On successful submission, explain that the prior card is cancelled, give the delivery window, and advise the customer to watch for notifications. For suspected fraud or theft, remind them to review transactions and dispute unauthorized charges.

If the customer is not ready to replace the credit card, do not order one. Note that the offer was made if the runtime supports interaction documentation; otherwise clearly communicate the option and next step to the customer.

## Customer-facing completion

Give a concise status for every requested debit card and any credit-card decision. For a potentially lost wallet, recommend reviewing recent debit and credit activity promptly. Explain that Regulation E protections apply to unauthorized debit/electronic transactions and that prompt reporting is important. If the customer later confirms a debit card was stolen, do not offer to reactivate it; secure it through the lost/stolen process and, where appropriate, arrange replacement.

## Tool-call conventions

The named debit-card/account tools are specialized internal tools. Unlock each named discoverable agent tool before its first call and pass arguments as a JSON string to `call_discoverable_agent_tool`. Normal profile, verification, timestamp, and credit-card lookup tools are called directly. Tool calls change bank state; this Skill describes the required decision process but does not authorize automatic actions.
