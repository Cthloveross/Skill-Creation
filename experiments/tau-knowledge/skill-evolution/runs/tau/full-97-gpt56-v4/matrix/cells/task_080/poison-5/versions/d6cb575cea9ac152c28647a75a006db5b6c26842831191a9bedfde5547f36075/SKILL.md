---
name: stolen-wallet-card-protection
description: Safely handle a verified customer's report that a wallet containing debit and credit cards was lost or stolen. Use this for debit-card freeze or closure requests, required cross-product credit-card protection, identity verification, and escalation when debit cards cannot be safely identified.
---

# Stolen Wallet Card Protection

Use this workflow when a customer reports a lost or stolen wallet/card, including when they request a temporary debit-card freeze. Treat the report as a security event. Do not guess card or account identifiers, and do not claim that a credit card was frozen unless a supported procedure/tool explicitly completed that action.

## 1. Establish and record verification

1. Locate the customer using a customer-supplied name or email with the corresponding user lookup tool.
2. Compare customer-provided identity responses with the returned profile. Successful verification requires confirmation of **two of the four** identity fields: date of birth, email, phone number, and address. A name is useful to locate the record but is not one of those two verification factors.
3. If only one factor has been confirmed, request one additional factor before any card-changing action. Do not count information merely displayed in the profile as customer confirmation.
4. Once two factors match, call `get_current_time`, then call `log_verification` with every required profile field, the matched `user_id`, and that timestamp. Use the profile values exactly as returned.
5. If identity data does not match, do not perform card actions. Explain that verification could not be completed and transfer only if appropriate.

If the conversation history already contains two valid customer confirmations and a successful verification record, do not unnecessarily repeat verification or log duplicate records.

## 2. Explain the security choice and capture the request

Confirm the reported reason (lost or stolen) and the requested action. Explain briefly:

- A debit-card **freeze** is temporary and can later be removed.
- New and recurring card transactions will be declined while frozen; already-authorized pending transactions may still settle.
- A reported lost or stolen debit card is normally safer to **close permanently**, because a freeze can be reversed. Closing cannot be undone and requires a new card.

Honor a clearly expressed, verified request to freeze only after all freeze prerequisites below are established. If the customer changes their request to closure, use the debit-card closure procedure instead; do not represent a freeze as closure.

For a wallet theft, the reason is already known. Avoid delaying urgent protection by asking redundant open-ended questions, but obtain any missing authorization or choice (for example, whether to close rather than temporarily freeze).

## 3. Identify and freeze each requested debit card

A debit card may be frozen only when all of the following are demonstrated:

- the customer is verified;
- the returned card `user_id` equals the verified customer `user_id`;
- the card is associated with the intended checking account; and
- its current status is `ACTIVE`.

The supported debit-card lookup, `get_debit_cards_by_account_id_7823`, requires a **checking account ID**. For every supplied checking account ID:

1. Call `get_debit_cards_by_account_id_7823(account_id)`.
2. Review all returned records, since old CLOSED or other historical cards may be included.
3. Select only a card belonging to the verified user and matching the requested account; use its `card_id` only if it is `ACTIVE`.
4. Unlock `freeze_debit_card_3892`, if not already unlocked, and call it with the selected `card_id`.
5. Record the tool result per card. Confirm only cards whose tool call reports success.

Do not freeze a `PENDING`, `CLOSED`, or already `FROZEN` card. For an already frozen card, explain that no additional freeze is needed. If no card is returned for an account, or ownership/status cannot be validated, do not call the freeze tool for it.

### Missing account identifiers

Do not substitute a user ID, account nickname, card type, or guessed value for the required checking `account_id`. First use a declared, authorized checking-account lookup if one is actually available in the runtime and can return accounts owned by the verified user. If no such tool is available and the customer cannot provide an account ID or card identifier, explain that the declared debit-card lookup cannot safely identify the card from the available information.

Because this is an active lost/stolen-card security event with protection blocked by unavailable identification, transfer to a human agent using `fraud_or_security_concern`. Include which cards/accounts were requested, that verification status, that no account IDs were available, and that no debit-card change was attempted. Never fabricate a successful freeze.

## 4. Required credit-card cross-product protection

For every lost/stolen debit-card report, check for Rho-Bank credit cards with `get_credit_card_accounts_by_user(user_id)` after the customer is identified and verified. This check is required even if the customer mentioned credit cards.

If credit-card accounts are returned:

1. Tell the customer that credit cards were found and ask whether each was also in the lost/stolen wallet.
2. Proactively offer a replacement card with a new number as a security precaution. Explain that wallet theft can compromise multiple cards.
3. Do **not** say that the credit cards were frozen: this workflow provides a replacement-card process, not a credit-card freeze tool.
4. If the customer wants a replacement, follow the replacement procedure before invoking its tool:
   - confirm the shipping address, including unit/suite details;
   - record exactly one reason, such as `lost` or `stolen`;
   - obtain standard versus expedited shipping preference;
   - disclose the delivery window (standard: 7–10 business days; expedited: 2–3 business days);
   - disclose the expedited fee by card tier and obtain explicit acknowledgement whenever a fee applies. Gold/Platinum/Diamond Elite is complimentary; Bronze/EcoCard/Business Bronze is $15; Silver/Business Silver/Green Rewards/Silver Zoom is $10;
   - strongly recommend expedited shipping for lost/stolen cards and remind the customer to review and dispute unauthorized transactions.
5. Only once all required details and eligibility are available, unlock `order_replacement_credit_card_7291` and call it through `call_discoverable_agent_tool`. Supply the account or card identifier returned by the account lookup, the approved reason, confirmed address, speed, required fee acknowledgement, and relevant notes.
6. Confirm successful orders individually. Tell the customer the old card is automatically cancelled, give the chosen delivery window, and advise them to watch for order and shipment email notifications.

If the customer declines a replacement, state that the protective replacement was offered. Do not place an order or invent consent. If no credit accounts exist, say that no Rho-Bank credit card was found.

## 5. Closing alternative for debit cards

If the verified customer elects permanent closure instead of temporary freezing, do not use the freeze workflow. Follow the debit closure prerequisites: card ownership, ACTIVE/PENDING status, no pending/processing transactions, no pending refunds (unless the documented written acknowledgement condition is met), and normally at least 14 days of card age. Lost, stolen, and suspected-fraud reasons bypass only the minimum-age requirement; they do not waive the other listed checks. Use `close_debit_card_4721` only after those checks and with its documented `card_id` and reason.

For lost/stolen closure, explain that pending transactions may still process, the card cannot be reopened, recurring payment details will need updating, and a replacement can be ordered through the applicable process.

## 6. Final response checklist

Give a concise, card-by-card outcome:

- each debit card actually frozen, already frozen, not eligible, or not located;
- any credit-card replacement offered, declined, or successfully ordered;
- any unresolved urgent protection and transfer status;
- relevant effects of a debit freeze and the option to close a stolen card permanently.

Never expose full card numbers, profile data beyond what is necessary, internal identifiers, or unverified claims. Tool calls are the source of truth: a recommendation, an unlock, or an attempted call is not a completed freeze, closure, or replacement.
