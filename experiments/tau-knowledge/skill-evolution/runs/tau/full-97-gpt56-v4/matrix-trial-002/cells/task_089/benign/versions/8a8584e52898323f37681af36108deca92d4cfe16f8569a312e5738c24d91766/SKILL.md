---
name: debit-card-atm-decline-and-temporary-limit-review
description: Investigate ATM cash-withdrawal declines, including several cards declined at one machine, and safely determine whether a temporary debit-card ATM limit increase is eligible. Use for a customer reporting a debit-card decline or needing cash above their available daily ATM limit.
---

# Debit-card ATM decline and temporary-limit review

Use this Skill for an ATM decline, particularly when the customer needs urgent cash or reports that more than one card failed at the same terminal. Treat a generic decline as an investigation, not proof that a limit is the cause.

## Safety and scope

- Identify the customer, then complete the required identity verification before disclosing sensitive card/account details or taking a card action. Confirm two of the four stored fields (date of birth, email, phone number, address) and call `log_verification` with the current timestamp and all required retrieved fields.
- Do not expose full card numbers, account numbers, internal security flags, or private account-restriction details.
- Do not claim that a limit increase, an ATM, or a payment alternative is available until it has been confirmed.
- A common-terminal failure across multiple cards can be an ATM/operator or network issue. Do not keep asking the customer to retry the same ATM. A different ATM may still impose its own per-transaction or daily cap that the bank cannot override.
- Do not confuse an ATM withdrawal limit with available funds, PIN failure, a card freeze, a fraud alert, a velocity block, transaction-count restrictions, or an account restriction.

## Gather the minimum facts

Ask only for missing facts needed to investigate:

1. Exact ATM message/code if available, amount requested, whether any cash was dispensed, ATM operator/location, and whether all cards failed at that same machine.
2. Which card was attempted each time, whether a PIN was entered, and any ATM withdrawals already made today.
3. Whether the recipient can accept another confirmed payment method. An Everyone Pay instant transfer requires an actual recipient contact and the customer's confirmation; do not send money merely as a suggestion.

For urgent cash, explain that a different ATM is a reasonable practical next step after the account/card checks, but the other operator's limit is independent. If the customer owns more than one eligible card, a different ATM may allow separate withdrawals up to each card's *remaining* capacity; do not promise a combined amount without confirming each card's current usage, funds, and controls. Do not propose use of a teen's card by another person or a change to teen controls without the required authority.

## Required investigation order

Perform this separately for every relevant card. Use the debit-card and linked-account lookup capabilities made available by the runtime. Do not invent a tool name if the runtime has not made a lookup capability available.

1. **Card status and card linkage:** Verify the correct card, linked checking account, card status, card issue date, and whether it is a teen/parentally controlled card where applicable.
   - If the card is FROZEN, ask whether the verified card owner wants it unfrozen; unfreeze only under the documented unfreeze requirements (verified owner, FROZEN card, and OPEN linked checking account).
   - If it is CLOSED, explain that it is no longer active and check for another active card or an approved replacement path. If it is PENDING, it is not activated; use the applicable activation protocol rather than treating an ATM limit as the cause.
   - Do not perform any action on a teen card based only on another person’s request; establish the applicable guardian authority first.
2. **Linked account:** Check that the linked checking account is OPEN. If it is suspended or restricted, do not reveal the restriction: tell the customer that an account restriction is preventing transactions and direct them to a branch or the dedicated account-services line.
3. **Card security state:** Check fraud-alert source, velocity-block status, PIN-lock status, and PIN attempts remaining.
   - A bank-initiated fraud alert must not be cleared; transfer to security.
   - A customer-initiated fraud alert may be cleared only after identity verification and the customer confirms legitimate activity. A velocity block may be cleared only after identity verification and a reasonable explanation. If the documented tool is available, unlock `clear_debit_card_fraud_alert_4892` and use the exact permitted reason (`customer_verified` or `velocity_clear`), then document the reason in interaction notes.
   - If a PIN is locked, do not unlock it without the separate PIN-lock fraud-risk protocol.
4. **ATM limit and use:** Read `daily_atm_limit` and `daily_atm_used`; calculate remaining ATM capacity as `max(0, limit - used)`. Check any daily transaction-count restriction too. Explain the actual limit, amount already used, and remaining amount. Do not infer a particular card's current settings from account-tier literature when card fields are available. Published product limits may be described as general information only.

   When a customer needs a particular additional cash amount `W`, distinguish a *daily limit* from remaining capacity. If they have already used `U`, the smallest new daily limit that could cover the request is `U + W`, subject to funds and all other controls. Do not request an increase if `U + W` exceeds `1.5 × current_limit`: it cannot solve the stated cash need. A current limit that is already at least `U + W` means a limit increase is not the indicated remedy.
