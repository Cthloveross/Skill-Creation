---
name: pin-lock-fraud-assessment
description: Investigate one or more PIN-locked debit cards, protect against suspected fraud, and complete an explicitly requested fraud closure after verification. Use for debit-card PIN locks, decline codes 55 or 75, suspicious failed ATM/POS attempts, or a request to close a card during a PIN-lock investigation.
---

# PIN-Lock Fraud Assessment and Fraud Closure

Apply the PIN Lock Investigation Protocol before any unlock decision. This Skill supports investigation, escalation, and an explicit card-closure request; it does not invent transaction facts or expose internal scoring to the customer.

## Non-negotiable safety rules

- Do **not** unlock a PIN-locked card until its required assessment is complete.
- Never disclose internal risk scores, points, flags, thresholds, decline codes, or internal fraud rationale.
- A name lookup is not verification. Before retrieving sensitive debit-card details or taking a card action, verify two of date of birth, email, telephone number, and address, then call `log_verification` with the current time.
- Investigate every currently locked card across every checking account before permitting any unlock. Do not use credit-card records in place of checking-account, debit-card, or debit-card transaction evidence.
- Do not infer missing locations, timestamps, card history, prior locks, transaction status, or customer confirmation. Treat unavailable material data as unknown and do not unlock based on estimates.
- A customer denial of suspicious activity is not a basis to unlock. Keep the affected card protected and escalate as required.

## Required data collection

After verification:

1. Call `get_all_user_accounts_by_user_id_3847` for the verified user. Identify every checking account.
2. For **each** checking account, use `get_debit_cards_by_account_id_7823` and review all returned cards, including historical cards relevant to a recent stolen replacement.
3. For **each** relevant checking account, use `get_bank_account_transactions_9173`. Review declined PIN-related ATM/POS activity, successful ATM/PIN activity, successful transactions in the previous seven days, overdraft fees, pending activity, and suspicious successful transactions.
4. Collect authoritative card fields available in the lookup result, including PIN-lock reason, PIN-lock count in the prior 90 days, issuance date, daily ATM limit, security alerts, and velocity status. The basic lookup does not guarantee all protocol fields; do not substitute assumptions.

If these banking tools are discoverable in the runtime, unlock each documented read tool before using it and call it with only documented arguments.

## Automatic triggers

For every PIN-locked card, check these before a score-based unlock decision:

1. **Security hold:** if `pin_lock_reason` is `security_hold`, chat cannot unlock the card. Transfer to the security team using `transfer_to_human_agents` with reason `fraud_or_security_concern`. State the affected card identifier/last four digits and the security-hold investigation in the transfer summary, without exposing internal codes to the customer.
2. **Other cards locked on the same account:** assess all of them individually before any unlock decision.
3. **Stolen replacement in prior 90 days:** require enhanced verification before a decision.

A transfer concerning one card does not cancel a separately requested, eligible fraud-protection action on another verified card.

## Risk assessment and customer questions

Normalize the evidence and run the packaged assessor once per PIN-locked card:

```text
python3 scripts/assess_pin_lock.py < assessment-input.json
```

The script reads one JSON object on stdin and writes one JSON object on stdout. Its input schema is documented in the script header. It returns known protocol flags, score, automatic triggers, unknown inputs, customer-question categories, and a conservative disposition. It is a decision aid; source records and policy control.

Before relying on the output, verify that card IDs, transaction IDs, locations, timestamps, amounts, status, and account ownership match the source records. Resolve all obtainable material unknowns.

For scores of 5 or more, ask the required source-specific questions without mentioning scoring:

- For a location mismatch, ask whether the customer was at the recorded location.
- For a decreasing-amount pattern, ask whether the customer remembers attempting the recorded amounts in recorded order.
- For an overnight/high-risk time, ask whether the customer was using the card at the recorded time.
- For high risk, obtain specific location and time confirmation plus a satisfactory explanation before any unlock.

If the customer says they were asleep, denies being at the location, denies the attempts, or gives an inconsistent explanation, retain the relevant flags, do not unlock, and escalate to security. Clearly distinguish a **declined** attempt from a completed withdrawal: do not file a monetary dispute merely because a declined attempt appears as a negative attempted amount in a transaction feed. Check separately for successful unauthorized transactions.

Only clear a flag following the precise confirmation that resolves that flag. Do not remove unrelated concerns after a general statement that activity is recognized.

## Dispositions

Apply the protocol and evidence together:

- Low risk: unlock only after standard verification.
- Medium risk: first ask whether the failed attempts were the customer's.
- High risk: ask specific location/time questions; unlock only after confirmation and a satisfactory explanation.
- Very high risk: do not unlock on the call; require callback or enhanced verification.
- Critical risk, any unresolved three-point flag, denied high-risk attempt, or security hold: do not unlock; escalate/refer as the protocol requires.
- Three or more prior PIN locks in 90 days: do not unlock; follow the PIN-reset process instead.

Use an ordinary banking unlock action only if it is available in the execution runtime and the final disposition expressly permits it. This Skill does not assume an unlock tool name or parameters.

After an eligible unlock: no follow-up offer for zero prior locks; offer PIN-lock notifications for one prior lock; offer a PIN reset for two prior locks; require reset rather than unlock for three or more.

## Explicit suspected-fraud closure request

When a verified customer explicitly asks to close a specific debit card because suspicious attempts or suspected fraud concern them, action the request; do not merely defer it to an earlier transfer.

1. Confirm from the card record that the card belongs to the verified user and is `ACTIVE` or `PENDING`.
2. Use the reviewed transaction history to check for pending/processing transactions and pending refunds. If such items exist, explain the applicable closure limitation and follow the documented process. For a `fraud_suspected` reason, the minimum-card-age restriction is bypassed, but the remaining documented closure requirements still apply.
3. Confirm that the customer's stated concern supports the closure reason. An explicit request following denial of suspicious physical-card ATM/POS attempts is `fraud_suspected`.
4. Call the normal banking action `close_debit_card_4721` directly with:

```json
{"card_id":"<verified-card-id>","reason":"fraud_suspected"}
```

Do this only after verification and ownership/status checks. Do not substitute an unlock, an unfreeze, a generic transfer, or an unsupported closure reason. Wait for and inspect the action result.
5. If successful, tell the customer the card is permanently deactivated and cannot be reactivated, that recurring payment details must be updated, and that refunds to the closed card credit the linked checking account. Recommend changing online-banking credentials when fraud is suspected.
6. If the closure action fails or eligibility cannot be established, do not claim it closed. Explain the blocking condition and transfer/escalate with an accurate summary.

Closing the specifically requested fraud-risk card does not authorize unlocking other PIN-locked cards. Continue to protect and escalate a different card with a security hold.

## Replacement after a fraud closure

A closure does not itself place a replacement order. After successful closure, determine the linked checking-account tier and replacement history, then establish replacement eligibility. Obtain the customer's delivery preference, design preference, and delivery address; disclose the exact applicable delivery and design fees before ordering. Do not promise a free expedited or fastest delivery option unless the tier, availability, and fee have been verified. Use the normal ordering process only after these checks and preferences are complete.

## Failure handling

If verification, ownership, card status, required transaction review, timestamps/locations, or requested closure eligibility cannot be established, do not unlock or claim completion. Escalate when appropriate. If successful unauthorized transactions are found, gather all required dispute information before filing a dispute; do not dispute declined attempts alone. For suspected fraud, use the appropriate fraud dispute category and perform the separately required card action only when the dispute process and evidence support it.
