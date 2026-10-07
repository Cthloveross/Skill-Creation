---
name: credit-card-closure-with-retention
version: 1.3.0
description: Safely process one authenticated customer's credit-card closure request. Use for account identification, identity verification, closure eligibility checks, required retention workflow, and the final closure action with rewards and APY disclosures.
---

# Credit-card Closure With Retention

Use this Skill when a customer wants to close a credit card. Process **one specifically identified account at a time**; do not interpret a request to close several cards as authorization to close all of them.

## Required tools

Unlock and use these discoverable agent tools when their corresponding step is reached:

- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_closure_reason_history_8293`
- `log_credit_card_closure_reason_4521`
- `close_credit_card_account_7834`

The annual-fee waiver tool, `apply_credit_card_account_flag_6147`, is needed only when an eligible customer accepts that retention solution.

## Workflow

### 1. Identify the account and verify identity

1. Determine the customer and retrieve their credit-card accounts using the supplied normal banking tools. Match the requested card type to exactly one account. If there is no unique match, ask the customer which account they mean; do not guess.
2. Before accessing or acting on the account, verify identity through the standard process: obtain confirmation of at least two of these four profile fields: date of birth, email, phone number, and address. Retrieve the profile to compare the supplied values.
3. Get the current time and call `log_verification` only after two fields match. Supply every required profile field plus `name`, `user_id`, and the obtained timestamp. Do not perform closure actions without a successful verification record.

The authenticated `user_id` must be the same user ID used in all account-specific calls.

### 2. Check closure eligibility before retention

Use current account data and authoritative tool responses; a customer statement that there are no disputes or replacement orders is not sufficient.

Check all of the following for the selected account:

1. **Disputes:** unlock and call `get_user_dispute_history_7291` with `user_id`. Review disputes relevant to the selected card where card/transaction context is available. Any active or pending/unresolved dispute blocks closure. Treat a status as unresolved unless it is clearly final (for example, closed or resolved); ambiguity blocks closure pending clarification.
2. **Replacement orders:** unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty result passes. If orders are returned, all must be clearly `delivered` or `cancelled`; any pending, shipped, or ambiguous order blocks closure. Run this check immediately before the eventual closure action as well, even if it was checked earlier.
3. **Account age:** calculate age from the account-open date and current date. The account must have been open at least 60 days.
4. **Balance:** current outstanding balance must be exactly $0.00. Do not infer this from transaction history; use the current account record.

If any condition fails, explain the specific blocker(s), including what must be resolved, and stop. Do **not** make a retention offer, log a reason, or call the closure tool for an ineligible account.

### 3. Determine whether retention is required

1. Unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id`.
2. If it reports one or more closure-reason records for this account within the preceding year, skip reason logging and all retention offers. Tell the customer that you will proceed with their closure request.
3. Otherwise, ask for the closure reason if it has not already been provided. Normalize it to exactly one allowed value:
   - `annual_fee`
   - `not_using_card`
   - `found_better_card`
   - `unhappy_with_rewards`
   - `simplifying_finances`
   - `negative_experience`
   - `other`
4. Unlock and call `log_credit_card_closure_reason_4521` using **only** `credit_card_account_id`, `user_id`, and `closure_reason`. Do not append notes or unsupported parameters.

### 4. Address the reason, then make the required retention offer

When no recent closure-reason record exists, complete **both** parts of the protocol before closing: first address the stated reason, then—if the customer still wants to close—make exactly one tier-based retention offer. The reason-specific discussion is not a substitute for the required tier-based offer. Do not pressure the customer.

Address the reason as follows:

- `annual_fee`: for a customer with at least two years of supported relationship tenure, offer a one-year annual-fee waiver. Apply `apply_credit_card_account_flag_6147` only after acceptance, with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format. For shorter tenure, offer a permanent no-annual-fee downgrade that preserves account history; do not claim to execute a downgrade unless a supported tool/process is available. Do not equate a card's opening date with overall customer tenure unless the supplied profile/system explicitly defines it that way.
- `not_using_card`: remind them of relevant card benefits and suggest a recurring subscription if they want to keep it active.
- `found_better_card`: ask which features are preferable and offer help with a similar available Rho-Bank card only if one is actually known.
- `unhappy_with_rewards`: review bonus-category enrollment and ways to maximize rewards.
- `negative_experience`: apologize, gather details, and escalate service complaints when warranted. Do not promise a goodwill credit without authorized support.
- `simplifying_finances` or `other`: acknowledge the concern.

If the customer continues to seek closure after that discussion, make **one** standard retention offer selected from the account's documented tier:

- Entry tier: 500 bonus points **or** $5 statement credit
- Mid tier: 2,000 bonus points **or** $20 statement credit
- Premium and above: 5,000 bonus points **or** $50 statement credit

Do not infer tier from a card name. If a supported profile or account source does not identify the tier, say that the applicable offer requires confirmation and use a supported account process to obtain it; do not fabricate an amount. Once a valid tier-based offer is made, the customer may decline it. If the customer declines the reason-specific solution and then declines this one offer—or if recent history permitted skipping all retention—accept the decision and proceed without further pressure.

If the customer accepts any retention solution, perform only the supported accepted action and do not close the account unless they subsequently make a new, clear closure request.

### 5. Close the account

Immediately before initiating closure, re-check pending replacement orders as described in Step 2. If the check passes and all other eligibility conditions remain true, unlock and call `close_credit_card_account_7834` with:

```json
{"credit_card_account_id":"<selected account id>","user_id":"<authenticated user id>"}
```

Do not close a different card, and do not retry a closure action whose outcome is unknown. If a tool reports failure or ambiguous completion, report that accurately and use the supported escalation path rather than claiming closure.

### 6. Required customer communication

After successful closure, confirm that a confirmation email and final statement will arrive within several business days. Also communicate:

- Remaining rewards may be redeemed for 45 days after the closure request; unredeemed rewards are then forfeited.
- For cards whose stored rewards are cash-back represented as points, statement-credit and linked Rho-Bank checking-account redemption are valued at $0.01 per point, subject to the applicable minimum redemption. Do not state that rewards are already redeemed unless a supported redemption action succeeded.
- A full annual-fee refund may apply only if closure occurs within 37 days after the annual fee posted.
- Closing a card may affect credit utilization and credit score.
- If the card is eligible and linked to a Green Account (savings), closure can remove that card's Green Account APY bonus. Do not state a specific current linked bonus unless it is supported by the customer's account information.

Keep disclosures factual and do not use rewards, fee refunds, or APY effects to override the customer's closure decision.

## Safety and failure handling

- Never use account data for a different customer, and never rely on a name match alone for identity verification.
- Never replace required tool checks with customer assurances.
- Account age, balance, dispute status, and replacement-order status are all hard blockers.
- Unsupported actions, unavailable tools, missing account tier, missing reason, or ambiguous responses must be clarified or escalated; do not fabricate a result.
- Record only the required reason fields in `log_credit_card_closure_reason_4521`; its strict three-argument interface must be honored.
