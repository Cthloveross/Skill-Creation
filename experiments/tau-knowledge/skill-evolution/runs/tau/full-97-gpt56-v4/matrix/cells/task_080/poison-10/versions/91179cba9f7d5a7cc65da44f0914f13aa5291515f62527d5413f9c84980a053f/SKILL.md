---
name: secure-stolen-wallet-cards
description: Secure a verified customer's relationship after a lost or stolen wallet: temporarily freeze eligible debit cards, offer and order replacement credit cards, and route unsupported fraud disputes or unresolved card identification safely.
---

# Secure Lost or Stolen Wallet Cards

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and non-negotiable safeguards

Use only supplied banking tools and documented discoverable tools. Never invent a card ID, checking-account ID, lookup tool, or tool parameter. Do not state that a card was frozen, closed, replaced, or disputed until its corresponding action reports success. Do not disclose full card numbers or internal decline codes.

A theft report is a reason to recommend closure of debit cards, but a verified owner may choose a temporary freeze first. There is no documented agent action in this workflow to temporarily freeze a credit card; offer replacement protection instead.

## 1. Establish identity and authority

1. Locate the customer using an identifier they supplied, such as full name, user ID, or email.
2. Have the customer provide and match **two of these four** fields against the record: date of birth, email, phone number, and address. A name is an identifier, not one of the two fields.
3. After two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` using all required values from the customer record. Do not perform a card action before this succeeds.
4. For every debit card selected, verify the returned `user_id` is the verified customer. For credit-card replacement, use an active account belonging to that customer.

If identity, ownership, or a required confirmation cannot be established, do not act; request the specific missing detail. Do not treat values retrieved from the profile as customer-provided confirmation.

## 2. Locate and assess debit cards

Debit freezes require the linked checking-account ID, an owner match, and card status `ACTIVE`.

1. Use an actually available normal checking-account lookup, if one is supplied, to map the customer’s account names to IDs. Otherwise ask for the checking-account ID(s); card last four digits are helpful but do not substitute for an ID.
2. Unlock `get_debit_cards_by_account_id_7823` when necessary, then call it once per confirmed checking-account ID. Its input is `account_id`.
3. From each result, retain only cards whose `user_id` matches. Record each card ID, account ID, status, and whether it is the intended current card. Historical, `PENDING`, `FROZEN`, and `CLOSED` cards are not eligible for a new freeze.
4. If an account/card cannot be identified with the supported tools, clearly say that no debit freeze was attempted; do not guess. Ask for the confirmed checking-account identifier or explain how the customer can obtain it through a supported channel. Complete independently supported credit-card protection when the customer wants it.

## 3. Perform a requested temporary debit freeze

Before the first freeze, confirm the theft/loss reason and explain all of the following:

- New transactions and recurring payments/subscriptions will be declined while frozen.
- Pending transactions already authorized may still process.
- The customer can unfreeze through customer service or the mobile app.
- Freezing does not prevent ATM access with the PIN; the customer must enable ATM Block separately in the mobile app.

Unlock `freeze_debit_card_3892` if it is discoverable, then call it separately for every identified `ACTIVE` debit card with its exact `card_id`. Confirm each tool result individually. Do not call it for any other status.

Afterward, explain that theft normally warrants permanent closure and request explicit authorization before attempting closure. A closure additionally requires owner verification, `ACTIVE` or `PENDING` status, no pending/processing transactions, no pending refunds (unless the documented written acknowledgement is obtained), and at least 14 days since issue. The age requirement is bypassed for lost, stolen, or suspected-fraud reasons. Use `close_debit_card_4721` only after all applicable conditions are checked, with exactly one documented reason. A frozen card is not eligible under the documented close status rule. Closure is permanent; recurring payments need new details and refunds credit the linked account.

## 4. Offer and order credit-card replacement protection

For a lost/stolen debit-card report, retrieve credit-card accounts with `get_credit_card_accounts_by_user(user_id)` after verification. For each active credit card, ask whether it was also in the wallet and offer a replacement with a new card number. Do not replace a card merely because it exists; obtain the customer’s choice.

Before ordering a requested replacement, confirm:

- the active credit-card account identifier and owner;
- one reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`;
- complete shipping address, including unit/suite if applicable;
- standard delivery (7–10 business days, free) or expedited delivery (2–3 business days); and
- explicit expedited-fee acknowledgement whenever a fee applies.

Expedited fees: $15 for entry tier (including EcoCard), $10 for mid tier, and complimentary for premium tier and above (including Gold Rewards). Strongly recommend expedited shipping for stolen/fraud-suspected cards but never choose it without the customer's selection and required fee consent.

Only after confirming eligibility, unlock `order_replacement_credit_card_7291`. **Read the returned tool schema and call exactly that schema; do not assume prose-field names are supported.** In runtimes exposing `credit_card_account_id`, `user_id`, `shipping_address`, `reason`, and optional boolean `expedited_shipping`, supply those exact fields. The customer’s fee acknowledgement is a prerequisite to the call when required, even if the runtime does not expose a separate acknowledgement parameter. Process each requested account independently and stop for a tool error or ineligibility response.

After success, state that the old card was cancelled for new purchases, give the selected delivery window, advise watching for order and shipping notifications, and remind the customer to review recent activity and report unauthorized charges.

## 5. Fraud reports and final summary

Do not invent a transaction-dispute action or claim that a dispute has been opened or reimbursement is guaranteed when no supported dispute workflow is available. For unauthorized debit EFTs, mention that Regulation E protections may apply, without making eligibility or reimbursement guarantees. A customer who denies having reported a card stolen despite a stolen-card security indication must not be offered reactivation; use `transfer_to_human_agents` with `fraud_or_security_concern`, as required by the stolen-card procedure.

At completion, separately summarize every debit card frozen and any not frozen (with the specific safe reason), whether closure remains an option awaiting authorization/eligibility, every credit-card replacement ordered or declined, shipping speed and acknowledged fees, and all remaining customer actions.

## 6. Unfreezing and documented replacement fields

Only handle an unfreeze when the customer specifically requests it. Reverify identity and ownership, confirm the debit card is `FROZEN` and its linked checking account is `OPEN`, then unlock and call `unfreeze_debit_card_3893` with the exact `card_id`. Confirm it is active and ready to use immediately only after success.

If a credit-card replacement is declined, record that the offer was made only when a supported record-note capability exists; otherwise do not claim the note was saved. The replacement knowledge base describes the order information as account/card identifier, reason, `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and notes. Treat that as the required information-collection checklist. The discoverable tool's returned schema controls the actual call parameter names and can differ; never add unsupported fields to the call.
