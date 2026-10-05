---
name: credit-card-account-closure
version: 1.0.0
description: Safely process a verified customer's request to close a credit-card account, including eligibility checks, replacement and dispute review, required retention handling, closure-reason logging, closure execution, and post-closure disclosures. Use for authenticated credit-card closure requests when the internal closure tools are available.
---

# Credit Card Account Closure

Use this Skill only for a customer who requests closure of a specific credit-card account. It is a banking workflow: do not close an account, apply a retention benefit, waive a fee, or downgrade a card until identity, ownership/authority, eligibility, and the customer's decision have been confirmed.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For an account closure, document how the control was satisfied:

- **Identity:** use the standard verification process below and create the verification audit record.
- **Authority and ownership:** the verified user must match the selected account's `user_id`; do not accept a name match alone as ownership.
- **Product eligibility / balance:** assess all closure blockers below, including a zero balance and no pending transaction activity.
- **Fees:** disclose the annual-fee refund condition; do not promise a refund without a fee-posting date and a confirmed eligibility determination.
- **Limits, cutoffs, recipient details, and transfer/payment confirmation:** these do not apply to an account-close action unless a separate payment, transfer, or rewards-redemption action is requested. Do not perform such a separate action under this workflow without its own required checks and confirmation.
- **Closure confirmation:** obtain an unambiguous request to close the identified account after explaining any applicable retention path. A clearly stated preference to continue closing, including a decline of retention, satisfies this only after identity and account selection are confirmed.

## Inputs and tool access

Collect or establish at runtime:

- the authenticated/verified `user_id`;
- the exact target `credit_card_account_id` and target card type;
- a current account record containing account owner, opening date, balance, and rewards balance;
- current time for the verification record and date calculations;
- current dispute, replacement-order, and pending-transaction information;
- the customer's closure reason and decision about any applicable retention offer.

The specialized tools are discoverable. Before each first use, unlock it with `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool` using exactly the documented arguments:

| Purpose | Tool | Required arguments |
|---|---|---|
| Review disputes | `get_user_dispute_history_7291` | `user_id` |
| Review replacement activity | `get_pending_replacement_orders_5765` | `credit_card_account_id` |
| Check prior retention/closure-reason records | `get_closure_reason_history_8293` | `credit_card_account_id` |
| Log the reason | `log_credit_card_closure_reason_4521` | `credit_card_account_id`, `user_id`, `closure_reason` only |
| Apply a qualified annual-fee waiver | `apply_credit_card_account_flag_6147` | `credit_card_account_id`, `user_id`, `flag_type`, `expiration_date`, `reason` |
| Process the closure | `close_credit_card_account_7834` | `credit_card_account_id`, `user_id` |
| Process a downgrade when selected | `downgrade_credit_card_3847` | `credit_card_account_id`, `user_id`, `target_card_type` |

Never add undeclared fields to `log_credit_card_closure_reason_4521`. Do not assume a specialized tool was called successfully merely because it was unlocked.

## Procedure

### 1. Identify the customer and verify identity

1. Locate the customer and retrieve their account list using an approved lookup (for example, a supplied user ID, email, or exact name). If multiple customer records or multiple possible target accounts exist, ask the customer to identify the intended account; never guess from a card name alone.
2. Retrieve the selected account and verify that its `user_id` matches the verified customer.
3. Ask the customer to independently confirm at least two of these four identity fields: date of birth, email address, phone number, and street address. Do not reveal the values as prompts or count a provided name as one of the two fields.
4. After two fields match the retrieved customer profile, call `get_current_time` and call `log_verification` with the complete required profile fields, `name`, `user_id`, and the returned timestamp. If verification fails or is incomplete, stop; do not inspect sensitive account details further or take an account action.

### 2. Establish the requested account and current information

1. Confirm the customer wants to close the exact selected account, not another card in their profile.
2. Obtain a current account record immediately before the workflow. Confirm account ownership, opening date, current balance, and rewards balance.
3. Check current transaction activity using the available account/transaction data. A displayed zero balance is not sufficient if an unsettled, pending, or otherwise non-final transaction exists. If transaction-to-account association is unclear, obtain clarification or treat it as a blocker.

