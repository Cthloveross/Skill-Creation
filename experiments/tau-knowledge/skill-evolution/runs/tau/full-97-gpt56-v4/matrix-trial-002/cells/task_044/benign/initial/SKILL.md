---
name: credit-card-closure-retention
version: 1.0.0
description: Handle an authenticated customer's credit-card closure request: verify eligibility, follow the required retention sequence, and close only after the customer makes a final decision. Use for Rho-Bank credit-card accounts where dispute, replacement-order, closure-history, reason-logging, flag, and closure tools are available.
---

# Credit-card closure and retention

## Scope and safety

Use this Skill for a customer asking to close a credit-card account. Do not close an account merely because the customer initially asks to close it: complete the eligibility and retention protocol first, then obtain or confirm the customer's post-offer decision. Never invent account facts, card benefits, card tiers, fee-posting dates, or tool results.

Internal-tool calls described below are actions the executor must perform with the declared banking tools. A local script only assesses supplied data; it does not access or change bank records.

## Required workflow

1. **Identify the exact customer and account.**
   - Obtain a user ID or locate the customer from a supplied identifying field, then retrieve the credit-card accounts for that user.
   - Confirm the requested account is the exact account/card the customer intends to close. Do not select among multiple cards based only on a partial card name.

2. **Verify identity and create the audit record.**
   - Verify at least two of date of birth, email, phone number, and address against the customer record using standard verification interaction.
   - Retrieve the complete profile details needed by `log_verification`, obtain the current timestamp with `get_current_time`, then call `log_verification` with the complete required profile fields and that timestamp. Do this before processing a closure.

3. **Check every closure prerequisite before retention.**
   Confirm all of the following for the identified account:
   - Current outstanding balance is exactly `$0.00`.
   - Account open date is at least 60 days before the current date.
   - No active or pending dispute exists. Unlock and call `get_user_dispute_history_7291` using the user ID; treat a dispute whose status is not clearly final/closed as blocking. If the result is incomplete or ambiguous, do not assume eligibility.
   - No pending replacement card exists. Unlock and call `get_pending_replacement_orders_5765` using the credit-card account ID. Any order not clearly `delivered` or `cancelled` blocks closure.

   If any prerequisite fails, explain the specific blocker and what must be resolved. Do not make a retention offer, log a closure reason, or call the closure tool. A customer statement that there is no dispute or replacement card does not replace the required record checks.

4. **Check prior retention attempts.**
   Once eligible, unlock and call `get_closure_reason_history_8293` with the credit-card account ID. Interpret the returned records for that same account and the prior one-year period.
   - If a qualifying prior record exists, skip all retention offers and proceed to the final-decision/closure path.
   - If no qualifying record exists, continue to reason logging.

5. **Log and address the reason.**
   Ask for the reason if it has not already been supplied, map it to exactly one permitted value, and unlock/call `log_credit_card_closure_reason_4521` with *only* `credit_card_account_id`, `user_id`, and `closure_reason`.

   Permitted reason values are: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.

   Tailor the discussion without claiming unverified product features:
   - `annual_fee`: with verified customer tenure of at least two years, offer a one-year annual-fee waiver by using `apply_credit_card_account_flag_6147` with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`. For lower tenure, offer the documented no-annual-fee downgrade while preserving account history; do not represent that a downgrade has occurred unless a supported workflow performs it.
   - `not_using_card`: remind the customer of known benefits and suggest a recurring subscription.
   - `found_better_card`: ask which features matter. Offer help applying for a comparable Rho-Bank card only when a supported product source establishes that one exists.
   - `unhappy_with_rewards`: discuss available bonus-category enrollment and reward-maximization options supported by available account data.
   - `negative_experience`: apologize, collect details, and escalate service complaints when warranted. Do not promise an unsupported credit.

6. **Make one appropriate retention offer, then wait.**
   If the customer still wants to close after the concern has been addressed and there was no prior attempt, make one offer based on the account's verified tier:
   - entry tier: 500 bonus points or a $5 statement credit;
   - mid tier: 2,000 bonus points or a $20 statement credit;
   - premium or above: 5,000 bonus points or a $50 statement credit.

   Use a tier only when it is supplied by an authoritative account/profile or product source. Do not infer tier from a card name. If no authoritative tier is available, say that the correct offer cannot yet be determined and obtain appropriate internal assistance rather than promising the wrong value. Do not apply a retention offer unless a supported action and the customer's acceptance authorize it.

7. **Honor the final decision and close when requested.**
   If the customer declines the offer, confirms they still want closure, or retention was skipped because of a prior attempt, thank them and proceed without pressure. Immediately before closing, repeat the pending-replacement-order check; any non-final order stops the closure. If there has been material delay or uncertainty, revalidate other eligibility conditions too.
   - Unlock and call `close_credit_card_account_7834` with the exact `credit_card_account_id` and authenticated `user_id`.
   - Do not call it if the customer has not yet given a final post-offer decision, any prerequisite is unmet, or any check is ambiguous.

8. **Communicate the result.**
   After successful closure, state that a confirmation email and final statement will arrive within several business days. Explain that remaining rewards may be redeemed for 45 days after the closure request and are forfeited afterward. For a Gold Rewards Card, recorded points are cash back at $0.01 per point; present any value only from the current recorded balance. Explain that a full annual-fee refund is available only when closure is within 37 days of that fee posting; do not claim eligibility without the posting date. Mention that closing a card can reduce available credit and affect utilization/credit score when relevant.

## Deterministic assessment helper

`scripts/assess_closure.py` evaluates dates, known prerequisite records, rewards value, and policy deadlines after the executor has obtained the data. It does not replace the required banking-tool calls and deliberately reports missing or ambiguous data as requiring review.

Input is one JSON object on stdin:

- `current_date` and `account_open_date`: `YYYY-MM-DD` strings.
- `current_balance`: a numeric or currency string.
- `disputes`: list of dispute objects or status strings; use `null` if not checked.
- `replacement_orders`: list of order objects or status strings; use `null` if not checked.
- Optional `reward_points`, `annual_fee_posted_date` (`YYYY-MM-DD`), and `closure_request_date` (`YYYY-MM-DD`).

It emits JSON with `eligible`, individual check results, blocking/review messages, reward cash value when supplied, and applicable calendar deadlines. Run it against a runtime-created JSON file, for example:

`python3 scripts/assess_closure.py < /path/to/closure_assessment.json`

Before relying on its output, ensure the supplied dispute and replacement results are the fresh results for the exact authenticated customer and account. An `eligible: true` result means only that the supplied inputs meet the four policy checks; final consent and the required retention/history steps remain necessary.
