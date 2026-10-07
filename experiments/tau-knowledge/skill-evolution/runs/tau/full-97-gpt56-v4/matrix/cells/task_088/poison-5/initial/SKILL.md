---
name: debit-card-decline-investigation
description: Investigate a customer-reported debit-card purchase decline, especially when no decline code is available. Use this for safe identity verification, account/card/transaction review, balance and pending-debit diagnosis, and policy-compliant handling of card status, fraud alerts, velocity blocks, PIN locks, and limits.
---

# Debit Card Decline Investigation

Use this Skill when a customer says a debit-card purchase or cash withdrawal was declined, including a generic cashier decline with no displayed code. It is a diagnostic workflow: do not guess a decline code, disclose internal security reasons, or take a card/account action before its prerequisites are complete.

## Required controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, treat identity logging, card freezes/unfreezes, security-alert clearing, PIN changes/unlocks, limit changes, transfers, deposits, card ordering, activation, and escalation-related actions as banking actions. Read-only investigation should be limited to the identified customer's relevant accounts and cards; obtain and log verification before any state-changing action.

## Inputs to collect

1. Identify the profile using customer-provided name or email. If matching is ambiguous, request a unique profile identifier; do not select among multiple customers.
2. Ask for the declined transaction context:
   - purchase versus ATM withdrawal;
   - approximate amount, merchant/location, local time, and whether it was domestic/international, online, contactless, chip, signature, or PIN;
   - any displayed decline/error code;
   - whether the customer recognizes the attempt.
3. Before account-specific assistance or an action, verify two of four profile fields: date of birth, email, phone number, and address. Retrieve the enrolled profile values through the normal user-information tool, compare only customer-supplied values, obtain the current timestamp, then call `log_verification` with all required record fields.
4. Never request a full card number, PIN, CVV, password, or SSN in ordinary decline diagnosis. Do not echo sensitive values back.

If the customer cannot verify identity or disputes identity/ownership, do not expose account details or modify anything; transfer/escalate as appropriate.

## Retrieve facts after identifying the customer

Unlock and use the documented internal tools only as needed:

1. `get_all_user_accounts_by_user_id_3847(user_id)` to find checking accounts, their status, class, balance, and opening date.
2. For each plausible linked OPEN checking account, use `get_debit_cards_by_account_id_7823(account_id)` to identify cards, status, issue reason, expiration, limits, and any returned security/restriction/PIN fields.
3. `get_bank_account_transactions_9173(account_id)` to review recent pending and posted activity, including the claimed check deposit and pending debits. Transaction history is reverse chronological; credits have positive amounts and debits have negative amounts.

When tools are discoverable, first call `unlock_discoverable_agent_tool` with the exact documented tool name, then invoke it using `call_discoverable_agent_tool`. Do not manufacture a tool result or assume an unreturned field has a particular value.

Use `scripts/decline_summary.py` to consistently summarize retrieved structured facts if the executor has normalized tool results into JSON. The script does not call tools and makes no banking changes.

## Generic decline diagnostic sequence (no code available)

Perform and record these checks in order for the card plausibly used:

1. **Card status.**
   - `FROZEN`: after verified identity and ownership, ask whether the customer wants it unfrozen. Only unfreeze after confirmation and only if the linked checking account is OPEN.
   - `CLOSED`: explain that it is no longer active; identify an active/pending replacement if one exists. Do not reactivate a closed card.
   - `PENDING`: it is not activated; use the separate activation workflow only after checking physical-card possession, account status, expiration, issue reason, last four, expiration, CVV, a valid new PIN, and confirmation.
   - `ACTIVE`: continue.
2. **Linked account status.** If not OPEN, do not disclose specific suspension/restriction details. Say: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
3. **Fraud alert.** If an active customer-initiated alert is returned, first verify identity and have the customer confirm recent transactions are legitimate; only then clear it with `clear_debit_card_fraud_alert_4892(card_id, reason="customer_verified")`. If the alert is bank-initiated, do not clear it; say there is a security flag requiring additional review and transfer to the security team.
4. **Velocity block.** If returned as active, explain that the temporary block normally lifts after 30 minutes. After identity verification and the customer's request/confirmation, clear it with `clear_debit_card_fraud_alert_4892(card_id, reason="velocity_clear")`.

