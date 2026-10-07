---
name: diagnose-shared-atm-debit-card-declines
description: Safely triage a customer reporting debit-card ATM declines, especially when several cards fail at one ATM. Use to distinguish a likely terminal problem from card, account, balance, limit, PIN, or security issues without taking unverified banking actions.
---

# Diagnose shared-ATM debit-card declines

Use this Skill for ATM cash-withdrawal declines, including urgent situations. Its first goal is a safe, immediately actionable path; it does not assume that a decline at one ATM means that a card is defective.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Inputs to collect

Collect only what is necessary for the stage of the workflow:

- Whether all affected cards failed at the same ATM/terminal and whether a different ATM has been tried.
- Whether cash was dispensed, the requested amount for the card being discussed, and any exact decline text/code.
- The relevant account product, if known, and whether the customer has already withdrawn cash during the applicable daily period.
- For an investigation or any account/card action: identity verification, authority over each account/card, and the cardholder/account relationship. A parent must not be assumed authorized to change a teen card's controls.

Do not request or repeat a full card number or PIN. Do not claim a card is usable, a balance is sufficient, or a daily limit remains available unless the required current records have been checked.

## Fast path: several cards fail at one ATM

When multiple cards fail at the *same* machine, no cash was dispensed, and another ATM is available:

1. Do **not** repeatedly retry at the same ATM.
2. Explain that the common ATM/terminal or its network is the most useful issue to rule out first; this is not proof that every card has a problem.
3. Ask the customer to use a nearby ATM at a different location or bank if practical. The other operator may impose a separate per-transaction cash limit or fee.
4. Have them preserve the screen message, time, location, requested amount, and receipt if available. Ask them to report whether cash was dispensed and the exact result at the alternate ATM.
5. Do not freeze/unfreeze cards, clear alerts, reset PINs, change limits, or transfer funds merely to handle this one-machine pattern.

If product documentation supplies a daily ATM limit, it is a combined daily cap, not a guarantee that the requested amount will succeed: prior same-day withdrawals, available balance, authorization holds, card status, and an ATM operator limit can still prevent the withdrawal. State a request is only *within the published nominal limit* when the requested amount is no greater than that published limit; do not infer remaining capacity without current usage.

Use `scripts/atm_decline_plan.py` to create a consistent non-action recommendation from the collected facts. The script recommends only; it does not call banking tools or execute any action.

## If the alternate ATM also declines, or the pattern is not shared

Before accessing nonpublic account/card details or performing any banking action, verify identity using two of date of birth, email, phone number, and address, then log the successful verification with the declared verification tool. Confirm the customer is the owner or otherwise authorized for the specific account/card.

Then use the declared normal banking tools to:

1. Retrieve the customer's accounts and identify the linked checking account and its status.
2. Retrieve the debit cards for that checking account. Confirm card status, the last four supplied by the customer if needed, daily ATM limit and current daily usage when available, and security/PIN fields.
3. Retrieve account transactions when balance, pending debits, authorization holds, prior withdrawals, overdrafts, or a PIN-lock investigation are relevant.
4. Compare the requested amount against available funds and the *remaining* daily limit. Determine same-day ATM use from the current transaction history when a current usage field is not returned. Explain pending authorizations and pending transactions when they reduce available funds.
5. Treat each card separately. A shared-terminal pattern is only an initial clue; a documented exhausted limit on a particular card explains that card’s decline.

For a teen card, verify the adult’s identity and confirm the guardian relationship from linked customer/account records before looking up or disclosing the teen account. Do not make a change merely because the adult says they are a parent. Product-level teen controls may be fixed rather than adjustable: do not promise that a temporary ATM-limit increase is available. In particular, a Light Green Account’s $150 daily ATM withdrawal limit is policy-based and cannot be temporarily increased. Explain its remaining capacity and offer an appropriate authorized-adult alternative.

Interpret a specific code using the documented procedure. In particular:

- **Code 58 / terminal-specific restriction:** the terminal is flagged; use another register, terminal, or merchant. Multiple unrelated terminal failures require card diagnosis.
- **Code 61 / withdrawal limit:** explain published limit, used amount, and remaining amount. Do not propose an increase until confirming that the specific product’s limit is adjustable. Where it is allowed, a temporary increase requires verified identity, ownership/authority, an OPEN linked checking account, account age of at least 60 days, no overdraft fees in the last 30 days, an ACTIVE card, a maximum new limit of 150% of current limit, and specific customer confirmation of the card, limit type, new amount, and 24-hour duration. If the request fails or policy fixes the limit, do not retry or report an increase; explain the unchanged limit and alternatives. Third-party ATM limits cannot be overridden.
- **Code 51 / insufficient funds:** check current balance, pending transactions/holds, and applicable overdraft settings before concluding funds are insufficient.
- **Code 55 or 75 / PIN locked:** do not unlock directly. Follow the complete PIN-lock fraud-risk procedure before taking action.
- **Code 05:** inspect card status first, then linked account status, fraud alert, and velocity block in that order. Customer-initiated alert and velocity-block clears require identity verification and their documented conditions. Bank-initiated fraud alerts must be escalated to security and never cleared by the agent.
- **Codes 91/96/92 or an unexplained technical failure across unrelated locations:** advise a short wait and retry as documented; collect timestamps and affected locations. Escalate only when the applicable procedure requires it.

Never disclose internal fraud-only decline codes or reasons. Follow the relevant security escalation procedure for a stolen-card, bank-initiated alert, security hold, suspected fraud, or failed verification.

## Customer-facing response structure

1. Acknowledge the urgency.
2. State the observed pattern plainly (for example, multiple cards at one ATM) and give the immediate safe next step.
3. Describe any stated daily-limit fact as conditional on prior use and available balance.
4. Say exactly what outcome to report after the alternate attempt: cash dispensed/not dispensed, exact message/code, ATM location, time, and amount.
5. Offer the verified diagnostic path if the alternate ATM fails. Do not promise a fix before the checks are complete. For a limit change, state the exact card, new limit, and 24-hour duration; obtain confirmation; then report success only after the tool confirms it.

## Helper script

`python3 scripts/atm_decline_plan.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "cards_declined_at_same_atm": true,
  "alternate_atm_tried": false,
  "alternate_atm_available": true,
  "cash_dispensed": false,
  "requested_amount": 0,
  "published_daily_limit": null,
  "amount_used_today": null,
  "decline_code": null
}
```

`requested_amount`, `published_daily_limit`, and `amount_used_today` must be nonnegative numbers or `null`. `decline_code` may be a string, number, or `null`. Omit unknown monetary values rather than guessing them.

Output includes a `classification`, ordered `next_steps`, conditional `limit_assessment`, and fields to collect. Validate that `ok` is true before using the recommendation. An invalid input returns `ok: false` with an error and must be corrected rather than treated as a diagnosis.

Example invocation:

```sh
printf '%s' '{"cards_declined_at_same_atm":true,"alternate_atm_tried":false,"alternate_atm_available":true,"cash_dispensed":false,"requested_amount":null,"published_daily_limit":null,"amount_used_today":null,"decline_code":null}' | python3 scripts/atm_decline_plan.py
```
