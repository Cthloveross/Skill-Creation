---
name: pin-lock-fraud-investigation
description: Investigate PIN-locked debit cards before any unlock or PIN-reset decision. Use for debit-card PIN lock/tries-exceeded reports, especially when multiple cards are affected. It provides a complete evidence checklist, internal risk scoring, customer-question workflow, and safe banking-action gates.
---

# PIN Lock Fraud Investigation

Never simply unlock a card reported as PIN-locked. Do not disclose risk-score calculations, individual points, thresholds, or internal fraud rules to the customer.

## Required runtime data and tools

Use the normal banking tools available in the task runtime; do not guess tool names or parameters. The documented card and transaction lookups are:

- `get_debit_cards_by_account_id_7823(account_id)` for every relevant checking account.
- `get_bank_account_transactions_9173(account_id)` for each relevant account.
- `reset_debit_card_pin_6284(card_id, last_4_digits, new_pin)` only when a PIN reset is appropriate and its requirements have been met.

Obtain the customer's checking accounts and the current PIN-lock details through the runtime's supported account/card lookups. A usable assessment needs, per locked card: card/account identity, active status, PIN lock reason, whether it is PIN-locked, issuance date and reason, ATM limit, prior PIN locks in 90 days, and security flags. It also needs account opening date/current balance and transactions, including declined PIN attempts, successful ATM/PIN use, and overdraft fees. Treat unavailable fields as **unknown**, not benign.

## Investigation workflow

1. **Identify and verify.** Locate the customer and all of their checking accounts and debit-card history. Before an action that changes card access or a PIN, verify identity using two of the four required identity fields, get the current timestamp, and create the required verification log. Do not expose stored identity values as prompts; ask the customer to provide them.
2. **Inventory every locked card.** Check all debit cards across the customer's relevant checking accounts, including prior/replacement cards as needed to determine issuance history. If another card is PIN-locked, do not unlock any one card until every locked card has been investigated and individually assessed.
3. **Apply immediate escalation rules.**
   - A `security_hold` lock cannot be unlocked by chat; offer transfer to the security team for that card.
   - If any card was replaced for `stolen` within the prior 90 days, require enhanced verification before proceeding.
   - Multiple locked cards require completion of every card investigation before any unlock.
4. **Collect evidence.** Retrieve transaction histories for the relevant accounts. Isolate declined ATM/POS PIN attempts and recent successful activity. Preserve the transaction descriptions/timestamps for location and time questions. Review other cards for velocity blocks and active fraud alerts. Check the suspicious period for successful transactions the customer says were unauthorized.
5. **Score each locked card internally.** Normalize the gathered facts and run `scripts/score_pin_lock_risk.py`. The script reports missing evidence rather than treating it as zero. Resolve material missing evidence before an unlock decision. Review its flag results and decision gates; it is an internal aid, not a substitute for the protocol.
6. **Ask only required, targeted questions.** For a medium-or-higher complete assessment, ask whether the failed attempts were the customer's. If location is scored, ask whether they were at the recorded location. If decreasing amount pattern is scored, ask whether they remember the listed attempted amounts. If the time flag is at least two points, ask whether they were using the card at that time. Do not state scores or fraud conclusions. Record answers and rerun the assessment after a confirmed explanation removes an allowed flag. If the customer denies an attempt, is confused, or says they were asleep during a suspicious attempt, retain/escalate the concern; do not unlock merely because they request it.
7. **Make the permitted decision.**
   - Low (0–4): unlock only after standard identity verification.
   - Medium (5–7): unlock only after asking whether the failed PIN attempts were theirs.
   - High (8–10): ask the location/time questions indicated by flags; unlock only with confirmation and a satisfactory explanation.
   - Very high (11–14): do not unlock on this interaction; require callback verification or enhanced verification (last four SSN plus a security question).
   - Critical (15+): do not unlock; investigate unauthorized successful transactions and recommend closure/replacement where fraud is suspected.
   - Any single three-point flag requires supervisor review regardless of total. Three or more prior locks in 90 days requires PIN reset and cannot be handled as an unlock.
8. **If access cannot be restored.** Check for successful unauthorized transactions in the suspicious period. If found, follow the supported dispute, closure, and replacement processes. If none are found, explain a security review is needed and offer the applicable supported options: security-team transfer, closure/replacement, or PIN reset. Use `transfer_to_human_agents` with `fraud_or_security_concern` when a security-team/supervisor handoff is needed and summarize completed investigation steps without revealing scoring details.
9. **Perform an allowed action only with a documented runtime action.** Use the runtime's approved unlock action only after all gates above have passed. Do not fabricate an unlock tool. For reset, require verified ownership, ACTIVE status, customer confirmation of the card last four digits, and a new PIN that is exactly four digits, nonsequential, not all identical, and not a birth year or birth month/day. Never repeat or display a PIN.
10. **Post-unlock follow-up.** With one prior lock in 90 days, offer PIN-lock notifications. With two prior locks, offer a PIN reset because this is the third lock in 90 days. With zero prior locks, no additional step is required.

## Scoring helper

Run with JSON on standard input and JSON on standard output:

```bash
python3 scripts/score_pin_lock_risk.py <<'JSON'
{
  "now": "2025-01-01T12:00:00-05:00",
  "home": {"city": "...", "state": "...", "country": "..."},
  "declines": [{"timestamp": "...", "location": {"city": "...", "state": "...", "country": "..."}, "amount": 0}],
  "successful_transactions_last_7_days": [{"location": {"city": "...", "state": "...", "country": "..."}}],
  "last_legitimate_pin_use": "...",
  "successful_atm_amounts": [0],
  "daily_atm_limit": 0,
  "prior_locks_90d": 0,
  "card_active_since": "...",
  "other_cards": [{"velocity_block": false, "fraud_alert": false}],
  "account_opened": "...",
  "overdraft_fee_count": 0,
  "current_balance": 0
}
JSON
```

`declines` must contain only relevant declined ATM/POS PIN attempts, in chronological order (the helper sorts them). Locations should be parsed/confirmed before use; do not infer a city from an ambiguous description. Dates may be ISO-8601 or `MM/DD/YYYY`. Output contains `flags`, `total`, `risk_level`, `single_flag_escalation`, `missing`, and `decision_gates`. A nonempty `missing` list means the total is incomplete and cannot support an unlock.

## Validation

Before relying on helper output, ensure (a) every decline has a timestamp, amount, and sufficiently resolved location, (b) ATM average uses successful ATM withdrawals rather than all purchases, (c) transaction timestamps use a consistent timezone, (d) the selected card's daily ATM limit and lock history are used, and (e) all other cards were reviewed. Re-run after material customer answers, and retain only the customer-safe conclusion in the response.