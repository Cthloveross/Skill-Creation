---
name: debit-card-pin-lock-investigation
description: Investigate a PIN-locked debit card before any unlock or PIN reset. Use for debit-card PIN declines (including codes 55 and 75) when a card may be locked; it gathers required account/card/activity facts, applies the fraud-risk protocol, obtains required customer confirmations, and selects a safe unlock, reset, replacement, or security-transfer outcome.
---

# Debit-card PIN Lock Investigation

Use this workflow for every card with `pin_locked = true`. Never unlock merely because the customer says the attempts were theirs, and do not disclose risk scores, flag names, calculations, security thresholds, or internal fraud criteria to the customer.

## Preconditions and scope

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

1. Verify identity and authority before any banking action. Confirm at least two independent profile fields, retrieve the matching profile, obtain the current time, and create the required verification record with `log_verification` before an action. Confirm the customer owns the relevant checking account and card.
2. Identify the relevant checking account. Retrieve accounts with `get_all_user_accounts_by_user_id_3847` and retrieve cards with `get_debit_cards_by_account_id_7823` for the checking account(s) relevant to the reported cards. If card ownership/account association is unclear, retrieve every checking account needed to resolve it.
3. Investigate every locked card separately. Do not unlock a card while another card **on that same checking account** remains PIN-locked and uninvestigated. A customer may choose which card or account to investigate first; locks on a different checking account are separately assessed and do not by themselves create this same-account trigger. Never represent that unreviewed cards are cleared.
4. Retrieve each relevant checking account's transactions using `get_bank_account_transactions_9173`. Obtain the available card security/PIN-lock fields through the normal card lookup workflow. If a named specialized tool is not currently available, unlock it using the normal discoverable-agent-tool mechanism before calling it.
5. Confirm the selected card is ACTIVE before an unlock or PIN reset. Also check linked account status, card limits, fraud-alert state/source, velocity block, card issue history, and ownership. A bank-initiated fraud alert must be transferred to security; do not try to clear it. A customer-initiated alert may be cleared only after identity verification and confirmation that transactions are legitimate, using `clear_debit_card_fraud_alert_4892(card_id, reason="customer_verified")`. A velocity block automatically lifts after 30 minutes; it may be cleared early only after identity verification and a reasonable explanation, using `clear_debit_card_fraud_alert_4892(card_id, reason="velocity_clear")`.

Use only normal banking tools for banking changes. The assessment script only produces an internal recommendation; it never unlocks, resets, closes, replaces, or clears a card.

## Gather assessment facts

For each PIN-locked card, collect enough information to assess all fields below. Inspect the current card plus historical cards on the account and the relevant transaction history. Treat unavailable information as an incomplete assessment, not as zero risk.

- Current lock reason; all other currently PIN-locked cards; any card replaced within 90 days with `issue_reason = stolen`.
- Declined ATM/POS PIN attempts: date/time, amount, and location. Review the successful transactions from the last seven days and the most recent successful PIN use.
- Daily ATM limit, current account balance, account opening date, card issue date, and number of prior PIN locks in the last 90 days.
- Recent successful ATM withdrawals for the average, overdraft fees, and the other cards' velocity-block/fraud-alert state.
- Whether successful transactions during the suspicious period were reviewed and whether the customer identifies any as unauthorized. Record both review completion and the authorization result; do not infer that a posted transaction was authorized.

Transcribe the reviewed facts into the JSON schema documented for `scripts/evaluate_pin_lock.py`, run it, and use its output as an internal checklist. It performs deterministic scoring and reports missing assessment inputs. It is not a substitute for reviewing the original banking records.

Example internal call (use live facts, never these placeholder values):

```json
{"card":{"pin_lock_reason":"incorrect_pin","daily_atm_limit":500,"date_issued":"2024-01-15","prior_pin_locks_90d":0},"account":{"date_opened":"2022-01-01","current_balance":700,"overdraft_fees_recent":0},"home_location":{"city":"Home City","state":"HS","country":"US"},"declined_attempts":[{"time":"2025-01-02T09:00:00-05:00","amount":40,"location":{"city":"Home City","state":"HS","country":"US"}}],"successful_last_7_days":[{"time":"2025-01-01T12:00:00-05:00","location":{"city":"Home City","state":"HS","country":"US"}}],"last_legitimate_pin_use":"2025-01-01T12:00:00-05:00","successful_atm_withdrawals":[40],"other_cards":[],"other_cards_locked":false,"stolen_replacement_within_90_days":false,"now":"2025-01-02T10:00:00-05:00"}
```

The script reads one JSON object on stdin and emits one JSON object on stdout. Its `missing` array must be empty before treating a score-based low-risk outcome as unlock-eligible. `other_cards_locked` means another currently locked card on the selected card's **same checking account**. The helper accepts native lookup aliases `pin_locks_last_90_days` and `current_holdings`, although normalized `prior_pin_locks_90d` and `current_balance` are preferred. It accepts ISO-8601 timestamps and documented U.S. bank date/timestamp formats. Use `flags`, `score`, `risk_level`, `blockers`, `required_questions`, and `recommended_path` internally; do not show them to the customer.

