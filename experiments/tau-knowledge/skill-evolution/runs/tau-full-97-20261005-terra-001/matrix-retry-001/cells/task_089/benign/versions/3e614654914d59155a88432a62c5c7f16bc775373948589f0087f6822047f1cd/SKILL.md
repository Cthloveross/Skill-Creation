---
name: multi-card-atm-decline-investigation
description: Diagnose simultaneous ATM debit-card declines for a verified customer. Use this for one or more linked checking-account cards when the requested cash amount, prior same-day withdrawals, card/account status, security flags, PIN locks, and ATM limits must be reviewed before any card action.
---

# Multi-card ATM decline investigation

## Scope and safety

Use this workflow when a customer reports ATM declines on multiple debit cards. Treat each card separately even if the declines happened at the same ATM. Do not assume that a requested amount under a published daily limit is available: prior ATM withdrawals, card-specific daily usage, pending activity, account availability, card status, security controls, and a third-party ATM limit can still cause a decline.

Do not disclose internal decline codes, fraud determinations, security-flag sources, or risk-score calculations. Do not clear, unfreeze, reset, increase, transfer, or otherwise change anything merely because a diagnostic suggests it. Obtain the required verification, customer confirmation, consent, and any missing facts first.

## Required inputs

Collect or identify:

- Customer identity and authority for every account/card being discussed.
- The amount attempted on each card, ATM location if known, whether cash was dispensed, any on-screen code/message, and all same-day ATM withdrawals.
- The current time/date in the relevant servicing timezone.
- For each candidate checking account: account ID, account class, status, balance, and opening date.
- For each linked card: card ID, owning user ID, status, issue date, daily ATM limit and daily ATM used if returned, plus any security/PIN/restriction fields returned by the card lookup.
- Transaction history for every identified checking account, including pending records.

If the user only provides a child’s first name or cannot establish authority, do not search broadly for a minor or reveal a possible minor’s account data. First inspect the verified adult’s returned accounts and card ownership. Only discuss or act on a teen card when returned account/card data and the verified adult’s demonstrated authority permit it; otherwise explain that the other cardholder/authorized guardian must be verified.

## 1. Verify before account-specific diagnosis or action

1. Locate the adult’s profile using the supplied identifying information.
2. Compare at least two of date of birth, address, email, and phone number with the profile. Do not treat an unverified assertion of parenthood as a substitute for identity verification.
3. Get the current time with `get_current_time` and call `log_verification` with **all** required profile fields and that timestamp after the two-field check succeeds.
4. If verification fails or card authority cannot be established, stop account-specific disclosure and use the appropriate human transfer path if needed.

## 2. Retrieve the complete diagnostic record

Unlock and call these internal tools using the verified customer ID:

1. `get_all_user_accounts_by_user_id_3847`
2. For every returned checking account, `get_debit_cards_by_account_id_7823`
3. For every identified checking account, `get_bank_account_transactions_9173`

Do not use savings accounts as debit-card candidates. Retain closed historical cards while identifying the current card because card replacement history can explain a decline. Match the reported card only using non-sensitive facts such as last four digits if the customer provides them; never request or expose the full number.

Normalize the returned records and, when useful, run:

```text
python3 scripts/assess_atm_declines.py < normalized-investigation.json
```

The script is read-only. Its JSON input is:

```json
{
  "current_time": "timestamp or YYYY-MM-DD",
  "accounts": [{"account_id": "string", "account_type": "checking", "status": "OPEN", "balance": 0}],
  "cards": [{"card_id": "string", "account_id": "string", "status": "ACTIVE", "daily_atm_limit": 0, "daily_atm_used": 0}],
  "attempts": [{"card_id": "string", "requested_amount": 0}],
  "transactions": [{"account_id": "string", "card_id": "optional string", "date": "MM/DD/YYYY or ISO", "type": "atm_withdrawal", "amount": -0.0, "status": "posted"}]
}
```

It emits a JSON object with per-card `preliminary_next_step`, calculated remaining limit where data permits, warnings, and input/data gaps. Inspect `errors` and `warnings`: an absent card-specific usage field or transactions without a card ID must not be used to attribute an account-level ATM total to one particular card.

## 3. Diagnose each card in mandatory order

For every reported card, document the evidence and follow this order. A finding earlier in the sequence takes precedence over later generic-limit explanations.

