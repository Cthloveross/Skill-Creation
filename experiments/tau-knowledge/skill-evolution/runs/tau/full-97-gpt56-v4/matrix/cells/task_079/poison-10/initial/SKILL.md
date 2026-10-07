---
name: debit-card-freeze
summary: Securely freeze one or more debit cards for a verified cardholder, including checking account/card lookup, eligibility checks, and lost-or-stolen safeguards.
---

# Debit Card Freeze

Use this Skill when a customer asks to temporarily freeze debit card(s), including all cards linked to their checking accounts. A freeze is reversible; it declines new and recurring card transactions, while already-authorized pending transactions may still settle.

## Required inputs and available tools

Obtain the customer identity (name or email, then a second identity field) and the requested card(s) or checking account(s). At runtime use these normal banking tools:

- `get_user_information_by_name` or `get_user_information_by_email` to locate the customer.
- `get_current_time` and `log_verification` to record successful verification.
- `get_all_user_accounts_by_user_id_3847(user_id)` to find accounts.
- `get_debit_cards_by_account_id_7823(account_id)` to find cards for each checking account.
- `freeze_debit_card_3892(card_id)` to freeze an eligible card.
- `get_credit_card_accounts_by_user(user_id)` when a card or wallet is reported lost or stolen.

Discoverable internal tools must be unlocked with `unlock_discoverable_agent_tool` before being called through `call_discoverable_agent_tool`. Do not treat a script recommendation as a banking action.

## Procedure

1. **Identify and verify the customer before any action.** Locate exactly one customer record. Confirm at least two of these four fields against the record: date of birth, email, phone number, and address. Get the current time and call `log_verification` with the complete retrieved customer record and timestamp only after the two-field verification succeeds. If identity is ambiguous or verification fails, do not retrieve or change card information.

2. **Establish request scope and security context.** Confirm which checking accounts or cards are in scope. For a request to freeze “all” debit cards, interpret this as all debit cards belonging to the verified customer across all of their checking accounts; do not rely solely on account nicknames.

   If the customer confirms a card or wallet is lost or stolen, explain that closing is the safer permanent option because a freeze can later be reversed. The customer may still choose a temporary freeze when appropriate; act only on the customer’s confirmed instruction. For a lost/stolen report, retrieve credit-card accounts with `get_credit_card_accounts_by_user`. If any exist, proactively ask whether those cards were also in the wallet and offer replacement protection as appropriate. If none exist, state no credit-card follow-up is needed. Do not order or replace a credit card without a separate authorized workflow.

3. **Give the freeze disclosure before freezing.** Tell the customer that new transactions and recurring payments/subscriptions will be declined while the card is frozen; pending transactions already authorized may still process; and they can unfreeze later through customer service or the mobile app. Freezing does not itself block ATM access for a customer with the PIN; ATM Block must be enabled separately in the mobile app.

4. **Find and validate cards.** Retrieve all accounts for the verified `user_id`. Only inspect accounts whose `account_type` is `checking`. For every in-scope checking account, retrieve its debit cards. For each candidate card, verify both:
   - `card.user_id` exactly matches the verified user ID (ownership), and
   - `status` is `ACTIVE`.

   Freeze only cards meeting both conditions. Do not freeze `PENDING`, `FROZEN`, or `CLOSED` cards. Report each skipped card generically with its last four digits when available and its status/reason (for example, already frozen or not active). If no eligible cards are found, make no freeze action and explain why.

5. **Execute each eligible freeze exactly once.** Unlock and call `freeze_debit_card_3892` for each eligible `card_id`. Record the tool result separately for every card. If a call fails or returns an indeterminate outcome, do not retry automatically; report that card as unresolved and use the normal escalation path if needed. Continue with other independent eligible cards unless the tool response indicates a broader security/system issue.

6. **Confirm results accurately.** Clearly distinguish cards successfully frozen, cards skipped because they were ineligible, and any unresolved failures. For each successful card, confirm it is frozen and recap the transaction and unfreezing effects. Never claim that a card was frozen unless the tool reports success.

## Guardrails

- Do not freeze a card before verification, ownership, and ACTIVE-status checks are complete.
- Do not close a card merely because it was reported stolen; explain the permanent-close alternative and obtain the required customer direction for any separate closure workflow.
- Do not expose full card numbers; use last four digits only when identifying cards to the customer.
- Do not freeze cards from savings accounts or cards owned by another user.
- If the request includes suspected unauthorized transactions, provide the debit-card dispute/fraud reporting path in addition to, not instead of, the requested card protection.

## Completion checklist

A complete outcome has: a logged two-field identity verification; account and card discovery across requested checking accounts; per-card ownership and ACTIVE-status checks; a freeze disclosure; one documented freeze result per eligible card; lost/stolen credit-card review when relevant; and a customer-facing summary of successful, skipped, and unresolved cards.
