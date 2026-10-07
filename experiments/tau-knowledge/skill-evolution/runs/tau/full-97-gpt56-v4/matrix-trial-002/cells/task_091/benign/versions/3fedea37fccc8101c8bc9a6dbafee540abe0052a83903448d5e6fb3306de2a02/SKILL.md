---
name: pin-lock-fraud-review
version: 1.0.0
description: Investigate requests to unlock PIN-locked debit cards. Use for debit-card PIN decline/lock cases requiring identity verification, account/card and transaction review, fraud-risk scoring, customer risk questions, and safe unlock, reset, replacement, or security-transfer decisions.
---

# PIN-lock fraud review

Do not disclose fraud-score calculations, point values, or internal decision thresholds to the customer. Do not unlock, reset a PIN, order a card, expose account details, or log successful verification until the caller is verified.

## 1. Verify identity first

1. Locate a possible profile from a customer-provided identifier, but treat lookup as identification rather than verification.
2. Confirm **two of these four** profile fields: date of birth, email, phone number, and address. A mismatch is not a match. If one supplied field is wrong, politely request a different profile field; do not repeatedly accept the same mismatch.
3. Once two fields match, obtain the current time and call `log_verification` with all required profile fields and that timestamp. Only then discuss or act on card-specific information.
4. If identity cannot be verified, state that the security review and account changes cannot proceed and offer an appropriate human/security transfer if the customer needs further help.

## 2. Retrieve complete scope after verification

Unlock and use the documented internal tools in this order:

- `get_all_user_accounts_by_user_id_3847` with `user_id`
- For every checking account, `get_debit_cards_by_account_id_7823` with `account_id`
- `get_bank_account_transactions_9173` for each relevant checking account

Review active and historical cards. The debit-card lookup is also the source for PIN lock state, PIN attempts, lock reason, limits, issue date, status, and card history when those fields are present. The transaction history is reverse chronological; sort relevant events chronologically before velocity and amount-pattern analysis.

If the customer reports multiple locked cards, inventory every locked card and assess each one separately. Never unlock one while another locked card on the account remains uninvestigated.

## 3. Check automatic escalation before any unlock

For each account/card group, determine whether:

- the card has `pin_lock_reason = security_hold`; it cannot be unlocked by chat. Offer transfer to the security team;
- another card on the account is PIN locked; complete every individual investigation before considering any unlock; or
- a card was replaced for `issue_reason = stolen` within the preceding 90 days; require enhanced verification.

Use the current date for rolling date windows. A security hold is a hard stop for chat unlocking. Do not treat a recent stolen-card trigger as permission to skip the fraud review.

## 4. Gather and score evidence for each locked card

Review declined `atm_withdrawal_declined` and `pos_declined` events, relevant successful transactions, all cards, account age, and current balance. Compare locations to the verified address city/state and use the transaction timestamp for time and velocity checks.

Determine the protocol flags below once per card. For multi-event criteria, use the most concerning applicable result unless the criterion expressly concerns totals or a sequence:

- **A1–A3 location:** location mismatch, number of distinct decline locations, and whether recent successful activity was solely home-city while declines were elsewhere.
- **B1–B3 time:** most risky decline time band, time since the most recent successful PIN use, and shortest interval between consecutive failed attempts.
- **C1–C4 amounts:** chronological pattern of failed amounts, whether all are round hundreds, maximum attempted amount relative to recent successful ATM-withdrawal average, and highest amount/aggregate same-day attempts relative to the daily ATM limit.
- **D1–D3 card history:** prior PIN locks in 90 days, age since issue/activation, and other cards' velocity blocks or fraud alerts.
- **E1–E3 account:** age since opened, recent overdraft-fee count, and current balance.

Use the policy's stated point bands exactly. Do not score unavailable evidence as zero. Retrieve the missing source where possible. If a required material input cannot be determined, keep the card unresolved and transfer/escalate rather than making an unlock decision from an incomplete score.

Use `scripts/assess_pin_risk.py` to total an already-derived, complete set of flag values and to consistently apply score and escalation rules. It deliberately does not parse bank prose or make bank actions.

Example invocation through the packaged runtime:

```json
{"automatic_triggers":{"security_hold":false,"other_cards_locked":true,"recent_stolen_replacement":false},"flags":{"A1":1,"A2":0,"A3":0,"B1":0,"B2":0,"B3":0,"C1":0,"C2":0,"C3":0,"C4":0,"D1":0,"D2":0,"D3":0,"E1":0,"E2":0,"E3":0}}
```

The script emits JSON with the score, risk band, missing flags, and safe next-step gates. Do not relay that JSON or its numeric contents to the customer.

## 5. Ask required customer questions and recalculate

When the score is medium or above, first ask: “I see failed PIN attempts on your card. Were those attempts yours?”

For every scored location mismatch, ask whether the customer was at the transaction location. If confirmed, remove the location-related score supported by that confirmation and recalculate. If denied, retain it.

For a scored decreasing amount pattern, ask whether the customer remembers trying the specific amounts in chronological order. Remove only that amount-pattern flag if confirmed.

For a time-of-day score of two or three, ask whether the customer was trying to use the card at that time. Remove that time flag only if confirmed. If the customer says they were asleep or otherwise clearly denies the activity, treat it as likely fraud: do not unlock and proceed with the fraud/unauthorized-activity response.

For a high result, obtain satisfactory explanations for the flagged location and time activity before unlocking. Re-run the assessment after any permitted flag removal. A single remaining three-point flag requires supervisor review regardless of total.

## 6. Decision and action

Apply the final complete assessment:

- Low: unlock only after standard identity verification.
- Medium: unlock only after the failed-attempt ownership question.
- High: unlock only after the required specific questions, confirmation, and satisfactory explanation.
- Very high: do not unlock on this call; require callback verification or enhanced verification consisting of last four SSN plus a security question.
- Critical: do not unlock. Check suspicious-period successful transactions for activity the customer identifies as unauthorized; recommend closure and replacement.
- D1 of three or more prior locks: do not unlock; a PIN reset is required.
- Any single three-point flag: route for supervisor review even if the total is otherwise low.

Use only a declared, available banking action tool with its documented parameters for an actual PIN unlock; never guess an unlock tool name or parameters. If no such tool is available, explain that the unlock cannot be completed in chat and transfer to the security/specialized team.

For a reset, follow the documented reset procedure: verified owner, ACTIVE card, confirmed card last four, and a customer-supplied compliant new four-digit PIN (not sequential, all identical, birth year, or birth month/day). Unlock `reset_debit_card_pin_6284` and call it with `card_id`, `last_4_digits`, and `new_pin`. Never repeat or display the PIN.

When unlock is not permitted, review successful suspicious-period activity with the customer. If unauthorized transactions are identified, follow the available dispute, closure, and replacement processes. If none are identified, explain the security concern without internal scoring and offer card closure/replacement, security-team investigation, or a PIN reset as appropriate. For any replacement, retrieve tier and replacement history and apply the documented tier-specific waiting periods, eligibility limits, and exact delivery/design fees before ordering; disclose that applicable fees are charged automatically.

After an eligible unlock: with one prior lock, offer PIN-lock notifications; with two prior locks, offer PIN reset and explain frequent locks can mean the PIN is hard to remember. No extra post-unlock step is required for zero prior locks.

## Validation checklist

Before ending, confirm: identity was logged only after two matching fields; every reported locked card was reviewed; automatic triggers were checked; each score was complete and separately assessed; required questions were asked and any recalc documented internally; no prohibited unlock occurred; and the customer received a clear non-technical next step.
