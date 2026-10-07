---
name: pin-lock-fraud-investigation
description: Investigate one or more PIN-locked debit cards before any unlock or PIN-reset action. Use when a customer reports PIN-related declines or locked debit cards and the agent must retrieve account/card activity, assess fraud risk, collect required verification, decide escalation, and communicate safely.
---

# PIN-Lock Fraud Investigation

Use this workflow for every debit card where `pin_locked` is true. Never unlock merely because a customer requests it or says they did not make the attempts. Do not reveal internal scores, point values, fraud calculations, security triggers, or decline-code reasoning to the customer.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and verification prerequisites

1. Establish the customer profile with a supplied identifier, such as their full name or email. Confirm the record belongs to the customer.
2. Obtain confirmation of at least two of these four identity fields: date of birth, email, phone number, and address. A profile lookup is not itself customer confirmation.
3. Call `get_current_time` and then `log_verification` only after the two-field verification succeeds. Include the full returned profile fields and verification timestamp in the audit record.
4. Before a card action, verify the customer owns the linked account/card, identify the precise card by returned `card_id` and last four digits, and confirm its current status and eligibility. Do not ask the customer to state a full card number or PIN.
5. Never place a PIN, SSN, password, or full card number in a script input, customer-facing message, or unnecessary tool argument.

If identity cannot be verified, do not unlock, reset, close, or alter a card. Explain that additional verification is needed or transfer to an appropriate human team when necessary.

## Retrieve and scope all affected cards

The requirement to assess applies to every locked card, even if the customer asks to start with only one.

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
2. For every checking account, unlock and call `get_debit_cards_by_account_id_7823(account_id)`. Retain active and historical cards because issuance reason and date can affect the review.
3. Identify every current card reporting `pin_locked=true` from the card lookup response and record its linked account, last four digits, lock reason, issue reason, issue date, daily ATM limit, security flags, and status. If the lookup response does not include a needed PIN-lock or security field, obtain it through the normal documented card-review capability; do not infer it from the customer's statement.
4. Unlock and call `get_bank_account_transactions_9173(account_id)` for each linked account. Keep the raw returned transaction records for the internal review. Review declined PIN attempts (including `atm_withdrawal_declined` and `pos_declined` when available), successful PIN uses, successful ATM withdrawals, recent successful transactions, and overdraft fees.
5. Determine whether any card on the profile was issued as a stolen replacement within 90 days. Check all relevant card history, not only the locked card.

When several cards are locked, finish fact gathering and a distinct assessment for every locked card before unlocking any of them. A card can have a different score and outcome from another card.

## Automatic escalation gates

Evaluate these gates before calculating an ordinary score for each applicable card:

- **Security hold:** If `pin_lock_reason` is `security_hold`, the card cannot be unlocked by chat. Offer transfer to the security team. If transfer is needed, use `transfer_to_human_agents` with `reason: fraud_or_security_concern` and a concise factual summary; do not expose the internal reason to the customer.
- **Another card locked:** If another card on the same account is also PIN-locked, finish investigation of all cards before any unlock. This is a hold on unlocking, not permission to skip individual assessment.
- **Recent stolen replacement:** If any account card was replaced for `issue_reason=stolen` within 90 days, require enhanced verification before any otherwise eligible action. Enhanced verification must include the required additional identity checks; do not treat standard verification as sufficient.
- **Three or more prior locks:** A score of 3 for D1 means this card cannot be unlocked and requires a PIN reset route instead. It also triggers supervisor review under the single-flag rule.

Do not override a security hold, an incomplete multi-card review, or a required enhanced-verification gate based on a low numeric score.

## Build the internal assessment

For each card, derive the following score inputs from the gathered records. Use the most risk-indicative applicable observation where a category covers multiple declined attempts, and retain the underlying facts in the case notes. Do not invent location, timestamp, limit, card-age, or successful-PIN information that is missing from returned data.

| Flag | Score rule |
|---|---|
| A1 location mismatch | same address city 0; different city/same state 1; different state 2; different country 3 |
| A2 location scatter | one location 0; two 1; three or more 2 |
| A3 travel conflict | 1 only when last-7-day successful activity is solely in home city while declines are elsewhere; otherwise 0 |
| B1 time of day | 06:00–22:00 0; 22:00–00:00 1; 00:00–02:00 2; 02:00–06:00 3 |
| B2 since legitimate PIN use | through 7 days 0; 7–30 days 1; over 30 days 2 |
| B3 failed-attempt velocity | over 5 minutes 0; 2–5 minutes 1; 1–2 minutes 2; under 1 minute 3 |
| C1 amount pattern | same retried or increasing 0; decreasing sequence 2 |
| C2 round-number testing | mixed 0; all round hundreds 1 |
| C3 versus successful ATM average | within 2x 0; 2–5x 1; over 5x 2 |
| C4 versus daily ATM limit | under 80% 0; 80–100% 1; multiple attempts total over the limit 2 |
| D1 prior PIN locks in 90 days | 0/1/2/3+ prior locks score 0/1/2/3 |
| D2 card age | over 3 months 0; 1–3 months 1; under 1 month 2 |
| D3 other card issues | none 0; velocity block 1; fraud alert 2 |
| E1 account age | over 6 months 0; 3–6 months 1; under 3 months 2 |
| E2 overdraft history | none 0; one 1; two or more 2 |
| E3 current balance | $100 or more 0; $50–100 1; under $50 2 |

