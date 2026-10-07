---
name: credit-card-closure-retention
version: 1.0.0
description: Handle an authenticated request to close a Rho-Bank credit card, including mandatory closure eligibility checks, prior-retention abuse prevention, reason logging, compliant retention/downgrade handling, and final closure communication. Use when the customer wants to close a credit card or asks about alternatives before confirming closure.
---

# Credit Card Closure and Retention

## Scope and safety rules

Use this Skill for a specific, authenticated credit-card account. Work only on the account that the customer identifies and whose ownership is confirmed. Treat closure as irreversible: do not close an account merely because the customer asked about retention, alternatives, or a downgrade. Obtain or rely on a clear current instruction to close, and ask again if the customer has expressly withheld confirmation.

Do not invent a card tier, benefit, reward rate, retention amount, fee-posting date, or product comparison. In particular, a card name is not evidence of its retention tier unless an authoritative source available in the task explicitly maps it. Do not claim that a Rho-Bank card competes with an external card until the customer identifies the relevant external-card features and a supported comparison establishes equivalent or better benefits.

Perform required internal actions with the normal banking tools. Scripts in this package only calculate dates and amounts; they never perform banking actions.

## Inputs to collect or reuse

Reuse facts already confirmed in the conversation and public task inputs; do not needlessly ask the customer to repeat them. Establish:

- authenticated `user_id` and target `credit_card_account_id`;
- customer identity confirmation of at least two of date of birth, email, phone number, and address;
- the target account's card type, open date, balance, rewards balance, and category (personal/business if a downgrade is considered);
- the customer's closure reason and, for a competing-card reason, the specific features that matter;
- an unambiguous choice after any retention discussion.

When two of the four identity fields are confirmed against the profile, record verification before account servicing:

1. Call `get_current_time` if a verified timestamp is not already available.
2. Call `log_verification` with the complete profile fields required by its schema (`name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`).

A lookup value by itself is not a customer confirmation. Customer statements in the active transcript can be used when they match the retrieved profile. Never substitute missing profile data with guessed data.

## Mandatory workflow

### 1. Locate the account and verify closure eligibility

Retrieve the customer's credit-card accounts, identify exactly one requested account, and validate the following in this order. If a prerequisite fails, tell the customer what must be resolved and stop: do **not** make retention offers, log a retention reason, downgrade, or close the account.

1. **Pending disputes.** Unlock and call `get_user_dispute_history_7291` with `user_id`. Review every returned dispute relevant to the target card. Treat active/non-final statuses (such as `open` or `under_review`) as blocking. A closed dispute is not pending. If the tool does not provide enough card context to determine whether an active dispute belongs to the target account, do not assume eligibility; explain the limitation and use an appropriate human/system escalation path.
2. **Replacement cards.** Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty order list passes. If any order is not clearly `delivered` or `cancelled`, closure is blocked.
3. **Account age.** Confirm the account has been open at least 60 calendar days. Use the current date and `scripts/closure_math.py` when a date calculation is needed.
4. **Outstanding balance.** Confirm that the account's current outstanding balance is exactly $0.00. Pending transactions or an ambiguous balance must be resolved before closure.

Do not treat an absence of transactions as proof that there are no disputes, and do not infer replacement status from account data.

### 2. Check prior retention attempts

Only after all closure prerequisites pass, unlock and call `get_closure_reason_history_8293` with exactly `credit_card_account_id`.

- If it reports a closure-reason record for that account in the past year, do not make any retention offer and do not log another reason. Tell the customer that you will proceed with their closure request, subject to their current clear confirmation, then follow Step 5.
- If no such record exists, continue to reason logging.

### 3. Understand and log the reason

Ask for the reason if it is not already clear. Map the customer's statement to exactly one permitted value:

`annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

Unlock and call `log_credit_card_closure_reason_4521` with **only**:

- `credit_card_account_id`
- `user_id`
- `closure_reason`

For example, a customer who says another bank's card has better rewards has supplied `found_better_card`, even if they have not yet named the features. Log the known reason, then ask which rewards, fees, protections, or other features attracted them.

### 4. Address the concern without unsupported promises

Tailor the discussion to the logged reason:

- **Annual fee:** Customers with at least two years of tenure may be offered a one-year annual-fee waiver. Only after they accept, unlock and call `apply_credit_card_account_flag_6147` with the exact account and user IDs, `flag_type: annual_fee_waived`, `reason: loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`. Use the helper for leap-year-safe calculation. For less than two years, offer a permanent same-category no-fee downgrade instead.
- **Not using card:** Remind them of applicable benefits and suggest a recurring subscription only; do not create one without consent.
- **Found better card:** Ask which features attracted them. Offer help applying for another Rho-Bank card only if supported information establishes similar or better benefits. If the comparison cannot be established, say so plainly rather than speculating.
- **Unhappy with rewards:** Review available bonus-category enrollment and legitimate reward-maximization options when the relevant information is available.
- **Negative experience:** Apologize, collect details, and escalate to a supervisor if warranted. Do not promise a goodwill credit without authorized policy/tool support.

For rewards balances on the listed cash-back cards, database “points” are cash back at $0.01 per point. The helper can present the balance in dollars. This conversion does not establish an earning rate or a comparative product benefit.

### 5. Make a retention offer or perform an authorized downgrade

If the customer still wants to close after the concern has been addressed, make one retention offer based on an **authoritatively known** tier:

- entry tier: 500 bonus points or a $5 statement credit;
- mid tier: 2,000 bonus points or a $20 statement credit;
- premium and above: 5,000 bonus points or a $50 statement credit.

If the available records do not classify the account into one of those tiers, do not guess based on branding. Explain that a tier-specific offer cannot be quoted until its tier is confirmed, and use an approved escalation route if one exists. Never silently apply a reward or statement credit: the supplied materials contain no tool or authority for doing so.

For an accepted eligible downgrade, first explain that credit limit, account number, account history, and unredeemed reward value are preserved, while rewards/benefits change; it is immediate and the existing physical card works until the replacement arrives. Unlock and call `downgrade_credit_card_3847` using the same-category target:

- personal: `Bronze Rewards Card`
- business: `Business Bronze Rewards Card`

Use only after explicit customer consent. Do not offer a downgrade as a substitute for a competing-card comparison unless the customer asks for it or the annual-fee scenario authorizes it.

### 6. Close only after a clear final decision

If the customer declines the offer, is ineligible for offers because of prior retention history, or continues to request closure, thank them without pressure. Before executing closure, ensure the current dialogue contains clear confirmation. A statement such as “before I confirm” means confirmation is still pending.

After confirmation, unlock and call `close_credit_card_account_7834` with `credit_card_account_id` and `user_id`. Report the result accurately. Then communicate:

- a confirmation email and final statement arrive within several business days;
- unredeemed rewards remain redeemable for 45 days after the closure request and are then forfeited;
- a full annual-fee refund may be available if closure occurs within 37 days of the fee posting. State this conditionally unless the posting date is actually known.

If a required tool fails, returns ambiguous data, or lacks the information needed for a safe decision, do not retry an action that may have succeeded and do not claim completion. Explain the blocker and use the available human-transfer route when necessary. For an unresolved closure request, `account_closure_request` is the appropriate transfer reason.

## Helper script

`scripts/closure_math.py` reads one JSON object from stdin and emits one JSON object to stdout. It performs deterministic calculations only.

Input schema:

```json
{
  "opened_date": "MM/DD/YYYY or YYYY-MM-DD, optional",
  "today": "MM/DD/YYYY, YYYY-MM-DD, or a timestamp beginning with either format; optional",
  "annual_fee_posted_date": "MM/DD/YYYY or YYYY-MM-DD, optional",
  "reward_points": "nonnegative number, optional"
}
```

`today` is required whenever a date-derived field is requested. Output includes any calculable fields: `account_age_days`, `meets_60_day_minimum`, `one_year_waiver_expiration`, `annual_fee_full_refund_eligible`, and `cash_back_value_dollars`. It emits `errors` for invalid or missing dependent inputs.

Runnable form, with a runtime-created JSON payload containing the live account dates and/or rewards balance:

```sh
python3 scripts/closure_math.py < payload.json
```

Validate that `errors` is empty before relying on a calculated result. For a waiver, verify that `one_year_waiver_expiration` has `MM/DD/YYYY` formatting before sending the flag tool call.
