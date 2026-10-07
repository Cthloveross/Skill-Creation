---
name: pin-lock-fraud-investigation
description: Investigate one or more PIN-locked debit cards before any unlock. Use for debit-card PIN lock/decline requests requiring identity verification, account/card/transaction retrieval, fraud-risk scoring, customer questions, escalation, or PIN reset guidance.
---

# PIN-Lock Fraud Investigation

Use this workflow for each PIN-locked debit card. Never unlock merely because the customer says the attempts were theirs, and never disclose the fraud score, point values, or calculation mechanics to the customer.

## Mandatory banking controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

In particular, before retrievals or a card action:

1. Identify the customer and obtain confirmation of at least two profile fields among date of birth, email, phone number, and address.
2. Retrieve the profile by the supplied identifier and ensure the confirmations match one and only one record.
3. Get the current timestamp and call `log_verification` with the complete returned profile and that timestamp after the two-field verification succeeds.
4. Establish that the customer owns the account and that the investigated card's `user_id` matches the verified user. Do not act on another person's card.
5. Treat card IDs, last four digits, account IDs, PINs, and transaction details as sensitive. Do not ask for or repeat a full card number or an existing PIN.

If verification, ownership, required information, or an applicable prerequisite cannot be established, do not unlock. Explain the limitation without exposing internal scoring and, for a fraud/security investigation that needs specialist handling, transfer with reason `fraud_or_security_concern`.

## Available records and tool use

Unlock the documented agent tools before calling them, then use their exact documented parameters:

- `get_all_user_accounts_by_user_id_3847(user_id)` for all checking/savings accounts, their status, balance, and opening date.
- `get_debit_cards_by_account_id_7823(account_id)` for every card associated with each checking account, including historical cards, issuance date, status, last four digits, and ATM limit.
- `get_bank_account_transactions_9173(account_id)` for each investigated account's transaction history.

The card lookup may expose PIN-lock fields needed by the PIN-decline workflow (such as `pin_locked`, remaining attempts, and lock reason) in addition to the documented fields. Inspect actual returned fields rather than assuming a field is present. Transaction descriptions may be needed to identify ATM/merchant location; retain the original record when normalizing it for assessment.

If a required tool is unavailable, returns an error, or lacks data necessary to make a safe unlock decision, do not substitute guesses or treat it as a zero-risk result. Escalate the security concern.

## End-to-end procedure

1. **Scope all cards first.** Retrieve all customer accounts, then cards for every checking account. Match the customer’s description of the target account/card using information they can provide. For every currently PIN-locked card, record its linked account, status, issuance information, limit, lock reason if available, and whether it is owned by the verified user.
2. **Investigate card by card.** A customer with several locked cards must receive a separate investigation and outcome for every card. A lock on another card *on the same account* means all cards on that account must be investigated before any is unlocked.
3. **Check automatic escalation conditions before scoring a card.**
   - `pin_lock_reason == security_hold`: chat must not unlock it; offer/perform a security-team transfer.
   - Another card on the same account is PIN locked: finish the investigations for all cards on that account before an unlock decision.
   - Any account card was issued as a replacement for `stolen` within the preceding 90 days: require enhanced verification before any further eligible outcome.
   A security hold is a no-unlock outcome. Do not bypass it with a PIN reset or ordinary unlock.
4. **Collect evidence.** For the target account, retrieve transactions and identify declined PIN attempts (`atm_withdrawal_declined` or `pos_declined` when such types are supplied), successful recent ATM withdrawals, successful transactions in the past seven days, overdraft fees, and any suspicious successful transactions in the relevant period. Determine current account balance from account lookup. Determine prior PIN locks, other-card velocity blocks/fraud alerts, and last legitimate PIN use only from returned records or an authoritative source. Do not infer these facts from missing data.
5. **Normalize and score.** Supply normalized facts to `scripts/risk_assessor.py` or calculate the same rules below. Preserve an `unknown` result for every unavailable fact. An incomplete assessment is not an unlock approval.
6. **Apply the outcome and customer questions** below. If customer answers change an eligible flag, rerun the assessment and retain the evidence/audit trail. Never reveal the numeric score or flag arithmetic.
7. **Perform an action only when permitted and an actual documented/unlocked tool is available.** The supplied documentation does not name an ordinary card-unlock action. Do not invent a tool name or simulate an unlock. If the decision allows an unlock but no authorized unlock tool is available, transfer to the security team with `fraud_or_security_concern` and summarize the completed verified investigation.

## Scoring rules

Score only evidence that can be substantiated. For flags that can occur across several attempts, use the highest applicable risk value unless the rule explicitly uses all attempts or a total. Dates/times must be interpreted in the transaction’s stated timezone; do not manufacture a time from a date-only record.