### 3. Check closure eligibility before retention

Check these in this order. Do not make a retention offer if any blocker exists.

1. **Disputes:** call `get_user_dispute_history_7291` for the verified user. The target account must have no active or pending transaction disputes. Review dispute status and transaction/card context to associate records with the target account. `closed` or clearly fully resolved disputes do not block closure; `open`, `under_review`, pending, unknown, or ambiguously associated non-final disputes do. If a current status cannot be determined, do not close.
2. **Replacement cards:** call `get_pending_replacement_orders_5765` with the target account ID. An empty `orders` collection passes. If any order is not clearly `delivered` or `cancelled` (including pending or shipped), closure is blocked. An ambiguous or malformed response is not a pass; retry or escalate through the appropriate internal support path.
3. **Account age:** calculate from the account opening date to current date. The account must be open for at least 60 days.
4. **Balance and pending transactions:** the outstanding balance must be exactly $0.00, and there must be no pending transaction activity. The customer must wait for transactions to post and pay the full statement balance before retrying if either condition fails.

The bundled evaluator can organize these determinations but does not substitute for tool calls or customer verification:

```sh
python3 scripts/assess_closure_eligibility.py <<'JSON'
{
  "as_of_date": "YYYY-MM-DD",
  "identity_verified": true,
  "closure_authority_confirmed": true,
  "explicit_closure_confirmation": true,
  "account": {
    "account_id": "account identifier",
    "user_id": "verified user identifier",
    "date_of_account_open": "YYYY-MM-DD",
    "current_balance": "$0.00"
  },
  "verified_user_id": "verified user identifier",
  "pending_transactions_confirmed_absent": true,
  "disputes": [{"status": "closed", "belongs_to_target_account": true}],
  "replacement_orders": []
}
JSON
```

See **Eligibility helper contract** for its JSON schema and interpretation. Any `blockers` output means do not offer retention or call the closure tool.

### 4. Review prior retention attempts, obtain/log the reason, and handle retention

Only after all eligibility checks pass:

1. Call `get_closure_reason_history_8293` for the target account and determine whether it has a closure-reason record within the prior year (using the current date). If such a record exists, skip all retention offers and proceed to closure once the customer confirms the request. If the history result is unavailable or its dates cannot be evaluated, resolve the system issue before continuing; do not claim the required check was completed.
2. If no prior-year record exists, ask why the customer wishes to close and map the answer to exactly one permitted value:
   - `annual_fee`
   - `not_using_card`
   - `found_better_card`
   - `unhappy_with_rewards`
   - `simplifying_finances`
   - `negative_experience`
   - `other`
3. Call `log_credit_card_closure_reason_4521` with only the target account ID, verified user ID, and mapped `closure_reason`. A customer who says another card has better benefits maps to `found_better_card`.
4. Address the stated concern without pressure:
   - **Annual fee:** if the customer has been a customer for at least two years, offer a one-year annual-fee waiver. If accepted, calculate an expiration date one year from the current date in `MM/DD/YYYY`, then call `apply_credit_card_account_flag_6147` with `flag_type: "annual_fee_waived"` and `reason: "loyalty_benefit"`. If the customer has been a customer for less than two years, offer a permanent no-annual-fee downgrade instead, preserving history. Do not infer customer tenure from an ambiguous source.
   - **Not using card:** remind the customer of relevant benefits and suggest a recurring subscription if they wish to keep it active.
   - **Found better card:** ask which features matter and, only if an internal alternative is known to offer similar or better benefits, offer help applying rather than closing.
   - **Unhappy with rewards:** discuss available bonus categories and ways to maximize rewards based on spending.
   - **Negative experience:** apologize, gather details, and escalate to a supervisor where warranted; consider a modest goodwill credit only under applicable authority.
