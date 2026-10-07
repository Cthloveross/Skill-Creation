---
name: debit-card-decline-investigation
description: Investigate a customer-reported debit-card decline when the decline code may be unknown. Use for a declined debit-card purchase, ATM attempt, or other card transaction that requires safe diagnosis, account/card lookups, and an appropriate resolution or security escalation.
---

# Debit Card Decline Investigation

Use this workflow to diagnose a debit-card decline without guessing the cause. It supports generic declines and known decline codes while preserving banking prerequisites and security restrictions.

## Required controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements as applicable.

For this workflow:

1. Identify the customer from a supplied name or email only to locate a prospective profile. Do not treat profile lookup as identity verification.
2. Verify the caller using at least two independently confirmed profile fields (date of birth, email, phone number, or address), obtain the current timestamp, and record the successful verification with `log_verification` before taking an account/card action or revealing sensitive account details.
3. Ensure the customer is the account/card owner before changing a card setting, clearing a security control, ordering/replacing a card, or filing a dispute.
4. Do not expose internal fraud codes, security flags, detailed restriction reasons, PIN values, full card numbers, or private transaction details beyond what is necessary for the verified customer.
5. Do not repeat an operation whose result is unknown. Explain the uncertainty and escalate if necessary.

## Gather the issue facts

Ask only for facts needed to diagnose the decline:

- Approximate amount, date/time, merchant or ATM context, and whether it was in-person, online, recurring, or ATM.
- Whether chip, tap, signature, or PIN was used, and any message or decline code shown.
- Whether the card was frozen, lost/stolen, replaced, newly received, damaged, or expired.
- Whether the customer recognizes recent card activity when a security issue is plausible.

Do not infer a decline code from a cashier's statement. If no code is available, follow the generic-decline sequence below.

## Discover and use the lookup tools

The banking tools described in the knowledge base are discoverable agent tools. Before using one, call `unlock_discoverable_agent_tool` for that exact name, then call it through `call_discoverable_agent_tool` with JSON-string arguments.

Use these tools as needed:

- `get_all_user_accounts_by_user_id_3847` with `{"user_id":"..."}` to obtain the customer's accounts, account IDs, types, statuses, balances, classes, and opening dates.
- `get_debit_cards_by_account_id_7823` with `{"account_id":"..."}` to retrieve cards for each relevant checking account.
- `get_bank_account_transactions_9173` with `{"account_id":"..."}` to examine pending and posted activity.
- `clear_debit_card_fraud_alert_4892` only after all stated verification prerequisites are met and only where clearing is permitted.
- `transfer_to_human_agents` directly when escalation is required.

The executor must inspect actual returned fields and statuses rather than assuming that every documented optional field is present. If the user has multiple checking accounts/cards, use the transaction context and card last four digits if available to identify the relevant card; otherwise ask the customer to identify the card safely.

## Generic decline diagnostic sequence

For a generic “declined” report with no reliable code, inspect the relevant active/recent card and linked account in this order. Do not skip forward based on speculation.

### 1. Card status

Retrieve the debit cards for the relevant checking account and inspect the card status.

- **FROZEN:** Ask whether the customer wants to unfreeze it. Only unfreeze after verified ownership, confirmation of the selected card, and confirmation that the linked checking account is OPEN. Follow the debit-card unfreezing procedure and use its specified tool.
- **CLOSED:** Explain that the card is no longer active. Check for a current active or pending replacement and offer the appropriate supported next step.
- **PENDING:** The card is not yet activated. Follow the card-activation workflow; confirm physical possession, OPEN linked account, non-expiration, card details, and the issue reason before selecting the correct activation tool.
- **ACTIVE:** Continue to account status.

### 2. Linked checking-account status

Confirm the relevant linked checking account is OPEN.

- If it is not OPEN, say only: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
- Do not disclose details for suspended or restricted statuses.

### 3. Fraud alert

Inspect `fraud_alert_active` and `alert_source` if returned.

- If no active alert is returned, continue.
- If the alert is customer-initiated, ask the customer to verify recent transactions. Clear it only after identity verification, confirmation that activity is legitimate, verified ownership, and use of `clear_debit_card_fraud_alert_4892` with `reason: "customer_verified"`.
- If the alert is bank-initiated, never attempt to clear it. Tell the customer: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Transfer using reason `fraud_or_security_concern` and a concise factual summary.

### 4. Velocity block

Inspect `velocity_blocked` if returned.

- If true, explain that the temporary security block normally lifts after 30 minutes and offer an early lift only after identity verification.
- Clear early only after verified identity, ownership, and a reasonable explanation for the unusual pattern, using `clear_debit_card_fraud_alert_4892` with `reason: "velocity_clear"`.
- If identity cannot be verified or the explanation is suspicious, transfer using `fraud_or_security_concern`.

## Balance and pending-activity diagnosis

If the transaction could be balance-related, including a known Code 51 or insufficient-funds message:

