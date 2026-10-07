---
name: pin-lock-fraud-assessment
description: Investigate PIN-locked debit cards before any unlock. Use for PIN-related declines or requests to unlock a debit card PIN lock, especially when several cards on one account are locked. It retrieves all relevant checking accounts/cards and transaction history, applies the documented fraud-risk protocol per card, guides safe customer questions, and routes fraud/security cases without revealing internal scoring.
---

# PIN-Lock Fraud Assessment

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow whenever `pin_locked` is true or a PIN-related decline indicates that the PIN tries were exceeded. Do not unlock merely because the customer asks. Do not disclose internal point values, score totals, fraud-detection logic, or internal decline reasons to the customer.

The assessment is per card. If more than one card on an account is PIN-locked, investigate **every locked card** before any one is unlocked. A card may have a different outcome from the others.

Use only ordinary banking tools that are actually available in the execution runtime. Tool names cited below are discoverable-agent tools: unlock each tool before calling it. Do not invent an unlock tool, its parameters, card fields, transaction fields, or a successful result. If an approved PIN-unlock capability is not available after the assessment authorizes an unlock, explain the next authorized route or transfer for security handling rather than attempting another card action.

## Required retrieval and verification sequence

1. Verify the caller using the institution's standard process. Match at least two identity fields against the profile, obtain the current timestamp with `get_current_time`, and record a successful verification with `log_verification` when that tool is available. Verification is necessary but does not replace fraud assessment or enhanced verification.
2. Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)`. Identify all checking accounts, their ownership, open/restricted status, balances, and opening dates. Preserve account ownership, product eligibility, status, and balance findings with the case record.
3. For every relevant checking account, unlock and call `get_debit_cards_by_account_id_7823(account_id)`. Collect all card records, including historical/replacement cards, not only the named card. Confirm the selected card belongs to the verified user and is linked to the intended checking account.
4. For every account that has a card being investigated, unlock and call `get_bank_account_transactions_9173(account_id)`. Obtain enough history to review the suspicious period, recent successful activity, ATM history, overdraft fees, and potential unauthorized successful transactions.
5. Obtain any available PIN-lock audit/history and detailed decline metadata needed for the protocol (PIN lock reason, prior lock count, decline timestamps, locations, and successful PIN uses). The documented ordinary card and transaction retrieval schemas may not expose all of these fields. Never infer missing timestamps, locations, lock counts, PIN use, security flags, or an unlock result. Mark the assessment incomplete and obtain authorized review when evidence needed for a decision is unavailable.

## Immediate checks before scoring

For each locked card, perform and record these checks before score calculation:

- If `pin_lock_reason` is `security_hold`, chat agents cannot unlock it. Offer transfer to the security team.
- If any other card on the same account is also `pin_locked`, do not unlock any of those cards until all of them have been investigated and scored individually.
- If any account card was issued as a stolen-card replacement in the preceding 90 days (`issue_reason = stolen` and recent `date_issued`), require enhanced verification before proceeding.
- If the card/account ownership, account openness, card eligibility/status, or required identity verification cannot be confirmed, do not perform a banking action.

A security-hold, suspected compromise, customer denial of suspicious attempts, fraud indication, or inability to complete required verification should be transferred using `transfer_to_human_agents` with reason `fraud_or_security_concern` and a concise, non-sensitive case summary.

## Score each card

Normalize retrieved evidence and run the packaged scorer:

```text
python scripts/score_pin_lock.py < assessment.json
```

The script reads one JSON object from standard input and emits one JSON object on standard output. Its input schema is documented in the script header. It calculates only supported, supplied facts; `null` flag scores and `incomplete_fields` mean the case must not be treated as eligible for an unlock until the missing evidence is resolved. Treat the calculation as internal-only.

The scorer implements these protocol categories:

- **Location:** mismatch from home city/state/country, scatter across decline locations, and conflict with successful activity in the past seven days.
- **Time:** declined-attempt hour, time since the last successful PIN use, and shortest interval between failed attempts.
- **Amounts:** decreasing failed amounts, all-round-hundreds testing, attempted amount compared with successful ATM average, and total/individual attempt compared with the daily ATM limit.
- **Card history:** prior PIN locks in 90 days, card age, and other cards' velocity/fraud alerts.
- **Account history:** account age, overdraft count, and current balance.

The script deliberately does not scrape cities or timestamps from free-form transaction descriptions. Supply structured decline location and timestamp data from an authorized source. This avoids making an unlock decision from a guessed location or time.

## Threshold and customer-contact procedure

Apply the calculated total after required customer confirmations have been recorded and the score recalculated where the protocol permits. A currently present single 3-point flag requires supervisor review regardless of the total. A prior-lock count of three or more requires a PIN reset rather than an unlock.

- **0–4 (low):** Unlock only after standard identity verification and all prerequisites are confirmed.
- **5–7 (medium):** Ask: “I see failed PIN attempts on your card. Were those attempts yours?” Unlock only after the required response and ordinary prerequisites.
- **8–10 (high):** Ask targeted questions about the relevant location and time. Unlock only if the customer confirms the activity and gives a satisfactory explanation.
- **11–14 (very high):** Do not unlock on the call. Require callback verification or enhanced verification (last four SSN plus a security question).
- **15 or higher (critical):** Do not unlock. Check for successful unauthorized transactions and recommend closure/replacement as appropriate.

For a score of 5 or higher, ask only questions supported by the evidence:

- If location mismatch was scored: ask whether the customer was at the identified location. If confirmed, remove the location flags and recalculate.
- If decreasing amount pattern was scored: ask whether the customer recalls the specific failed amounts in chronological order. If confirmed, remove that amount-pattern flag and recalculate.
- If time-of-day was 2 or 3 points: ask whether the customer was attempting to use the card at the recorded time. If confirmed, remove the time flag and recalculate. If the customer says they were asleep or otherwise denies being there, treat it as a critical fraud concern.

Do not state the numeric score or describe the calculations. Use neutral language such as “I need to review some recent card activity to keep the account secure.”

## Authorized outcome handling

Before any PIN unlock, reconfirm the verified user is the card owner, the card/account is eligible, every locked card on the account has been assessed, the applicable verification level is complete, and the calculated protocol permits it. Then use only an available approved PIN-unlock capability.

After an authorized unlock, apply the prior-lock follow-up:

- 0 prior locks: standard unlock.
- 1 prior lock: offer PIN-lock notifications.
- 2 prior locks: offer a PIN reset because this is the third lock in 90 days.
- 3 or more prior locks: do not unlock; require a PIN reset.

If an unlock is not allowed, review the suspicious period for successful transactions the customer says were unauthorized. If unauthorized transactions are found, follow the debit-card dispute procedure and required verification; where fraud is suspected, use the fraud-appropriate dispute category, close/reissue as required by that procedure, and never claim a dispute was filed unless the authorized tool succeeded. If no unauthorized transactions are identified, explain only the necessary security limitation and offer the documented options: replacement/closure when appropriate, security-team investigation, or PIN reset.

Use the normal PIN-reset procedure only after its separate prerequisites are met: verified owner, ACTIVE card, last-four confirmation, and a compliant new 4-digit PIN. Never repeat, display, or read a PIN back to the customer.

## Validation checklist

Before closing the interaction, ensure the case record contains: verified customer and timestamp; all retrieved accounts/cards; each locked card's independent automatic-trigger result; transaction-review coverage; structured facts used for every non-null score; unknown evidence and escalation rationale; customer answers and recalculation changes; threshold outcome; any action actually completed; and required post-unlock offer or transfer/dispute follow-up.
