---
name: debit-card-pin-lock-investigation
description: Investigate one or more PIN-locked debit cards before any unlock. Use for customers reporting PIN lockouts, incorrect-PIN declines, or PIN-tries-exceeded declines. It guides identity verification, card-by-card fraud assessment, safe escalation, customer questioning, and eligible unlock/PIN-reset/closure follow-up.
---

# Debit Card PIN-Lock Investigation

Use this Skill when a debit card is PIN-locked or a PIN-related decline may require an unlock. Do not simply unlock a card after a customer reports a forgotten or failed PIN.

## Required banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A lookup result, a known email address, and a card last-four supplied before verification are not by themselves completed identity verification. Confirm two of the four identity fields (date of birth, email, phone number, address), then call `log_verification` with the complete user record and a current timestamp before an unlock, PIN reset, closure, dispute, or other account-changing action.

## Runtime data and tool plan

1. Resolve the customer record using an available user lookup. Obtain the current timestamp with `get_current_time` when logging verification.
2. After identity verification, call `get_all_user_accounts_by_user_id_3847(user_id)`. Identify the relevant checking account(s), including the account the customer calls their primary or product-named account.
3. For **every** relevant checking account, call `get_debit_cards_by_account_id_7823(account_id)`. Retain each card's ID, last four, status, issue reason, issued date, and ATM limit. Also retain PIN-lock fields if returned.
4. Call `get_bank_account_transactions_9173(account_id)` for each relevant account. Preserve the transaction date/time if supplied, description/location, amount, type, and status. Review declined PIN attempts (`atm_withdrawal_declined` or `pos_declined`) and successful activity. Also identify overdraft fees and potential unauthorized successful transactions.
5. Assess each PIN-locked card separately using the protocol below. When multiple cards are locked, finish every card's investigation before unlocking any card.

The supplied `scripts/risk_score.py` is an internal calculation aid. It does not retrieve data, verify identity, identify a cardholder, unlock a card, transfer a customer, file a dispute, close a card, or reset a PIN. Do not expose its flag-by-flag calculations or numerical score to the customer.

## Immediate escalation screen

Perform this screen for every card before considering an unlock:

- If `pin_lock_reason` is `security_hold`, do not unlock the card in chat. Offer transfer to the security team.
- If another card on the same account is PIN-locked, complete the investigation of all affected cards before any unlock. Their outcomes may differ.
- If any card on the account was replaced within the past 90 days with `issue_reason = stolen`, require enhanced verification.

A current card with three or more prior PIN locks in the past 90 days requires a PIN reset and cannot be unlocked. A single 3-point risk flag requires supervisor review regardless of the total.

## Fraud-risk assessment

Build a structured input from the retrieved records and run the calculator once per locked card. Example runnable invocation (replace all placeholder values with live retrieved data):

```sh
python3 scripts/risk_score.py <<'JSON'
{
  "now": "2025-01-15T12:00:00-05:00",
  "customer": {
    "address_city": "Home city",
    "address_state": "ST",
    "address_country": "US",
    "account_opened": "2023-01-15",
    "current_balance": 600,
    "overdraft_count": 0
  },
  "card": {
    "date_issued": "2024-01-15",
    "daily_atm_limit": 500,
    "pin_lock_reason": null,
    "prior_locks_90d": 0
  },
  "account_cards": [],
  "declined_attempts": [],
  "successful_transactions_7d": [],
  "successful_pin_uses": [],
  "successful_atm_withdrawals": []
}
JSON
```

### Calculator input/output contract

The script reads one JSON object from standard input and writes one JSON object to standard output.

- `now` is an ISO-8601 timestamp or date.
- `customer` supplies home location, account opening date, current balance, and count of recent overdraft fees.
- `card` supplies issuance date, daily ATM limit, PIN lock reason, and number of **prior** locks in the last 90 days.
- `account_cards` supplies all cards on the account, including `card_id`, `pin_locked`, `issue_reason`, and `date_issued` where known.
- Each declined attempt may include `timestamp`, `amount`, `city`, `state`, and `country`. Preserve chronological order when it is known; the script sorts timestamped attempts for velocity and amount-pattern checks.
- `successful_transactions_7d` may include a `city`; `successful_pin_uses` needs a timestamp; and `successful_atm_withdrawals` needs an amount.
- Optional `confirmed_location_attempts_mine`, `confirmed_amount_pattern_mine`, and `confirmed_time_attempt_mine` model the specific permitted customer confirmations. `customer_was_asleep_at_attempt_time: true` marks the time answer as critical.

