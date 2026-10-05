---
name: explain-credit-card-referral-bonus-status
version: 1.0.0
description: Explain why a customer has or has not received credit-card referral bonuses by retrieving their referral records, interpreting documented statuses, and checking whether a rejected referral plausibly coincided with the rolling seven-day two-bonus cap. Use for referral-status and missing-referral-bonus inquiries; do not use it to create referral links.
---

# Explain Credit Card Referral Bonus Status

## Purpose

Give a factual, customer-ready explanation of each referral outcome without inventing card terms, payout amounts, qualification dates, or a manual remedy that the documented program does not support.

The referral statuses mean:

- `COMPLETE`: the referred person met the bonus criteria. The bonus is granted under the applicable card program terms.
- `IN_PROGRESS`: the referred person opened the account but is still working toward qualifying criteria.
- `NO_PROGRESS`: the invitee has not applied.
- `APPLIED`: the application is awaiting a decision.
- `REJECTED`: too many referral processes are in progress; review referral activity before advising next steps and do not advise an immediate retry.
- `ERROR`: retry later or escalate internally if the condition persists.

Across all card types, no more than two successful referral bonuses may be earned in a rolling seven-day window. The third and later referrals in that window are automatically denied. Exact timestamps, rather than calendar weeks, control this rule.

## Runtime procedure

1. Obtain an identifier supplied by the customer (user ID, exact full name, or email) and use the corresponding normal customer lookup tool. If the lookup is ambiguous, ask the customer to provide a more specific identifier.
2. Follow the runtime's normal identity-verification and verification-logging process before making account-specific disclosures when that process is required. Do not expose unnecessary customer profile fields in the response.
3. Call `get_referrals_by_user(user_id)` for the resolved customer. Use the records returned by that tool as the source of truth for referral status and record dates.
4. Convert the returned records into the JSON schema accepted by `scripts/analyze_referrals.py`, then run the script. The script is an aid for consistent status interpretation and a *plausibility* check of the seven-day cap; it does not make account changes.
5. Explain every relevant referral in plain language:
   - Count `COMPLETE` records as referrals that met the documented qualifying criteria. Do not quote a bonus amount unless it is documented for that exact card.
   - For `IN_PROGRESS`, explain that no bonus is due yet because the qualifying criteria are still pending. For **Silver Rewards Card**, qualification requires approval plus at least $750 in spend within 60 days of account opening; its bonus normally posts one to two billing cycles after the requirement is met. For **Platinum Rewards Card**, qualification requires approval plus at least $1,500 in spend within 90 days of opening. For other cards, say that card-specific criteria remain to be met rather than guessing terms.
   - For `REJECTED`, explain the status and, only if the record dates support it, say it is consistent with the rolling seven-day cap. Do not present a date-only calculation as confirmation because the policy uses exact timestamps. A cap-denied referral cannot be reinstated during that same window.
   - For `APPLIED`, say the application decision is pending; for `NO_PROGRESS`, the invitee has not started; for `ERROR`, advise retrying later or use the normal internal escalation path if it persists.
6. Keep the response focused on status, qualification, and documented limits. The available referrer transaction and account tools do not establish an invitee's qualifying spend, so do not use them to declare that a particular invitee met or missed spend requirements.

## Customer-response pattern

Use the actual returned record counts and card names. A suitable structure is:

> I found [number] completed referral(s), which have met their applicable bonus criteria. [For each pending referral: status and the applicable documented next condition.] [For each rejection: status and, if supported by the date review, that it is consistent with the two-successful-referrals-in-a-rolling-seven-day limit.] Because the limit is rolling and uses exact timestamps, I cannot confirm the precise timing from dates alone. I cannot quote additional card terms or bonus amounts unless they are documented for that card.

Do not claim that a rejected referral will be retroactively restored. Do not imply that an `IN_PROGRESS` referral has been denied, and do not promise an exact payout date unless the exact program's timing is documented.

## Script interface

Run the helper with actual retrieved records, for example:

```sh
python3 scripts/analyze_referrals.py < actual_referrals.json
```

Input JSON object:

```json
{
  "referrals": [
    {
      "referral_id": "string",
      "referred_account_type": "string",
      "referral_status": "COMPLETE | IN_PROGRESS | NO_PROGRESS | APPLIED | REJECTED | ERROR",
      "date": "YYYY-MM-DD"
    }
  ],
  "as_of": "optional current timestamp for reporting only"
}
```

`date` must be present and ISO date-formatted for a rejected-record cap review. `as_of` is retained in output for audit context and is not used to alter status conclusions. The script emits one JSON object to stdout. If the input is malformed, it emits `{ "ok": false, "errors": [...] }` and does not make a conclusion.

Output includes status counts, per-record documented interpretations, and `cap_reviews`. A `cap_reviews[].plausible_from_dates` value of `true` means two or more `COMPLETE` records have dates within the rejected record's preceding seven calendar days. It is not proof of an exact rolling-timestamp violation.

## Validation before responding

- Confirm that every retrieved referral is represented in the analysis and that the status counts sum to the number retrieved.
- Treat the live referral status as authoritative even if the date-only cap review is inconclusive.
- State the rolling limit as two **successful bonuses** across card types in a rolling seven-day period, not two referrals per calendar week.
- State Silver and Platinum terms only for those exact card names. Do not infer terms for Bronze, Gold, or another card without a documented program.
- Never create or offer a referral link as part of a missing-bonus explanation.
