---
name: referral-bonus-status-explanation
description: Explain why a credit-card customer has pending, completed, or rejected referral bonuses using their referral records and the documented rolling seven-day cap. Use for referral-status and missing-referral-bonus questions; do not use it to generate a referral link.
---

# Referral bonus status explanation

Use this Skill when a customer asks why a referral bonus is missing, why only some referrals paid, or what a referral status means.

## Documented rules

- A customer can receive at most **two successful referral bonuses in any rolling 7-day period**, across every credit-card type. A third or later referral in that window is automatically denied and cannot be reinstated until enough time has passed to fall below the cap.
- Do not treat a calendar week or an individual card as a separate weekly allowance.
- Approval alone does not necessarily earn a bonus: the referred applicant must also satisfy the applicable card's qualifying-spend rule.
- For **Silver Rewards Card**, the referred person must be approved and spend at least $750 within 60 days of account opening. The $75 bonus normally posts one to two billing cycles after that requirement is met. The documented annual cap is seven bonuses.
- For **Platinum Rewards Card**, the referred person must be approved and spend at least $1,500 within 90 days of account opening. The bonus is normally credited after that requirement is met. The documented annual cap is seven bonuses; self-referrals and duplicate applications do not qualify.
- The supplied knowledge does not establish referral terms for other card types. Do not invent their bonus amounts, annual limits, or spend requirements.

See `references/referral_policy.md` for the policy summary used by this Skill.

## Runtime procedure

1. Obtain a customer identifier from information the customer provides. Use the available user lookup tool appropriate to the supplied identifier (email, full name, or user ID). If the lookup is absent, ambiguous, or returns no matching customer, request enough information to resolve it.
2. Retrieve the customer's referrals with `get_referrals_by_user(user_id)`.
3. Record each referral's ID, referred card type, status, and date/timestamp. Preserve the returned status verbatim. The normal interpretation of the supplied records is:
   - `COMPLETE`: a completed/successful referral record.
   - `IN_PROGRESS`: the referral has not yet completed; it may still need approval and/or qualifying spend.
   - `REJECTED`: the referral did not qualify. Determine whether the dates support the documented rolling-limit explanation before stating that as the reason.
4. Optionally provide normalized records to `scripts/analyze_referrals.py`. The helper identifies rejected records that have at least two earlier completed referrals in the prior rolling seven days. It does not change records or contact the customer.
5. Give a status-specific explanation for **every relevant record**, rather than describing only the rejection. Use the clear status wording below so the customer can distinguish a paid referral, a rejected referral, and one that remains pending:
   - State that the number of `COMPLETE` records accounts for the number of bonuses already received. For example, say that “the two completed referrals account for the two bonuses you received” when the records show that pattern.
   - For **each** `IN_PROGRESS` record, name its card and explicitly say it **“is in progress”** (or **“is still in progress”**). Do not replace this status statement solely with “has not completed” or a discussion of possible deadlines. For a Silver record, then explain that the referred person must be approved and spend **$750 within 60 days** of account opening, and that the bonus typically posts **one to two billing cycles** after that requirement is met. For other cards, say that the record is in progress and avoid claiming undocumented requirements.
   - For each `REJECTED` record, name its card and explicitly say it is rejected or denied. If a rejected record follows two completed referrals within seven days, explain that it was subject to the cross-card cap: at most two bonuses in a **rolling seven-day period** across all card types. State that an auto-denied referral from this limit **cannot be reinstated within that same seven-day window**.
   - If records contain only dates and the result depends on an exact seven-day boundary or same-day ordering, say exact timestamps are needed to confirm the window. If records do not support a documented cause for a rejection, state that the available records show it as rejected but do not establish why. Do not speculate.
6. Do not promise reinstatement of a referral rejected for the weekly cap. Do not transfer solely because that cap caused the result.

## Required response check

Before sending the final response, compare it with the retrieved records and ensure all applicable items are present:

- The completed-referral count is connected to the bonuses received.
- Each pending card is named and described with the literal customer-facing phrase **“in progress”** or **“still in progress.”**
- A Silver pending referral includes `$750`, `60 days`, and `one to two billing cycles`.
- Each rejected card is named and described as rejected or denied.
- When supported by record timing, a cap denial says `two` bonuses, `rolling seven-day period` (or `rolling 7-day window`), and `across all card types`.
- A cap-denial explanation says it cannot be reinstated within the same seven-day window.

For records matching the usual pattern of two completed referrals, a later rejected referral within seven days, and a separate in-progress referral, explain in this order: the two completed referrals account for the two bonuses received; the rejected referral was blocked by the shared rolling cap and cannot be reinstated during that window; and the named pending referral **is in progress**, is not yet payable, and has any documented card-specific qualification and payout terms.

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

`successful_statuses` is optional and defaults to `["COMPLETE"]`. Supply it only if the runtime's referral system explicitly documents additional successful statuses. The script emits JSON containing status groups, completed-counts by calendar year, and `weekly_limit_candidates`. A candidate means the dates/timestamps support at least two prior successful referrals in the seven-day interval before a rejected record. `confidence` is `confirmed` when ordering and timestamps are sufficient and `date_only_confirmed` when distinct date-only records are unambiguously less than seven days apart; `needs_timestamps` means the boundary or ordering cannot be confirmed from the data.

The helper rejects malformed input, unknown date formats, missing required fields, and non-array `referrals` with a JSON error on stdout and a nonzero exit status. Review the returned records against the tool output before responding; the helper is a consistency aid, not a source of undocumented rejection reasons.

## Boundaries

This Skill is read-only: do not use account-change or link-generation actions to resolve a status question. If the customer separately requests a new referral link, first confirm that the exact card has a documented active referral offer and that the customer understands the matching terms. Only then provide the customer-facing `get_referral_link(user_id, card_name)` tool for the customer to run themselves; never generate it on their behalf. If the offer is undocumented, terms are incorrect, or the referral would be automatically rejected, explain why and do not provide the tool.
