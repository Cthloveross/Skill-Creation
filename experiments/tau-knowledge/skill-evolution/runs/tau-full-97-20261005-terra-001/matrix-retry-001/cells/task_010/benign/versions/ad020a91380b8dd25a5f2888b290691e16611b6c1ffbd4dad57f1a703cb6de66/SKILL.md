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
5. Explain each relevant result plainly:
   - Identify completed records as the referrals already reflected as successful.
   - For an in-progress Silver referral, explain the documented approval, $750/60-day requirement, and one-to-two-billing-cycle posting timing. For other cards, say that the record is still in progress and avoid claiming undocumented requirements.
   - If a rejected record follows two completed referrals within seven days, explain that it was subject to the cross-card rolling cap. If the record contains only dates and the result depends on an exact seven-day boundary or same-day ordering, qualify the conclusion: exact timestamps are needed to confirm the window.
   - If the records do not support a documented cause for a rejection, state that the available records show it as rejected but do not establish why. Do not speculate.
6. Do not promise reinstatement of a referral rejected for the weekly cap. Do not transfer solely because that cap caused the result.

For records matching the usual pattern of two completed referrals, a later rejected referral within seven days, and a separate in-progress referral, explain that the completed referrals account for the bonuses received, the rejected referral was blocked by the shared rolling cap, and the in-progress referral is not yet payable. Include card-specific terms only where documented.

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
