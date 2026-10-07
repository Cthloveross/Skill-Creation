---
name: secure-stolen-wallet-cards
description: Safely handle a verified customer's report that a wallet containing debit and credit cards was lost or stolen. Use this for debit-card freeze or closure requests and the required cross-product credit-card protection offer; do not use it to claim that a physical credit card has been locked when no such supported action exists.
---

# Secure Lost or Stolen Wallet Cards

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety boundary

This workflow addresses a report that a debit card or wallet is lost/stolen, including a customer's request to freeze debit cards and protect any credit cards. A debit-card freeze is temporary; a debit-card closure is permanent and cannot be reversed. A reported stolen card should be recommended for closure rather than temporary freezing, but a verified owner may choose a freeze when the debit-card freeze prerequisites are met.

The available knowledge documents a physical debit-card freeze action, but **does not document a temporary lock/freeze action for physical credit cards**. Never state or imply that a debit-card freeze protects a credit card, and never substitute virtual-card management for a physical-card lock. For credit cards in the stolen wallet, perform the required credit-card check and offer a replacement/security review instead.

Do not invent tool parameters, card identifiers, account selections, transaction outcomes, account eligibility, or successful status changes. The executor, not this Skill, performs banking actions through its normal banking tools.

## Inputs to collect or use at runtime

Use the current conversation and runtime lookups; do not embed customer-specific values in this package.

- Customer identity claim (name or registered email) and enough verification responses.
- The customer's requested debit accounts/cards and whether they explicitly want temporary freeze or permanent closure.
- An explicit action confirmation after the customer has been told the applicable effects.
- For each optional credit-card replacement: the specific credit account, exact reason, confirmed complete shipping address, shipping speed, consent to an expedited fee when applicable, and customer approval to place the order.

A name is an account-locating claim, not sufficient verification by itself. Verify two of the four profile fields—date of birth, email, phone number, and address—against the retrieved profile. After a successful two-field match, obtain the current timestamp and call `log_verification` with all fields required by that tool. If fewer than two fields match, do not perform, prepare, or claim any banking action.

## End-to-end workflow

### 1. Verify before any action

1. Locate the profile with `get_user_information_by_name` or `get_user_information_by_email` using the customer's supplied claim.
2. Ask for and compare at least two of date of birth, email, phone number, and address. Do not reveal profile values merely to solicit confirmation.
3. When two fields match, call `get_current_time`, then call `log_verification` with the matched user's full retrieved profile fields and that timestamp.
4. If the requester cannot be verified or is not the owner, stop. Do not disclose card details or take action.

### 2. Identify and validate the requested debit cards

1. Call `get_all_user_accounts_by_user_id_3847(user_id)` and limit the debit-card search to the customer-selected checking accounts. If an account nickname or description is ambiguous, ask the customer to identify the account or the card's last four digits; do not guess.
2. For every selected checking account, call `get_debit_cards_by_account_id_7823(account_id)`.
3. Select only the card(s) the customer identifies. For each, ensure that its returned `user_id` equals the verified user, its `account_id` is the selected checking account, and its current status is `ACTIVE` before a freeze.
4. Explain before freezing that new and recurring transactions will be declined, already-authorized pending transactions may still process, and the customer can unfreeze later through customer service or the mobile app. Explain that freezing alone does not block ATM access for someone with the PIN; ATM Block must be enabled separately in the mobile app.
5. Capture an explicit confirmation to freeze the identified cards. A customer who reports theft should also be told that permanent closure is generally the safer option. If they choose closure instead, follow the closure branch below rather than treating closure as a freeze.
6. For each independently eligible, confirmed card, use `freeze_debit_card_3892(card_id)`. Do not freeze cards in PENDING, FROZEN, or CLOSED status.
7. Read the operation result and, when available, re-query the debit card to confirm it is FROZEN. Report each success or failure separately. Do not say all cards were secured if any lookup, ownership check, status check, confirmation, or tool action failed.

Use `scripts/validate_card_security_plan.py` before dispatching a batch of proposed actions when structured lookup results are available. It only validates a plan; it never calls banking tools or changes account state.

### 3. Closure branch when requested

A lost/stolen report supports recommending immediate permanent debit-card closure. Before calling `close_debit_card_4721(card_id, reason)`, verify ownership, that the card is ACTIVE or PENDING, the customer-selected reason, no pending/processing transactions, and no pending refunds (unless the customer provides the required written acknowledgement that refunds will credit the linked checking account). Lost, stolen, and fraud-suspected reasons bypass only the 14-day minimum card-age condition; do not assume they bypass the other closure checks.