## Apply the protocol

### Automatic conditions

- `security_hold`: do not unlock. Transfer/offer transfer to the security team for that card immediately; do not delay this for score gathering.
- Another PIN-locked card on the same checking account: complete the investigation of every such locked card before any unlock on that account.
- A stolen-card replacement in the last 90 days: require enhanced verification. This does not waive the assessment for any card.

### Score and customer confirmation

The script implements the location, timing, amount, card-history, and account-history flags from the protocol. It uses the highest applicable location/time/amount-vs-average severity, the shortest failed-attempt interval, and aggregate declined attempts where the policy calls for an aggregate pattern. For the daily-limit aggregate, it totals only attempts on the same calendar day. Review the raw facts if a result seems inconsistent.

For a score of 5 or more, ask the customer only the questions corresponding to flagged conditions:

- Location: ask, “I see your card was locked after failed PIN attempts at [location from transaction]. Were you at that location?” If confirmed, set `confirmations.location_confirmed` and recalculate; this removes the location flags.
- Decreasing amount pattern: ask, “The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?” Use the actual attempts (and do not fabricate a third amount). If confirmed, set `confirmations.amount_pattern_confirmed` and recalculate; this removes that pattern flag only.
- Time-of-day score of at least 2: ask, “These attempts occurred at [time]. Were you trying to use your card at that time?” If confirmed, set `confirmations.time_confirmed` and recalculate. If they say they were asleep or otherwise deny it, set `confirmations.time_asleep_or_denied`; do not unlock.

Do not coach answers. Preserve a flag when an answer is denied, unclear, or suspicious. Re-run the script after a permitted confirmation rather than manually subtracting points. Any remaining single 3-point flag requires supervisor review regardless of the total.

### Decide and act

- 0–4: unlock only after the complete assessment, standard verification, all automatic conditions are resolved, and no single-flag escalation applies.
- 5–7: ask, “I see failed PIN attempts on your card. Were those attempts yours?” Record `confirmations.failed_attempts_owned: true` only if the customer clearly confirms it. Unlock only after that ownership question and any flag-specific questions are satisfactorily answered.
- 8–10: ask the specific location/time questions. Unlock only if the customer confirms and gives a satisfactory explanation; record `confirmations.high_risk_explanation_satisfactory: true` only after that explanation.
- 11–14: do not unlock on this interaction. Require callback verification or enhanced verification (last four SSN plus security question).
- 15+: do not unlock. Review for successful unauthorized activity, recommend closure/replacement where fraud is suspected, and transfer to security as appropriate.
- Three or more prior locks in 90 days: do not unlock; require a PIN reset.

Before an actual unlock, re-check customer identity, ownership, ACTIVE card status, linked account status, card details, limits, and all required confirmations. Use the authorized normal unlock tool only if the tool is available and the assessment permits it. Do not invent an unlock-tool name or parameters.

If the result requires a PIN reset, follow the PIN-reset procedure: verified owner, ACTIVE card, confirmed last four digits, and a customer-selected compliant four-digit PIN (not sequential, repeated, birth-year, or birth month/day). Use `reset_debit_card_pin_6284` only with its documented `card_id`, `last_4_digits`, and `new_pin` parameters. Never repeat or display the PIN.

After an eligible unlock: no additional prompt for zero prior locks. After one prior lock, MUST offer: “Would you like me to enable PIN lock notifications so you're alerted if this happens again?” After two prior locks, MUST ask: “This is your third PIN lock in 90 days. Would you like me to reset your PIN to a new number? Frequent locks sometimes indicate the current PIN is difficult to remember.” If no unlock is permitted, check for successful unauthorized transactions. For unauthorized activity, file the appropriate dispute and arrange closure/replacement under the applicable procedure. Otherwise explain only that a security review prevents immediate unlocking and offer the applicable security transfer, PIN reset, or replacement option.

## Validation and failure handling

- Validate that the selected card belongs to the verified customer and linked checking account, is ACTIVE, and is actually PIN-locked before any PIN-lock action.
- Do not substitute missing timestamps, locations, amounts, historical ATM amounts, account/card ages, balance, prior-lock data, or other-card security state with guesses. Resolve them from records or escalate/continue investigation.
- Confirm the script output has `missing: []`, every needed transaction time parsed correctly, and a `recommended_path` consistent with the decision before an unlock. Re-run after relevant customer confirmation. For any result that prevents an unlock, separately complete the required review for successful unauthorized activity before selecting the security, dispute, closure, replacement, callback, or PIN-reset outcome.
- If security-hold, bank-initiated fraud alert, unauthorized activity, suspicious/inconsistent identity or explanations, or an unavailable required control prevents safe completion, transfer to human security support with a concise internal summary and no calculated score.
