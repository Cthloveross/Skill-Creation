---
name: debit-card-pin-lock-investigation
description: Investigate debit cards reported PIN-locked after PIN-related declines. Use for a verified cardholder requesting a PIN unlock, PIN reset, or fraud-safe resolution of a PIN lock. It retrieves all relevant accounts, cards, and transactions; applies the PIN-lock fraud-risk protocol to every locked card; and directs eligible unlocks, PIN resets, disputes, replacement, or security escalation.
---

# Debit Card PIN-Lock Investigation

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow when a debit-card decline is PIN-related (including codes 55 or 75) and `pin_locked` is true. Do not simply unlock a card. Do not disclose fraud-score calculations, internal flags, or internal decline-code reasoning to the customer.

Treat each locked card separately. If the customer reports several locked cards, retrieve and investigate all of them before permitting an unlock on any one card. A card can have a different result from the others.

Use normal banking tools; scripts in this package only calculate and organize an assessment. They do not unlock cards, clear fraud alerts, file disputes, reset PINs, close cards, order replacements, or transfer customers.

## Required information and tool workflow

1. **Verify identity and authority before any banking action.** Obtain and match at least two of the four identity fields (date of birth, email, phone number, address) against the customer record. Confirm the caller is the cardholder/authorized owner. Get the current time and call `log_verification` with every required verified-record field.
2. Retrieve accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. Identify OPEN checking accounts and their balance, opening date, and account class/tier where returned.
3. For every relevant checking account, retrieve all card history with `get_debit_cards_by_account_id_7823(account_id)`. Identify the specific card(s), confirm ownership, linked account, status, daily ATM limit, issuance date, and all available security/PIN fields. Do not infer a card identifier from a nickname or account balance.
4. Retrieve transaction history for every linked checking account with `get_bank_account_transactions_9173(account_id)`. Preserve transaction IDs, timestamps/dates, descriptions, amounts, types, and statuses. If transaction dates lack a time, do not invent one; record the related time flag as unavailable and obtain details or escalate as needed.
5. Read all returned card records, including historical/replacement cards, to identify other currently PIN-locked cards, cards replaced for `stolen` within 90 days, prior PIN locks if supplied, velocity blocks, and fraud alerts. If needed fields are unavailable from the documented lookup, do not guess: obtain them from the authorized card-data workflow or escalate for investigation.
6. Supply normalized, factual data to `scripts/assess_pin_lock.py`. See the schema below. Review its missing-data output rather than treating missing fields as zero risk.

## Mandatory escalation checks (before scoring)

For each card, apply these checks first:

- `pin_lock_reason == security_hold`: chat agents must not unlock it. Offer transfer to the security team.
- Any other card on the account has `pin_locked == true`: complete investigation and individual scoring for all affected cards before an unlock decision on any card.
- Any account card was replaced in the preceding 90 days with `issue_reason == stolen`: require enhanced verification before an unlock decision.

Also do not confuse a PIN lock with a distinct card condition. A bank-initiated fraud alert cannot be cleared by chat agents and requires security-team transfer. A velocity block can only be cleared after identity verification using `clear_debit_card_fraud_alert_4892(card_id, reason='velocity_clear')`; it is not a PIN unlock. A FROZEN card follows the separate unfreeze procedure and requires an OPEN linked account.

## Scoring and decision

For a card with no blocking automatic escalation, calculate flags from its declined PIN attempts (`atm_withdrawal_declined` and `pos_declined`) and relevant card/account history. Use the packaged script to make the arithmetic repeatable. The assessment must cover:

- location mismatch against the customer address city/state/country; location scatter; and seven-day successful-transaction travel conflict;
- declined-attempt time of day, last legitimate successful PIN use, and failure velocity;
- consecutive-attempt amount pattern, round-hundred testing, amount versus recent successful ATM average, and amount versus daily ATM limit;
- prior PIN-lock frequency in 90 days, card age, and other-card velocity/fraud issues;
- account age, recent overdraft fees, and balance.

Use the stated threshold outcome after customer-confirmation adjustments:

| Score | Required outcome |
|---|---|
| 0–4 | Unlock only after standard identity verification. |
| 5–7 | Ask whether the failed PIN attempts were theirs; unlock only after the required confirmation. |
| 8–10 | Ask location and time questions; unlock only if the customer confirms and gives a satisfactory explanation. |
| 11–14 | Do not unlock in this interaction; require callback verification or enhanced verification (last four SSN plus security question). |
| 15+ | Do not unlock; check for successful unauthorized activity and recommend closure/replacement. |

