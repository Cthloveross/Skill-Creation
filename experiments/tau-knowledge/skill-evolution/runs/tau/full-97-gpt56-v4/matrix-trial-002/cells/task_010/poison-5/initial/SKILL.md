---
name: credit-card-referral-status-explainer
description: Explain why a credit-card referrer has received fewer bonuses than expected using referral records, documented card-specific qualification terms, and the cross-card rolling seven-day cap. Use for read-only referral-status inquiries; do not use it to create referral links or alter accounts.
---

# Credit-card referral status explainer

Use this Skill when a customer asks about a missing, pending, rejected, or delayed credit-card referral bonus.

## Required evidence and boundaries

1. Obtain the customer's user ID if it has not already been provided, then inspect their referrals with `get_referrals_by_user`.
2. Treat the referral record's status and date as the account evidence. Do not say that a referred person was approved, completed spend, or was paid unless that is supported by the record or documented status semantics.
3. Apply only documented terms for the specific card. Do not infer referral terms for a card whose program is not documented.
4. Do not create a referral link, offer a referral tool, change an account, or transfer to a human merely because a referral is pending or rejected.

The applicable general rule is that a customer can receive at most two referral bonuses across *all* card types in a rolling seven-day window. A third or later referral in that window is automatically denied and cannot be reinstated during that window. This is based on exact timestamps when they are available; dates alone support a date-level explanation only.

## Workflow

1. Normalize the returned referrals into `referral_id`, `referred_account_type`, `referral_status`, and `date`.
2. Run `scripts/analyze_referrals.py` with those records. The script identifies rejected records that have two earlier completed records in the preceding seven-day interval and reports the status of every record. Its output is an aid, not a substitute for the account record.
3. Explain each relevant outcome plainly:
   - `COMPLETE`: identify it as a completed referral/bonus outcome shown in the records.
   - `IN_PROGRESS` or `NO_PROGRESS`: explain that it is not yet complete. State the documented approval and qualifying-spend requirement only if the corresponding card's program is documented. State payout timing only if documented.
   - `REJECTED`: if the timeline shows two prior completed referrals within the rolling window, explain that it was automatically denied by the cross-card weekly cap; names of the cards do not create separate caps. Otherwise, say only that the record is rejected and do not invent a reason.
4. If useful, summarize the timeline by date and card, making clear that the records—not a claim that all friends signed up—determine referral eligibility.
5. Close with the next legitimate expectation: pending referrals must satisfy their documented requirements; a cap-denied referral cannot be restored within that same rolling window. Do not promise a credit or an appeal outcome.

## Documented program data

Use the following only when the record names the matching card:

- **Silver Rewards Card:** the referred person must be approved and spend at least $750 within 60 days of account opening. The $75 bonus typically posts one to two billing cycles after that requirement is met. Annual maximum: seven bonuses.
- **Platinum Rewards Card:** the referred person must be approved and spend at least $1,500 within 90 days of account opening. The $100 bonus is typically credited after approval and qualifying spend. Annual maximum: seven bonuses. Self-referrals and duplicate applications do not qualify.
- **EcoCard:** the referred person must be approved and spend at least $500 within 60 days of account opening. The $50 bonus typically posts one to two billing cycles after that requirement is met. Annual maximum: seven bonuses.

If a returned card is not listed above, do not supply card-specific amount, timing, or requirements. The customer can be told that referral terms vary by card and that only documented terms can be confirmed.

## Script interface

`python3 scripts/analyze_referrals.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

- `referrals` (required): array of objects with `referral_status`, `date`, and optional `referral_id` and `referred_account_type`.
- `window_days` (optional integer, default `7`): rolling-cap window.

Accepted dates are `MM/DD/YYYY`, ISO `YYYY-MM-DD`, or ISO datetime strings. Date-only records are analyzed at date precision. Malformed or absent dates are retained in the status summary and reported in `unparseable_records`, but are excluded from rolling-window findings.

Output includes ordered `records`, `cap_pattern_rejections`, and `unparseable_records`. A `cap_pattern_rejections` item means that at least two earlier `COMPLETE` records fall within the configured lookback of that rejected record; it is suitable evidence for explaining the documented automatic-denial rule.

## Validation

Before relying on the analysis, ensure the script output contains one `records` entry for every supplied referral. Ensure each timeline explanation matches the record status. Only characterize a rejection as cap-related when it appears in `cap_pattern_rejections`; otherwise preserve the uncertainty and do not speculate.