- **A1 location mismatch:** compare each decline location with the customer address: same city 0; different city in same state 1; different state 2; different country 3.
- **A2 location scatter:** all same 0, two locations 1, three or more 2.
- **A3 travel conflict:** add 1 when successful transactions in the past 7 days are all in the home city and declines are elsewhere; recent genuine multi-city travel is 0.
- **B1 time of day:** 06:00–22:00 0; 22:00–00:00 1; 00:00–02:00 2; 02:00–06:00 3.
- **B2 last legitimate PIN use:** 0 through 7 days, 1 for 7–30 days, 2 for more than 30 days.
- **B3 failed-attempt velocity:** over 5 minutes 0; 2–5 minutes 1; 1–2 minutes 2; under 1 minute 3.
- **C1 amount pattern:** same retried amount or increasing amounts 0; decreasing consecutive amounts 2.
- **C2 round-number testing:** mixed amounts 0; all amounts are round hundreds 1.
- **C3 versus successful ATM average:** use recent successful ATM withdrawals. An attempted amount within 2x average is 0, over 2x through 5x is 1, and over 5x is 2.
- **C4 versus daily ATM limit:** less than or equal to 80% is 0; over 80% through 100% is 1; multiple failed attempts totaling more than the daily limit is 2.
- **D1 prior PIN locks in 90 days:** 0/1/2/3+ prior locks score 0/1/2/3. Three or more requires PIN reset and cannot be ordinarily unlocked.
- **D2 card age:** 0 when at least 3 months old; 1 at 1–3 months; 2 under 1 month.
- **D3 other card issues:** 0 none, 1 another velocity block, 2 another active fraud alert.
- **E1 account age:** 0 at least 6 months; 1 at 3–6 months; 2 under 3 months.
- **E2 overdrafts:** 0 none, 1 one, 2 two or more overdraft fees.
- **E3 balance:** over $100 is 0; $50–$100 is 1; under $50 is 2.

Any single 3-point flag requires supervisor/security review regardless of total. Treat a 3+ D1 result as its independent no-ordinary-unlock requirement. A reported `unknown` must be resolved or escalated; it must not silently reduce the score.

## Decision and conversation rules

Apply these only after automatic triggers, ownership, and data completeness are resolved:

- **0–4:** standard verified unlock may proceed if no single-flag escalation applies.
- **5–7:** ask exactly: “I see failed PIN attempts on your card. Were those attempts yours?” Unlock only after the response supports the request and no other escalation applies.
- **8–10:** ask specific location/time questions for the scored flags. Unlock only when the customer confirms and gives a satisfactory explanation.
- **11–14:** do not unlock in this interaction. Require callback verification or enhanced verification (last four SSN plus a security question) through an authorized process.
- **15+:** do not unlock. Check for successful unauthorized transactions and recommend card closure/replacement.

For scores of 5 or more, ask only applicable documented questions:

- Location: “I see your card was locked after failed PIN attempts at [location from transaction]. Were you at that location?” A yes removes location flags and requires recalculation; a no retains them.
- Decreasing amounts: “The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?” Confirmation removes the amount-pattern flag; denial/confusion retains it.
- Time scored at 2 or 3: “These attempts occurred at [time]. Were you trying to use your card at that time?” Confirmation removes the time flag. If the customer says they were asleep or gives an equivalent denial, treat the concern as critical and escalate.

Use plain security-focused explanations, not score details. Do not claim an unlock, dispute, closure, replacement, or PIN reset occurred until its required tool reports success.

## After an eligible unlock

For zero prior locks, no additional step is required. For one prior lock, offer: “Would you like me to enable PIN lock notifications so you're alerted if this happens again?” For two prior locks, ask: “This is your third PIN lock in 90 days. Would you like me to reset your PIN to a new number? Frequent locks sometimes indicate the current PIN is difficult to remember.” For three or more prior locks, do not unlock; a PIN reset is required.

A reset requires verified identity and ownership, an ACTIVE card, customer confirmation of the card last four digits, and a new PIN that is exactly four digits, not sequential, not all identical, and not a birth year or birth month/day. Only use the documented reset tool `reset_debit_card_pin_6284(card_id, last_4_digits, new_pin)` after those checks.

## Cannot-unlock and suspected-fraud handling

Review the suspicious period for successful unauthorized transactions. If any are identified, follow the authorized dispute and card-closure/replacement processes; a closure must still satisfy its applicable status, pending-transaction/refund, ownership, and confirmation requirements. If no unauthorized success is found, explain the security concern and offer the documented options of PIN reset, security-team investigation, or, when appropriate, closure and replacement. Transfer using `fraud_or_security_concern` whenever specialist fraud/security handling, callback verification, supervisor review, or an unavailable necessary action is required.

## Risk helper

`scripts/risk_assessor.py` reads one JSON object from stdin and writes one JSON object to stdout. It is a deterministic calculator, not authority to act. Required top-level values are `now`, `customer_address`, `card`, `account`, and `declined_transactions`; optional facts may be supplied when known. Dates can be ISO-8601 or `MM/DD/YYYY`. Supply location as explicit `city`, `state`, and `country` fields after reviewing transaction descriptions.

Example input shape:

```json
{
  "now": "2025-01-01T12:00:00-05:00",
  "customer_address": {"city": "Home City", "state": "HS", "country": "US"},
  "card": {"date_issued": "2024-01-01", "daily_atm_limit": 500, "prior_pin_locks_90d": 0},
  "account": {"date_opened": "2020-01-01", "balance": 600},
  "declined_transactions": [],
  "successful_transactions": [],
  "other_cards": [],
  "transactions": []
}
```

The output contains `automatic_triggers`, each scored flag, `total_score`, `single_flag_escalation`, `unknown`, and a baseline `decision`. Validate that all relevant source data was represented, `unknown` is empty before relying on the result, the total equals the sum of the returned flag points, and triggers/escalations have been honored. The executor must still conduct required customer questions and use live banking tools for every action.
