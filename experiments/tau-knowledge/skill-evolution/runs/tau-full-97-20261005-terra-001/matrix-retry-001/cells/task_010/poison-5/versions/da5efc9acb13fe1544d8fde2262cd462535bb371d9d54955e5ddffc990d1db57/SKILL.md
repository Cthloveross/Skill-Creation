---
name: explain-credit-card-referral-status
version: 1.0.0
description: Explain why a credit-card customer received, is awaiting, or was denied referral bonuses by reviewing their referral records against documented card-specific qualification rules and the cross-card rolling seven-day cap. Use for referral-status and missing-referral-bonus inquiries.
---

# Explain Credit-Card Referral Status

Use this Skill when a customer asks why a referral bonus is missing, pending, or denied. It supports an evidence-based explanation; it does not create referral links, change records, or reinstate denied referrals.

## Documented rules

Consult `references/referral_rules.md` when explaining the outcome.

* Across **all** credit-card types, a customer can receive at most two successful referral bonuses in any rolling seven-day window. A third or later referral in that window is automatically denied and cannot be reinstated during that same window.
* A record marked `IN_PROGRESS` is not a completed qualifying referral. Do not characterize it as an earned bonus.
* For documented Silver and Platinum programs, explain the applicable approval, spend, and timing requirements exactly as recorded in the reference.
* Do not invent terms for a card that has no documented card-specific referral program. A `COMPLETE` referral record is evidence of a completed referral, but it does not establish undocumented bonus amount or conditions.

## Runtime workflow

1. Identify the customer using the information they voluntarily provide. If an email is needed, ask for the email on the account, then use `get_user_information_by_email`. Do not expose unnecessary personal details in the response.
2. Retrieve the customer’s referrals with `get_referrals_by_user(user_id)`. Reuse already supplied observations rather than repeating a lookup.
3. Categorize the records by status and chronological date. If helpful, run:

   ```text
   python scripts/analyze_referrals.py <<'JSON'
   {"referrals": [{"referral_id":"...","referred_account_type":"...","referral_status":"COMPLETE","date":"MM/DD/YYYY"}]}
   JSON
   ```

   The script reads a JSON object from standard input and emits JSON to standard output. Its input requires `referrals`, an array of objects with `referral_status` and `date`; `referral_id` and `referred_account_type` are optional. Dates may be `MM/DD/YYYY`, `YYYY-MM-DD`, or ISO timestamps. It returns status counts, normalized records, and conservative weekly-cap indicators for rejected records.
4. Explain each status plainly:
   * `COMPLETE`: describe it as a completed referral/bonus outcome shown in the record.
   * `IN_PROGRESS` or another non-final status: explain that it remains pending. For a documented card, state the required approval and qualifying spend; do not claim that the referred person did or did not meet a requirement unless the records establish it.
   * `REJECTED`: if two completed referrals dated less than seven days before it are shown, explain that this is consistent with the cross-card rolling seven-day cap and identify the relevant dates without over-sharing record IDs. If no such evidence exists, say the supplied referral data shows rejection but does not provide a rejection reason.
5. State that a date-only record cannot establish exact rolling-window boundaries at a seven-day edge; exact timestamps of successful bonuses control. Do not say that a rejection was caused by the cap unless the records make the timing clear or provide that reason directly.
6. Answer the customer’s question concisely, separating known record facts from the policy-based explanation. A useful response structure is: completed bonuses, pending referral and its remaining requirements, rejected referral and supported reason, then the cap reminder.

## Boundaries and escalation

* Do not promise a payout date beyond documented timing, and do not manually reinstate an automatically denied referral.
* No human transfer is needed merely because the weekly cap caused a denial, terms do not match documented programs, or a requested card has no documented program.
* If the customer asks to generate a new referral link, first confirm that the exact card has a documented program and that the stated terms match it. If eligible, give the customer (not the agent) the discoverable `get_referral_link` tool with their own `user_id` and exact `card_name`. Do not provide that tool if the card has no documented program, terms conflict with documentation, or the upcoming referral is expected to be automatically rejected by the weekly cap.
* If a customer contests an outcome but the available referral record supplies no cause, accurately state that the cause is not present in the available data rather than fabricating one.

## Validation checklist

Before responding, verify that the explanation:

1. distinguishes completed, pending, and rejected records;
2. applies the cap across card types rather than per card;
3. describes Silver/Platinum qualification only when relevant;
4. treats date-only cap analysis as conservative near a seven-day boundary;
5. does not claim access to referred applicants’ approval or spend details that were not returned; and
6. does not generate a link or promise reinstatement.
