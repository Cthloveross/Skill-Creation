---
name: credit-card-closure-workflow
description: Verify identity, determine eligibility, complete required retention steps, and safely process a Rho-Bank credit-card closure request. Use for a customer asking to close a specific credit card account.
---

# Credit Card Closure Workflow

Use this Skill to handle **one specifically identified credit-card account at a time**. Do not close other cards merely because a customer says they want to close several cards.

## Required information and tools

Obtain the authenticated `user_id` and the target `credit_card_account_id`. Use the ordinary account/profile lookup tools available in the runtime to identify the account. Confirm that the account belongs to the authenticated user and that its card type matches the card the customer named.

The following specialized tools must be unlocked before calling them with `call_discoverable_agent_tool`:

- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_closure_reason_history_8293`
- `log_credit_card_closure_reason_4521`
- `apply_credit_card_account_flag_6147` (only for an eligible annual-fee waiver)
- `close_credit_card_account_7834`

Unlock only the tools needed by the path being followed. Specialized tool arguments must be JSON strings and must exactly use the documented fields.

## 1. Verify identity first

Before discussing account-specific details or processing closure, verify the customer using **at least two of these four profile fields**: date of birth, email, phone number, and address.

1. Look up the claimed customer profile by the customer-provided identifier.
2. Ask for enough additional verification fields to reach two matches. Do not present the stored values as hints.
3. Compare the supplied values against the profile.
4. If two fields match, get the current timestamp with `get_current_time` and call `log_verification` with the complete retrieved profile values and `time_verified`.
5. If identity cannot be verified, do not inspect or alter the account. Ask for another verification field or use the appropriate supported escalation path.

A customer name identifies a likely profile but is not a substitute for two of the four verification fields.

## 2. Identify the requested account

Use `get_credit_card_accounts_by_user` for the verified user. Match the requested card type to exactly one account. If no unambiguous match exists, ask the customer to identify the card; do not guess from balances, rewards, or another card's data.

Record the target account's opening date, displayed balance, card type, and reward-points balance for the subsequent checks and communication.

## 3. Check closure eligibility before retention

All four conditions are required. Check them before making a retention offer, logging a closure reason, or attempting closure.

1. **Disputes:** unlock and call `get_user_dispute_history_7291` with `{"user_id":"..."}`. Review all returned disputes. Any active, open, pending, or under-review dispute blocks closure. If status semantics are unclear, treat the account as blocked until clarified; do not assume that a missing transaction history means no dispute.
2. **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with `{"credit_card_account_id":"..."}`. An empty order set passes. If any order is not clearly `delivered` or `cancelled` (including pending or shipped), closure is blocked. This check must be performed immediately before an eventual closure call, so repeat it after a lengthy interaction or before processing if necessary.
3. **Account age:** calculate the number of elapsed calendar days from `date_of_account_open` through the current date. It must be at least 60 days. Use `get_current_time` if the date is not already reliably available.
4. **Balance:** the target account's outstanding/current balance must be exactly `$0.00`. If transactions or account data indicate an uncertain/pending balance, wait for posting and re-check rather than treating it as zero.

If any condition fails, clearly state only the applicable blocker(s) and what must be resolved (dispute resolution, replacement delivery/cancellation, reaching 60 days, or full payoff). Do **not** make retention offers and do **not** call the closure tool. The request may be resumed after the condition is resolved.

## 4. Check prior closure-reason attempts

For an eligible account, unlock and call `get_closure_reason_history_8293` with:

```json
{"credit_card_account_id":"<target account id>"}
```

If the account has closure-reason records within the prior year, skip reason logging and all retention offers. Respect the customer's decision and go directly to the final immediate replacement-card re-check and closure step.

If there is no such record, obtain the customer's reason if it was not already provided. Normalize it to exactly one permitted value:

- `annual_fee`
- `not_using_card`
- `found_better_card`
- `unhappy_with_rewards`
- `simplifying_finances`
- `negative_experience`
- `other`

Unlock and call `log_credit_card_closure_reason_4521` with **only**:

```json
{
  "credit_card_account_id":"<target account id>",
  "user_id":"<verified user id>",
  "closure_reason":"<allowed value>"
}
```

Do not add reason text, timestamps, or any other parameters.

## 5. Address the concern and retention

Address the stated reason concisely and without pressure. For example, discuss missed benefits for non-use, ask which features a better card has, suggest bonus-category enrollment for rewards concerns, or apologize and gather details for a negative experience. For an annual-fee concern:

- If the customer has been with the bank for at least two years, an annual fee waiver for one year may be offered. If accepted, use `apply_credit_card_account_flag_6147` with the target account and verified user, `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from today formatted `MM/DD/YYYY`.
- If tenure is under two years, offer a permanent downgrade to a no-annual-fee card while preserving account history. Do not claim to execute a downgrade unless a supported tool/process is available.

If the customer still wishes to close and has not already clearly declined retention, make one appropriate retention offer based on the account's documented tier:

- entry tier: 500 bonus points or a $5 statement credit;
- mid tier: 2,000 bonus points or a $20 statement credit;
- premium or above: 5,000 bonus points or a $50 statement credit.

Do not infer a tier from a card name unless the runtime explicitly supplies the tier. If tier cannot be determined, ask or use an approved source rather than fabricating an offer. If the customer explicitly declines retention, do not pressure them or repeat an offer. If an accepted offer has no supported fulfillment tool, explain that it requires the available approved process; do not falsely claim it was applied.

After a declined retention offer, or after prior-history rules require offers to be skipped, continue to closure.

## 6. Close the account

Immediately before closing, ensure the balance and dispute findings remain valid and repeat `get_pending_replacement_orders_5765` if the earlier result is no longer immediate/current. Do not proceed when any eligibility fact is stale, failed, or ambiguous.

Unlock `close_credit_card_account_7834` and call it with exactly:

```json
{
  "credit_card_account_id":"<target account id>",
  "user_id":"<verified user id>"
}
```

Treat the tool response as authoritative. If it reports an error or failure, do not say the account is closed; explain the reported actionable issue or escalate through the supported path. Never retry an operation whose result is unknown.

## 7. Required closing communication

After confirmed closure, tell the customer that they will receive a confirmation email and final statement within several business days. Also state:

- Remaining rewards may be redeemed for 45 days after the closure request; after that they are permanently forfeited.
- A full annual-fee refund may apply only when closure occurs within 37 days of the annual fee posting.
- Closing a card can reduce available credit and can affect utilization and credit score.

For any cash-back card represented in the backend as points, explain a reward balance as `points × $0.01`. This includes the Green Rewards Card; its stored points are cash back, not a separate points currency. Do not promise redemption, a refund, or a specific annual-fee result unless the relevant account facts and supported action are available.

## Safety and completion checks

Before communicating success, confirm all of the following:

- identity verification was logged after two valid profile-field matches;
- the target account belongs to the verified customer;
- balance was zero, age was at least 60 days, no active/pending dispute existed, and no non-final replacement order existed;
- prior reason history was checked;
- the reason was logged only when required and using an allowed enum value;
- retention was skipped only for ineligibility, qualifying prior history, or a clear customer decline;
- the close tool returned confirmed success; and
- post-closure rewards, annual-fee, confirmation/final-statement, and credit-impact information was provided.