Tell the customer that closure is irreversible, recurring payments need updated payment details, and pending transactions can still process. If required transaction/refund information or acknowledgement cannot be obtained, do not close the card. A closure request is not authorization to close unrelated cards.

### 4. Required credit-card security check

For every lost/stolen debit-card or wallet report, call `get_credit_card_accounts_by_user(user_id)` after verification. If credit cards exist:

1. Tell the customer that a stolen wallet can expose multiple cards, identify only the relevant cards after verification, and ask whether each was in the wallet.
2. Explain that no supported physical credit-card temporary-lock action is documented in this workflow. Offer replacement with a new card number as the available security precaution; do not place an order merely because the customer asked to freeze it.
3. If the customer reports suspicious transactions, advise review of recent transactions and use normal dispute channels for unauthorized transactions. Do not label a transaction fraudulent without the customer's report or a completed investigation.
4. If the customer declines replacement, document that the offer was made using the normal customer-record process if available. Do not take a replacement action.

### 5. Optional credit-card replacement

Proceed only when the customer affirmatively requests replacement and all prerequisites below are recorded for that specific credit account:

- Verified identity and authority; account/card was looked up; eligibility has been confirmed under the applicable knowledge base.
- The exact replacement reason is one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.
- A complete shipping address has been confirmed, including any unit or suite.
- Shipping speed is `standard` (7–10 business days, no fee) or `expedited` (2–3 business days).
- For expedited shipping, disclose and obtain acknowledgement of the applicable fee: $15 for entry tier (including EcoCard), $10 for mid tier, and $0 for premium tier and above (including Gold Rewards). For `stolen` or `fraud_suspected`, strongly recommend expedited shipping and remind the customer to review transactions.

Once eligible and confirmed, call `unlock_discoverable_agent_tool` for `order_replacement_credit_card_7291`, then call `call_discoverable_agent_tool` with that exact tool name and a JSON object containing the looked-up credit-card account identifier, `reason`, `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and relevant `notes`.

After a successful order, state the selected delivery range and that the old card is automatically cancelled for new purchases. Advise the customer to watch for order and shipment email notifications. For stolen or suspected-fraud reasons, remind them to review and dispute unauthorized transactions. Document the interaction and order details through the normal record process.

If eligibility, fee acknowledgement, address confirmation, or affirmative replacement consent is absent, do not unlock or call the ordering tool. Explain what is still needed. If no supported physical-credit-card action can meet an urgent freeze request and the customer demands further action, use the normal escalation path rather than claiming a lock occurred.

## Plan-validation helper

`scripts/validate_card_security_plan.py` reads one JSON object from stdin and writes one JSON object to stdout. It uses only supplied structured data and performs no I/O other than stdin/stdout.

Input schema:

```json
{
  "verified": true,
  "user_id": "verified-user-id",
  "freeze_confirmed": true,
  "selected_debit_card_ids": ["card-id"],
  "debit_cards": [
    {"card_id": "card-id", "account_id": "checking-account-id", "user_id": "verified-user-id", "status": "ACTIVE"}
  ],
  "credit_replacements": [
    {
      "account_id": "credit-account-id",
      "user_id": "verified-user-id",
      "card_type": "card product name",
      "reason": "stolen",
      "shipping_speed": "standard",
      "shipping_address": "confirmed complete address",
      "fee_acknowledged": false,
      "customer_confirmed": true,
      "eligibility_confirmed": true
    }
  ]
}
```

`credit_replacements` is optional. The output contains `freeze_actions` only for selected, verified-owner ACTIVE cards when verification and freeze confirmation are true. It contains `replacement_actions` only for replacements that have every required supplied prerequisite; these are recommendations for the executor, not executed orders. All withheld operations appear in `blockers` with a stable code and explanation. Review every blocker and tool result before communicating completion.

Example executor invocation: call `run_skill_script` with `relative_path` set to `scripts/validate_card_security_plan.py` and `input_json` set to the runtime lookup records transformed into the schema above. Treat `freeze_actions` as candidates for `freeze_debit_card_3892` and `replacement_actions` as candidates for the documented unlock/call sequence only after confirming the live conversation facts remain current.

## Completion checklist

- Verification was completed and logged before every banking action.
- Each affected debit card was individually matched to its owner, selected account, and current status.
- The customer received the freeze effects and ATM limitation before a temporary freeze, and explicitly confirmed the action.
- Every debit action has an individual tool outcome; failures and ineligible cards remain clearly unresolved.
- Credit cards were checked and replacement protection was offered for a lost/stolen report.
- No physical credit-card freeze was claimed unless a separately documented and supported physical-card action was actually completed.
- Every replacement order has explicit consent, eligibility, address, reason, shipping choice, and applicable fee acknowledgement.
