---
name: credit-card-closure-and-retention
version: 1.0.0
description: Safely handles a verified customer's request to close a credit card account by enforcing closure prerequisites before retention, documenting the closure reason and retention path when permitted, and using the authorized closure workflow.
---

# Credit Card Closure and Retention

Use this Skill when a customer requests closure of a credit card account, including when they mention a competing card, annual fee, low usage, rewards, or a negative experience. It applies to personal and business cards. It does not authorize closure without successful identity verification and all prerequisite checks.

## Required runtime inputs

At runtime, obtain the authenticated `user_id`, the intended `credit_card_account_id`, the account record, and enough information to check:

- current outstanding balance;
- whether there are active or pending transaction disputes;
- account opening date (or account age);
- replacement-card-order status;
- account card type, rewards balance, and, if retention is reached, the applicable card tier.

Do not select an account based only on a similar card name. Confirm that the account belongs to the verified customer and is the requested card.

## Procedure

### 1. Verify identity and identify the account

1. Follow the normal identity-verification procedure. Confirm **two of the four** identity fields: date of birth, email, phone number, and address. Do not treat a name alone as one of those two fields.
2. Retrieve the full profile only as needed to compare customer-provided values. Once two fields are confirmed, call `log_verification` with all of its required fields and a timestamp obtained from `get_current_time`.
3. Retrieve the customer's credit card accounts and identify the requested account. Confirm ownership, card type, account ID, balance, opening date, and rewards balance.
4. If the customer cannot be verified, account ownership is unclear, or the requested account is absent, do not disclose additional account information or process closure. Use the normal supported escalation path if necessary.

### 2. Check closure eligibility before any retention activity

All of the following must be satisfied. A failed or unknown check stops the process; do **not** log a closure reason, make a retention offer, downgrade, waive a fee, or invoke closure.

1. **Disputes:** confirm there are no active or pending transaction disputes. A customer assertion alone is not a substitute for an available authoritative check. If the available runtime has no way to resolve an uncertain dispute status, explain that eligibility cannot yet be confirmed and do not close.
2. **Replacement cards:** immediately before closure workflow, unlock and call `get_pending_replacement_orders_5765` with exactly `credit_card_account_id`. An empty order collection passes. If any order is not clearly `delivered` or `cancelled` (including `pending`, `shipped`, unknown, or an ambiguous response), closure is blocked until delivery or cancellation is confirmed. Record the timestamp and outcome in the normal case record when that facility exists.
3. **Account age:** the account must be open at least 60 days.
4. **Balance:** current outstanding balance must be exactly $0.00. If not, ask the customer to wait for pending transactions to post and pay the full statement balance before retrying.

`scripts/assess_closure.py` can consistently assess structured eligibility facts, but it does not query systems or substitute for required banking-tool checks.

### 3. Check prior retention attempts

Only after all eligibility checks pass, unlock and call `get_closure_reason_history_8293` with exactly `credit_card_account_id`.

- If it returns any closure-reason record within the past year, skip all retention activity and proceed to the closure decision in Step 6.
- If no such record exists, continue to Step 4.
- If the result does not establish whether a record exists in the past year, do not assume it is clear; resolve the ambiguity before offering retention.

### 4. Log and address the customer's reason

Ask for the reason if it is not already clear. Map it to one allowed value and call `log_credit_card_closure_reason_4521` with **only**:

- `credit_card_account_id`
- `user_id`
- `closure_reason`: one of `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`

Do not add tool arguments. Address the concern without pressure:

- `annual_fee`: for a customer of at least two years, offer a one-year loyalty waiver. If accepted, use `apply_credit_card_account_flag_6147` with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`. For less than two years, offer the relevant no-annual-fee downgrade instead.
- A business card can downgrade only within the business category, to `Business Bronze Rewards Card`; a personal card can downgrade only to `Bronze Rewards Card`. Confirm acceptance and benefit changes before calling `downgrade_credit_card_3847`. Downgrades preserve account history, account number, credit line, and reward value.
- `not_using_card`: explain relevant benefits and suggest a recurring subscription if appropriate.
- `found_better_card`: ask which features matter and offer help applying for a comparable Rho-Bank card only if one is actually available.
- `unhappy_with_rewards`: review available bonus-category enrollment and lawful ways to maximize rewards.
- `negative_experience`: apologize, gather details, and escalate service issues when warranted.

Do not offer a downgrade merely because the customer wants to close for a reason other than annual fees unless the customer explicitly asks to downgrade to avoid annual fees.

### 5. Make one retention offer when required

If there was no prior attempt and the customer still wants to close after Step 4, make one offer based on the verified card tier:

- entry tier: 500 bonus points or $5 statement credit;
- mid tier: 2,000 bonus points or $20 statement credit;
- premium and above: 5,000 bonus points or $50 statement credit.

Use an authoritative tier classification. Do not infer a tier from an unsupported card-name convention. If no classification is available, resolve that data gap rather than inventing an offer.

### 6. Close only after the required decision point

If the customer declines the retention offer, or retention was skipped due to a prior attempt, thank them and unlock/call `close_credit_card_account_7834` with the exact `credit_card_account_id` and verified `user_id`. Do not add unrecognized parameters. Communicate success only after the tool reports success.

When closure proceeds, tell the customer:

- a confirmation email and final statement arrive within several business days;
- unredeemed rewards may be redeemed for 45 days after the closure request, then are permanently forfeited;
- a full annual-fee refund applies only when closure is within 37 days of the annual-fee posting.

For cash-back cards, backend `points` represent cash back at $0.01 per point when redeemed as a statement credit or checking-account credit. This includes Business Silver Rewards Card. The EcoCard's sustainability points also redeem at $0.01 per point. Do not claim a refund or redemption has occurred unless the applicable system confirms it.

## Script interface

`scripts/assess_closure.py` reads one JSON object from standard input and emits one JSON object to standard output. It accepts this schema:

```json
{
  "current_balance": "0.00",
  "account_age_days": 61,
  "pending_disputes": false,
  "replacement_orders": [],
  "card_type": "optional card type",
  "reward_points": 0
}
```

Alternatively, provide `opened_date` and `current_date` instead of `account_age_days`. Dates may be `MM/DD/YYYY`, `YYYY-MM-DD`, or a timestamp beginning with one of those formats. `replacement_orders` is an array of objects with a `status` field. `delivered` and `cancelled` are final; all other statuses block closure.

Example runtime call (with values obtained at runtime, not copied from a case):

```text
run_skill_script(
  relative_path="scripts/assess_closure.py",
  input_json={
    "current_balance": "0.00",
    "account_age_days": 60,
    "pending_disputes": false,
    "replacement_orders": []
  }
)
```

Validate the result before proceeding: `input_errors` must be empty, `eligible` must be `true`, and `blockers` must be empty. An `eligible: false` result means explain and resolve each listed blocker, then obtain fresh facts and repeat the eligibility checks. The script never performs bank actions and its recommendation does not itself close an account.
