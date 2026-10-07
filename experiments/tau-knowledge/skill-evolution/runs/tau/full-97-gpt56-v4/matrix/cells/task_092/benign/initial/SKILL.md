---
name: pin-lock-fraud-investigation
description: Investigate one or more PIN-locked debit cards before any unlock. Use for debit-card PIN lock/decline requests, particularly when the customer reports unrecognized attempts, multiple locked cards, or potential fraud.
---

# PIN-lock fraud investigation

Use this Skill before unlocking any card with `pin_locked = TRUE` (including PIN decline codes 55 and 75). Treat it as a security workflow, not as a simple PIN-unlock request. Do not disclose fraud-score calculations, point values, thresholds, or internal decision logic to the customer.

## Guardrails

- Do not unlock, reset a PIN, close a card, or file a dispute until the required investigation and identity verification are complete and the applicable tool/action is available.
- A customer profile lookup is **not** identity verification. Obtain confirmation of two of the profile fields (date of birth, email, phone number, and address), compare them with the retrieved record, get the current time, then call `log_verification` with the verified record values and timestamp.
- Never ask the customer to disclose their existing PIN. Never repeat a new PIN back to them.
- Investigate every currently locked card on the account before unlocking any card when more than one card is locked. Score each card independently.
- Do not treat missing evidence as a zero-risk flag. Obtain the missing data using available normal banking tools or escalate for investigation.
- Use only tools that are declared or explicitly unlocked in the current runtime. Do not invent an unlock, dispute, closure, replacement, or PIN-status tool name.

## Runtime data collection

1. Identify the customer from a name or email using the corresponding user lookup. Confirm the intended customer if lookup is ambiguous.
2. Complete standard identity verification before account-changing actions. Log it as described above.
3. Unlock and call these documented lookup tools as needed:
   - `get_all_user_accounts_by_user_id_3847` with `{"user_id": "..."}` to obtain all checking accounts, balances, statuses, and opening dates.
   - `get_debit_cards_by_account_id_7823` with `{"account_id": "..."}` for **every checking account**. Inventory card ID, last four digits, status, issue reason, issue date, and ATM limit.
   - `get_bank_account_transactions_9173` with `{"account_id": "..."}` for each relevant account. Preserve transaction dates/times, type, description, amount, and status.
4. Obtain normal PIN-status/lock-history information if a declared tool provides it. For each active/relevant card, record whether `pin_locked` is true, lock reason, attempts, current lock date, and prior lock dates. The documented card-list response may not contain all of these fields; do not infer them from card status.
5. Build a separate case record per locked card. Associate declines, successful PIN uses, and prior lock events with a particular card only where the data supports the association. If account-level transactions cannot reliably be associated with a card, flag that limitation for security review rather than fabricating a card-level score.

## Automatic triggers (check before scoring)

For each case, first check the following:

1. `pin_lock_reason == "security_hold"`: chat must not unlock this card. Offer/perform security-team escalation.
2. Any other card on the same account is PIN-locked: complete the investigation for all locked cards before any unlock decision.
3. Any account card was replaced within the last 90 days with `issue_reason == "stolen"`: require enhanced verification before an unlock decision.

A security hold, an unrecognized lock attempt, suspected unauthorized activity, unavailable evidence needed to resolve a security case, or a required supervisor/security review should be transferred using `transfer_to_human_agents` with reason `fraud_or_security_concern`. The summary must identify affected card last-four digits when available, all checks performed, the customer’s recognition/denial statement, automatic triggers, and that no unauthorized repeat action was taken.

## Assess every locked card

Review declined records of type `atm_withdrawal_declined` and `pos_declined`, card data, and account history. Work from actual timestamps and descriptions; location and time are not reliably available from a date-only record. Use the protocol’s mutually exclusive band for each flag and use the applicable evidence from the suspicious failed-attempt sequence. Record the evidence privately, but do not expose the scoring details to the customer.

Calculate all of these flags:

- **Location:** A1 location mismatch against the customer’s address city (0/1/2/3); A2 location scatter (0/1/2); A3 compare last seven days of successful activity with the declined locations (0/1).
- **Time:** B1 declined-attempt time of day (0/1/2/3); B2 time since the last successful PIN use (0/0/1/2); B3 velocity between consecutive failures (0/1/2/3).
- **Amounts:** C1 amount sequence (decreasing sequence is 2, otherwise listed benign patterns are 0); C2 all-round-hundreds testing (0/1); C3 amount versus average recent successful ATM withdrawal (0/1/2); C4 amount(s) versus daily ATM limit (0/1/2, including total attempts over the limit).
- **Card history:** D1 number of *prior* PIN locks in the last 90 days (0/1/2/3); D2 active card age (0/1/2); D3 security issues on other debit cards (0/1/2).
- **Account:** E1 account age (0/1/2); E2 recent overdraft-fee history (0/1/2); E3 current balance (0/1/2).