1. Confirm the checking account balance and compare it with the attempted amount without overstating an unavailable balance.
2. Retrieve account transactions and total relevant pending debits; explain that pending transactions can reduce available funds.
3. Ask about recent authorization holds not yet posted, such as gas, hotel, rental-car, or restaurant holds.
4. Inspect `overdraft_pos_enabled` if returned.
5. If the balance is genuinely insufficient, state the available balance as permitted and offer funding the account, transferring funds where separately eligible and authorized, or reducing the transaction amount. Do not initiate a transfer without all transfer prerequisites and explicit confirmation.
6. If the posted balance appears adequate but availability may be reduced by holds/pending items, explain that holds often release in 1–3 business days and that the merchant may be able to release or adjust a hold.

## Known-code routing

When the customer provides a reliable code, apply its dedicated documented procedure after verification and lookup. Important routes include:

- **05:** Use the generic sequence above.
- **14 / 56:** Verify card details and compare all cards on file. For a replaced old card, direct the customer to the newer card; for saved merchant cards, recommend updating saved details. Do not reveal full card numbers.
- **19:** Recommend an immediate retry; if it recurs, advise waiting 10–15 minutes.
- **41 / 43:** Treat as security-sensitive. A stolen-card claim that the customer disputes requires a security-team transfer. Do not reactivate a lost or stolen card.
- **51 / 52:** Follow balance/account-status diagnostics.
- **54:** Check expiration and whether an eligible replacement exists; activate the pending replacement or direct the customer to an active replacement. Order only after all ordering prerequisites.
- **55 / 75:** If PIN is locked, do not unlock directly. Complete the PIN Lock Investigation Protocol, including required risk assessment and escalation triggers, before any unlock decision. If PIN is not locked but attempts are low, warn the customer and offer the separate PIN-reset procedure.
- **57 / 58:** Check restrictions and transaction context. Never remove gambling/adult MCC restrictions by phone. A terminal-specific block should be resolved by trying another terminal or merchant. Do not modify parental controls without guardian authorization.
- **61 / 65:** Calculate remaining limit from the actual card limits and daily usage/count. A temporary limit increase requires OPEN account, account age of at least 60 days, no overdraft fees in the last 30 days, ACTIVE card, one increase maximum per 24 hours, a requested limit no more than 150% of the current limit, and explicit confirmation before the request.
- **62:** Explain geographic/new-card restrictions based on actual card data; do not promise a change unless a supported tool and all prerequisites are available.
- **82:** Ask about physical damage. If damage is not established, handle as a potential security concern, review authorized activity only after verification, and recommend safe card protection/replacement as appropriate.
- **83 / 91 / 92 / 96:** Explain this as a temporary technical/network issue and recommend retry timing and an alternative payment method. If a system issue prevents required completion, transfer with `technical_system_error`.
- **87:** Explain that cash back was not permitted and advise retrying without cash back.

For codes 04, 07, 34, and 59, do not disclose the code or internal fraud reason. Use only the customer-safe response specified by the relevant security procedure, and transfer on continued pressure or when specialist handling is required.

## Actions with special prerequisites

### Card activation

Before activation, require verified identity, physical possession, a PENDING non-expired card, OPEN linked checking account, matching last four/expiration/CVV, and a valid newly chosen PIN. Select the activation tool strictly by `issue_reason`:

- `new_account` or `first_card`: `activate_debit_card_8291`
- `lost`, `stolen`, or `fraud`: `activate_debit_card_8292`
- `expired`, `damaged`, `upgrade`, or `bank_reissue`: `activate_debit_card_8293`

### Freeze/unfreeze

Require verified ownership. Freeze only ACTIVE cards. Unfreeze only FROZEN cards whose linked checking account remains OPEN. Never substitute freezing for the required handling of confirmed lost/stolen or serious fraud scenarios.

### PIN reset/change

Require verified ownership and ACTIVE status. Never repeat a PIN aloud or store it in notes. A new PIN must be exactly four digits, non-sequential, non-repeating, and not based on the customer’s birth year or birth month/day.

### Limit increases

Use `request_temporary_debit_card_limit_increase_8374` only after every eligibility and maximum-limit condition above is established. Confirm the 24-hour duration, requested amount, limit type, and any third-party ATM limitation.

## Escalation and closeout

Transfer only when required or appropriate, with the most specific supported reason:

- `fraud_or_security_concern` for bank-initiated alerts, suspected compromise, unverifiable security-sensitive situations, or required security review.
- `technical_system_error` for a system failure preventing completion.
- `specialized_department_required` for matters outside the available banking scope.
- `other` only when none applies; provide a detailed factual summary.

In the final customer response, summarize only verified findings, the customer-safe reason for the decline, what was done (including any successfully completed action), and the next step. If no conclusive cause is visible, say so plainly, recommend the safest retry/next action consistent with the evidence, and document or escalate recurring failures rather than inventing a resolution.

## Validation checklist

Before completing the interaction, verify that:

- identity verification was logged before any protected banking action;
- the relevant checking account and debit card were actually identified from runtime results;
- generic declines followed card status, account status, fraud alert, then velocity block order;
- pending activity and holds were considered when funds were relevant;
- no prohibited security alert clearing or unauthorized card change occurred;
- every tool action had its stated prerequisites and customer confirmation; and
- the final response contains no internal-only codes, fraud logic, PIN, full card number, or unsupported claim.
