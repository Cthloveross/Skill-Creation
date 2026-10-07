---
name: lost-wallet-card-protection
version: 1.0.0
description: Securely handle a verified customer's misplaced, lost, or stolen wallet containing debit cards, including temporary debit-card freezes and an optional replacement credit-card order.
---

# Lost Wallet Card Protection

Use this Skill when a customer reports that a wallet or debit card is missing and wants protection for one or more debit cards. It also covers the required cross-product check and, if requested, replacement of an exposed Rho-Bank credit card.

## Safety and prerequisites

Before **every** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements applicable to that action.

For this workflow specifically:

1. Identify the customer using a supplied identity value and retrieve the matching customer record.
2. Verify at least two of the four identity fields (date of birth, email, phone number, and address) against the customer record. Do not treat name alone as one of these fields.
3. Obtain the current time and call `log_verification` with the complete retrieved customer record and verification timestamp after successful verification.
4. Confirm the customer owns each affected product by comparing its `user_id` with the verified user.
5. Treat “misplaced and still looking” as a temporary-freeze request. If the customer confirms a card is lost or stolen, explain that closing it is safer; follow the applicable close procedure if they choose permanent deactivation.
6. Do not expose full card numbers or use a card selected only by account nickname. Retrieve and confirm the actual account and card records first.

If identity, ownership, status, eligibility, address, shipping choice, fee consent, or required confirmation cannot be established, do not perform the dependent action. Explain what is needed or transfer to an appropriate human agent for a technical/system problem.

## Debit-card freeze procedure

Use this sequence for all checking accounts/cards the verified customer explicitly asks to freeze.

1. Confirm that the customer wants a **temporary freeze** and ask/record the reason. Explain before action that:
   - new transactions will be declined while frozen;
   - recurring payments and subscriptions will also be declined;
   - already-authorized pending transactions may still process; and
   - the customer can unfreeze later through customer service or the mobile app.
   Freezing does not itself block ATM use with the PIN; the customer must enable ATM Block in the mobile app to block ATM access.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` using the verified `user_id`. Select only OPEN checking accounts that correspond to the customer’s requested accounts. Do not assume every account is checking or open.
3. For each selected checking account, unlock and call `get_debit_cards_by_account_id_7823` with its `account_id`.
4. For each card to be frozen, verify that its `user_id` belongs to the verified customer and its status is exactly `ACTIVE`. A card that is PENDING, CLOSED, or already FROZEN is not eligible for the freeze call; report its actual status instead.
5. Unlock `freeze_debit_card_3892`, then call it once for each eligible requested `card_id`. Use only the retrieved card ID.
6. Confirm each successful result individually. State that the freeze is temporary; a reminder may be sent if a frozen card is not unfrozen within 90 days.

Never retry a state-changing action solely because its outcome is unclear. If the tool returns an unknown, partial, or error result, inspect available records or transfer for technical assistance rather than assuming success.

## Cross-product credit-card check

For every lost or stolen debit-card/wallet report, call `get_credit_card_accounts_by_user` for the verified user. If any relevant credit card exists, explain that wallet loss can expose multiple cards, ask whether it was also in the wallet, and offer a replacement with a new card number. Record or communicate a decline if the customer declines. Do not order a replacement until the customer expressly requests it.

## Credit-card replacement procedure

Use this only after the verified customer confirms that a credit card was exposed and requests replacement.

1. Retrieve the customer’s credit-card accounts using `get_credit_card_accounts_by_user`; choose the customer-confirmed, eligible credit-card account. Confirm ownership, account status, and replacement eligibility before unlocking the ordering tool.
2. Confirm one supported reason exactly: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`. For a card exposed in a lost wallet, obtain the customer’s choice of `lost` or `stolen` rather than silently inventing it. If the customer only reports possible exposure, use `fraud_suspected` only when that reflects the customer’s reported concern and is accepted by the applicable process.
3. Confirm the complete shipping address, including any unit/suite information, and ask for `standard` or `expedited` shipping.
   - Standard: 7–10 business days, no fee.
   - Expedited: 2–3 business days. Entry-tier fee: $15; mid-tier fee: $10; premium-tier and above: complimentary.
   - Obtain explicit expedited-fee acknowledgement whenever the selected tier has a fee. Strongly recommend expedited shipping for fraud-suspected or stolen cards, but do not substitute it for the customer’s selection.
4. Unlock `order_replacement_credit_card_7291` and call it with the retrieved credit-card account identifier, supported reason, confirmed shipping address, shipping speed, expedited-fee acknowledgement when applicable, and relevant notes.
5. Confirm the order result and delivery window. Explain that the old card is automatically cancelled for new purchases, that email notifications will be sent when ordered and shipped, and that unauthorized transactions should be reviewed/disputed for fraud-suspected or stolen cases.

## Tool-call conventions

Named specialized tools must be unlocked with `unlock_discoverable_agent_tool` before their first call and invoked using `call_discoverable_agent_tool`. Pass JSON containing only values obtained from the customer or retrieved records. Ordinary supplied tools such as identity lookup, `get_current_time`, `log_verification`, and `get_credit_card_accounts_by_user` are called directly.

Use `scripts/check_readiness.py` before a state-changing call when structured session data is available. It checks the minimum known prerequisites; it does not replace record retrieval, customer verification, eligibility rules, confirmations, or tool-result review.

## Completion response

Summarize only completed actions and their results: which debit cards were frozen (or why any were not), whether a credit-card replacement was offered/ordered/declined, applicable delivery timing, and the customer’s available next step. Do not claim success until the corresponding banking tool has returned success.

## Runnable readiness-check example

```sh
python3 scripts/check_readiness.py <<'JSON'
{"operation":"freeze","identity_verified":true,"owner_verified":true,"card_status":"ACTIVE","customer_confirmed":true}
JSON
```

The script reads one JSON object from standard input and writes a JSON object with `ready` (boolean) and `missing` (array of unmet prerequisite labels). A `ready: true` result permits proceeding only after the live banking records and required disclosures have also been handled.
