---
name: pin-lock-fraud-investigation
description: Investigate one or more PIN-locked debit cards before any unlock. Use for PIN decline codes 55 or 75, or whenever a customer reports a locked debit-card PIN. It enforces card-by-card fraud review, account-wide escalation checks, identity verification, and safe next steps without disclosing fraud-score calculations.
---

# PIN-Lock Fraud Investigation

## Purpose and boundaries

A PIN-locked card must **never** be unlocked solely because the customer asks. Perform the fraud-risk assessment for every affected card. Do not reveal the point values, score, individual calculations, or internal fraud thresholds to the customer.

The workflow supports a customer who does not know a card's last four digits: identify the customer and their checking account(s), then retrieve all debit cards for those accounts. Do not ask repeatedly for information that can be obtained from authorized internal records.

This Skill does not invent banking tool names or cause banking actions itself. Use only tools actually supplied by the runtime or explicitly documented below. If the required account/card data or a required operational action is unavailable, do not claim that an unlock, reset, dispute, closure, or replacement occurred; transfer to the security team when investigation cannot safely continue.

## Runtime inputs and tool usage

Use the conversation and prior observations as context, but refresh data needed for a decision.

1. Locate the customer using a unique supplied profile identifier (such as their exact name or email) with the corresponding available user lookup. Confirm the returned record matches the customer before continuing.
2. Obtain each linked checking-account ID using an authorized account lookup available in the runtime. This Skill does not prescribe an undocumented lookup name.
3. Unlock and call the documented debit-card lookup if it is not already available:
   - `unlock_discoverable_agent_tool(agent_tool_name="get_debit_cards_by_account_id_7823")`
   - `call_discoverable_agent_tool(agent_tool_name="get_debit_cards_by_account_id_7823", arguments='{"account_id":"..."}')`
4. Inspect **all** returned current and historical cards. Match a card by account/card context; do not guess based on an unverified last four. Record status, issue reason, issued date, daily ATM limit, PIN-lock fields if returned, and any fraud-alert or velocity-block fields.
5. Retrieve, through supplied authorized tools, the linked account status/open date/current balance; debit-card transaction history; PIN-lock history; and all card-security indicators. Restrict transaction analysis to the target card and relevant recent time periods. If those data cannot be retrieved, the review is incomplete.

The debit-card lookup requires a checking-account ID and can return multiple historical cards. A card that was replaced for `stolen` within 90 days is an account-wide escalation condition. A card must be ACTIVE before a PIN reset; do not reset a frozen, pending, or closed card.

## Identity verification

Before any unlock, PIN reset, fraud-alert change, or other card action, verify the customer by having them confirm two of the four profile fields: date of birth, email, phone number, and address. Do not read the stored values to the customer as prompts. After two fields match, call `get_current_time` and `log_verification` with the complete returned profile and timestamp. The customer being able to state a name alone is not verification.

## Mandatory account-wide triage

For every account-level review, first check these triggers:

- A target card has `pin_lock_reason = security_hold`: chat must not unlock it. Offer/perform a transfer to the security team using `fraud_or_security_concern`.
- Another card on the same account is PIN locked: investigate **every** locked card individually before any unlock. Do not unlock the first card while other locked cards remain unreviewed.
- Any account card was issued as a stolen replacement in the previous 90 days: enhanced verification is required before an eligible unlock decision.

Also inspect card status, linked-account status, active bank-initiated fraud alerts, and velocity blocks. Never clear a bank-initiated fraud alert; transfer to security. Do not expose a suspended or restricted account's details. A velocity block may be handled only according to an actually available, authorized workflow after identity verification.

## Build one assessment per card

Gather the following normalized facts per card. Use the reference timestamp and the customer's address city/state/country for comparisons.

- Declined ATM withdrawal or POS attempts: timestamp, location city/state/country, amount, and description.
- Successful activity in the previous seven days and the latest successful PIN use.
- Recent successful ATM withdrawal amounts.
- Current card's prior PIN-lock count in the prior 90 days; issue/active date; daily ATM limit.
- Other cards' PIN-lock, velocity-block, and fraud-alert states.
- Account open date, current balance, and recent overdraft-fee count.