Before either clearing action, reconfirm card ID, ownership, correct alert type, completed identity verification, and customer confirmation. Document why it was cleared. Never attempt to clear a bank-initiated alert.

## Balance and deposit availability diagnosis

For a purchase decline where funds may be the issue:

1. Compare the requested amount with the account balance and any available-balance information actually returned.
2. Inspect recent transactions for pending debits; calculate their debit total using absolute values. A pending debit reduces available funds.
3. Explain that merchant authorization holds (hotels, car rentals, fuel, restaurants) can reduce available funds even if they have not yet appeared as transactions.
4. Find the customer's claimed check deposit in transaction history. Do not treat a visible deposit as proof that all funds are available. Mobile-check availability depends on account type and amount, and may be subject to extended review; direct the customer to the app's displayed availability date/hold notice.
5. If an account response includes `overdraft_pos_enabled`, explain that a false setting means debit-card POS overdraft coverage is not enabled; offer to explain options rather than claiming that coverage applies.
6. If available funds are genuinely insufficient, state the available balance only after verification and offer safe options: wait for check funds to become available, transfer funds if eligible and requested, or make a smaller purchase. Do not initiate any transfer without all required controls and confirmation.

For a $-denominated transaction, use the helper output only as a transaction-review aid. It cannot determine authorization holds or definitive available balance from posted transactions alone.

## Other decline-code branches

When a reliable code is supplied or retrieved, follow its specific documented workflow rather than the generic branch:

- **51 / insufficient funds:** perform the balance, pending-debit, authorization-hold, and POS-overdraft review above.
- **05 / generic decline:** follow the full ordered generic sequence above.
- **55 or 75 / PIN locked:** do not unlock merely because the user asks. Follow the separate PIN Lock Investigation Protocol and its fraud-risk assessment first.
- **57 / transaction not permitted:** inspect returned restriction fields. Do not remove gambling/adult MCC blocks by phone; parental controls require guardian authorization.
- **58 / terminal restricted:** advise another register or merchant; if multiple unrelated terminals fail, use Code 05 diagnostics.
- **61 / limit exceeded:** use card limit and usage fields to calculate remaining limit. A temporary increase requires OPEN account, age at least 60 days, no overdraft fee in the last 30 days, ACTIVE card, no prior temporary increase within 24 hours, an amount no greater than 150% of the current limit, and customer confirmation. Third-party ATM limits cannot be overridden.
- **62 / geographic restriction:** confirm the situation and returned regions; a new-card setup restriction can clear within 24 hours of activation.
- **65 / activity count exceeded:** explain the returned daily count and limit; it normally resets at midnight.
- **19:** request an immediate retry; if it repeats, wait 10–15 minutes.
- **91 or 96:** advise retrying in a few minutes, then 10–15 minutes if persistent.
- **92:** explain a temporary routing issue and suggest retrying or another merchant.
- **04, 07, 34, or 59:** do not disclose the code or fraud rationale. Provide only the prescribed neutral branch/in-person response and escalate if pressed.
- **41 / lost** and **43 / stolen:** follow the lost/stolen-card protocol. A stolen card requires enhanced verification; never reactivate a lost or stolen card.

## Customer-facing closeout

Give a concise, evidence-based explanation. Distinguish facts observed (for example, a pending debit or a pending check deposit) from possibilities (for example, an authorization hold). State the exact next step and timing. If no cause can be established after the relevant card, account, security, balance, and transaction checks, ask the customer to retain the decline details and escalate with screenshots, timestamp, merchant/location, amount, device/app/browser details, and the workflow that produced the decline.

## Helper execution

Run from the package directory:

```sh
python3 scripts/decline_summary.py <<'JSON'
{"purchase_amount":449.99,"account_balance":500.00,"transactions":[{"amount":-25.0,"status":"pending","type":"debit_card_purchase"}]}
JSON
```

Input is one JSON object with optional `purchase_amount` (number), `account_balance` (number), `available_balance` (number), `overdraft_pos_enabled` (boolean), and `transactions` (array of objects with numeric `amount`, string `status`, and optional `type`, `description`, `date`). The script writes one JSON object containing pending-debit totals, check-deposit candidates, comparison flags, cautions, and validation errors. A nonempty `errors` list means do not rely on calculations until the input is corrected.
