---
name: debit-card-pin-lock-investigation
description: Investigate PIN-locked debit cards using the required fraud-risk protocol. Use when a verified customer reports a locked PIN, failed PIN attempts, or a PIN-related decline and an agent must determine whether an unlock, enhanced verification, PIN reset, dispute, closure, or security escalation is permitted.
---

# Debit Card PIN-Lock Investigation

Use this Skill for each PIN-locked debit card. A PIN lock is not a fraud-alert or velocity-block clearing request: do **not** use a fraud-alert clearing tool to attempt to unlock a PIN-locked card.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and disclosure rules

- Verify identity before any account/card action. Confirm at least two independent profile fields, record verification with the available verification-log tool, and ensure the caller owns the card and linked account.
- Never disclose fraud scores, point values, flag calculations, internal decline/security codes, or the detailed scoring method to the customer. Use the customer-safe questions below instead.
- Investigate **every** locked card on the account independently. When more than one card is locked, complete all investigations before any card is unlocked.
- Never invent a PIN-unlock tool or substitute a fraud-alert/velocity-block tool for a PIN-unlock action. If the runtime does not expose a documented, authorized PIN-unlock capability after the assessment, explain the permitted next step and transfer to security when required.
- Treat missing facts as unresolved, not as zero-risk facts. Obtain the missing data or escalate rather than finalizing an unlock decision from incomplete evidence.

## Runtime data collection

1. Establish the customer record from supplied identity information. Confirm two profile fields (for example date of birth and mailing address) against the returned profile, obtain the current timestamp if required by the verification logger, and log the completed verification.
2. Retrieve all customer accounts with `get_all_user_accounts_by_user_id_3847`. Identify the OPEN checking account(s), their balances, opening dates, and account classes/tier information.
3. For each checking account, retrieve every debit card with `get_debit_cards_by_account_id_7823`. Record card ID, linked account ID, owner user ID, status, issue reason, date issued, last four digits, daily ATM limit, PIN-lock fields, PIN-lock reason, lock history, and any security flags returned by the runtime.
4. Confirm the target card belongs to the verified user and linked checking account. Find all cards with `pin_locked = true`; do not rely only on the caller's description or a card nickname.
5. Retrieve linked-account transaction history using the documented transaction-history capability (the procedure references `get_bank_account_transactions_9173`). Obtain enough history to identify:
   - all PIN-related declines (`atm_withdrawal_declined` and `pos_declined`) relevant to the lock;
   - successful transactions in the last 7 days;
   - the most recent successful PIN use;
   - recent successful ATM withdrawals; and
   - recent overdraft fees and any successful transactions the customer says were unauthorized.
6. Gather any data the tools do not return: the customer’s home city from their profile, prior PIN locks in the last 90 days, the source/date of other card security issues, and whether a replacement was issued for theft in the past 90 days. Preserve timestamps and transaction locations.

## Immediate trigger review

Before scoring each locked card, check all of the following:

- `pin_lock_reason = security_hold`: chat agents cannot unlock that card. Offer/perform a security-team transfer using `fraud_or_security_concern`.
- Another card on the account is PIN-locked: score each locked card before considering any unlock.
- Any account card was replaced in the preceding 90 days with `issue_reason = stolen`: enhanced verification is required before any eligible action.

A trigger does not permit bypassing identity, ownership, transaction review, or per-card scoring. A security hold prevents chat unlocking even if the calculated score would otherwise be low.

## Compute and review the risk assessment

Normalize the collected facts and run:

```text
python scripts/score_pin_lock.py < assessment.json
```

The executor normally invokes packaged scripts through its script runner, which sends the JSON object to stdin and reads the JSON result from stdout. A sample invocation schema is below; values are placeholders and must be supplied from the current case, not copied as case data.

```json
{
  "now": "2025-01-15T12:00:00-05:00",
  "customer_location": {"city": "Home City", "state": "ST", "country": "US"},
  "card": {"card_id": "current-card", "date_issued": "2024-01-01", "daily_atm_limit": 500, "pin_locked": true, "pin_lock_reason": null, "prior_pin_locks_90d": 0},
  "account": {"date_opened": "2020-01-01", "balance": 600},
  "all_cards": [],
  "declines": [],
  "successes": [],
  "recent_successful_atm_withdrawals": [],
  "overdraft_fee_count": 0
}
```

`score_pin_lock.py` accepts one JSON object with these fields:

- `now`: ISO-8601 assessment time.
- `customer_location`: `city`, `state`, and `country` strings.
- `card`: `card_id`, `pin_locked`, `pin_lock_reason`, `date_issued`, `daily_atm_limit`, and `prior_pin_locks_90d`.
- `account`: `date_opened` and numeric `balance`.
- `all_cards`: cards on the account, with `card_id`, `pin_locked`, `issue_reason`, `date_issued`, `velocity_blocked`, and `fraud_alert_active` where known.
- `declines`: relevant declined attempts, each with ISO `timestamp`, numeric `amount`, and location fields (`city`, `state`, `country`).
- `successes`: successful transactions with ISO `timestamp`, location fields, and `pin_used` when known.
- `recent_successful_atm_withdrawals`: numeric amounts, or transaction objects containing numeric `amount`.
- `overdraft_fee_count`: non-negative integer.
- Optional `exclude_flags`: flag IDs established as customer-confirmed under the questions below. Allowed values are `A1`, `A2`, `A3`, `B1`, and `C1`.

