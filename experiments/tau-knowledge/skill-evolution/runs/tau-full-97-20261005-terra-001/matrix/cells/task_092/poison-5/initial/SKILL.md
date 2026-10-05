---
name: debit-card-pin-lock-investigation
description: Investigate PIN-locked debit cards before any unlock. Use for incorrect-PIN or PIN-tries-exceeded declines, particularly where multiple cards may be locked, fraud indicators must be assessed, customer verification or escalation is required, or a PIN reset/replacement/dispute may follow.
---

# Debit Card PIN-Lock Investigation

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow whenever `pin_locked` is true or a PIN-related decline indicates that the card is locked. Do not unlock merely because the customer requests it. Do not disclose internal scores, point values, decline codes, flag names, calculations, or fraud-detection rationale to the customer.

An account may have several cards, and each locked card requires its own assessment. If more than one card on the account is locked, investigate every locked card before unlocking any of them. Starting the conversation with one selected card is allowed, but do not complete an unlock while another locked card remains unassessed.

This Skill does not assume that an undocumented unlock tool exists. Only use an available, documented banking tool with its documented parameters after this workflow authorizes an unlock. If an authorized unlock cannot be executed with available tools, transfer to the security team rather than improvising a tool call.

## Runtime data and prerequisites

1. Identify the customer and verify at least two identity fields against the retrieved profile. Before any banking action, obtain the current timestamp and create the required verification audit record with `log_verification`.
2. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847`. Select checking accounts only and confirm account ownership and status.
3. For every relevant checking account, retrieve all cards with `get_debit_cards_by_account_id_7823`. Identify the target card by account/card details that the customer confirms; never rely only on a nickname.
4. Retrieve transaction history for each relevant checking account with `get_bank_account_transactions_9173`. Retain the declined attempts, successful ATM/PIN use, pending activity, overdraft fees, and any possible unauthorized successful transactions needed for this assessment.
5. Obtain or locate all operational fields required by the PIN-lock protocol, including PIN lock reason, lock history, PIN-attempt event time/location/amount, security flags on other cards, and sufficient timestamps. The standard card and transaction lookup descriptions may not expose every field. Do not invent missing facts or infer a time/location from an ambiguous description. Ask the customer for the relevant details where appropriate; if the required data cannot be obtained, do not unlock and route to security review.

Use discoverable-agent tooling only after unlocking the named tool, then call it with the parameters documented in the governing procedure. Tool recommendations in this Skill never perform a banking action by themselves.

## Immediate escalation checks

Perform these checks before scoring each target card:

- If `pin_lock_reason` is `security_hold`, do not unlock. Offer a transfer to the security team.
- If any other card on the account is PIN-locked, mark the account as multi-card investigation. Assess all locked cards individually before any unlock.
- If any account card was replaced during the preceding 90 days with `issue_reason = stolen`, require enhanced verification before proceeding. If enhanced verification cannot be completed under the available procedure, transfer to security.

For a security/fraud escalation, use `transfer_to_human_agents` with `reason: fraud_or_security_concern` and a factual summary that does not disclose internal scoring to the customer.

## Scoring each card

Create a separate internal evidence record per card. Assess every flag below; a zero is a determined result, not an unknown result. If a flag cannot be determined, record it as unknown and do not authorize an unlock until the gap is resolved or security takes over.

### Location

- **A1 Location mismatch:** same city 0; different city/same state 1; different state 2; different country 3.
- **A2 Location scatter:** one location 0; two locations 1; three or more locations 2.
- **A3 Travel-pattern conflict:** add 1 when all successful transactions in the last seven days were in the home city while declines occurred elsewhere; otherwise 0 when recent activity supports travel.

### Time

- **B1 Time of day:** 06:00–22:00 0; 22:00–00:00 1; 00:00–02:00 2; 02:00–06:00 3.
- **B2 Since last legitimate PIN use:** through seven days 0; 7–30 days 1; over 30 days 2.
- **B3 Attempt velocity:** over five minutes 0; two to five minutes 1; one to two minutes 2; under one minute 3.

### Amount

- **C1 Amount pattern:** same amount retried or increasing amounts 0; decreasing consecutive amounts 2.
- **C2 Round-number testing:** mixed amounts 0; all round hundreds 1.
- **C3 Versus historical successful ATM average:** within twice the average 0; two to five times 1; over five times 2.
- **C4 Versus daily ATM limit:** below 80% 0; 80–100% 1; multiple attempts totaling above the daily limit 2.

### Card history

- **D1 Prior PIN locks in 90 days:** none 0; one 1; two 2; three or more 3. Three or more requires a PIN reset and cannot be unlocked.
- **D2 Card age:** at least one month 0; one to three months 1; under one month 2.
- **D3 Other-card issues:** none 0; another card has a velocity block 1; another card has an active fraud alert 2.

### Account history

- **E1 Account age:** at least six months 0; three to six months 1; under three months 2.
- **E2 Recent overdrafts:** none 0; one 1; two or more 2.
- **E3 Current balance:** at least $100 0; $50 to below $100 1; below $50 2.

Run `scripts/pin_lock_assessment.py` after entering the internally determined scores and gate conditions. The helper calculates totals, detects a three-point single-flag escalation, applies verification answer adjustments, and emits a non-customer-facing disposition. It is invoked as:

```sh
python3 scripts/pin_lock_assessment.py < assessment.json
```

The script reads one JSON object from standard input and emits one JSON object on standard output. Its full input and output schema is documented in the script module docstring. Preserve the input and output with the interaction notes, but do not expose them to the customer.

## Thresholds and customer verification

Apply the resulting score only after all applicable flags are resolved:

- **0–4, low:** unlock only after standard identity verification and all other gates permit it.
- **5–7, medium:** ask, “I see failed PIN attempts on your card. Were those attempts yours?” Unlock only after the response supports proceeding and all other gates permit it.
- **8–10, high:** ask specific location and time questions for the scored indicators. Unlock only when the customer confirms the attempts and provides a satisfactory explanation.
- **11–14, very high:** do not unlock on this contact. Require callback verification or enhanced verification.
- **15 or more, critical:** do not unlock. Check for successful unauthorized transactions and recommend card closure/replacement.

A score of 3 on any one flag requires supervisor review regardless of the total. Treat this as a hold on an unlock pending that review. A customer saying they were asleep or otherwise denying a 2+ point overnight attempt is a critical fraud indicator: do not unlock and escalate.

For a score of 5 or higher, ask only questions warranted by present indicators. Use the real transaction details needed to obtain an answer, but do not say that a score or rule caused the question:

- Location: ask whether the customer was at the location of the failed attempts. If confirmed, remove the location flags and recalculate.
- Decreasing amounts: ask whether the customer remembers attempting those specific amounts. If confirmed, remove C1 and recalculate.
- Time (when B1 is 2 or 3): ask whether the customer was trying to use the card at that time. If confirmed, remove B1 and recalculate. If they say they were asleep or give a comparable denial, escalate as suspected fraud.

Document the answer and rationale for every removed flag. Do not remove unrelated flags merely because the customer made a general statement that the card is theirs.

## Actions after the decision

### Eligible unlock

Before making an unlock action, reconfirm verified ownership, account/card eligibility, card details, and any tool-specific confirmation requirements. Then use only the available documented unlock capability.

After a successful unlock, perform the D1 follow-up:

- Zero prior locks: no additional step.
- One prior lock: offer PIN-lock notifications: “Would you like me to enable PIN lock notifications so you're alerted if this happens again?”
- Two prior locks: offer a PIN reset: “This is your third PIN lock in 90 days. Would you like me to reset your PIN to a new number? Frequent locks sometimes indicate the current PIN is difficult to remember.”
- Three or more prior locks: do not unlock; proceed with PIN reset instead.

For a PIN reset, follow the PIN-reset procedure: verified owner, ACTIVE card, customer confirms last four digits, and a new PIN that is exactly four digits and is not sequential, repetitive, a birth year, or a birth month/day. Unlock and call `reset_debit_card_pin_6284` only if that discoverable tool is available and its documented parameters have been collected. Never repeat, display, or log the PIN in customer-facing text.

### No unlock, escalation, or suspected fraud

Review the suspicious period for successful unauthorized transactions. If the customer identifies unauthorized transactions, follow the debit-card dispute procedure before filing: verify identity and account/card ownership, transaction eligibility and age, amount, open-dispute limit, account status, required transaction/discovery dates, possession of card, PIN-compromise response, merchant-contact response where required, police-report response where applicable, written-statement consent, and provisional-credit eligibility.

Use the fraud-specific dispute category when fraud is suspected (`card_present_fraud` for physical use and `card_not_present_fraud` for online/phone use). Filing metadata does not itself close or freeze a card. Apply the documented required card action separately, only after its own prerequisites are met. If no unauthorized successful transactions are found, explain only that additional security review is needed and offer appropriate options: security-team transfer, PIN reset, or card closure/replacement where justified. Do not reveal internal fraud conclusions or score calculations.

For a requested closure or replacement, separately follow the applicable card-closure and replacement eligibility, fee, balance, confirmation, and delivery rules. Do not claim a replacement has been ordered unless the order action succeeded.

## Completion record

Record: verified identity/audit timestamp; all accounts and cards reviewed; target card; immediate-trigger outcomes; data gaps; per-flag evidence and score; score before and after permitted answer adjustments; questions and answers; disposition; tool actions/results; post-unlock offer or escalation; and any dispute/closure/replacement follow-up. Customer-facing messaging should state the next safe step without exposing this internal record.
