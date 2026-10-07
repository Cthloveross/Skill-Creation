---
name: credit-card-closure-with-checking-payoff
description: Safely handle a verified customer's request to close a credit card when the card may first need to be paid from the customer's Rho-Bank checking account. Use for closure requests requiring identity verification, eligibility checks, optional retention handling, and normal banking-tool actions.
---

# Credit-card closure with checking payoff

Use this Skill for a customer who wants to close a specific credit card, including cases where they authorize paying its balance from a Rho-Bank checking account. Do not treat identifying a customer, knowing one identity attribute, or an earlier unlogged check as authorization to move money or close an account.

## Required sequence

1. **Identify and verify the customer.** Locate the customer and enumerate their card accounts using the ordinary banking lookup tools. Identify the requested card by its card type/account selection; never infer it from transaction history or select a different card with a balance.
   - Obtain and compare **two of these four** customer-provided factors against the profile: date of birth, email, phone number, address.
   - Get the current timestamp and call `log_verification` only after two factors match. Supply all profile fields and the timestamp required by that tool.
   - If verification cannot be completed, do not disclose balances, look up funding accounts for payment, move money, log a closure reason, or close the card. Ask for a second factor or use the applicable human-transfer path if needed.

2. **Collect current, account-specific closure prerequisites immediately before proceeding.** Follow the retention protocol's required check order: 
   1. Unlock and retrieve the authenticated user's dispute history, then assess disputes attributable to the selected card. Block closure unless every selected-card dispute is conclusively final (for example, closed, resolved, or withdrawn). If a returned dispute cannot be associated with the selected card, treat account-specific eligibility as ambiguous and resolve or escalate it rather than assuming it is clear.
   2. Unlock and retrieve pending replacement orders for the **selected credit-card account**. Block closure if any order is not clearly delivered or cancelled.
   3. Check the selected card's current opening date and determine that it is at least 60 days old.
   4. Check the selected card's current balance and require exactly $0.00 before closure.

   Do not assume no dispute or replacement order merely because a general transaction list is empty. If a response is ambiguous, retry or escalate rather than closing.

3. **Handle a nonzero balance before closure.** Tell the customer the current balance and explain that closure requires exactly $0.00. Do not state that an account has sufficient funds until a current account lookup establishes it. If the customer chooses payment from Rho-Bank checking:
   - use an authenticated checking-account lookup **only if that tool is actually declared and available in the runtime** to find accounts belonging to this user. Do not guess a tool name or claim an account was located without a successful result;
   - present only the customer's returned eligible checking accounts and obtain their selection plus explicit authorization of the exact payment amount. Authorization to pay a stated amount is not a selection of an account when more than one account is available;
   - if no declared lookup can retrieve the account and the customer cannot provide a usable account ID, explain this limitation plainly and do not submit a payment. Offer the applicable human-transfer path only if normal resolution is unavailable; do not promise that the account has been found;
   - verify available funds and refresh the card balance; payment must be positive and cannot exceed either amount;
   - unlock `pay_credit_card_from_checking_9182`, then call it with exactly `user_id`, `checking_account_id`, `credit_card_account_id`, and `amount`;
   - use the confirmation/new balances to confirm the target card is now $0.00. If the payment fails, is unknown, or does not produce a zero card balance, do not retry blindly and do not close the account.
   If no checking account is found, funds are insufficient, or the customer chooses another method, explain that payment must be completed and ask them to return after the balance is zero. Do not substitute another account or split/alter the authorized amount without new authorization.

4. **Run the retention protocol only after eligibility is met.** Check `get_closure_reason_history_8293` for the selected account within the past year.
   - If a record for that account falls within the prior year, skip retention offers and proceed to the closure decision. If the response cannot establish the relevant date, do not assume that no recent record exists.
   - Otherwise, ask/confirm the closure reason and normalize it to one allowed value: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`. For example, a customer whose stated primary reason is a better competitor card maps to `found_better_card`; never send a free-form reason. Unlock and call `log_credit_card_closure_reason_4521` with only `credit_card_account_id`, `user_id`, and `closure_reason`.
   - Address the applicable concern. For an annual-fee concern, use the documented tenure rule before offering a fee waiver flag; do not invent a waiver. For a better-card concern, ask which features matter and offer help only if a suitable bank product is actually available.
   - If the customer still wants to close, make one appropriate tier-based retention offer. Confirm the product's documented tier before choosing an entry-, mid-, or premium-tier amount; do not infer a numeric offer merely from a marketing name when its tier is not documented. Do not apply a retention credit, points, fee waiver, downgrade, or other benefit unless the customer accepts and the applicable documented tool/process supports it. If the customer accepts an alternative, do not close unless they later make a fresh closure decision.

5. **Close only after the customer declines retention or retention is properly skipped.** Refresh the balance and recheck any volatile closure condition where appropriate, especially replacement orders. Confirm the customer still wants the specified account closed. Unlock the documented closure tool if required by the runtime, then invoke `close_credit_card_account_7834` with the selected `credit_card_account_id` and authenticated `user_id` only. Never close another card.

6. **Communicate the result.** After a successful closure confirmation, tell the customer a confirmation email and final statement will arrive within several business days. State that unredeemed rewards can be redeemed for 45 days after the closure request, then are forfeited. For cash-back card rewards represented as points, explain that redemption value is $0.01 per point when relevant. If an annual fee was posted recently, say a full refund may apply only when closure occurs within 37 days of that fee charge; do not promise a refund without confirming its posting date.

## Tool-use rules

- Named specialized tools in this procedure must be unlocked with `unlock_discoverable_agent_tool` before `call_discoverable_agent_tool` when they are not already available. Preserve the documented argument names and send JSON arguments exactly.
- Read-only lookups must use the authenticated `user_id` and the selected account ID, not a guessed identifier.
- Record and rely on successful tool confirmations. Never repeat an operation whose state is reported as unknown.
- If a prerequisite, tool permission, account selection, or response is unavailable or ambiguous, stop the affected action and explain what is needed. In particular, never fabricate a checking-account lookup, account ID, available balance, or a successful payment. Use an appropriate human transfer only when normal resolution is not possible.

## Deterministic validation helper

`scripts/closure_eligibility.py` evaluates supplied, already-verified facts. It performs no banking action and does not replace mandatory live lookup and confirmation.

Example invocation:

```json
{"as_of":"2025-01-01","opened_on":"2024-10-01","balance":"0.00","disputes":[{"status":"closed"}],"replacement_orders":[{"status":"delivered"}]}
```

The script emits JSON with `eligible`, `blockers`, `account_age_days`, and a `checks` object. It rejects malformed dates/amounts rather than treating them as eligible. Before closing, use it only as a consistency check: require `eligible: true`, then still use current banking-tool responses and customer confirmation.

## Unsupported payment channels

The checking-payment process does not establish that any other payment channel is available. If the customer asks for other methods and no declared tool or supplied policy supports one, do not invent options, links, fees, timing, or instructions. State that the balance must be cleared by an available supported method before closure; if the runtime cannot support or identify such a method, offer an appropriate handoff rather than claiming a payment can be processed. If the customer accepts that handoff, transfer using the runtime's specialized-department path and include the verified status, selected card, balance, completed checks, authorization, and the unavailable capability in the summary.

After a successful transfer confirmation, tell the customer that the handoff has been arranged and that a human agent will assist; do not continue account actions in that conversation.
