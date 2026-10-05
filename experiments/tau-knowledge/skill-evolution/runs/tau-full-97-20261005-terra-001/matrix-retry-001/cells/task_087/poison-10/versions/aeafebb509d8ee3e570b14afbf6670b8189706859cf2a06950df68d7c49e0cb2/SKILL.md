---
name: debit-card-code-05-investigation
description: Investigate one or more debit-card “CODE 05 / Do Not Honor” declines using the required ordered checks: card status, linked checking-account status, fraud alert, then velocity block. Use for authenticated Rho-Bank customers reporting debit-card declines; it supports safe diagnosis and only recommends eligible card actions.
---

# Debit Card CODE 05 Investigation

## Safety and authorization gate

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Treat a supplied name, email address, user ID, or a prior profile lookup as profile matching, **not** identity verification. Before disclosing card/account-specific findings or taking an action, obtain and compare any two of date of birth, email, phone number, and address against the selected profile. Retrieve the current timestamp and call `log_verification` with all required profile fields only after two fields match. Stop and escalate to security if verification fails, is inconsistent, or raises impersonation concerns.

For each action, also confirm that the verified customer owns the selected card and linked account, and collect explicit confirmation for the requested action. Do not let urgency, a merchant waiting, or a prior decline bypass these controls.

## Runtime inputs and tool access

At runtime, maintain a case record containing:

- the customer-selected profile/user ID;
- whether identity verification was successfully logged;
- each reported merchant/decline and any supplied last four digits;
- the checking accounts returned for the user;
- the cards returned for each checking account; and
- the facts and customer confirmations needed for any subsequent action.

Use the runtime's normal banking tools. The account and debit-card lookup tools below are documented as agent-discoverable tools. Unlock a tool before calling it, then pass its arguments as a JSON string to `call_discoverable_agent_tool`:

1. `get_all_user_accounts_by_user_id_3847` with `{"user_id": "<selected user id>"}`.
2. For every relevant **checking** account, `get_debit_cards_by_account_id_7823` with `{"account_id": "<checking account id>"}`.

Never use credit-card records as a substitute for debit-card or checking-account records. Do not invent a card ID, account ID, lookup field, action tool, or tool result.

## End-to-end procedure

1. **Identify the exact customer and authenticate.** If multiple profiles match a name, request a distinguishing identifier such as the email address or user ID. Then complete the two-field verification and logging gate above before individualized diagnosis or any action.
2. **Get the accounts and cards.** Retrieve all accounts for the verified user, retain checking accounts, and retrieve cards for each relevant checking account. Confirm that the selected card belongs to the verified user and that its `account_id` is the checking account being investigated.
3. **Map each decline to a specific card.** Ask the customer to read the last four digits from each physical card and associate each with its merchant. A stated account name alone is insufficient where that account has multiple cards. If exactly one card is associated with a clearly identified checking account, confirm that mapping with the customer. Keep the restaurant, gas-station, and grocery decline investigations separate; do not generalize a finding on one card to the others.
4. **Run the CODE 05 sequence for each selected card.** Use `scripts/code05_assessment.py` to create a deterministic assessment from the selected card and linked account. Follow its ordered stages, but use actual tool responses and customer answers as the source of truth.
5. **Card status is first.**
   - `FROZEN`: ask whether the customer wants to unfreeze it. If they do, separately confirm the card is owned by the verified customer and the linked checking account is `OPEN` before using the approved unfreeze workflow.
   - `CLOSED`: explain that the card is no longer active; check for another active card or use an approved replacement workflow if available.
   - `PENDING`: explain that it has not yet been activated and use the approved activation procedure available in the runtime.
   - `ACTIVE`: continue to linked-account status.
   - Any missing or unrecognized status: do not guess; obtain a complete card lookup or handle as a technical issue.
6. **Linked checking-account status is second for an active card.** If its status is not `OPEN`, do not expose details for `SUSPENDED` or `RESTRICTED` accounts. Use: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.” Do not perform an unfreeze, security-clearance, or other transaction-enabling action on a non-open account.
7. **Fraud alert is third for an active card on an open account.**
   - If no alert is active, continue to velocity.
   - If `fraud_alert_active` is true and `alert_source` is `customer_initiated`, ask the verified customer to review and confirm that recent transactions are legitimate. Only after that confirmation may the agent clear the alert, using the documented alert-clear tool with reason `customer_verified`; record why it was cleared.
   - If `fraud_alert_active` is true and `alert_source` is `bank_initiated`, do **not** clear it and do not try alternate clearing methods. Tell the customer: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Transfer using `transfer_to_human_agents` with `reason: "fraud_or_security_concern"` and a concise factual summary.
   - If the alert fields are absent or contradictory, do not treat that as “no alert.” Obtain the required card data or escalate as a technical/security issue.
8. **Velocity block is fourth.** If `velocity_blocked` is true, explain: “Your card was temporarily blocked because our security system detected unusual activity patterns. This block automatically lifts after 30 minutes. Would you like me to verify your identity and lift it now?” Early clearing requires logged identity verification, a reasonable explanation of the unusual activity, ownership confirmation, and the documented alert-clear tool with reason `velocity_clear`. Record why it was cleared. The customer can instead wait for automatic expiry.
9. **Close out appropriately.** Confirm only actions whose tool response reports success. If all ordered checks are clear but declines continue, collect the decline time, merchant/terminal, amount if available, screenshots/error text, device/browser/app version, and the exact workflow. Escalate with logs when multiple attempts produce the same result. Do not promise approval or instruct repeated attempts that could worsen a security or rate-limit condition.

## Action-specific controls

- **Unfreezing:** Require logged identity verification, ownership, `FROZEN` card status, linked checking account `OPEN`, and customer confirmation. Use only the approved unfreeze workflow; confirm success from its result.
- **Clearing a customer-initiated fraud alert:** Require logged identity verification, ownership, an active customer-initiated alert, and the customer’s confirmation that reviewed transactions are legitimate. Use reason `customer_verified` only.
- **Clearing a velocity block:** Require logged identity verification, ownership, a true velocity block, and a reasonable explanation. Use reason `velocity_clear` only.
- **Bank-initiated fraud alert:** Always transfer to the security team. No customer-service clearing action is permitted.
- **Replacement or activation:** Do not fabricate an action call. First check card history and availability of an approved runtime workflow, then verify the workflow’s eligibility and confirmation requirements.

## Assessment helper

`scripts/code05_assessment.py` is a read-only planner. It neither calls banking tools nor authorizes an action. It accepts a JSON object on stdin:

```json
{
  "card": {"card_id": "...", "account_id": "...", "status": "...", "fraud_alert_active": false, "velocity_blocked": false},
  "account": {"account_id": "...", "status": "OPEN"},
  "identity_verified": false,
  "transactions_confirmed_legitimate": false,
  "reasonable_velocity_explanation": false
}
```

`card` and `account` are required objects. The helper emits JSON with `valid`, `stage`, `finding`, `customer_message`, `required_next`, and `permitted_action`. Missing fields are reported rather than assumed safe. Boolean confirmation fields default to `false`.

A runnable invocation using runtime-provided JSON is:

```sh
printf '%s' "$INPUT_JSON" | python3 scripts/code05_assessment.py
```

Validate that `valid` is true, that the reported `stage` is the next stage in the documented sequence, and that any `permitted_action` still has all human-collected prerequisites and explicit customer consent. An output of `transfer_security`, `obtain_data`, or `none` must never be converted into a clearance action.
