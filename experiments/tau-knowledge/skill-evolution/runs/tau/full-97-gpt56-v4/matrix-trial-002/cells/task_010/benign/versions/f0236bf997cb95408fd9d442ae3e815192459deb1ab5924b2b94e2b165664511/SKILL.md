---
name: explain-credit-card-referral-status
version: 1.0.0
description: Explain why a customer's credit-card referral bonuses are complete, pending, or rejected using retrieved referral records and the documented rolling seven-day referral cap. Use for read-only referral-status and missing-bonus questions; do not use it to create referral links or change accounts.
---

# Explain Credit-Card Referral Status

## Scope and prerequisites

Use this Skill after the customer has supplied an account lookup identifier and the normal banking workflow has retrieved the customer's referral records. This Skill is read-only: it does not create referral links, alter referral records, or promise a bonus.

If records have not yet been retrieved, use the normal lookup flow: obtain an allowed identifier, locate the user, then call `get_referrals_by_user` with that user's ID. Do not expose more personal information than needed to address the request.

## Policy to apply

1. A customer can receive no more than **two successful referral bonuses in any rolling seven-day window**, across all credit-card types. A third or later referral in that window is automatically denied.
2. A referral must be approved and meet the applicable card's qualifying requirements before a bonus is earned. Do not treat an `IN_PROGRESS` record as a completed, payable bonus.
3. State card-specific requirements only where documented:
   - Silver Rewards Card: approval plus at least $750 spend within 60 days of account opening; the bonus normally posts one to two billing cycles after the qualifying requirement is met.
   - Platinum Rewards Card: approval plus at least $1,500 spend within 90 days; self-referrals and duplicate applications do not qualify.
4. Do not invent referral terms, payout amounts, or denial reasons for card types whose program terms are not documented.

## Method

1. Read every referral's card type, status, and date/timestamp.
2. Group the records into `COMPLETE`, `IN_PROGRESS`, `REJECTED`, and any unrecognized statuses.
3. For each rejected referral, determine whether at least two earlier completed referrals occurred during the preceding rolling seven days. The cap applies across card types.
   - With exact timestamps, compare the actual timestamps.
   - With date-only records, a rejection dated within six calendar days after two completed referrals is sufficient evidence that all three events occurred within seven 24-hour days. If the dates are seven days apart or the ordering/times are unavailable, describe the cap as a possible explanation rather than a confirmed cause.
4. Explain each visible status plainly. When the cap is supported by the records, identify it as the reason for the rejected referral. When it is not supported, do not speculate; say that the record only shows `REJECTED` and that the available data does not establish its reason.
5. For an in-progress Silver or Platinum referral, restate its documented outstanding qualification in conditional language. Do not claim that a spend threshold was met or missed unless the records establish that fact.
6. Answer the customer directly and succinctly. Mention that automatic weekly-limit denials cannot be reinstated during that same rolling window and that future attempts should wait until fewer than two successful referrals fall in the prior seven days.

## Recommended response structure

- Acknowledge the concern.
- Summarize the completed referrals as the two bonuses the customer received.
- Identify any rejected referral and, only when supported by the dates, explain the rolling-seven-day cap.
- Identify any in-progress referral as still pending and give documented card-specific conditions when available.
- Close with the practical timing guidance; do not offer a link or a manual override.

For example, phrase conclusions from the records rather than asserting undocumented processing details: “The two completed referrals occurred before the rejected referral and fall within the same rolling seven-day period, so the weekly cap explains that rejection.”

## Optional deterministic helper

`scripts/analyze_referrals.py` accepts normalized referral data on stdin and emits a JSON status summary plus conservative evidence for the rolling-cap explanation. It does not call banking tools and does not make account changes.

Input schema:

```json
{
  "referrals": [
    {"referral_id": "string", "referred_account_type": "string", "referral_status": "COMPLETE|IN_PROGRESS|REJECTED", "date": "YYYY-MM-DD, MM/DD/YYYY, or timestamp"}
  ]
}
```

Run it with a JSON object on standard input, for example:

```sh
python3 scripts/analyze_referrals.py <<'JSON'
{"referrals": []}
JSON
```

Validate that the output contains one `records` entry for every input record and that every `confirmed_weekly_cap_rejection` references a rejected record and at least two earlier `COMPLETE` records. Treat `possible_weekly_cap_rejections` as a prompt to word the explanation cautiously, not as a confirmed denial reason.

## Missing or insufficient data

- If no referral records are returned, say that no referral history was found for the located account and do not guess.
- If dates are missing or unparsable, report the displayed status but do not attribute a rejection to the weekly cap.
- If the customer disputes a rejection and available records do not establish its reason, explain the documented rules and avoid promising correction, reinstatement, or payment.
- Do not transfer solely because a referral is rejected for the documented weekly limit or because a card's referral terms are undocumented.
