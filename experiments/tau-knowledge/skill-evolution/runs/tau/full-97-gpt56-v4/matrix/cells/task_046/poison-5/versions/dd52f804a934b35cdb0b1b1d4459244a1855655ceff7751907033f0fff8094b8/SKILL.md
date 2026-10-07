---
name: credit-card-closure-workflow
description: Safely handle a customer's request to close a credit card. Use when a customer identifies a credit card for closure, including retention and eligibility handling. The workflow verifies identity, confirms mandatory eligibility before any retention or closure, records the reason when permitted, and uses the declared closure tools.
---

# Credit Card Closure Workflow

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety rules

Use this workflow only for a request to close a credit card account. Do not close a card based solely on a name, an account identifier supplied by an unauthenticated person, or a stated intent. Never make retention offers, apply a retention benefit, log a closure reason, or call the closure tool until the eligibility gate below has passed.

A customer lookup is not identity verification. Verify identity by having the customer confirm at least two of the following fields against the account profile: date of birth, email address, phone number, and street address. Once two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` with the complete profile values and that timestamp. If verification cannot be completed, do not disclose account details or take account action.

## Runtime tool preparation

The specialized tools named in this workflow are agent-discoverable. Before calling one for the first time, unlock it with `unlock_discoverable_agent_tool` using exactly its documented name, then use `call_discoverable_agent_tool` with a JSON-string `arguments` object.

Tools used by this workflow:

- `get_closure_reason_history_8293` with `{ "credit_card_account_id": "..." }`
- `log_credit_card_closure_reason_4521` with exactly `{ "credit_card_account_id": "...", "user_id": "...", "closure_reason": "..." }`
- `apply_credit_card_account_flag_6147` with `{ "credit_card_account_id": "...", "user_id": "...", "flag_type": "annual_fee_waived", "expiration_date": "MM/DD/YYYY", "reason": "loyalty_benefit" }`
- `close_credit_card_account_7834` with `{ "credit_card_account_id": "...", "user_id": "..." }`

Treat an unavailable tool, ambiguous result, or failed tool call as a reason not to claim the action succeeded. Explain the limitation and, if needed, transfer to a human using the appropriate closure-related reason.

## Procedure

### 1. Identify the customer and the exact card

1. Obtain a user ID, full name, or email address and look up the customer with the matching read-only user lookup tool.
2. Complete the two-field identity verification described above and log it. Confirm the requester is authorized to act for the identified user.
3. Call `get_credit_card_accounts_by_user` using the authenticated user ID.
4. Select only the card the customer requested. If multiple cards have a similar type or the requested card remains ambiguous, ask the customer to identify it; do not guess. Confirm the selected account belongs to the authenticated user.
5. Review the card type, open date, balance, and rewards returned. Do not reveal unrelated account details beyond what is needed to identify the requested card.

### 2. Mandatory eligibility gate

Confirm every condition before discussing retention or closure, in this order:

1. **Pending disputes:** no active or pending transaction disputes. If needed, inspect the customer's credit-card transactions and any available dispute status; a customer assertion alone is not sufficient where account data indicates otherwise.
2. **Pending replacement card:** no replacement card ordered but not received or activated.
3. **Account age:** the account has been open for at least 60 days, calculated from its open date using the current date.
4. **Outstanding balance:** the selected card's current balance is exactly $0.00.

If any condition is unmet or cannot be confirmed, clearly tell the customer the specific prerequisite that must be resolved. Do **not** proceed with retention offers, closure-reason logging, or closure. For a remaining balance, state the amount due and that it must be paid to $0.00 before closure; do not initiate a payment unless the customer separately requests one and its own requirements are satisfied.

### 3. Check retention-history restriction

Only after eligibility passes, unlock and call `get_closure_reason_history_8293` for the selected account.

- If it returns one or more closure-reason records in the prior year, skip all retention steps. Tell the customer that you will proceed with the closure request, then obtain confirmation to close if it has not already been clearly given and move to Step 6.
- If no such recent record exists, continue to Step 4.
- If the history result does not establish whether recent records exist, stop rather than offering retention or closing.

### 4. Record the closure reason

Ask the customer for the reason if it has not already been clearly provided. Map only an unambiguous customer reason to one permitted value:

- annual fee concern → `annual_fee`
- does not use the card → `not_using_card`
- found another/better card → `found_better_card`
- unhappy with rewards → `unhappy_with_rewards`
- simplifying finances → `simplifying_finances`
- negative service experience → `negative_experience`
- another stated reason → `other`

Unlock and call `log_credit_card_closure_reason_4521` with only its three allowed arguments. Do not add notes, a timestamp, or extra parameters. If the customer's stated reason spans multiple categories, ask which is primary before logging.

### 5. Address the concern and make one retention offer

Address the logged reason appropriately:

- For an annual-fee concern, determine whether the customer has been with the bank for at least two years. If yes, offer a one-year fee waiver. Only if the customer accepts, unlock and call `apply_credit_card_account_flag_6147` with `annual_fee_waived`, `loyalty_benefit`, and an expiration date exactly one year from the current date in `MM/DD/YYYY` format. If under two years, offer a permanent downgrade to a no-annual-fee card while preserving account history; do not represent a downgrade as completed unless a supported tool completes it.
- For non-use, remind the customer of card benefits and suggest a recurring subscription.
- For a better card, ask which features attracted them and, if applicable, offer help applying for a comparable Rho-Bank card rather than closing the current card.
- For rewards dissatisfaction, review available bonus-category enrollment and suggest reward-maximization options based on spending patterns.
- For a negative experience, apologize, gather details, and escalate to a supervisor if warranted; a goodwill credit requires separately supported authorization.

If the customer still wants to close, make no more than one retention offer based on the selected card tier:

- Entry tier: 500 bonus points or a $5 statement credit.
- Mid tier: 2,000 bonus points or a $20 statement credit.
- Premium and above: 5,000 bonus points or a $50 statement credit.

Do not apply or promise an offer that the available tools do not support. If the customer declines, does not wish to discuss retention, or the history restriction required skipping it, continue without pressure.

### 6. Confirm and close

Before an irreversible closure, confirm that the customer still wants the **identified account** closed, summarize any consequential facts (including unredeemed rewards), and confirm there is no remaining balance or other changed eligibility condition. Then unlock and call `close_credit_card_account_7834` with the selected credit-card account ID and authenticated user ID.

Only report closure as complete after the tool returns a successful result. If it succeeds, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; they are forfeited afterward.
- If an annual fee posted recently, a full refund may be available if closure occurs within 37 days of the fee charge.

For cash-back cards, including the Business Silver Rewards Card, rewards stored as points represent cash back at **1 point = $0.01** when redeemed as a statement credit or a credit to the customer's Rho-Bank checking account. State this conversion accurately when discussing remaining rewards.

## Required execution record

In the final response, state the selected card (without exposing unnecessary identifiers), whether identity verification and each eligibility condition passed, whether retention was skipped or offered and the customer's decision, and the closure tool outcome. When closure cannot proceed, state the exact blocking condition and the customer action required; do not imply that a closure request has been submitted.
