---
name: stolen-wallet-debit-card-protection
description: Handle a verified customer's stolen or lost wallet report when they request temporary debit-card freezes, including locating checking accounts/cards, enforcing debit-card freeze eligibility, and the required credit-card cross-product security offer. Use in the bank-agent runtime with normal banking tools.
---

# Stolen Wallet: Debit Card Protection

Use this Skill when a customer reports a lost or stolen wallet containing debit cards and asks to freeze them. It covers **debit-card** actions documented by the bank policy. It does not invent a credit-card freeze or replacement action when no corresponding documented tool has been made available.

## Preconditions and verification

1. Identify the customer from a supplied name, email, or user ID using the appropriate normal lookup tool.
2. Verify identity by matching at least two of the four profile fields: email, date of birth, phone number, and address. Do not treat an unverified assertion as sufficient.
3. Obtain the current timestamp with `get_current_time`, then call `log_verification` using the looked-up profile values and timestamp. Only continue after verification has succeeded.
4. Confirm the customer is requesting a temporary freeze rather than permanent closure. For a stolen card, explain that closure is permanent and is recommended for security, but honor a clear informed request to freeze if the customer expressly chooses it.

A freeze means new and recurring transactions will be declined; already-authorized pending transactions may still process. The customer can unfreeze later. Do not claim that freezing blocks ATM usage; separately explain that ATM blocking must be enabled in the mobile app.

## Locate the requested debit cards

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
2. Select only the customer’s open checking accounts that correspond to the account names or other identifiers they supplied. Account labels may not be unique or may not be returned as a dedicated field. If an account cannot be uniquely matched, ask a focused clarification; never guess from a similar name.
3. For each selected checking account, unlock and call `get_debit_cards_by_account_id_7823` with its `account_id`.
4. Match each returned card to the verified customer: its `user_id` must equal the verified user ID and its `account_id` must equal the account being processed. Record the `card_id`, account identifier, status, and last four digits only for communicating confirmation.
5. If no card is returned, the returned card belongs to another user, or an account is not a checking account, do not freeze anything for that item. Explain the precise limitation and offer to continue with the identifiable cards.

## Freeze eligible cards

For every requested card, apply the rule independently:

- The card must be owned by the verified customer and currently have status `ACTIVE`.
- Do not freeze a `PENDING`, `FROZEN`, or `CLOSED` card. For an already frozen card, report that it is already protected; do not repeat the action.
- For each eligible card, unlock `freeze_debit_card_3892`, then call it with `{"card_id": "<card_id>"}` through `call_discoverable_agent_tool`.
- Treat a tool error, rejection, or ambiguous response as a failure for that card. Do not state that it was frozen and do not blindly retry a mutating action.

After each successful action, report only the relevant account/card reference (such as account name and last four digits) and that it is frozen. Provide an itemized outcome for all requested debit cards so partial success is clear.

## Credit-card security protocol

A lost/stolen debit-card report requires the cross-product check even if the customer mainly asked about debit cards:

1. Call `get_credit_card_accounts_by_user` with the verified user ID.
2. If credit-card accounts exist, tell the customer that you found their Rho-Bank credit card(s), ask whether each was in the wallet, and offer a replacement card with a new number as a precaution. Explain that wallet theft can compromise multiple cards.
3. If the customer reports suspicious credit transactions, advise reviewing the transactions and pursuing appropriate dispute/fraud support; do not characterize a transaction as unauthorized without the customer’s confirmation.
4. Do not claim that a credit card was frozen, closed, replaced, or noted merely because it appeared in the lookup. Use a credit-card action only if a separate documented policy and its matching normal banking tool are available. Otherwise explain that no documented agent action is available in this workflow and transfer when the customer needs immediate credit-card protection.

## Escalation and final response

Use `transfer_to_human_agents` with `fraud_or_security_concern` if immediate requested protection cannot be completed because a necessary banking system/tool is unavailable, card/account identification remains unresolved, or a required credit-card action is unsupported in the available workflow. Include the verification state, affected card categories, completed debit freezes, and unresolved items in the summary. Never expose full card numbers, profile details, or internal IDs in the customer-facing response.

Before completing the interaction, summarize: debit cards successfully frozen, cards not eligible or not located and why, the temporary nature and transaction effects of a freeze, and the status of the credit-card replacement offer. Do not call closing tools when the customer explicitly retained the temporary-freeze request.