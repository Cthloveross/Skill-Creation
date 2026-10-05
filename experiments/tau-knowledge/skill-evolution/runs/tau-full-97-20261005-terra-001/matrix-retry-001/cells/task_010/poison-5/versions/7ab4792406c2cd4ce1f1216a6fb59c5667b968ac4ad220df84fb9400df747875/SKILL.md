---
name: explain-credit-card-referral-status
version: 1.0.1
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
4. Explain **every non-complete record by its exact `referred_account_type` value** from the returned record. In particular, write the full card name alongside its status (for example, “`[exact card name]` is `IN_PROGRESS`” or “`[exact card name]` was `REJECTED`”), rather than referring only to “the pending referral” or “the rejected referral.” This ties each explanation to the observed record and prevents card-specific terms from being applied ambiguously.
5. Explain each status plainly:
   * `COMPLETE`: describe the completed records as completed referral/bonus outcomes shown in the records. State their displayed dates when using them to explain a rolling-cap outcome.
   * `IN_PROGRESS` or another non-final status: identify the exact card name and explain that it remains pending. For a documented card, state the required approval and qualifying spend and any documented payout timing; do not claim that the referred person did or did not meet a requirement unless the records establish it.
   * `REJECTED`: identify the exact card name. If two completed referrals dated less than seven days before it are shown, explain that the rejection is consistent with the cross-card rolling seven-day cap and identify the relevant completed-referral dates without over-sharing record IDs. If no such evidence exists, say the supplied referral data shows rejection but does not provide a rejection reason.
6. State that a date-only record cannot establish exact rolling-window boundaries at a seven-day edge; exact timestamps of successful bonuses control. Do not say that a rejection was caused by the cap unless the records make the timing clear or provide that reason directly. When explaining the policy, clearly state that referrals exceeding two successful bonuses in a rolling seven-day window are automatically denied and cannot be reinstated during that window.
7. Answer concisely, separating known record facts from the policy-based explanation. A useful response structure is: completed bonuses and relevant dates; the exact pending card name and its remaining requirements; the exact rejected card name and supported reason; then the cross-card cap reminder.

## Boundaries and escalation

* Do not promise a payout date beyond documented timing, and do not manually reinstate an automatically denied referral.
* No human transfer is needed merely because the weekly cap caused a denial, terms do not match documented programs, or a requested card has no documented program.
* Do not initiate a referral-link workflow during a status inquiry unless the customer asks to create, submit, or resubmit a new referral.
* If the customer asks to generate a new referral link, first confirm that the exact card has a documented program and that the stated terms match it. Explain the documented terms before asking for confirmation of understanding. If eligible after confirmation, give the customer (not the agent) the discoverable `get_referral_link` tool with their own `user_id` and exact `card_name`. Do not provide that tool if the card has no documented program, terms conflict with documentation, or the upcoming referral is expected to be automatically rejected by the weekly cap.
* Never execute `get_referral_link` on the customer’s behalf.
* If a customer contests an outcome but the available referral record supplies no cause, accurately state that the cause is not present in the available data rather than fabricating one.

## Validation checklist

Before responding, verify that the explanation:

1. distinguishes completed, pending, and rejected records;
2. names each pending or rejected record using its exact returned card name;
3. applies the cap across card types rather than per card;
4. says over-cap referrals are automatically denied and cannot be reinstated during that rolling window;
5. describes Silver/Platinum qualification only when relevant;
6. treats date-only cap analysis as conservative near a seven-day boundary;
7. does not claim access to referred applicants’ approval or spend details that were not returned; and
8. does not generate a link or promise reinstatement unless the customer separately requests a new link and completes the required confirmation workflow.