The supporting transaction specification may omit declined transaction types, times, successful PIN indicators, card linkage, or lock history. If such information is not returned, request it through a supported normal banking/security path; do not call the score complete merely because the generic transaction feed lacks it.

Use `scripts/risk_score.py` to add already-derived flag values and apply the threshold deterministically. It deliberately rejects missing or out-of-range flags. Example stdin JSON (values shown are placeholders and must be replaced with current-case findings):

```json
{"flags":{"A1":0,"A2":0,"A3":0,"B1":0,"B2":0,"B3":0,"C1":0,"C2":0,"C3":0,"C4":0,"D1":0,"D2":0,"D3":0,"E1":0,"E2":0,"E3":0}}
```

The script emits JSON containing `total_score`, `risk_level`, `required_protocol`, whether any single flag is 3, and the applicable question categories. Re-run it after a valid customer confirmation changes a flag.

## Customer conversation and recalculation

For a score of 5 or above, ask the required questions privately and plainly, without mentioning points:

- If A1 is scored, ask whether they were at the declined-attempt location.
- If C1 is scored, ask whether they remember attempting the listed amounts in sequence.
- If B1 is 2 or 3, ask whether they were trying to use the card at the relevant time.

If the customer confirms the location, remove the location flags as directed by the PIN-lock protocol and recalculate. If they confirm the amount sequence, remove C1 and recalculate. If they confirm the time, remove B1 and recalculate. A denial, confusion, or statement that they were asleep maintains the relevant concern; an asleep-attempt response is critical suspected fraud. Ask the medium-risk question—whether the failed PIN attempts were theirs—before a medium-risk unlock.

If the customer reports that they did not make the attempts or does not recognize activity, do not minimize that report or unlock based solely on a low numeric result. Check the suspicious period for successful unauthorized transactions, record the customer’s statement, and transfer to security with `fraud_or_security_concern`. Do not represent a transfer as a completed dispute, closure, or replacement.

## Decision rules

Apply these rules after complete scoring and any permitted recalculation:

- **0–4 (low):** unlock only after standard identity verification and only if no automatic trigger or unresolved fraud concern applies.
- **5–7 (medium):** unlock only after the failed-attempt ownership question is asked and appropriately resolved, plus standard verification.
- **8–10 (high):** ask location/time questions as applicable. Unlock only after confirmation and a satisfactory explanation, plus required verification.
- **11–14 (very high):** do not unlock in this interaction. Require callback verification or enhanced verification (last four SSN plus a security question) through an available approved path.
- **15+ (critical):** do not unlock. Check for successful unauthorized transactions and recommend security handling, card closure, and replacement as appropriate.
- **Any individual 3-point flag:** supervisor review is required regardless of total. Do not bypass it by relying on a lower total.
- **D1 = 3:** PIN reset is required; do not unlock. This remains true even if the aggregate score would otherwise be lower.

For an eligible unlock, use only the normal current-runtime banking action. Confirm the outcome without exposing internal scoring. Post-unlock: no extra step for D1=0; offer PIN-lock notifications for D1=1; for D1=2, ask whether the customer wants a PIN reset because this is the third lock in 90 days.

When a PIN reset is required or requested, verify identity and card ownership, ensure the card is ACTIVE, obtain and confirm card last four digits, and validate a proposed new PIN: exactly four digits, nonsequential, not all identical, and not a birth year or birth month/day. Use an explicitly available reset tool only. Never display or read the PIN back.

## Completion record

Before ending or transferring, retain a concise internal summary: verified/not verified; all accounts and cards reviewed; locks and automatic triggers; evidence limitations; customer recognition statements; whether scoring was complete; resulting approved action or escalation; and any tool result. Tell the customer only the safe outcome and next step, for example that the card needs a security review, not the fraud-score mechanics.

## Script interface

`scripts/risk_score.py` reads one JSON object from stdin and writes one JSON object to stdout. Input must contain exactly the 16 named flag values (`A1` through `E3` as listed above); each must be an integer within its protocol range. It returns either `{"ok": true, ...}` or `{"ok": false, "error": "..."}`. It never accesses customer data, takes no banking action, and does not substitute for evidence collection or required security escalation.