Call the included calculator once all fields are available. It accepts only normalized facts and returns an internal result. It deliberately returns `assessment_incomplete` when required fraud inputs are missing; do not convert a partial score into an unlock decision.

```text
python3 scripts/assess_pin_lock.py <<'JSON'
{
  "reference_time": "2025-01-31T15:00:00-05:00",
  "home_location": {"city":"Example City","state":"EX","country":"US"},
  "card": {
    "status":"ACTIVE", "pin_locked":true, "pin_lock_reason":"incorrect_pin",
    "date_issued":"2024-01-01", "daily_atm_limit":500,
    "prior_pin_locks_90d":0
  },
  "account": {"opened_at":"2020-01-01", "current_balance":600, "overdraft_count":0},
  "declines": [{"timestamp":"2025-01-31T14:30:00-05:00", "city":"Example City", "state":"EX", "country":"US", "amount":20}],
  "successful_pin_use_at":"2025-01-30T10:00:00-05:00",
  "successful_last_7_locations":[{"city":"Example City","state":"EX","country":"US"}],
  "successful_atm_amounts":[20,40],
  "other_cards":[{"pin_locked":false,"velocity_blocked":false,"fraud_alert_active":false,"issue_reason":"new_account","date_issued":"2024-01-01"}],
  "confirmations": {"location_confirmed":false,"amount_pattern_confirmed":false,"time_confirmed":false,"customer_was_asleep":false}
}
JSON
```

Input and output are JSON on stdin/stdout. Dates/timestamps must be ISO-8601. Currency values are numeric in dollars. The calculator is a decision aid, not an authorization tool; review its `missing_inputs`, `automatic_triggers`, `flags`, and `decision` before acting.

## Interpret the assessment and converse safely

1. If the assessment is incomplete, collect the missing internal facts or transfer to security rather than unlock.
2. Any three-point flag requires supervisor/security review regardless of total. Three or more previous locks also means the PIN cannot be unlocked and must be reset through an authorized reset process after required verification.
3. Apply the risk outcome:
   - **0–4:** unlock only after standard identity verification and all account-wide reviews are complete.
   - **5–7:** ask: “I see failed PIN attempts on your card. Were those attempts yours?” Unlock only after the response and verification support it.
   - **8–10:** ask the targeted location/time questions below. Unlock only if the customer confirms and gives a satisfactory explanation.
   - **11–14:** do not unlock on this contact. Require callback verification or enhanced verification (last four SSN plus a security question) under the available security process.
   - **15+:** do not unlock. Check for successful unauthorized transactions during the suspicious period; if present, file the appropriate dispute and arrange closure/replacement through authorized tools. Otherwise recommend replacement, security investigation, or PIN reset.
4. For a score of 5 or more, ask only questions tied to scored flags:
   - Location: “I see your card was locked after failed PIN attempts at [location]. Were you at that location?” A yes removes the location flags and requires recalculation; a no keeps them.
   - Decreasing amount pattern: “The attempts were for [amounts]. Do you remember trying those specific amounts?” Confirmation removes that pattern flag and requires recalculation.
   - Time flag of 2 or more: “These attempts occurred at [time]. Were you trying to use your card at that time?” A confirmed answer removes the time flag and requires recalculation. If the customer says they were asleep or equivalent, treat it as critical suspected fraud; do not unlock and transfer/security-escalate.
5. After any changed answer, update `confirmations` and recalculate before deciding. Never reveal the numerical recalculation.

When an eligible unlock is completed using an authorized runtime action, confirm only that it is available again. With one prior lock, offer PIN-lock notifications. With two prior locks, offer a PIN reset because this is the third lock in 90 days. With three or more, do not unlock; use the approved PIN-reset workflow instead.

For a reset, confirm card ownership, ACTIVE status, last four digits, and a compliant new four-digit PIN. It cannot be sequential, all one digit, or based on birth year/month-day. Use `reset_debit_card_pin_6284` only if it is provided by the runtime, with `card_id`, `last_4_digits`, and `new_pin`; never repeat or display the PIN in the response.

For any security transfer, summarize the card(s) reviewed, relevant non-sensitive observations, completed verification, and why an unlock was not authorized. Use `transfer_to_human_agents` with reason `fraud_or_security_concern`.
