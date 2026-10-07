---
name: stolen-wallet-card-protection
version: 1.0.0
description: Safely handles a verified customer's report that debit cards were lost or stolen, including required permanent debit-card closure checks and cross-product credit-card replacement protection. Use when a customer reports a stolen/lost wallet or asks to freeze, close, or replace affected cards.
---

# Stolen Wallet Card Protection

Use this workflow for a lost or stolen wallet/card report. Treat stolen or confirmed lost debit cards as a security event: the debit-card procedure requires permanent closure, not a temporary freeze.

## Safety boundaries

- Perform no banking action until identity is verified, authority and ownership are confirmed, applicable product eligibility is checked, and the customer has supplied any required confirmation.
- Do not claim an action succeeded unless the applicable banking tool reports success.
- Do not invent a freeze, closure, replacement, transaction, refund, or dispute tool when it is not available in the runtime or documented procedure.
- Never use a card identifier merely because the customer named an account or card type. Retrieve it and verify its `user_id` and linked account first.
- If required checks cannot be completed, do not close the debit card. Explain the blocking requirement and, where appropriate, transfer to a human agent using the applicable supported reason.

## 1. Verify the customer and record it

1. Obtain identifying information and look up the customer with the available user lookup tool.
2. Compare at least two of these four fields against the retrieved profile: date of birth, email, phone number, and mailing address.
3. Obtain the current timestamp with `get_current_time`.
4. After successful comparison, call `log_verification` with every required field from the retrieved profile plus `time_verified`. Do not log verification if the comparison fails.
5. Confirm the customer is the card owner before each card action.

## 2. Confirm scope and authorization

For a request to freeze cards after loss or theft:

1. Clarify which cards were in the wallet and whether the cards are confirmed lost or stolen.
2. Explain that a confirmed lost/stolen **debit** card must be permanently closed and cannot later be reactivated; it cannot merely be frozen.
3. Obtain explicit authorization to close each affected debit card with reason `lost` or `stolen`. If authorization is declined or unclear, do not close it.
4. Explain that authorized pending debit transactions may still settle after closure. Ask whether the customer wants a replacement debit card; only begin a replacement workflow if a supported procedure and tool are available.

If the customer only misplaced a debit card and has not confirmed it lost/stolen, use the distinct debit-card freeze procedure instead; do not apply this closure workflow by default.

## 3. Locate and evaluate every affected debit card

1. Use `get_all_user_accounts_by_user_id_3847(user_id)` to retrieve checking accounts and their statuses. Match the customer-described accounts to retrieved accounts rather than guessing.
2. For each relevant checking account, use `get_debit_cards_by_account_id_7823(account_id)`.
3. Select only the identified affected card(s). Confirm all of the following independently for every selected card:
   - `card.user_id` matches the verified customer;
   - the linked checking account and selected card match the requested card;
   - card status is `ACTIVE` or `PENDING`;
   - there are no pending or processing transactions;
   - there are no pending refunds, unless the customer has provided the required written acknowledgement that refunds will be credited to the linked checking account;
   - the card has been active at least 14 days from `date_issued`, **except** this age requirement is bypassed for reason `lost`, `stolen`, or `fraud_suspected`.
4. Use `scripts/evaluate_debit_closure.py` to consistently evaluate structured lookup/check results. The helper is advisory; the executor remains responsible for obtaining the real transaction/refund checks and for tool calls.

If pending/processing transactions exist, stop closure for that card and tell the customer to wait for settlement. If a pending refund exists without written acknowledgement, stop closure and explain that it generally takes 3–5 business days or that they may acknowledge in writing that it will credit the linked checking account. For a non-security closure that fails the age requirement, provide the helper's `earliest_eligible_date`.

## 4. Close eligible debit cards

Only after all required checks pass for a card:

1. Use `close_debit_card_4721` with exactly the retrieved `card_id` and the confirmed reason (`lost`, `stolen`, or another supported closure reason).
2. Treat the result as authoritative. If it reports failure or is ambiguous, do not state that the card is closed; report the result and use safe escalation if resolution is needed.
3. For every successful closure, confirm that the card is permanently deactivated and cannot be reactivated, recurring payments must be updated, and refunds to the closed card credit the linked checking account.
4. For lost, stolen, or fraud-suspected cards, remind the customer that pending transactions can still process. For suspected fraud, recommend reviewing recent transactions, disputing unauthorized charges, and changing online-banking credentials.

## 5. Cross-product credit-card protection

For a lost or stolen debit-card report, use `get_credit_card_accounts_by_user(user_id)` to check whether the verified customer has credit cards. If cards exist:

1. Tell the customer that a Rho-Bank credit card is also on file, ask whether it was in the lost/stolen wallet, and offer a replacement with a new card number as a security precaution.
2. Do not represent that a debit-card closure freezes, closes, or replaces a credit card.
3. There is no documented credit-card freeze procedure in this skill. Do not invent one. If the customer requests an immediate credit-card security action that cannot be completed through the documented replacement workflow, explain the limitation and transfer to a suitable supported security/specialized team.
4. If the customer accepts a replacement, follow the documented credit replacement procedure before unlocking or calling its tool: verify identity, look up the credit-card account, confirm full shipping address, capture exactly one reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), select shipping speed, disclose the applicable expedited fee, obtain fee consent where required, and confirm eligibility.
5. Then unlock `order_replacement_credit_card_7291` with `unlock_discoverable_agent_tool`, and call it through `call_discoverable_agent_tool`. Supply the retrieved account/card identifier, reason, confirmed shipping address, shipping speed, expedited-fee acknowledgement where applicable, and relevant notes. Do not order without all prerequisites.
6. After a successful replacement order, tell the customer the old credit card is cancelled, delivery is 7–10 business days for standard or 2–3 business days for expedited, and email notifications will be sent. For stolen or fraud-suspected replacements, remind them to review and dispute unauthorized transactions.

## Helper interface

Run the helper with JSON on standard input and read JSON from standard output:

```json
{
  "as_of_date": "YYYY-MM-DD",
  "customer_user_id": "string",
  "reason": "stolen",
  "cards": [
    {
      "card_id": "string",
      "user_id": "string",
      "status": "ACTIVE",
      "date_issued": "YYYY-MM-DD",
      "pending_transactions": false,
      "pending_refunds": false,
      "refund_acknowledgement_in_writing": false
    }
  ]
}
```

`as_of_date`, ownership, status, issue date, and pending transaction/refund values must be derived from current runtime records—not assumed. Output contains one result per input card with `eligible_to_close`, `blockers`, and (when relevant) `earliest_eligible_date`. Missing required facts are blockers.

Example invocation in an executor that supports packaged scripts: run `scripts/evaluate_debit_closure.py` with the object above. Validate that every card intended for closure has `eligible_to_close: true` immediately before calling the closure tool. A `false` value means no closure tool call for that card.
