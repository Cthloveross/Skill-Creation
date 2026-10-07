---
name: stolen-wallet-card-protection
description: Safely handle a verified customer's urgent report that a wallet containing debit and credit cards may be lost or stolen. Use this for locating cards, choosing the supported debit-card protection path, and offering eligible credit-card replacement without claiming an unsupported credit-card freeze.
---

# Lost/Stolen Wallet Card Protection

## Scope and governing distinction

Use this Skill when a customer asks to freeze, close, or otherwise protect several cards after a wallet may be lost or stolen.

- A **debit-card freeze** is temporary and only applies to an `ACTIVE` debit card. It prevents new and recurring card transactions, although already-authorized pending transactions may still process. It can later be undone.
- A debit card confirmed lost or stolen should normally be **closed**, not merely frozen: closing is permanent and a closed card cannot be reactivated. Respect an explicitly requested temporary freeze only after explaining this distinction and confirming that it is the customer's informed preference.
- The supplied policy does **not** establish a credit-card freeze action. Do not invent one, promise one, or use a debit-card tool for a credit card. The supported cross-product action is to ask whether each credit card was in the wallet and offer a replacement with a new number.

Do not disclose internal decline codes or security flags. If an independently observed stolen-card security case requires enhanced verification, follow that specific procedure; if the customer says they never reported a card stolen in that situation, transfer to a human with `fraud_or_security_concern` rather than attempting reactivation.

## Required verification before any card-changing action

1. Locate the customer using a customer-provided identifier (for example name, email, or user ID) with the normal user lookup tool.
2. Obtain and compare **two of these four** identity fields against the retrieved profile: date of birth, email, phone number, address. A name alone does not count as one of the four fields.
3. If the customer cannot provide one requested field, offer another of the remaining fields. Do not use SSN as a substitute for this workflow unless a separate applicable policy explicitly requires it.
4. Once two fields match, obtain the current timestamp and call `log_verification` with the complete retrieved profile values and timestamp. Treat the customer as unverified unless the tool succeeds.
5. If two fields cannot be verified, make no freeze, closure, or replacement order. Explain that account security requires verification and offer an appropriate human transfer if needed.

Never rely on account details from the opening statement as proof of ownership. At every debit-card action, confirm the selected card's `user_id` matches the verified user.

## Clarify intent and give immediate, accurate guidance

Before irreversible action, establish:

1. Whether the wallet/cards are confirmed stolen, lost/misplaced, or merely unaccounted for.
2. Which listed cards were physically in the wallet. Do not assume every account card was present just because the customer has multiple cards.
3. For each debit card, whether the customer wants a temporary freeze after hearing its effects, or confirms permanent close/replacement protection because it was stolen/lost.
4. For each credit card in the wallet, whether the customer wants a replacement card. A replacement cancels the old credit card for new purchases.

For an urgent customer who has not yet decided, explain that a verified active debit card may be temporarily frozen while they decide; for a confirmed theft, recommend permanent debit closure. Avoid saying that an ATM remains protected by the normal freeze: the policy says freezing does not itself affect ATM access for someone with the PIN, and ATM Block is separately enabled by the customer in the mobile app.

## Locate debit cards and apply the supported debit procedure

For each checking account the customer identifies or that is found using the runtime's normal checking-account lookup:

1. Get the checking account ID. Debit cards exist only on checking accounts.
2. Call `get_debit_cards_by_account_id_7823(account_id)`.
3. Select only a card linked to that account and owned by the verified user. Multiple historical cards may be returned; use current status and the customer's identification rather than selecting an old closed card.
4. Apply the decision below separately to every selected debit card. A failure or ineligibility for one card must not cause actions on another card.

### Temporary debit freeze

Use only when all conditions hold: verified owner, selected card belongs to them, and its current status is `ACTIVE`.

- Tell the customer that new transactions and recurring payments will be declined, while already-authorized pending transactions may still process, and it can be unfrozen later.
- Use `freeze_debit_card_3892` with the exact `card_id` through the declared normal banking-tool mechanism.
- Confirm success only from the tool response. Report the affected card in a privacy-safe way (such as last four digits), not its full number.