Use `scripts/pin_lock_risk.py` to total already-derived internal flag values consistently and to produce the required procedural gates. The script does not retrieve data, parse transaction descriptions, verify identity, or take banking action.

Run it with a local JSON assessment file:

```sh
python3 scripts/pin_lock_risk.py < assessment.json
```

Input schema (all keys are required unless noted):

```json
{
  "automatic_triggers": {
    "security_hold": false,
    "other_pin_locked": false,
    "recent_stolen_replacement": false
  },
  "flags": {
    "A1": 0, "A2": 0, "A3": 0, "B1": 0, "B2": 0, "B3": 0,
    "C1": 0, "C2": 0, "C3": 0, "C4": 0, "D1": 0, "D2": 0,
    "D3": 0, "E1": 0, "E2": 0, "E3": 0
  },
  "confirmed_flags": [],
  "time_answer": "unknown"
}
```

`confirmed_flags` may contain only `A1`, `C1`, or `B1` after the applicable customer confirms the event; the script removes that flag for the recalculated assessment. `time_answer` is `unknown`, `confirmed`, `denied`, or `asleep`. JSON output includes validated flags, total, risk band, internal questions, hard blocks, and required next steps. It exits nonzero and emits an error JSON object if input is malformed or a score is outside the documented range.

Before relying on the output, verify that the card and transaction facts used to populate it are for the same card/account and suspicious period. A successful exit is structural validation only; it is not authorization to perform a banking action.

## Customer questions and reassessment

For a total of 5 or more, ask only the questions indicated by the actual nonzero flags:

- For A1: ask whether the customer was at the declined-attempt location.
- For C1: ask whether they remember attempting the listed amounts in that sequence.
- For B1 at 2 or 3: ask whether they were trying to use the card at the listed time.

Use transaction-derived locations, amounts, and local times, but do not mention internal scores. If the customer confirms the location, amount sequence, or time, remove only the corresponding A1, C1, or B1 value and rerun the calculator. Do not remove A2, travel conflict, velocity, limit, or any other corroborating flag merely because one fact was confirmed.

If the customer says they were asleep or otherwise denies the high-risk-time attempts, treat it as a critical security concern. Do not unlock. Review for unauthorized successful transactions and transfer/escalate as appropriate.

## Decision and permitted actions

Apply the post-question recalculated total, while retaining every automatic gate and any single-flag escalation:

- **0–4 low:** Unlock only after standard verification and all gates are cleared.
- **5–7 medium:** Unlock only after asking whether the failed PIN attempts were theirs and obtaining the needed response.
- **8–10 high:** Ask location/time questions where applicable. Unlock only if the customer confirms and gives a satisfactory explanation.
- **11–14 very high:** Do not unlock in chat. Require callback verification or enhanced verification.
- **15+ critical:** Do not unlock. Check for successful unauthorized transactions and recommend closure/replacement.
- **Any individual score of 3:** supervisor review is required regardless of total. Do not treat a recalculated low total as bypassing this rule.

When the procedure authorizes an unlock, use only a normal, currently available banking tool explicitly documented for that purpose and pass the returned card ID after rechecking card status and ownership. Do not guess a tool name or parameters. Record the action result. If no documented unlock capability is available, explain that the case needs the authorized security/card team and transfer rather than claiming it was unlocked.

For a no-unlock outcome, review the suspicious period for successful transactions the customer says were unauthorized. If found, follow the normal dispute process and arrange card closure/replacement where authorized. If none are found, explain that a security review is needed and offer the applicable options: security-team investigation, PIN reset, or closure/replacement when fraud is suspected. Do not state fraud codes or internal risk rationale.

## PIN reset and post-unlock follow-up

For D1=3, route to reset rather than unlock. A PIN reset requires verified identity, card ownership, an ACTIVE card, confirmation of the last four digits, and a new compliant four-digit PIN. It must not be sequential, all identical, or a birth-year/month-day value. Unlock and use `reset_debit_card_pin_6284` only when the documented prerequisites and tool parameters are satisfied. Never read a PIN back.

After an eligible successful unlock:

- D1=0: standard unlock, no added step.
- D1=1: offer PIN-lock notifications.
- D1=2: offer a PIN reset and explain that repeated locks can mean the PIN is hard to remember.
- D1=3+: no unlock; reset route only.

## Completion record

Keep an internal case record for each card: verified user and linked account/card IDs, automatic-gate results, transaction period reviewed, the derived flag values and calculation output, customer answers, reassessment changes, any unauthorized-transaction finding, final action/transfer, and tool result. Customer-facing completion language should state only the outcome and next safe step, never the calculations or protected security details.