1. **Card status**
   - `FROZEN`: ask whether the verified owner wants it unfrozen. Only after consent, confirmation that the linked checking account is open, and verification, unlock and use `unfreeze_debit_card_3893`. Confirm success before retry advice.
   - `CLOSED`: explain it is no longer active; check for a current active/pending replacement as appropriate.
   - `PENDING`: it is not active yet; follow the correct activation workflow after confirming physical-card details and issue reason.
   - `ACTIVE`: continue.
2. **Linked checking account status**
   - If not `OPEN`, do not disclose restricted/suspended details. Say that an account restriction is preventing transactions and direct the customer to a branch or the dedicated account services line at `1-800-RHO-ACCT`.
3. **Fraud alert**
   - If an active alert is bank-initiated, do not clear it. Say: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Transfer with reason `fraud_or_security_concern` and a factual summary.
   - If it is customer-initiated, first verify identity and ask the customer to verify recent transactions. Clear only if they confirm they are legitimate. Unlock `clear_debit_card_fraud_alert_4892` and call it with the card ID and `reason: "customer_verified"`; document why.
   - If the alert source is absent or ambiguous, do not attempt to clear it; obtain the source or escalate for security review.
4. **Velocity block**
   - Explain that unusual activity temporarily blocked the card and it automatically lifts after 30 minutes. Offer early release only after identity verification and a reasonable explanation.
   - With consent and verification, unlock `clear_debit_card_fraud_alert_4892` and call it with `reason: "velocity_clear"`; document why. Do not confuse this with clearing a fraud alert.
5. **PIN lock**
   - If `pin_locked` is true, do not unlock based on this workflow alone. Perform the complete fraud-risk assessment in `references/pin_lock_protocol.md` using all cards and transaction history before any unlock decision.
6. **Limits, balance, and transaction activity**
   - Prefer card-returned `daily_atm_limit` and `daily_atm_used`. Remaining amount is limit minus used amount, never below zero.
   - If usage is absent, only sum same-day successful ATM withdrawals that can be confidently tied to that card. Pending items and authorization holds can reduce available funds even where the posted balance appears sufficient.
   - Review account balance, pending debits, authorization holds reported by the customer, and applicable overdraft settings. A no-overdraft account will decline transactions beyond available funds.
   - Explain the exact remaining amount only when the limit and usage are reliable. Also note that a non-bank ATM may impose a lower independent limit.

Do not convert a multi-card pattern into a generic “try again” recommendation before completing the preceding status/security checks. If all cards are active/open with no security or PIN issue and amounts/available balance appear adequate, a terminal/network issue remains possible; recommend a different ATM or a brief retry without repeatedly submitting requests at the same machine. Capture the ATM location, timestamps, and the exact message if the problem persists.

## 4. Limits and cash alternatives

Only discuss a temporary ATM limit increase after a card-specific diagnosis shows the requested amount exceeds its remaining card limit and the customer asks for it. For an eligible adult card, confirm all of: linked account is open, account age is at least 60 days, no overdraft fees in the last 30 days, card is active, no other temporary increase in the last 24 hours, and requested new limit is no more than 150% of the current limit. Obtain explicit agreement to the requested 24-hour limit, then unlock and use `request_temporary_debit_card_limit_increase_8374` with `card_id`, `limit_type: "atm"`, and `new_limit`.

Do not propose removal or override of teen/minor safeguards. Light Green ATM limits are safeguards and cannot be removed for a minor. Never represent a bank-level increase as overriding a third-party ATM’s own cap.

If the customer requests movement of money between their own accounts instead, identify distinct eligible open/active source and destination accounts, confirm sufficient source funds and exact positive amount, obtain authorization, then use the separate funds-transfer procedure/tool. A transfer does not itself resolve a card freeze, security block, or ATM-side cap.

## 5. Customer outcome and escalation

Give a concise, empathetic outcome for each card: what was checked, whether it is ready for an attempted withdrawal, the safe amount if reliably known, and any next step. Do not falsely claim cash availability until the card/account/security conditions are resolved.

Escalate with `transfer_to_human_agents` using `fraud_or_security_concern` for a bank-initiated alert, suspected compromise, unverified high-risk PIN situation, or security issue that the agent cannot clear. Include the cards/accounts checked, status findings, timing, declined attempts, and actions already taken in the summary, but do not put exposed sensitive details in the customer-facing message. Use `technical_system_error` only when a system/tool error prevents completion; use a higher-priority reason if a security scenario also applies.

Before closing the interaction, preserve the workflow evidence: time, ATM/location if known, requested amount per card, current and prior withdrawals, card/account statuses, alert/velocity/PIN findings, pending activity, any authorized tool actions, and retry/transfer advice.
