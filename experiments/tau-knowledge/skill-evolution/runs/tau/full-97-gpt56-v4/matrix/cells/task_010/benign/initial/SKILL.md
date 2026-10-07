---
name: referral-bonus-status-explainer
description: Explain why a credit-card customer has or has not received referral bonuses by reviewing their referral records against the cross-card rolling seven-day cap and documented card-specific qualification rules. Use for read-only referral-status questions; it does not perform banking actions.
---

# Referral Bonus Status Explainer

Use this Skill when a customer asks about missing, delayed, rejected, or pending credit-card referral bonuses.

## Policy to apply

1. A customer may receive at most two successful credit-card referral bonuses in any rolling seven-day period. The cap is shared across card types. A third (or later) referral in that window is automatically denied and cannot be reinstated during that window.
2. A referral also must be approved and satisfy its card's qualifying requirements before a bonus is due.
3. For **Silver Rewards**, the referred person must be approved and spend at least $750 within 60 days of opening. The bonus normally posts one to two billing cycles after that requirement is met.
4. For **Platinum Rewards**, the referred person must be approved and spend at least $1,500 within 90 days of opening. Self-referrals and duplicate applications do not qualify.
5. Do not invent qualifying thresholds, payout timing, or rejection causes for other card products whose specific terms are unavailable.

## Runtime workflow

1. If the customer has not supplied a usable account identifier, ask for the email address on their profile or their user ID. Do not ask for information already supplied.
2. For this read-only explanation, retrieve the customer record and that customer's referrals with the normal banking tools. No identity-verification log is needed unless the task separately requires an authenticated account change or disclosure that requires verification.
3. Give the records to `scripts/analyze_referrals.py` as `referrals`. The helper identifies status buckets and flags rejected referrals that have two earlier `COMPLETE` referrals in the preceding seven calendar days. Its rolling-cap conclusion is only definitive when timestamps are available; dates alone should be described as consistent with the cap.
4. Respond in plain language, organized by referral status:
   - Confirm that `COMPLETE` referrals account for bonuses already earned, without promising an amount unless the referred card's documented offer establishes one.
   - For an `IN_PROGRESS` referral, explain the applicable documented next requirement and normal payout timing, if known. Otherwise say it remains in progress and status can be tracked in the referral dashboard.
   - For a `REJECTED` referral that is flagged by the helper, explain that it was the third successful referral attempt within the rolling seven-day cap, across all card types. If it is not flagged, do not assign a reason not present in the records; state that the status is rejected and offer to check the referral status/support channel.
5. Avoid exposing referral IDs, other applicants' personal information, or unnecessary profile details. Do not claim a pending referral will qualify, because approval and qualifying spend still must occur.
6. Do not change account data, retry a denied referral, or issue a bonus. If the user disputes a rejection and the available records do not establish the cause, offer appropriate human support rather than fabricating a resolution.

## Required response qualities

Directly answer the customer's count question. Explain that the weekly rule is rolling seven days rather than a calendar week and applies across card products. Distinguish a cap denial from a referral that is simply still pending qualification. Use cautious wording where only dates, rather than exact timestamps, are available.

## Helper interface

Run the helper with JSON on standard input:

```json
{
  "referrals": [
    {
      "referral_id": "optional internal identifier",
      "referred_account_type": "Silver Rewards Card",
      "referral_status": "IN_PROGRESS",
      "date": "YYYY-MM-DD"
    }
  ]
}
```

It writes JSON to standard output with `complete`, `in_progress`, `rejected`, `other`, and `cap_indicators`. Each output referral preserves only `card_type`, `status`, and `date`; no identifier is emitted. `cap_indicators` identifies a rejected record and the qualifying earlier completed dates used for the date-level check.

Validate that `referrals` is a JSON list and that each evaluated referral has a recognizable ISO `YYYY-MM-DD` date. Invalid or missing dates are retained in their status bucket but excluded from cap calculations. Treat a non-list input as an error and obtain clean referral data before relying on the analysis.