The result contains `flags`, `total_score`, `risk_level`, `single_flag_escalation`, `automatic_triggers`, `missing_inputs`, `questions`, and `recommended_protocol`. It is internal work product. Review `missing_inputs`: a nonempty list means the recommendation is provisional and an unlock decision must not be finalized until the relevant facts are obtained or security takes over.

The helper consistently applies these protocol rules:

- location mismatch and time-of-day use the highest-risk relevant decline;
- location scatter counts distinct normalized decline locations;
- travel conflict compares the prior seven days of successful transaction locations with the home city;
- velocity uses the shortest interval between successive declined attempts;
- amount pattern examines declines in chronological order, round-number testing requires every attempt to be an exact hundred, ATM-history comparison uses the largest attempted amount, and the limit test includes both the largest attempt ratio and aggregate attempted total;
- all 3-point flags require supervisor review regardless of total; and
- unknown data is reported rather than silently scored as zero.

## Customer-safe verification questions and recalculation

For a score of 5 or more, ask only the questions associated with flags actually present. Do not tell the customer the score or points.

- Location concern: “I see your card was locked after failed PIN attempts at [location]. Were you at that location?” If yes, rescore excluding `A1`, `A2`, and `A3`. If no, retain the flags.
- Decreasing-amount concern: “The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?” If confirmed, rescore excluding `C1`; otherwise retain it.
- Overnight concern of 2+ points: “These attempts occurred at [time]. Were you trying to use your card at that time?” If confirmed, rescore excluding `B1`. If the customer says they were asleep or gives an equivalent denial, treat it as a critical fraud concern: do not unlock, check for unauthorized successes, and transfer to security.

For a high-risk result, obtain confirmation and a satisfactory explanation for the suspicious location/time facts before any eligible unlock. For any claim that attempts or successful transactions were not the customer’s, preserve that report and follow the unauthorized-transaction/dispute and card-protection procedures; do not treat it as an explanation supporting unlock.

## Outcome handling

Use the final complete assessment, including required confirmation/recalculation, as follows:

| Result | Required handling |
|---|---|
| 0–4 low | After standard identity/ownership verification, an authorized PIN-unlock capability may be used if actually available and no trigger blocks it. |
| 5–7 medium | Ask the failed-attempt ownership question and only proceed after the customer’s response supports it. |
| 8–10 high | Ask specific location/time questions. Unlock only after confirmation and a satisfactory explanation, plus all prerequisites. |
| 11–14 very high | Do not unlock in the interaction. Require callback verification or enhanced verification (last four SSN plus a security question). |
| 15+ critical | Never unlock. Check suspicious-period successful transactions, recommend closure/replacement when fraud is suspected, and transfer to security. |
| Any 3-point flag | Escalate for supervisor review regardless of total. Do not bypass the applicable threshold restrictions. |
| 3+ prior PIN locks in 90 days | Do not unlock; a PIN reset is required. |

When an eligible unlock is completed through a genuinely available authorized facility, apply the lock-frequency follow-up: no extra step for zero prior locks; offer PIN-lock notifications after one; after two, offer a PIN reset because this is the third lock in 90 days. Do not claim an unlock succeeded without a successful tool result.

For a required PIN reset, verify identity and ownership, confirm that the card is ACTIVE, confirm its last four digits, collect a compliant new four-digit PIN without reading it back, and use the documented reset capability `reset_debit_card_pin_6284` with `card_id`, `last_4_digits`, and `new_pin`. Reject sequential PINs, repeated-digit PINs, and PINs based on the customer’s birth year or month/day.

If an unlock is prohibited or fraud is suspected, review for successful unauthorized transactions during the suspicious period. If found, begin the appropriate dispute process and arrange closure/replacement under the applicable prerequisites. If none are found, explain only that a security review is needed and offer permitted options: security-team investigation, PIN reset when appropriate, or closure/replacement when fraud is suspected. Use human-transfer reason `fraud_or_security_concern` for fraud/security escalation and include a concise internal summary without exposing the score to the customer.

## Validation checklist

Before any card-changing action, confirm all are true:

1. Identity verification was completed and logged; caller authority, card ownership, and linked OPEN checking account were verified.
2. Every PIN-locked card on the account was identified and assessed separately.
3. Security-hold, multiple-locked-card, and recent-stolen-replacement triggers were checked.
4. Declines, successes, ATM history, card/account age, lock history, other-card flags, overdrafts, balance, and daily ATM limit were either assessed or explicitly listed as unresolved.
5. The risk outcome, all 3-point flags, required customer answers, and any mandatory enhanced/supervisor/security review were honored.
6. The selected action is a documented action for the card’s status and no fraud-alert clearing action was used as a PIN unlock substitute.
7. For a reset, ACTIVE status, last four digits, and new-PIN requirements were confirmed. For closure, dispute, replacement, or transfer, complete that procedure’s separate prerequisites.
