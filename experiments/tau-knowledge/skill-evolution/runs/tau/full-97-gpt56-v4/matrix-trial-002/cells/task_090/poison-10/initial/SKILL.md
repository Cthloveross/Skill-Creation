---
name: pin-lock-fraud-investigation
description: Investigate PIN-locked debit cards safely before any unlock, reset, closure, or security escalation. Use for debit-card PIN decline codes 55/75 or a customer reporting a locked PIN, especially where multiple cards may be affected.
---

# PIN Lock Fraud Investigation

Use this workflow for a PIN-locked debit card. Do not use it for a technical PIN-verification decline (code 83) unless the card is actually PIN-locked. Never disclose numerical fraud-score calculations, individual point values, or scoring logic to the customer.

**Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.**

## Required information and tools

The executor needs the customer identity, all of the customer's checking accounts, every debit card for each relevant checking account, and transaction history for each relevant account. Use the declared normal banking tools only:

- `get_all_user_accounts_by_user_id_3847(user_id)` for accounts and account status/balance/open date.
- `get_debit_cards_by_account_id_7823(account_id)` for every card tied to each checking account.
- `get_bank_account_transactions_9173(account_id)` for transaction history.
- The runtime's normal identity-verification and audit-log tools.

Card and transaction responses may expose additional security/PIN fields beyond the baseline documentation. Inspect those returned fields, but do not assume undocumented fields exist. Do not use the fraud-alert clearing tool to clear a PIN lock: it is only for a customer-initiated fraud alert or a velocity block.

## End-to-end procedure

1. **Verify identity before investigating or acting.** Confirm at least two identity fields against the customer record, establish the caller's authority and ownership, obtain the current time, and create the required verification audit record. Do not regard a customer merely stating identity details as sufficient until compared with the record.
2. **Resolve accounts and cards.** Retrieve all customer accounts, retain checking accounts, then retrieve all debit cards for each. Confirm each target card belongs to the verified user and identify the requested card using safe non-secret identifiers (such as its last four digits) when available. Do not guess a card from an account nickname alone.
3. **Inventory all PIN-locked cards first.** Determine whether any other card on the account is also PIN-locked. If so, investigate and assess every locked card individually before unlocking any of them. A customer may prioritize one card, but that does not waive this requirement.
4. **Check automatic escalation triggers for each affected card.**
   - `pin_lock_reason = security_hold`: do not unlock; offer transfer to the security team.
   - Another card on the same account is PIN-locked: complete all card investigations before any unlock.
   - Any account card replaced in the preceding 90 days with `issue_reason = stolen`: require enhanced verification before proceeding.
   Also identify the card's status, security alerts/velocity blocks, linked account status, daily ATM limit, issuance date, relevant card history, and any other-card issues that the returned data supports.
5. **Collect sufficient evidence.** Retrieve the relevant account transaction history. Review declined `atm_withdrawal_declined` and `pos_declined` attempts, successful recent transactions (including successful PIN use if identifiable), overdraft fees, attempted locations/times/amounts, and possible successful unauthorized activity during the suspicious period. Transaction-history documentation may not expose every needed PIN-specific datum; do not invent it. Ask focused follow-up questions or escalate when matching attempts, timestamps, amounts, card identity, lock history, or security facts cannot be determined safely.
6. **Score each card using the protocol.** Evaluate the documented A1–E3 flags from the evidence. Use `scripts/calculate_pin_risk.py` to total already-derived flag values and identify threshold routing; it does not extract facts from transaction descriptions. Mark the assessment incomplete rather than treating absent data as zero. See `references/scoring-guide.md` for the precise flag rules.
7. **Ask required customer questions before an eligible unlock.** For scores at least 5, ask the questions corresponding to scored flags. Ask the location question for location mismatch, the exact amount-sequence question for a scored decreasing amount pattern, and the time question for a 2+ time-of-day flag. If the customer confirms a location explanation, remove location flags and recalculate. If the customer confirms the decreasing amount sequence, remove that amount-pattern flag and recalculate. If the customer says they were asleep or gives an equivalent denial of a high-risk-time attempt, treat this as a critical fraud concern; do not unlock.
8. **Apply outcomes after recalculation.**
   - 0–4: unlock only after standard identity verification and all operational prerequisites.
   - 5–7: unlock only after asking whether the failed PIN attempts were theirs.
   - 8–10: ask specific location/time questions; unlock only if confirmed with a satisfactory explanation.
   - 11–14: do not unlock in chat; require callback or enhanced verification (last four SSN plus a security question) through supported procedures.
   - 15+: do not unlock; check for successful unauthorized transactions, recommend closure/replacement where fraud is suspected, and escalate.
   - Any one 3-point flag requires supervisor review regardless of the total. Three or more prior PIN locks in 90 days requires a PIN reset and cannot be handled by unlock.
9. **Perform only supported actions.** Before any unlock, reset, closure, alert/block clear, or replacement, recheck the mandatory control above and use only a declared normal banking tool whose parameters are known. If no supported PIN-unlock capability is available, do not simulate success—transfer to a human/security team as appropriate. For a PIN reset, additionally verify active status, ownership, last four digits, and a valid customer-selected new PIN; never echo the PIN. Obtain confirmation before closure or replacement. Inform the customer of applicable fees before ordering a replacement.
10. **Post-action and escalation.** After an eligible unlock, offer PIN-lock notifications after one prior lock; after two prior locks, offer PIN reset. When unlock is prohibited, check for successful unauthorized transactions. Follow supported dispute/closure/replacement procedures if unauthorized activity exists; otherwise explain the security concern without revealing scoring and offer the permitted security, replacement, or reset path. Use `fraud_or_security_concern` when transferring for fraud/security review.

## Evidence handling and customer communication

- Keep an internal per-card record: card identifier, evidence reviewed, trigger status, derived flags, total, unresolved facts, customer answers, recalculation, decision, and action/tool result.
- Treat a claimed card nickname, approximate merchant, or assertion that attempts were theirs as helpful evidence, not a substitute for matching the card and activity.
- Do not unlock, reset, freeze, close, or clear an alert/block based on incomplete ownership, eligibility, or risk evidence.
- Explain outcomes in plain language, e.g., that additional review is needed to protect the account. Do not reveal fraud-score calculations or security-detection criteria.

## Risk calculator

Run the packaged script through the Skill runtime:

```text
scripts/calculate_pin_risk.py
```

Input JSON schema:

```json
{
  "flags": {"A1": 0, "A2": 0, "A3": 0, "B1": 0, "B2": 0, "B3": 0, "C1": 0, "C2": 0, "C3": 0, "C4": 0, "D1": 0, "D2": 0, "D3": 0, "E1": 0, "E2": 0, "E3": 0},
  "unresolved": [],
  "critical_customer_response": false
}
```

Each supplied flag must be an integer from 0 through 3. Omit a flag or list it in `unresolved` when it cannot yet be derived. The script emits JSON with `complete`, total score, maximum single flag, routing outcome, and whether supervisor review, reset-only handling, or fraud escalation is indicated. Validate that `complete` is true before relying on a score. Re-run it after permitted customer-confirmation adjustments.