5. Make exactly one applicable retention offer by verified card tier if the customer still wants to close:
   - entry tier: 500 bonus points or a $5 statement credit;
   - mid tier: 2,000 bonus points or a $20 statement credit;
   - premium and above: 5,000 bonus points or a $50 statement credit.

Do not infer a tier solely from a product name when the tier is not documented. If the customer already clearly declined an eligible retention offer, record that decision and do not apply points or a statement credit. If they accept an offer, follow the approved benefit process and do not close unless they subsequently make a new, clear closure request.

For an annual-fee downgrade selected by a verified customer, use `downgrade_credit_card_3847` with the same-category target only: `Bronze Rewards Card` for personal cards or `Business Bronze Rewards Card` for business cards. Explain that account history, account number, and credit line are preserved; rewards transfer at the same value; benefits change; and the new card arrives in several business days. This is an alternative to closure, not a closure action.

### 5. Final recheck and close

1. Confirm the customer's final decision to close after any prior-attempt handling or declined offer.
2. Immediately before closure, call `get_pending_replacement_orders_5765` again for the target account. This is required even if it was checked earlier. Do not close unless the response is empty or every returned order is clearly delivered or cancelled.
3. If a new blocker, a changed balance, or a pending transaction is known, stop and explain the exact prerequisite that must be resolved. Do not call the closure tool.
4. Unlock and call `close_credit_card_account_7834` with exactly:

```json
{"credit_card_account_id":"<target account id>","user_id":"<verified user id>"}
```

5. Treat only a successful closure-tool result as confirmation that the account was closed. If the call fails or returns an ambiguous result, do not state that it closed; communicate the failure accurately and use the approved technical-support or escalation path.

### 6. Post-closure communication

After confirmed closure, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards remain redeemable for 45 days after the closure request and are permanently forfeited afterward.
- A full annual-fee refund may apply only if closure occurs within 37 days of the annual fee posting. Confirm the fee-posting date before representing that a refund will occur.
- Closing a card can reduce available credit and affect credit utilization, which may affect the customer's credit score, especially for a high-limit or old account.

For Silver Zoom Card rewards, database `points` represent cash back and redeem at $0.01 per point as a statement credit or credit to the customer's Rho-Bank checking account. State the value only from the current rewards balance; do not redeem rewards without a distinct customer request, appropriate account verification, and the relevant rewards workflow.

## Eligibility helper contract

`scripts/assess_closure_eligibility.py` reads one JSON object from standard input and writes one JSON object to standard output. It performs deterministic assessment only and never calls banking tools or changes account state.

Required fields:

- `as_of_date`: ISO date (`YYYY-MM-DD`).
- `identity_verified`: boolean.
- `closure_authority_confirmed`: boolean.
- `explicit_closure_confirmation`: boolean.
- `verified_user_id`: nonempty string.
- `account`: object with nonempty `account_id`, nonempty `user_id`, ISO `date_of_account_open`, and `current_balance` (number or currency-formatted string).
- `pending_transactions_confirmed_absent`: boolean.
- `disputes`: array from the dispute review. Each item needs `status` and `belongs_to_target_account` boolean.
- `replacement_orders`: array from the replacement-order review. Each item needs `status`.

Optional `final_dispute_statuses` may supply a list of statuses that are clearly fully resolved; its default is `closed` and `resolved`. The replacement final statuses are `delivered` and `cancelled`.

Output contains `eligible` (boolean), `account_age_days` (integer), `blockers` (array of actionable strings), and `checks` (per-check facts). Validate that `eligible` is true and `blockers` is empty before moving to retention or closure. Invalid or missing required data is returned as a blocker, not treated as approval.

## Failure handling

- Never bypass a blocker, substitute another account, or close a card based on stale or incomplete information.
- If the target account cannot be uniquely identified, the customer cannot complete identity verification, or ownership does not match, stop and request the missing information.
- If specialized tool access, tool execution, or output interpretation fails, do not perform the banking action. Escalate or retry only where the operating procedure permits.
- If the customer requests a human at any point, transfer using `transfer_to_human_agents` with the applicable closure-related reason and a factual summary of completed checks and blockers.