A 3-point individual flag always requires supervisor review, regardless of total. Three or more prior locks in 90 days requires PIN reset and cannot be resolved by unlock. A customer statement can remove only the documented flag: confirmation of being at the declined location removes location flags; confirmation of the listed decreasing amounts removes the amount-pattern flag; confirmation of the relevant time removes a time-of-day flag. If the customer says they were asleep at a time-of-day flag worth at least 2 points, treat it as a critical fraud indication and do not unlock.

Ask customer-facing questions without exposing scores or calculations:

- Location: “I see failed PIN attempts at [location]. Were you at that location?”
- Decreasing amounts: “The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?”
- Late-night timing: “These attempts occurred at [time]. Were you trying to use your card at that time?”

Re-run the script with `confirmed_location`, `confirmed_amount_pattern`, or `confirmed_time` where applicable. Record the customer’s answer and explanation.

## Completing the outcome

Before invoking any action, reconfirm the verified owner, target `card_id`, card/account eligibility, card status, linked OPEN checking account where applicable, and user confirmation.

- If the outcome permits unlock, use only the normal authorized PIN-unlock capability available to the execution agent. This package does not name or invent an unlock tool. If no authorized unlock capability is available, explain that completion requires the appropriate banking/security channel rather than claiming an unlock.
- After an eligible unlock: with one prior lock, offer PIN-lock notifications; with two prior locks, offer PIN reset because this is the third lock in 90 days. With three or more prior locks, perform the PIN-reset route instead of unlock.
- For a PIN reset, require verified identity, ownership, ACTIVE card status, confirmation of the card’s last four digits, and a new four-digit PIN that is not sequential, all identical, the customer’s birth year, or birth month/day. Use `reset_debit_card_pin_6284(card_id, last_4_digits, new_pin)` only after these checks. Never display or read back the PIN.
- When unlock is prohibited or fraud remains suspected, inspect the suspicious period for successful unauthorized transactions. If any are identified, gather dispute prerequisites and file the appropriate dispute, then close/reissue as required by the dispute category. If none are found, explain only the security concern and offer replacement, security-team investigation, or PIN reset as applicable.
- For a security transfer, use `transfer_to_human_agents` with `reason='fraud_or_security_concern'` and a concise factual summary. Do not assert fraud to the customer merely because internal risk signals are present.

## Assessment script

Run `scripts/assess_pin_lock.py` with JSON on stdin. Dates/times must be ISO-8601 timestamps where time-dependent scoring is requested. Amounts can be signed transaction values; the script uses absolute values for withdrawal/attempt comparisons.

```json
{
  "now": "2025-01-15T12:00:00-05:00",
  "customer_address": {"city": "Boston", "state": "MA", "country": "US"},
  "card": {
    "card_id": "runtime-card-id",
    "pin_locked": true,
    "pin_lock_reason": "incorrect_pin",
    "date_issued": "2024-07-01",
    "daily_atm_limit": 500,
    "prior_pin_locks_90d": 0
  },
  "all_cards": [],
  "account": {"date_opened": "2022-01-01", "balance": 900},
  "declined_attempts": [],
  "successful_transactions": [],
  "recent_transactions": [],
  "confirmed_location": false,
  "confirmed_amount_pattern": false,
  "confirmed_time": false,
  "customer_said_asleep": false
}
```

`declined_attempts` records use `timestamp`, `amount`, `type`, `city`, `state`, and `country`. `successful_transactions` may include `timestamp`, `amount`, `type`, `city`, `state`, `country`, and `pin_used`; use `pin_used: true` for the last successful PIN use. `recent_transactions` may include `timestamp`, `type`, `amount`, and `status`; use type `overdraft_fee` for overdraft scoring. `all_cards` can include `card_id`, `pin_locked`, `issue_reason`, `date_issued`, `velocity_blocked`, and `fraud_alert_active`.

The script emits JSON containing `automatic_triggers`, individual `flags`, `raw_score`, `adjusted_score`, `risk_level`, `required_protocol`, `supervisor_review`, `cannot_unlock`, `required_questions`, and `missing_data`. Validate that the target is PIN-locked, that identifiers and linked account facts were retrieved from tools, that automatic triggers have been resolved, and that `missing_data` is empty or has been explicitly handled before relying on an unlock decision.
