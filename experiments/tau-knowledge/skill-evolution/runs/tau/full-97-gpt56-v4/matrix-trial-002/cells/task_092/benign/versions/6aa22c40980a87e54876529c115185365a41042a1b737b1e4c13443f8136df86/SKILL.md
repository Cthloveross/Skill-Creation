---
name: debit-card-pin-lock-fraud-investigation
description: Investigate one or more PIN-locked debit cards using the required fraud-risk protocol. Use for customers reporting PIN lock, decline code 55, or decline code 75; gather account/card/transaction evidence, assess every locked card before unlocking any, ask risk-driven verification questions, and either unlock through an available authorized banking tool or take the required fraud-protection path.
---

# Debit-card PIN-lock fraud investigation

## Scope and safety

Use this Skill only for debit-card PIN locks and PIN-related declines. A PIN-locked card must **never** be unlocked until its fraud-risk assessment is complete. Do not disclose the scoring arithmetic, point values, internal flags, or other security logic to the customer.

Treat each card as a separate assessment. If more than one card on the same account is locked, complete the investigation of **all** locked cards before unlocking any of them. Do not make a banking change merely because this Skill recommends it: use only an available, authorized normal banking tool, after its prerequisites have been met.

## Required runtime inputs

At runtime, obtain:

- The customer's identity locator (email, name, or user ID) and the customer's stated issue.
- A standard identity verification: have the customer confirm at least two identity fields, then obtain the current timestamp and call `log_verification` with the complete returned user record and timestamp. Do not treat a mere lookup as verification.
- User record, all bank accounts, debit cards for each relevant open checking account, and transactions for each relevant account.
- The card lookup's PIN status/reason/attempt fields if supplied by the runtime, card status, issuance date, limits, and issue reason.
- Customer answers needed for risk questions and any proposed PIN reset.

The supported evidence retrieval tools documented for this workflow are:

1. Unlock and call `get_all_user_accounts_by_user_id_3847` using `user_id`.
2. For every relevant checking account, unlock and call `get_debit_cards_by_account_id_7823` using `account_id`.
3. For each account containing a card being investigated, unlock and call `get_bank_account_transactions_9173` using `account_id`.

If the environment exposes a specialized PIN-unlock tool, first unlock it and read its parameters before use. The supplied policy does not specify that tool's name or argument schema; do not invent one. If no authorized unlock capability exists after the assessment, explain the eligible outcome and transfer/escalate rather than claiming the card was unlocked.

## Evidence collection and initial triage

1. Identify the customer and perform the standard verification above before any state-changing action.
2. Retrieve all accounts. Restrict debit-card actions to checking accounts that are open and linked to the verified user.
3. Retrieve **all** debit cards for each relevant checking account, including historical cards. Confirm the selected card belongs to the verified user. Identify all cards whose returned PIN status is locked. Do not rely only on the customer's count or card nickname.
4. Retrieve account transactions. Preserve the raw information internally: date, description, amount, type, status, and transaction ID. Transaction lists are reverse chronological.
5. Ask whether the customer made the failed attempts for each locked card. For any attempts they deny, ask their location and approximate time. Ask whether they retain the physical card and whether they recognize recent ATM withdrawals, debit-card purchases, or other successful activity. Do not assume an unrecognized event is authorized.
6. Before assigning a score to a card, check these automatic conditions:
   - `pin_lock_reason` is `security_hold`: do not unlock that card; offer transfer to the security team.
   - Any other card on the account is PIN locked: investigate every locked card first; no card can be unlocked until those investigations are finished.
   - Any account card was issued as a stolen-card replacement within the preceding 90 days: require enhanced verification before proceeding.

When transfer is required for a security concern, use `transfer_to_human_agents` with `reason: "fraud_or_security_concern"` and a factual summary of the card(s), completed evidence, and why no unlock was performed. Never represent a transfer as an unlock.

## Per-card scoring worksheet

Use only declined attempts of type `atm_withdrawal_declined` or `pos_declined` when those types are returned. If the runtime does not return a field needed for a flag, mark that flag as unavailable rather than guessing. State the missing evidence internally and obtain a customer answer where the protocol requires one.

For each locked card, determine and internally record all applicable flags:

### Location

- **A1 location mismatch:** compare the declined location in the description with the customer address city: same city 0; different city in same state 1; different state 2; different country 3.
- **A2 location scatter:** all attempts at one location 0; two locations 1; three or more 2.
- **A3 travel conflict:** add 1 only when successful transactions in the last seven days are all in the home city while declines are elsewhere; add 0 when recent successful activity shows travel across cities.

### Time

- **B1 time of day:** 06:00–22:00 is 0; 22:00–00:00 is 1; 00:00–02:00 is 2; 02:00–06:00 is 3. Use transaction timestamps only if supplied; a date alone cannot establish an hour.
- **B2 since legitimate PIN use:** use the latest successful PIN use if the transaction data identifies it: less than seven days 0; 7–30 days 1; more than 30 days 2. If the time is unavailable, do not infer it from an ordinary non-PIN purchase.
- **B3 attempt velocity:** more than five minutes 0; 2–5 minutes 1; 1–2 minutes 2; under one minute 3. Do not derive minute intervals without timestamps.

### Amount