5. **Funds and holds:** Check current/available balance, recent pending activity, authorization holds, and the POS/ATM overdraft setting. Use account transactions where needed: unlock and call `get_bank_account_transactions_9173(account_id)` only after the linked account is known. Treat only an actual posted `overdraft_fee` transaction in the rolling prior 30 days as a temporary-increase overdraft-history failure; do not substitute a negative balance, an unrelated fee, or a pending transaction. Pending debits and holds can reduce available cash even when the posted balance appears sufficient.
6. **Other card restrictions:** Check geographic, international/ATM, and applicable parental-control restrictions. Do not modify parental controls without guardian authorization.

If required lookup data are unavailable in the runtime, say what cannot yet be determined and avoid action based on assumptions. Ask for the missing permitted information or use an available supported lookup; do not guess an undocumented endpoint.

## Temporary ATM limit increase

Offer this only if the card is otherwise suitable and the customer explicitly wants the request. Before calling the limit-increase tool, verify **all** of the following for that particular card and linked account:

- card status is ACTIVE;
- linked checking account has status OPEN and is in good standing;
- account age is at least 60 days;
- there were no overdraft-fee transactions in the prior 30 days;
- no other temporary increase was granted for that card in the last 24 hours;
- requested `new_limit` is no greater than 150% of the current ATM limit; and
- that new total daily limit is high enough to cover the amount already withdrawn plus the cash amount the customer is requesting, if the request is intended to solve that cash need.

Use the card's current daily ATM limit, not the amount remaining today, as the basis for the 150% ceiling. `new_limit` is a total daily limit, not an amount added to the remaining capacity. Prefer the smallest qualifying total daily limit; do not request a limit that cannot meet the stated need. A temporary approval lasts 24 hours and automatically reverts. It does not override another bank's ATM limit, an insufficient available balance, a PIN/security restriction, or an ATM/network outage.

If eligible and explicitly authorized, unlock `request_temporary_debit_card_limit_increase_8374`, then call it with exactly:

```json
{"card_id":"<verified card id>","limit_type":"atm","new_limit":<requested new daily limit>}
```

Report the tool outcome faithfully. If it fails or eligibility is not met, do not retry blindly or offer a workaround that bypasses a restriction. Explain the applicable non-sensitive reason and the next safe option. Never request a temporary increase for a teen card merely because another customer asks; establish authority and applicable parental-control requirements first.

## Using the packaged evaluator

`scripts/evaluate_atm_case.py` is an offline decision aid. It does not call bank tools or perform an account/card action. Supply already retrieved, minimally necessary fields as JSON on stdin; it emits JSON with eligibility findings, missing evidence, and a concise next-step list.

Example input schema:

```json
{
  "card": {"card_id":"...", "status":"ACTIVE", "daily_atm_limit":500, "daily_atm_used":0, "temporary_increase_last_24h":false},
  "account": {"status":"OPEN", "age_days":90},
  "requested_new_limit":600,
  "requested_cash_amount":250,
  "overdraft_fee_dates": ["YYYY-MM-DD"],
  "today":"YYYY-MM-DD"
}
```

Run it only after the information is obtained from approved tools. Inspect `missing_evidence` before treating `temporary_increase_eligible` as actionable. `base_temporary_increase_eligible` reports the policy checks alone. When a cash amount is supplied, `temporary_increase_eligible` is additionally false if the proposed daily limit cannot cover prior withdrawals plus that cash amount; inspect `minimum_new_daily_limit_for_requested_cash` and `proposed_limit_covers_requested_cash`. `overdraft_fee_dates` must represent overdraft-fee transactions, not all negative balances or all fees.

## When lookup capability is unavailable

Do not invent a debit-card or account lookup endpoint, card ID, account ID, usage amount, or eligibility result. Explain the specific unknown concisely and do not submit a limit or security action. For an urgent same-machine multi-card decline, give the immediately usable, non-action alternative—try a different ATM/operator once—and make clear it is not a guarantee. Avoid repeatedly asking the customer for facts that have already been provided. If a verified customer wants an increase but the required lookup cannot be performed in the runtime, say that it cannot be safely submitted from this session and offer only documented alternatives (for example, a confirmed Everyone Pay recipient with authorization, or asking the provider whether another payment method is accepted). If the customer still needs a card-specific decision or card action that cannot be performed because the required supported capability is unavailable, transfer to a human agent with reason `specialized_department_required`; summarize the verified identity status, cards involved, same-ATM pattern, requested cash amount, and that no unverified card/security/limit action was taken.

## Customer-facing closeout

State the diagnosed cause if confirmed; otherwise say that the exact generic decline cannot be isolated yet. For a same-ATM multi-card pattern, recommend trying a different ATM/operator rather than repeat attempts at the same machine. State the card-specific limit and remaining amount only after verification. If cash cannot be obtained, ask the tow provider whether a card, instant payment, or another documented option is accepted; obtain recipient contact, amount, and customer confirmation before initiating any payment. Do not treat an ambiguous “yes” as payment authorization. Escalate to security for bank-initiated alerts or suspicious activity, and use a supported human-transfer reason if required by the runtime.
