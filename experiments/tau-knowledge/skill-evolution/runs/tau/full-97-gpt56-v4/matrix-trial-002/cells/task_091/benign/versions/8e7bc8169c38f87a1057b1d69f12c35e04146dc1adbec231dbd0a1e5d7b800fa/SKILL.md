---
name: pin-lock-fraud-review
version: 1.1.0
description: Safely handle a request to unlock a PIN-locked debit card. Use for PIN-lock or PIN-decline cases requiring profile verification, complete card/account and transaction investigation, fraud-risk scoring, risk questions, and an unlock, PIN reset, replacement, or security escalation decision.
---

# PIN-lock fraud review

Do not reveal fraud-score calculations, point values, internal thresholds, or sensitive card data. Do not change a card, order a replacement, disclose account-specific activity, or log verification until the customer is verified.

## 1. Identify and verify the caller

1. Use a supplied name, email, or user ID only to locate a possible profile. Lookup is **not** verification.
2. Match **two distinct fields** from date of birth, email, phone number, and address. A mismatch is not a match. If a field mismatches, request a different field instead of treating the lookup result as confirmation.
3. After two fields match, obtain the current time and call `log_verification` with the complete profile data and timestamp. Only then continue with card-specific discussion.
4. If verification cannot be completed, make no account/card change. Explain that the security review requires verification and, if appropriate, transfer for secure assistance.

## 2. Build the complete card scope

Unlock and call the documented internal tools:

1. `get_all_user_accounts_by_user_id_3847` with `user_id`.
2. For **every checking account**, call `get_debit_cards_by_account_id_7823` with its `account_id`.
3. Call `get_bank_account_transactions_9173` for every checking account that has a reported locked card (and any other checking account needed to assess other-card issues).

Inventory all currently PIN-locked cards, including the account they belong to. Review historical cards for recent stolen replacements. Card data may provide lock reason, lock frequency, last successful PIN use, limits, issue date, and security flags when returned. Transactions are returned newest first; sort relevant declines chronologically for amount patterns and inter-attempt intervals.

A card locked on the **same account** as another locked card means all of those cards must be individually investigated before any is unlocked. Multiple locks on different accounts do not by themselves create that same-account trigger, but all reported cards still need an investigation.

## 3. Apply the automatic triggers

For each locked card/account group, record these triggers before deciding on an unlock:

- `security_hold`: no chat unlock; route to the security team.
- another PIN-locked card on the same account: complete every card investigation before considering an unlock.
- any card replaced for `issue_reason = stolen` within 90 days: require enhanced verification in addition to the fraud review.

Use the current date for the 90-day test. A trigger is an additional gate, not a substitute for the individual risk assessment.

## 4. Derive every fraud flag per locked card

Use the policy definitions and point bands exactly. Base conclusions on the card's relevant declined `atm_withdrawal_declined` / `pos_declined` activity, successful activity, card data, other cards, account opening date, overdraft fees, and current balance.

Derive and record the 15 flags:

- **A1–A3:** decline location versus verified home city/state; count of distinct decline locations; conflict with successful activity in the last seven days.
- **B1–B3:** decline time band; time since successful PIN use; shortest gap between consecutive failed attempts.
- **C1–C4:** chronological amount pattern; all-round-hundreds test; attempted amount versus average recent successful ATM withdrawal; and attempted/aggregate same-day ATM amount versus the daily ATM limit.
- **D1–D3:** PIN locks in 90 days; card age; other cards' velocity block or fraud alert.
- **E1–E3:** account age; recent overdraft-fee count; current balance.

Do not silently call unavailable evidence zero. Retrieve the source where possible. A flag can be zero where the returned data affirmatively establishes the zero condition (for example, no prior locks shown), but if a material input genuinely cannot be determined, keep that card unresolved and escalate rather than authorize an unlock.

Run the normalized flag values through `scripts/assess_pin_risk.py`. The script is a local internal calculator only: it makes no banking calls and its output must not be quoted to the customer.

