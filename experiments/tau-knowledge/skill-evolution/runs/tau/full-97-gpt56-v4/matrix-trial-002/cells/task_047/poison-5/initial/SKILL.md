---
name: credit-card-closure-and-retention
description: Safely handles a verified customer's request to close a specific credit card account, including eligibility screening, replacement-card and dispute checks, required retention workflow, closure, and customer communications. Use for credit-card closure requests; do not use for unrelated card servicing.
---

# Credit Card Closure and Retention

## Scope and safety

Use only normal banking tools provided by the runtime. Never treat a customer statement as a substitute for a required system check, never guess an account identifier, card tier, balance, dispute linkage, age, or eligibility, and never close an account until every prerequisite below is confirmed.

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements as applicable. For this workflow, identity and ownership verification, target-card matching, balance, account age, active/pending dispute status, replacement-card status, prior retention history, reason handling, and the customer's final closure decision are mandatory controls.

If identity, authority, ownership, target account, or any required eligibility result cannot be established, do not perform a closure or retention credit/waiver. Explain what is needed or transfer to a human only when the runtime/policy requires escalation.

## Inputs to obtain at runtime

Collect or locate:

- The authenticated customer's identity and `user_id`.
- A positive match for at least two of the customer's four identity fields: date of birth, email, phone number, and address.
- The particular credit-card account the customer intends to close; confirm it belongs to that `user_id` and matches the requested card product.
- The customer's closure reason and whether they still wish to close after any permitted retention discussion.
- Current date/time from `get_current_time` for the verification audit and age/offer-date calculations.

Do not use a name alone as identity verification. Compare the two customer-supplied identity fields against a user record, then call `log_verification` with the complete matched record fields and current timestamp. Do this before discussing account-specific details or taking banking actions.

## Procedure

1. **Identify and verify.** Locate the customer with the supplied name or email using the appropriate user lookup. Obtain and match two of DOB, email, phone, or address. Retrieve the full record by `user_id` if needed. Call `get_current_time`, then call `log_verification` with exactly the required complete record information and that timestamp. Confirm the requester is authorized and that the intended account belongs to this verified user.

2. **Locate and confirm the target account.** Call `get_credit_card_accounts_by_user` for the verified `user_id`. Ask a clarifying question if the requested product does not identify exactly one account. Confirm the selected account's product/card type and account ID with the customer; do not select another card merely because it is on the same profile.

3. **Check closure eligibility before retention.** Confirm all four requirements, in this order where practical:
   - **Disputes:** unlock and call `get_user_dispute_history_7291` with `user_id`. An active or pending dispute associated with the target card blocks closure. Review transaction/card context. If an active/pending dispute cannot be confidently linked or excluded, do not proceed without clarification/escalation.
   - **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any order not clearly `delivered` or `cancelled` blocks closure.
   - **Account age:** compare `date_of_account_open` to the current date. The account must have been open at least 60 days.
   - **Balance:** confirm the target account's current balance is exactly `$0.00`. Do not infer it from transaction history.

   If any requirement fails, clearly state the specific blocker and what must be resolved. Do not make retention offers or call the closure tool.

4. **Check prior closure-reason history.** Unlock and call `get_closure_reason_history_8293` using only the target `credit_card_account_id`. If the account has a closure-reason record within the past year, skip all retention offers and proceed to the final-decision/closure stage. A customer saying that no prior request occurred does not replace this check.

5. **Log and address the reason when no recent history exists.** Ask for the reason if it is not already clear. Map it to exactly one permitted value and unlock/call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`:
   - `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

   Address the concern using only supported information:
   - For `annual_fee`, a customer of 2+ years may receive a one-year annual-fee waiver. Unlock/call `apply_credit_card_account_flag_6147` with the target IDs, `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format. For less than two years, offer the documented no-annual-fee downgrade, preserving account history; do not claim it was completed unless a supported tool completes it.
   - For `not_using_card`, describe relevant existing benefits and suggest a recurring subscription.
   - For `found_better_card`, ask what features matter. Offer another Rho-Bank card only if comparable or superior benefits are verified in available information; do not invent a product comparison.
   - For `unhappy_with_rewards`, review available bonus-category enrollment and reward-maximization options only if supported by tools/data.
   - For `negative_experience`, apologize, gather details, and escalate if warranted. A goodwill credit is not automatic and requires a supported, justified tool path.

6. **Make one retention offer if required.** If no prior history blocked retention and the customer still wants to close after the concern response, make one offer based on an authoritative card-tier classification:
   - entry tier: 500 points or $5 statement credit;
   - mid tier: 2,000 points or $20 statement credit;
   - premium and above: 5,000 points or $50 statement credit.

   Do not infer tier from a product name or annual fee. If tier cannot be established from the available account data or supported source, say that it cannot be verified and do not fabricate an offer; escalate only if an appropriate operational path exists.

   If the customer accepts a statement-credit retention offer, first unlock `apply_statement_credit_8472`, then call it through `call_discoverable_agent_tool` with a JSON string containing `user_id`, `credit_card_account_id`, positive numeric `amount`, and `reason: "retention_offer"`. Confirm the tool result before stating the credit was applied. Do not apply any offer when the customer has declined it or still requests closure.

7. **Close only after a final decision.** If the customer declines the retention offer, continues to request closure, or a recent closure-reason record required skipping retention, unlock `close_credit_card_account_7834` and call it with `user_id` and `credit_card_account_id`. Ensure the target is still eligible immediately before this irreversible action. Do not repeat the action if its result is unknown; report/escalate instead. Confirm closure only from a successful tool result.

8. **Required customer communication after successful closure.** State that a confirmation email and final statement will arrive within several business days. State that unredeemed rewards can be redeemed for 45 days after the closure request and are then forfeited. If an annual fee posted recently, state that a full refund may apply when closure is within 37 days of the fee charge. Do not promise a refund unless it is confirmed through a supported process.

## Discoverable-tool calling pattern

For each specialized tool named above, call `unlock_discoverable_agent_tool` with the exact tool name before its first use, then call `call_discoverable_agent_tool` using that exact name and a JSON-encoded argument object. Preserve the documented argument set: in particular, the closure-reason logger accepts only its three named arguments. Treat tool failures, malformed responses, ambiguous results, and unknown execution state as blockers rather than evidence of success.

## Customer-dialogue checkpoints

- Ask only for information still needed; use prior valid clarifications and tool observations rather than repeating questions.
- A request to close is not itself final authorization to close until eligibility and the required retention/final-decision stage have completed.
- When a blocker exists, stop the workflow and explain it concisely. When closure succeeds, provide the required rewards and annual-fee notices.
- If a human transfer is necessary specifically for an account-closure request, use `transfer_to_human_agents` with `reason: "account_closure_request"` and a factual summary of verification, target account, checks completed, blockers, and actions not taken.

## Validation checklist

Before reporting success, verify that the execution record shows:

1. Two identity fields were matched and `log_verification` succeeded.
2. The exact target account belongs to the verified user.
3. A zero balance, age of at least 60 days, no target-card active/pending dispute, and no non-final replacement order were confirmed.
4. Closure-reason history was checked; when applicable, the reason was logged and exactly one properly tiered retention offer was handled.
5. The closure tool was called once with the verified `user_id` and target `credit_card_account_id`, and returned success.
6. The final customer message includes confirmation/final-statement timing, 45-day reward redemption/forfeiture, and the conditional 37-day annual-fee-refund notice.
