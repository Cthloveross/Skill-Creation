---
name: credit-card-account-closure
version: 1.0.0
description: Safely handle a verified customer's request to close a credit-card account, including eligibility checks, replacement-card blocking, retention protocol, downgrade or fee-waiver alternatives, and final closure communication.
---

# Credit Card Account Closure

Use this Skill when a customer asks to close a credit-card account or clearly indicates that they no longer want to keep one. It supports an agent-operated banking workflow; it does not itself make banking changes.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and prerequisite rules

1. Identify the exact requested account. If the customer has more than one card or the requested card type is ambiguous, ask which account they mean. Confirm that the account belongs to the authenticated customer and that the product is the requested product.
2. Complete standard identity verification before any account-changing action. Confirm at least two of the four identity fields (date of birth, email, phone number, address) with the customer, obtain the current time using `get_current_time`, and call `log_verification` with all fields and that timestamp. A profile lookup or an email supplied solely to locate a profile is not, by itself, confirmation of two identity fields.
3. Do not close, downgrade, apply a fee waiver, make a retention offer, or log a closure reason while any closure-eligibility condition is unmet or unknown. Explain every known blocker and what the customer must resolve.
4. Treat tool errors, missing account data, ambiguous dispute information, or ambiguous replacement-order information as a stop condition. Do not infer that a prerequisite passed.
5. Never close a different account, and never use the balance or rewards of another account to qualify the requested one.

## Required closure eligibility

Before retention or closure processing, establish all of the following for the requested account:

- The outstanding balance is exactly `$0.00`. Pending transactions should post before the customer pays the full statement balance.
- There are no active or pending transaction disputes.
- The account has been open at least 60 days.
- There is no pending replacement-card order.

Use the current date/time and the account opening date to calculate age. For replacement orders, unlock and call `get_pending_replacement_orders_5765` with only `credit_card_account_id`. An empty order collection passes. If orders are returned, closure is blocked unless **every** order is clearly `delivered` or `cancelled`; any non-final status, including `pending` or `shipped`, blocks closure.

Run the replacement-order check again immediately before the actual closure call, even if it was checked earlier. Record the timestamp and outcome in the case record when the runtime provides case notes.

`scripts/evaluate_closure.py` can consistently evaluate supplied account facts. It is advisory only: it neither verifies identity nor substitutes for live tool checks.

### Evaluator input and output

Provide one JSON object on stdin with this shape:

```json
{
  "identity_verified": true,
  "authenticated_user_id": "string",
  "account": {
    "account_id": "string",
    "user_id": "string",
    "current_balance": "currency string, number, or integer cents",
    "date_opened": "MM/DD/YYYY or YYYY-MM-DD",
    "pending_disputes": false
  },
  "as_of": "YYYY-MM-DD or timestamp beginning with YYYY-MM-DD",
  "replacement_orders": [],
  "customer_tenure_start": "optional MM/DD/YYYY or YYYY-MM-DD"
}
```

`pending_disputes` must be an explicit boolean. `replacement_orders` must be an array obtained from the replacement-order check, or `null` if not yet known. The script emits JSON containing `ok`, `eligible`, `blockers`, `facts`, and `retention`. Invoke it through the packaged-script runtime with relative path `scripts/evaluate_closure.py` and the current facts. Before acting, validate its result against the live account and tool responses.

## Workflow

### 1. Verify and assess eligibility

- Verify identity and authority as described above.
- Retrieve the customer’s credit-card accounts if necessary, select the exact account, and validate ownership.
- Check balance, pending disputes, and account age.
- Check replacement orders using `get_pending_replacement_orders_5765`.
- If any requirement fails, tell the customer specifically what remains to be resolved. For example, a nonzero balance must be paid to `$0.00`; do not attempt retention or closure. The customer may return after all blockers are resolved.

### 2. Check prior retention attempts

Only after all eligibility requirements pass, unlock and call `get_closure_reason_history_8293` with:

```json
{"credit_card_account_id":"<requested account id>"}
```

If this account has any closure-reason records within the past year, skip all retention offers and move to final closure processing. Tell the customer that you will proceed with the closure request. Do not use records from another account.