The output includes automatic triggers, supported flag results, total score, risk tier, supervisor/escalation markers, and a pre-answer recommended protocol. Missing data is listed as `missing_inputs`; obtain it where available rather than treating unknown data as benign.

Review the returned flags against the actual records. The calculator applies these documented controls: location mismatch/scatter and travel conflict; late-night timing, elapsed time since legitimate PIN use, and failed-attempt velocity; amount sequence, round-hundred testing, amount versus historical ATM average, and amount versus daily ATM limit; lock frequency, card age, other-card security issues; and account age, overdrafts, and balance. It uses the most severe applicable observation within a single flag rather than adding the same flag repeatedly.

## Risk-tier handling and customer conversation

Never reveal the calculations, scores, or internal thresholds to the customer. Explain only the necessary security review in clear language.

- **Low (0–4):** Unlock only after standard identity verification and all prerequisites are met.
- **Medium (5–7):** Before unlock, ask exactly: “I see failed PIN attempts on your card. Were those attempts yours?”
- **High (8–10):** Ask specific location and time questions. Unlock only if the customer confirms and gives a satisfactory explanation.
- **Very high (11–14):** Do not unlock on the call. Require callback verification or enhanced verification using last four SSN plus a security question.
- **Critical (15+):** Do not unlock. Check suspicious-period successful transactions for unauthorized activity; recommend closure and replacement where fraud is suspected.

For scores at least 5, ask only the applicable questions:

- Location: “I see your card was locked after failed PIN attempts at [location from transaction]. Were you at that location?” If confirmed, remove the location flags and recalculate. If denied, retain them.
- Decreasing amount pattern: “The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?” If confirmed, remove the amount-pattern flag and recalculate; otherwise retain it.
- Time of day scoring 2 or more: “These attempts occurred at [time]. Were you trying to use your card at that time?” If confirmed, remove the time-of-day flag and recalculate. If the customer says they were asleep or equivalent, treat the event as critical suspected fraud and do not unlock.

Customer recognition of one attempted purchase is not a blanket confirmation for other cards or other attempts. Keep the review card-specific.

## Performing an eligible outcome

Before an unlock, reconfirm the verified owner, selected card ID and last four, current card status/eligibility, the completed all-card review, the risk outcome, and any required customer confirmation. Use only the normal banking unlock capability that is actually available in the runtime and its documented parameters. Do not invent an unlock tool name or claim an unlock succeeded without a successful tool result.

After an eligible successful unlock:

- With zero prior locks: no extra step.
- With one prior lock: offer, “Would you like me to enable PIN lock notifications so you're alerted if this happens again?”
- With two prior locks: ask, “This is your third PIN lock in 90 days. Would you like me to reset your PIN to a new number? Frequent locks sometimes indicate the current PIN is difficult to remember.”
- With three or more prior locks: do not unlock; proceed with a PIN reset instead.

For a required PIN reset, verify the owner and that the card is ACTIVE, confirm the card last four, obtain a new four-digit PIN, and validate that it is neither sequential, all identical digits, nor the customer's birth year or birth month/day. Then use `reset_debit_card_pin_6284(card_id, last_4_digits, new_pin)` and do not repeat or display the PIN.

For a cannot-unlock outcome, inspect successful transactions during the suspicious period. If the customer identifies unauthorized transactions, gather the transaction date, amount, and merchant/ATM details and follow the available dispute process; advise prompt reporting. When appropriate, discuss closure/replacement or transfer to the security team. Card closure requires verified ownership, eligible ACTIVE or PENDING status, review of pending transactions/refunds, the closure reason, and the normal documented closure process. Do not close a card merely because the risk score is elevated without confirming the customer's requested/approved resolution and all closure prerequisites.

## Validation checklist

Before completing the case, verify that:

1. Identity verification was logged before every banking action.
2. All cards on the relevant account were retrieved and each PIN-locked card received its own assessment.
3. Security-hold, other-locked-card, recent-stolen-replacement, 3-point-flag, and frequent-lock rules were applied.
4. The account transactions, ATM limit, dates, locations, and other-card issues used in the decision came from retrieved records, not assumptions.
5. Required questions were asked and any permitted flag removal was recalculated.
6. No internal score or calculation was disclosed.
7. Any actual action has a successful normal-tool result and the customer was told the accurate outcome.