- **C1 amount pattern:** same-amount retries or increasing amounts 0; decreasing consecutive failed amounts 2.
- **C2 round-number testing:** all amounts being round hundreds is 1; otherwise 0.
- **C3 versus historical ATM average:** calculate the average of recent successful ATM withdrawals, then compare each relevant attempted amount: within 2× average 0, 2–5× 1, above 5× 2. If there is no usable historical ATM sample, leave unavailable rather than divide by zero or substitute all purchases.
- **C4 daily ATM limit:** below 80% is 0, 80–100% is 1, and multiple attempts totaling more than the daily limit is 2. Use the selected card's daily ATM limit and ATM attempts only; do not apply this flag to POS attempts or a missing limit.

### Card and account history

- **D1 prior PIN locks in 90 days:** 0/1/2/3+ prior locks score 0/1/2/3. The current lock is not a prior lock. At 3+ prior locks, unlocking is prohibited and a PIN reset is required.
- **D2 card age:** over three months 0; 1–3 months 1; under one month 2. Calculate from issuance date and current time.
- **D3 other-card issues:** no other issue 0; another card with velocity block 1; another card with an active fraud alert 2.
- **E1 account age:** over six months 0; 3–6 months 1; under three months 2, based on account opening date.
- **E2 overdrafts:** count recent `overdraft_fee` transactions: none 0, one 1, two or more 2.
- **E3 balance:** over $100 is 0; $50–100 is 1; below $50 is 2.

Maintain a private worksheet containing the evidence, unavailable flags, each score, total, and any flag equal to 3. Do not state the worksheet or total to the customer.

## Risk questions and rescoring

For a total of 5 or higher, ask the applicable questions before deciding:

- For a scored location mismatch: “I see your card was locked after failed PIN attempts at [location]. Were you at that location?” If yes, remove the location flags and recalculate. If no, retain them.
- For a scored decreasing amount pattern: “The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?” Remove that flag only if confirmed.
- For a B1 time score of 2 or 3: “These attempts occurred at [time]. Were you trying to use your card at that time?” Remove the time flag if confirmed. If the customer says they were asleep or otherwise clearly denies the attempt, treat it as likely fraud and do not unlock.

A customer confirmation affects only the stated flag(s); do not erase unrelated evidence. Recalculate after permitted removals. Any individual 3-point flag requires supervisor review regardless of the total, even if later answers lower the total unless the answer directly resolves that flag under the protocol.

## Decision and customer handling

Apply the final score and escalation rules separately per card:

- **0–4, low:** unlock only after standard identity verification and only after all simultaneously locked cards have completed investigation.
- **5–7, medium:** unlock only after asking, “I see failed PIN attempts on your card. Were those attempts yours?” and after a satisfactory answer.
- **8–10, high:** ask the specific location/time questions required by the flags. Unlock only if the customer confirms and gives a satisfactory explanation.
- **11–14, very high:** do not unlock in this interaction. Require callback verification or enhanced verification consisting of last four SSN plus a security question, using only capabilities actually supplied by the runtime.
- **15 or higher, critical:** do not unlock. Check for successful unauthorized transactions; recommend closure and replacement.
- **Any 3-point flag:** supervisor review; do not independently unlock.
- **D1 of 3 or more prior locks:** do not unlock; require a PIN reset.

If the card is eligible and a legitimate unlock tool is available, call it using its documented schema, then report only that the card has been unlocked and any safe next step. Do not ask for or reveal a PIN unless performing the separately authorized reset procedure.

For an eligible PIN reset, confirm verified ownership, active card status, last four digits, and a new PIN that is exactly four digits, non-sequential, not all one digit, and not the customer's birth year or birth month/day. Use `reset_debit_card_pin_6284` only after unlocking that discoverable tool and with its documented `card_id`, `last_4_digits`, and `new_pin` parameters. Never repeat or display the PIN in the response.

After a successful eligible unlock, follow D1-based aftercare:

- Zero prior locks: no extra step.
- One prior lock: offer PIN-lock notifications using the required wording.
- Two prior locks: offer a PIN reset and explain this is the third lock in 90 days.
- Three or more: do not unlock; reset is required.

## Suspected fraud, disputes, closure, and replacement

Whenever an unlock is prohibited or denied attempts suggest fraud, inspect the suspicious period for successful unauthorized transactions before recommending next steps.

- If there are unauthorized successful transactions, offer the fraud/dispute route. Before filing a dispute, collect every required dispute fact and use the documented fraud category (`card_present_fraud` for physical use, `card_not_present_fraud` for online/phone use). A fraud dispute records `close_and_reissue`, and the actual card closure/replacement must be performed separately only when all relevant prerequisites and tools are available.
- If there are no unauthorized successful transactions, explain that security checks prevent an unlock and offer security-team investigation, card closure/replacement where appropriate, or PIN reset. Do not file a dispute solely for declined attempts.
- Before closing a card, confirm ownership and applicable status; for suspected fraud, the normal 14-day card-age requirement is bypassed, but pending-transaction/refund requirements and the closure tool's documented requirements still apply.
- Before ordering a replacement, retrieve card history, count qualifying lost/stolen/fraud/damaged replacements in the last 12 months, determine the checking-account tier, tell the customer the exact applicable delivery/design/excess fee before ordering, and use only the documented order tool parameters.

## Completion record

Internally summarize for every locked card: account/card identity, lock state and reason, automatic triggers, evidence sources, available and unavailable flags, final non-disclosed risk outcome, questions and customer answers, action taken or reason action was withheld, transfer/dispute/closure status, and customer-facing next steps. Confirm only completed actions; never claim that an unavailable tool, transfer, dispute, closure, replacement, unlock, or reset has occurred when it has not.