Do not freeze a `PENDING`, `CLOSED`, or already `FROZEN` card. Explain its current status and, for already frozen, do not duplicate the action.

### Debit closure for a confirmed lost/stolen card

If the customer confirms loss/theft and chooses the recommended permanent protection, use the debit closure procedure rather than representing a freeze as permanent protection.

- Verify that the card is `ACTIVE` or `PENDING`, is owned by the customer, and identify the reason (`lost`, `stolen`, or `fraud_suspected`).
- Lost, stolen, and fraud-suspected cases bypass only the normal 14-day minimum card-age requirement. Do not assume they bypass ownership/status checks or requirements concerning pending transactions and pending refunds.
- Check the required pending-transaction and pending-refund conditions with the normal banking tools before closing. If a pending refund exists, follow the documented written-acknowledgement alternative; otherwise do not close until the documented blocking condition is resolved.
- Call `close_debit_card_4721` with `card_id` and reason only when eligible, and confirm the successful permanent closure. Explain that recurring payment credentials must be updated and the card cannot be reopened.
- For suspected fraud, advise review of recent transactions, disputes for unauthorized activity, and changing the online-banking password.

## Credit-card cross-product protection

After the debit-card handling, use `get_credit_card_accounts_by_user(user_id)` to identify the customer's credit-card accounts. For each active card, say that the customer has that card and ask whether it was also in the lost/stolen wallet. Do not treat the lookup alone as consent to replace it.

If the customer wants a replacement, collect all prerequisites before unlocking or calling the tool:

1. Confirm the credit-card account belongs to the verified user and is eligible under available policy.
2. Record exactly one reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.
3. Confirm the full delivery address, including any apartment/unit/suite.
4. Ask for standard (7–10 business days, free) or expedited (2–3 business days). Strongly recommend expedited shipping for stolen or fraud-suspected cards.
5. Determine fee by card tier and capture customer consent if a fee applies: entry-tier $15, mid-tier $10, premium-and-above $0. Do not infer fee acknowledgement from choosing expedited.

Only after these are present, unlock `order_replacement_credit_card_7291` with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool`. Supply the account/card identifier, reason, confirmed `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and useful notes. Use the exact parameter names/shape the unlocked tool reports if they differ from the policy summary.

After successful submission, state the expected delivery window, that the old card is automatically cancelled for new purchases, and that email notifications will be sent when ordered and shipped. For stolen/fraud cases, remind the customer to review recent transactions and dispute unauthorized charges. Do not state an order was placed unless the call succeeded.

## Failure handling and completion

- If account lookup does not find a claimed account/card, say that it could not be located; do not act on a similarly named account or card.
- If a debit card is ineligible for the requested action, state the applicable status/eligibility blocker and offer the supported alternative only when policy permits.
- If any normal or discoverable tool fails, do not retry a possibly state-changing action blindly. Preserve the result, explain that protection could not be confirmed, and escalate to a human where security risk warrants it.
- Keep a per-card outcome list: located card (masked), requested protection, completed action or blocker, and any replacement-order result. Conclude with only confirmed outcomes and outstanding choices.

## Optional planning helper

`scripts/card_action_plan.py` is a local, non-authoritative preflight helper. It never calls banking tools and does not perform actions. It validates a structured card list and returns per-card eligibility guidance. Runtime account/card data and verified status must be supplied by the executor; its output does not replace the policy checks above.

Example invocation concept:

```json
{"verified": true, "user_id": "<runtime user id>", "cards": [{"kind":"debit","card_id":"<id>","user_id":"<runtime user id>","status":"ACTIVE","requested_action":"freeze"}, {"kind":"credit","account_id":"<id>","user_id":"<runtime user id>","in_wallet":true,"requested_action":"replace"}]}
```

The script emits JSON with `ok`, `actions`, and `errors`. Use it only to organize next steps; inspect actual tool responses and collect all replacement prerequisites before any call.
