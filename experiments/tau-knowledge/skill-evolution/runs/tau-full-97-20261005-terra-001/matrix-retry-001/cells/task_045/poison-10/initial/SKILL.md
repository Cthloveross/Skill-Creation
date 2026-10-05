---
name: credit-card-closure-workflow
description: Safely process or prepare a Rho-Bank credit-card account closure request. Use for identity verification, closure eligibility checks, retention handling, downgrade alternatives, and final closure communication.
---

# Credit Card Closure Workflow

Use this Skill when a customer asks to close a credit card. It enforces the required eligibility gates before any retention offer or closure action. Do not substitute a different account merely because another customer account is eligible.

## Required runtime information

Obtain and confirm:

- Authenticated customer's `user_id`.
- Intended `credit_card_account_id` and card type, selected from the customer's accounts.
- Current account balance and open date.
- The customer's confirmation of at least two of: date of birth, email, phone number, address.
- A fresh dispute-history result and a fresh replacement-order result immediately before closure.
- The customer's primary closure reason, if eligibility permits the retention workflow.
- Whether a retention offer has been declined, or whether the customer instead chooses a downgrade where applicable.

Never expose profile data as an identity challenge. Ask the customer to supply or confirm fields, compare them to the profile, then log verification only after two fields match.

## Tool sequence

1. **Identify and verify.** Locate the user and list their accounts using the normal account lookup tools. Confirm that the requested card is unambiguous and belongs to the authenticated user. Retrieve the profile, obtain two matching identity confirmations, get the current time, and call `log_verification` with all fields from the verified profile and `time_verified`.
2. **Check closure eligibility before retention.** Confirm from the selected account that balance is exactly $0.00 and account age is at least 60 days. Unlock and call:
   - `get_user_dispute_history_7291` with `user_id`;
   - `get_pending_replacement_orders_5765` with `credit_card_account_id`.

   Any active/pending dispute blocks closure. A replacement result blocks closure if any order is not clearly `delivered` or `cancelled`. Treat missing, malformed, partial, or ambiguous results as a blocker; retry or escalate rather than closing.
3. **Stop on any blocker.** Explain only the applicable prerequisite(s): pay the full balance after pending transactions post, wait for dispute resolution, wait until day 60, or finish/cancel the replacement order. Do **not** make retention offers, log a closure reason, downgrade, or call the closure tool while an eligibility requirement is unmet.
4. **Check prior retention attempts.** Once eligible, unlock and call `get_closure_reason_history_8293` using the account ID. If there is a closure-reason record within the past year, skip all retention offers and proceed to the customer's closure decision.
5. **Reason and retention (only if no recent record).** Ask for one primary reason and map it exactly to one permitted value: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`. Unlock and call `log_credit_card_closure_reason_4521` with exactly `credit_card_account_id`, `user_id`, and `closure_reason`; do not add parameters. Address the concern, then make one card-tier offer if the customer still wishes to close:
   - entry tier: 500 points or $5 statement credit;
   - mid tier: 2,000 points or $20 statement credit;
   - premium and above: 5,000 points or $50 statement credit.

   If the reason is an annual fee and the customer has at least two years' tenure, an annual-fee waiver may be offered using `apply_credit_card_account_flag_6147` only after the customer accepts. Its exact arguments are account ID, user ID, `flag_type: annual_fee_waived`, an expiration date one year from today in `MM/DD/YYYY`, and `reason: loyalty_benefit`.
6. **Downgrade alternative.** For annual-fee concerns and tenure below two years, offer a no-annual-fee downgrade rather than a waiver. If accepted, unlock and call `downgrade_credit_card_3847` with account ID, user ID, and the same-category target: `Bronze Rewards Card` for personal cards or `Business Bronze Rewards Card` for business cards. Explain that account number, credit limit, history, and unredeemed rewards transfer, while benefits/rates change. Do not downgrade without explicit customer consent.
7. **Close only after an explicit final decision.** If the eligible customer declines the applicable retention offer, or retention was skipped due to prior attempts, thank them without pressure. Unlock and call `close_credit_card_account_7834` with exactly `credit_card_account_id` and `user_id`. Do not close if the customer accepts retention, chooses downgrade, is undecided, or eligibility data is stale/uncertain.

## Required closure communication

When closure is submitted, state that a confirmation email and final statement will arrive within several business days. Inform the customer that unredeemed rewards remain redeemable for 45 days after the closure request and are forfeited afterward. For cash-back cards, stored points represent cash back at 1 point = $0.01; use `points / 100` when communicating the available cash value. If an annual fee posted within 37 days, advise that a full refund may be available.

Closing may reduce total available credit and increase utilization, potentially affecting the customer's credit score.

## Deterministic eligibility helper

`scripts/assess_closure_eligibility.py` evaluates supplied account, dispute, and replacement-order facts without calling banking tools. It does not replace the mandatory fresh tool checks.

Input JSON schema:

```json
{
  "account": {
    "current_balance": "$0.00",
    "date_of_account_open": "YYYY-MM-DD",
    "card_type": "optional card type",
    "reward_points": 0
  },
  "as_of": "YYYY-MM-DD",
  "disputes": [{"status": "closed"}],
  "replacement_orders": [{"status": "delivered"}]
}
```

`disputes` and `replacement_orders` must be present and be arrays from fresh checks. The script emits JSON with `eligible`, structured `blockers`, account age, and a `reward_cash_value` when points are supplied. Any unknown dispute/order status is conservatively blocking.

Runnable invocation example:

```sh
python3 scripts/assess_closure_eligibility.py <<'JSON'
{"account":{"current_balance":"$0.00","date_of_account_open":"2024-01-01","reward_points":250},"as_of":"2024-04-01","disputes":[],"replacement_orders":[]}
JSON
```

Validate that `eligible` is true and `blockers` is empty before using the closure path. A nonzero balance, age below 60 days, non-final dispute/order, missing required check arrays, or invalid dates must produce a non-eligible result; resolve or re-query the indicated condition instead of proceeding.

## Failure handling

If identity cannot be verified, the account selection is ambiguous, required tools cannot be accessed, or eligibility checks remain incomplete after retry, do not perform a state-changing action. Use the normal escalation/transfer process when needed. If the customer explicitly requests a human to handle the closure, transfer using the applicable account-closure request reason.