### Script interface

The script reads one JSON object from stdin and emits one JSON object on stdout.

```json
{
  "automatic_triggers": {
    "security_hold": false,
    "other_cards_locked": false,
    "recent_stolen_replacement": false
  },
  "flags": {
    "A1": 0, "A2": 0, "A3": 0,
    "B1": 0, "B2": 0, "B3": 0,
    "C1": 0, "C2": 0, "C3": 0, "C4": 0,
    "D1": 0, "D2": 0, "D3": 0,
    "E1": 0, "E2": 0, "E3": 0
  }
}
```

All 15 flags must be policy-range integers. Null/omitted flags yield an incomplete assessment. Inspect `required_internal_gates`, not just the total: more than one gate can apply at once (for example, a required PIN reset and supervisor review). A known hard D1 or three-point flag remains a gate even if another flag is missing.

## 5. Ask only the required customer questions

Work on a card in the customer's requested priority after the complete inventory/investigation is done. Do not overwhelm the customer with questions for every card at once; finish the questions and decision for the current card before moving to the next, unless a security hold requires immediate transfer.

For a medium-or-higher assessment, first ask: **“I see failed PIN attempts on your card. Were those attempts yours?”** Then ask the applicable questions using the transaction facts, without scores:

- Location mismatch: ask whether the customer was at the stated location. If confirmed, remove only the supported location flag(s) and recalculate; if denied, retain them.
- Decreasing amounts: ask whether they remember trying the listed amounts in chronological order. Remove C1 only if confirmed.
- B1 of two or more: ask whether they were trying to use the card at that time. If they say they were asleep or clearly deny it, treat the activity as likely fraud: do not unlock and review unauthorized activity.

For a high assessment, confirmation plus a satisfactory explanation for flagged location/time activity is necessary before an unlock can be considered. Recalculate after any supported removal. Customer confirmation does not remove an unrelated flag or an automatic gate.

## 6. Decide and perform only supported actions

Apply every remaining gate and the final score:

- **Low:** eligible after standard verification.
- **Medium:** require the ownership confirmation before eligibility.
- **High:** require the specific questions, confirmation, and satisfactory explanation.
- **Very high:** do not unlock on the call; require callback verification or enhanced verification (last four SSN plus a security question).
- **Critical:** do not unlock. Check the suspicious period for successful transactions the customer says are unauthorized; recommend closure and replacement.
- **D1 = 3 points:** do not unlock; PIN reset is required.
- **Any 3-point flag:** supervisor review is required regardless of total.

For unauthorized activity, follow available dispute/closure/replacement procedures. If none is identified, explain the security concern without internal calculations and offer the allowed alternatives: security investigation, closure/replacement, or PIN reset as applicable. For a replacement, retrieve tier and replacement history, apply its rolling limit/wait and exact delivery/design fees, and disclose that fees are automatically charged before ordering.

Perform a PIN reset only for a verified owner and an ACTIVE card after obtaining the card's last four digits and a compliant customer-chosen four-digit PIN. It must not be sequential, all identical, the birth year, or birth month/day. Unlock and use `reset_debit_card_pin_6284` with `card_id`, `last_4_digits`, and `new_pin`; never repeat/display the PIN.

Use an actual PIN-unlock tool only if it is declared and its parameters are documented. Never invent an unlock tool or parameters. If no supported chat unlock action exists for an otherwise eligible card, explain that the unlock must be completed by secure card support and transfer using the fraud/security reason. Do not transfer before completing the customer questions needed to identify a fraud/unauthorized-activity response, except for a security hold.

After an eligible unlock, offer PIN-lock notifications after one prior lock; after two prior locks, offer a PIN reset. No extra post-unlock step is required after zero prior locks.

## Completion checklist

Before ending, verify that two profile fields were matched and logged; every reported locked card was scoped and assessed separately; automatic triggers and all material flags were addressed; required questions/recalculations occurred; no prohibited action was taken; and the customer received a clear, non-technical next step.
