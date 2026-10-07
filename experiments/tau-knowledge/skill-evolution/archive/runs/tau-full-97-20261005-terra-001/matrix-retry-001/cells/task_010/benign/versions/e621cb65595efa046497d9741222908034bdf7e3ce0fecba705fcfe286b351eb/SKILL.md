---
name: referral-bonus-status-explanation
description: Explain why a credit-card customer has pending, completed, or rejected referral bonuses from verified referral records and documented referral rules. Use for referral-status or missing-referral-bonus questions; do not use it to generate a referral link.
---

# Referral bonus status explanation

Use this Skill when a customer asks why a referral bonus is missing, why only some referrals paid, or what a referral status means.

## Documented rules

- A customer can receive at most **two successful referral bonuses in any rolling 7-day period**, across every credit-card type. A third or later referral in that period is automatically denied and cannot be reinstated until enough time has passed to fall below the cap.
- This is not a calendar-week limit and not a separate limit for each card type.
- Approval alone does not necessarily earn a bonus: the referred applicant must also satisfy the applicable card's qualifying-spend rule.
- For **Silver Rewards Card**, the referred person must be approved and spend at least **$750 within 60 days** of account opening. The $75 bonus normally posts **one to two billing cycles** after that requirement is met. The documented annual cap is seven bonuses.
- For **Platinum Rewards Card**, the referred person must be approved and spend at least $1,500 within 90 days of account opening. The bonus is normally credited after that requirement is met. The documented annual cap is seven bonuses; self-referrals and duplicate applications do not qualify.
- The supplied knowledge does not establish referral terms for other card types. Do not invent their bonus amounts, annual limits, or spend requirements.

See `references/referral_policy.md` for the policy summary used by this Skill.

## Runtime procedure

1. Follow the runtime's identity-verification requirements before disclosing customer referral records. If the runtime requires two confirmed identity fields and a verification log, obtain the confirmations from the customer, get the current time, and log the verification only after successful verification.
2. Obtain a customer identifier from information the customer provides. Use the available lookup tool appropriate to that identifier (email, full name, or user ID). If the lookup is absent, ambiguous, or has no matching customer, request enough information to resolve it.
3. Retrieve the customer's referrals with `get_referrals_by_user(user_id)`.
4. Record each referral's ID, referred card type, status, and date/timestamp. Preserve the returned status verbatim. The normal interpretation of supplied records is:
   - `COMPLETE`: a completed/successful referral record.
   - `IN_PROGRESS`: the referral has not yet completed; it may still need approval and/or qualifying spend.
   - `REJECTED`: the referral did not qualify. State the rolling-limit reason only when record timing and the documented policy support it.
5. Optionally provide normalized records to `scripts/analyze_referrals.py`. The helper identifies rejected records with at least two earlier completed referrals in the preceding rolling seven-day interval. It does not change records, look up applicant activity, or contact the customer.
6. Give a status-specific explanation for **every relevant record**, rather than describing only a rejection:
   - State that the number of `COMPLETE` records accounts for the number of bonuses already received. For example: “The two completed referrals account for the two bonuses you received.”
   - For every `IN_PROGRESS` record, name its card and explicitly say it **“is in progress”** or **“is still in progress.”** Do not replace that status with only “has not completed” or a possible deadline.
   - For a Silver `IN_PROGRESS` record, distinguish the observed status from unobserved applicant facts. The referral record does not establish whether the referred person was approved or completed qualifying spend. State plainly: **“The record does not show whether the referred person has been approved or completed the qualifying spend, so I cannot confirm either.”** Use the ASCII wording **“cannot confirm”** where possible. Then state the documented requirement: approval and **$750 within 60 days** of opening, with the bonus normally posting **one to two billing cycles** after the requirement is met.
   - Do not disclose, infer, or claim knowledge of the referred applicant's account activity, approval decision, transactions, or spending. Their account information is not established by the referrer's referral-status record.
   - For every `REJECTED` record, name its card and explicitly say it is rejected or denied. When the record shows two earlier completed referrals within seven days, explain that it was subject to the shared cap: at most two bonuses in a **rolling seven-day period** across all card types. State that an auto-denied referral from this limit **cannot be reinstated within that same seven-day window**.
   - If dates are at a seven-day boundary, are on the same date without ordering, or otherwise need exact ordering, say that timestamps are needed to confirm the rolling-window calculation. If records do not support a documented reason for a rejection, say the record is rejected but the available records do not establish why. Do not speculate.
7. Do not promise reinstatement of a referral rejected for the cap. Do not transfer solely because that cap caused the result.

## Required response check

Before sending a final response, compare it with the retrieved records and ensure all applicable items are present:

- The completed-referral count is connected to the bonuses received.
- Each pending card is named and described with **“in progress”** or **“still in progress.”**
- For a Silver pending referral, say the record **does not show** approval or qualifying spend and **cannot confirm** those facts; include `$750`, `60 days`, and `one to two billing cycles` as documented requirements and timing, not as observed applicant activity.
- Each rejected card is named and described as rejected or denied.
- When supported by record timing, a cap denial says `two` bonuses, `rolling seven-day period` (or `rolling 7-day window`), and `across all card types`.
- A cap-denial explanation says it cannot be reinstated within the same seven-day window.

For the common pattern of two completed referrals, a later rejected referral within seven days, and a separate in-progress Silver referral, explain in this order: the two completed referrals account for the two bonuses received; the rejected referral was blocked by the shared rolling cap and cannot be reinstated during that window; and the named Silver referral **is in progress**. Explain that the record does not show, and the agent cannot confirm, the referred person's approval or qualifying spend; then give the documented $750/60-day condition and one-to-two-billing-cycle posting timeframe.

## Helper input and output

Run the packaged helper as:

```sh
python3 scripts/analyze_referrals.py < referrals.json
```

Input is one JSON object on stdin:

```text
{
  "referrals": [
    {
      "referral_id": "string (optional)",
      "referred_account_type": "string (optional)",
      "referral_status": "string (required)",
      "date": "YYYY-MM-DD or ISO-8601 timestamp (required)"
    }
  ],
  "successful_statuses": ["COMPLETE"]
}
```

`successful_statuses` is optional and defaults to `["COMPLETE"]`. Supply it only when the runtime's referral system explicitly documents additional successful statuses. The script emits JSON containing normalized records, status groups, successful counts by calendar year, and `weekly_limit_candidates`. A candidate means that the dates/timestamps support at least two prior successful referrals in the seven-day interval before a rejected record. `confidence` is `confirmed` with sufficient timestamp ordering, `date_only_confirmed` for distinct date-only records unambiguously less than seven days apart, and `needs_timestamps` where same-day ordering prevents confirmation.

The helper rejects malformed input, unknown date formats, missing required fields, and non-array `referrals` with a JSON error on stdout and a nonzero exit status. Review returned records against the actual referral lookup before responding; the helper is a consistency aid, not evidence of an undocumented rejection reason or applicant activity.

## Boundaries

This Skill is read-only: do not use account-change or link-generation actions to resolve a status question. If the customer separately requests a referral link, first confirm that the exact card has a documented active referral offer and that the customer understands its matching terms. Only then provide the customer-facing `get_referral_link(user_id, card_name)` tool for the customer to run themselves; never generate it on their behalf. If the offer is undocumented, terms are incorrect, or the referral would be automatically rejected, explain why and do not provide the tool.
