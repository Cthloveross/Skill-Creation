---
name: referral-status-explanation
description: Safely review a verified customer's credit-card referral statuses, explain the rolling seven-day referral-bonus cap and documented card-specific requirements, and avoid asserting an unrecorded rejection reason. Use for questions about missing, pending, complete, or rejected referral bonuses.
---

# Referral Status Explanation

Use this Skill for an account-specific referral-status inquiry. It is read-only: do not create referral links, alter a referral, or promise a bonus.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this read-only workflow, identity, authority, and ownership of the referrer account are applicable. Balance, recipient, transfer, payment, card-detail changes, and confirmation to execute a transaction are not applicable because no transaction or account change is being made. Do not turn the inquiry into an action.

## Required procedure

1. **Verify identity before disclosing account-specific referral details.** Obtain confirmation of two of the four identity fields (date of birth, email, phone number, or address) and compare them against the customer record. After two fields match, call `log_verification` with the complete record and the current timestamp from `get_current_time`. A supplied email alone is only one field.
2. **Verify authority and ownership.** Use the verified customer's own `user_id` as the referrer ID. Do not disclose another person's referrals or infer ownership from a name alone.
3. **Retrieve current records** with `get_referrals_by_user(user_id)`. Retain the returned status and date exactly; do not infer approval, spend, or payout from a customer saying that friends signed up.
4. **Analyze records** by running `scripts/analyze_referrals.py` with a structured transcription of the referral records. The script is an aid for consistent counting and date-level rolling-window analysis; it does not contact bank systems or change any record.
5. **Explain results cautiously.**
   - `COMPLETE` means the record is complete. Do not invent a separate payout date unless a record supplies one.
   - `IN_PROGRESS` means the referral is still pending. It does not establish that the referred applicant has both been approved and met qualifying spend.
   - `REJECTED` has an established rolling-cap explanation only when the record dates show at least two earlier `COMPLETE` referrals in the preceding seven days. Referral records normally contain dates rather than exact timestamps, so call this *consistent with* or *likely due to* the cap, not a confirmed causal diagnosis.
   - If that date-level condition is absent, state that the record is rejected but that the available record does not state the reason. Do not speculate or transfer solely to obtain an unsupported reason.
6. **Give the applicable program terms.** Across all credit-card types, a customer may receive at most two referral bonuses in any rolling seven-day window. The third and subsequent referrals in that window are automatically denied. This is based on exact successful-bonus timestamps, not calendar weeks, and a denied referral cannot be reinstated within that same window. A referral also needs approval and its card-specific qualifying requirements.
7. **Close with an appropriate next step.** Pending referrals should be monitored until their documented qualification requirements are met. Do not claim that a rejected referral will be reinstated, and do not offer a referral-link tool in a status inquiry.

## Documented card terms

Only state terms documented for the card in question.

- **Silver Rewards Card:** the referred person must be approved and spend at least $750 within 60 days of account opening. The referral bonus is 75 and normally posts one to two billing cycles after this requirement is met. The program has an annual maximum of seven referral bonuses.
- **Platinum Rewards Card:** the referred person must be approved and spend at least $1,500 within 90 days of account opening. The bonus is $100; self-referrals and duplicate applications do not qualify. The annual maximum is seven referral bonuses.
- For another card, explain the universal approval and rolling-seven-day requirements, but do not fabricate a card-specific spend threshold, bonus amount, or annual limit.

## Script interface

Run from the package root:

```sh
python3 scripts/analyze_referrals.py <<'JSON'
{"referrals":[{"referred_account_type":"Silver Rewards Card","referral_status":"IN_PROGRESS","date":"2025-01-15"}]}
JSON
```

The script reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

- `referrals` (required): an array of objects with `referred_account_type`, `referral_status`, and `date` fields. Dates may be `YYYY-MM-DD`, `MM/DD/YYYY`, or ISO-8601 timestamps.

Output schema:

- `ok`: whether the input was valid;
- `summary`: total and per-status counts;
- `records`: normalized, non-identifying record assessments;
- `rolling_window_assessments`: rejected records for which two earlier complete records appear within seven calendar days, with an explicit timestamp caveat;
- `card_terms_for_pending_records`: documented requirements relevant to pending cards;
- `warnings`: missing or unusable data notices.

## Validation and response construction

Check that `ok` is true, that the summary count equals the number of retrieved records, and that every reported status is one returned by the bank tool. Treat script warnings as limitations to disclose, not as permission to guess.

A concise customer response should distinguish complete, pending, and rejected referrals; explain the cross-card rolling cap if supported by the dates; and state pending-card requirements where documented. Never expose referral identifiers, unrelated profile fields, or another customer's information.