### 3. Understand and log the reason

If there is no prior-attempt record, ask why the customer wants to close the account unless they already gave an unambiguous reason. Map the reason to exactly one permitted value:

- `annual_fee`
- `not_using_card`
- `found_better_card`
- `unhappy_with_rewards`
- `simplifying_finances`
- `negative_experience`
- `other`

Unlock and call `log_credit_card_closure_reason_4521` with exactly these three arguments and no extras:

```json
{
  "credit_card_account_id":"<requested account id>",
  "user_id":"<authenticated user id>",
  "closure_reason":"<permitted value>"
}
```

### 4. Address the concern

Offer an appropriate non-coercive solution.

- **Annual fee:** Establish customer tenure, not merely account age. If the customer has been with the bank for at least two years, offer a one-year annual-fee waiver. If they accept, unlock and call `apply_credit_card_account_flag_6147` with account ID, authenticated user ID, `flag_type` of `annual_fee_waived`, `reason` of `loyalty_benefit`, and `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format. If tenure is under two years, offer a permanent same-category downgrade to a no-annual-fee card instead. Do not claim waiver eligibility when tenure is unknown.
- **Downgrade:** For a personal card, the eligible target is `Bronze Rewards Card`; for a business card, it is `Business Bronze Rewards Card`. Explain that credit limit, account number, account history, and unredeemed rewards value are preserved; benefits and rewards rates change, the downgrade is immediate, and the existing physical card can be used until the replacement arrives. A recently paid annual fee may be eligible for a prorated refund. Only with customer confirmation, unlock and call `downgrade_credit_card_3847` with `credit_card_account_id`, `user_id`, and the applicable `target_card_type`.
- **Not using card:** Remind the customer of relevant card benefits and suggest a recurring subscription if appropriate.
- **Found better card:** Ask what features matter and, if a comparable bank card is known to be available, offer help applying rather than closing.
- **Unhappy with rewards:** Discuss enrollment in bonus categories and ways to maximize rewards based on spending patterns.
- **Negative experience:** Apologize, gather details, and escalate to a supervisor if warranted. Do not promise or apply a goodwill credit without a supported authorization path.

If the customer accepts a waiver or downgrade, complete that accepted alternative and do not close the account unless they make a new, confirmed closure request.

### 5. Make at most one retention offer

If the customer remains eligible and still wishes to close after the concern is addressed, make one offer based on the current card tier:

- Entry tier: 500 bonus points or a $5 statement credit.
- Mid tier: 2,000 bonus points or a $20 statement credit.
- Premium and above: 5,000 bonus points or a $50 statement credit.

Do not make this offer if prior closure-reason history requires retention to be skipped. No tool is specified for applying this offer; do not invent one or represent it as granted unless a supported process is available. If the customer declines, thank them and proceed without pressure.

### 6. Process closure

Before closure, confirm the customer still wants the irreversible closure, re-confirm account ownership, balance, disputes, and account age as necessary, and re-run the replacement-order check immediately before the action. If all prerequisites pass, unlock and call `close_credit_card_account_7834` with only:

```json
{
  "credit_card_account_id":"<requested account id>",
  "user_id":"<authenticated user id>"
}
```

If the call fails or returns an unclear result, do not claim that the account is closed. Explain the status and use normal escalation procedures for a technical-system error if needed.

### 7. Post-closure communication

After a successful closure, tell the customer that a confirmation email and final statement will arrive within several business days. Explain that:

- Remaining rewards may be redeemed for 45 days after submitting the closure request; unredeemed rewards are forfeited after that period.
- A full annual-fee refund is available only if closure occurs within 37 days of the annual-fee posting.
- Closing a credit card can affect credit score by reducing available credit and changing credit utilization, particularly for a high-limit or older account.

Do not promise a fee refund unless the actual fee-posting date establishes eligibility.

## Handling a currently ineligible request

When a live account review shows a positive balance, state the exact amount due if available, ask the customer to pay it and wait for the balance to become `$0.00`, and stop. Do not invoke retention history, log a closure reason, apply a waiver or downgrade, make a retention offer, or call the closure tool until the account is eligible.
