---
name: credit-card-account-closure
version: 1.0.0
description: Safely process a verified customer's credit-card account closure request, including account selection, mandatory eligibility gates, replacement-order checks, retention protocol, and closure communications. Use when a customer asks to close a credit card account.
---

# Credit Card Account Closure

## Scope and safety rules

Use this Skill for a request to close a credit card account. A closure is permitted only after identity verification and **every** eligibility requirement has been verified:

1. Current outstanding balance is exactly `$0.00`; wait for pending transactions to post and have the customer pay the full statement balance first.
2. There are no active or pending transaction disputes.
3. The account has been open at least 60 days.
4. There is no pending replacement-card order. An order blocks closure unless it is clearly `delivered` or `cancelled`.

Do not offer retention, log a closure reason, apply a retention-related flag, or call the closure tool if any eligibility check fails or is unknown. Do not infer a check from transaction history, a card name, or an old account snapshot. In particular, transaction history is not a substitute for the account's current balance, disputes, or pending-transaction status.

Never close a different account than the one the customer identified. If more than one account plausibly matches, ask the customer to select one using a non-sensitive distinguishing detail; do not guess.

## 1. Verify identity and identify the requested account

1. Locate the customer profile using the customer-provided identifier through the normal read-only lookup.
2. Verify the requester by having them confirm at least two of the following stored fields: date of birth, email address, phone number, and address. Do not read unneeded sensitive values to the customer as prompts. A lookup result alone is not two-field verification.
3. After two fields match, call `get_current_time`, then call `log_verification` with the complete stored profile fields and that timestamp. Do not continue if verification fails.
4. Retrieve the verified user's credit-card accounts and select the exact requested card/account. Confirm the account belongs to the verified user.

If the identity cannot be verified or no unambiguous requested account is found, explain what is needed and do not disclose account details or perform account actions.

## 2. Perform eligibility checks

Use current, account-specific data. Assess and clearly record each result.

- **Balance and pending activity:** Obtain the account's current balance from the account record or authorized current-balance source. A nonzero balance blocks closure; tell the customer the balance must be paid in full after pending transactions post. If current/pending status cannot be established, treat it as incomplete rather than zero.
- **Disputes:** Check the authorized dispute source for the selected account. Any active or pending dispute blocks closure until fully resolved. If no authorized source is available, do not assume there are no disputes and do not close.
- **Account age:** Compare `date_of_account_open` with the current date. The account must be at least 60 calendar days old.
- **Replacement orders:** Immediately before moving to closure processing, unlock and call the documented tool:
  1. `unlock_discoverable_agent_tool` with `agent_tool_name: "get_pending_replacement_orders_5765"`.
  2. `call_discoverable_agent_tool` with that tool name and exactly `{"credit_card_account_id":"<selected account id>"}`.

  An empty order collection passes this check. If any order is not clearly `delivered` or `cancelled`—including `pending`, `shipped`, missing, or ambiguous status—the account is blocked. If the tool errors or gives an ambiguous response, retry according to normal procedure; if it remains unresolved, do not close. Record the timestamp and outcome in available case notes; do not claim a note was recorded when no note facility exists.

The optional helper `scripts/evaluate_closure_eligibility.py` can consistently evaluate already obtained factual inputs. It does not retrieve data, verify identity, perform tool calls, or authorize closure.

### If an eligibility requirement is not met

Explain the specific prerequisite(s) that must be resolved. Do not proceed with retention offers or closure. For a balance, direct the customer to pay the entire balance once pending transactions have posted; for a dispute, wait for resolution; for replacement activity, wait for delivery or cancellation; and for account age, wait until 60 days have elapsed.

## 3. Retention protocol (only after all gates pass)

1. Unlock and call `get_closure_reason_history_8293` with exactly the selected `credit_card_account_id`.
2. If a closure-reason record exists for this account within the past year, skip retention offers and proceed to closure processing if the customer still requests it.
3. Otherwise, ask for the customer's primary reason if it is not already clear as one permitted value. Log exactly one permitted reason using `log_credit_card_closure_reason_4521` with only:
   - `credit_card_account_id`
   - `user_id`
   - `closure_reason`: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`

   Do not add parameters. When the customer gives multiple reasons, ask which is primary rather than choosing arbitrarily.
4. Address the concern appropriately. For a better-card reason, ask which features matter and offer help with an available comparable product only when supported by current product information. For an annual-fee reason, an annual-fee waiver is only a 2+-year loyalty benefit; otherwise a no-annual-fee downgrade may be discussed. Do not represent an unsupported offer as available.
5. If the customer still wants to close, make at most one tier-appropriate retention offer: entry tier: 500 points or $5 credit; mid tier: 2,000 points or $20 credit; premium and above: 5,000 points or $50 credit. Do not pressure the customer.

If the customer declines the offer, or prior-attempt history required retention to be skipped, accept the decision and continue. If the customer accepts an alternative rather than closure, do not close the account.

## 4. Close the account

Immediately before closure, confirm that identity verification is logged, all four eligibility results remain passing, the selected account ID and verified user ID match, and the customer still wants closure.

Then unlock and call `close_credit_card_account_7834` using exactly these arguments:

```json
{
  "credit_card_account_id": "<selected account id>",
  "user_id": "<verified user id>"
}
```

Do not add undocumented arguments. If the tool fails or its result is unclear, do not state that closure succeeded; explain that processing could not be completed and follow the normal support/escalation path.

On a successful closure result, tell the customer that a confirmation email and final statement will arrive within several business days. Remind them that:

- Remaining rewards may be redeemed for 45 days after the closure request, after which unredeemed rewards are forfeited.
- A full annual-fee refund may be available when closure is within 37 days of that fee posting; do not promise a refund without confirming the fee posting date.
- Closing a card can reduce available credit and affect credit utilization, potentially affecting credit score.

For cards represented as cash-back cards in the rewards system, stored points convert at 1 point = $0.01 when redeemed as a statement credit or checking-account credit. Do not assume a redemption occurred merely because the customer was informed.

## Helper interface

Run the helper by passing one JSON object on stdin and receiving one JSON object on stdout:

```text
python3 scripts/evaluate_closure_eligibility.py
```

Input fields:

```json
{
  "current_date": "YYYY-MM-DD",
  "date_of_account_open": "YYYY-MM-DD or MM/DD/YYYY",
  "current_balance": "currency string or number",
  "pending_disputes": true,
  "replacement_orders": [{"status": "pending"}]
}
```

`pending_disputes` and `replacement_orders` may be `null` when unavailable. The output contains `eligibility` (`eligible`, `not_eligible`, or `indeterminate`), per-check states, blocking reasons, and whether retention or closure may begin based on eligibility alone. Before relying on an `eligible` result, validate that the inputs came from current authorized sources and that any pending transaction assessment was included.
