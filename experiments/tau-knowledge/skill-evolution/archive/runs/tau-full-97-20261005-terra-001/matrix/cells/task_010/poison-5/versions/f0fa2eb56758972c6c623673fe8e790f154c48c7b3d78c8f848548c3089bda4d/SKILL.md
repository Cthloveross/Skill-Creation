---
name: credit-card-referral-status-explanation
description: Explain why a credit-card customer has or has not received referral bonuses after referral records have been retrieved. Use this for COMPLETE, IN_PROGRESS, and REJECTED referral statuses, including the cross-card rolling seven-day referral-bonus limit. Do not use it to create referral links or alter referral records.
---

# Credit-card referral status explanation

## Purpose
Use this Skill after obtaining the customer's referral records through the normal banking tools. It turns the records into a precise, customer-safe explanation without inventing card terms, qualification results, or timestamps that are not in the records.

The package covers the documented program rules in `references/referral_policy.md`:

- At most two successful referral bonuses may be received in a rolling seven-day window across all card types.
- `COMPLETE` means the referral met the applicable bonus criteria.
- `IN_PROGRESS` means the referred customer has opened an account but has not yet met the bonus criteria.
- `REJECTED` means there are too many referral processes; it should not be immediately retried and existing activity should be reviewed.
- Silver and Platinum card qualification terms are only stated when the respective card is in the retrieved record.

## Required information and safe workflow

1. If records are not already available, obtain an account identifier using the supported account lookup methods, then use `get_referrals_by_user(user_id)`.
2. Do not disclose referral details to an unverified third party. Use only the records belonging to the customer whose issue is being handled.
3. Supply the normalized referral records to `scripts/analyze_referrals.py`. The helper is advisory: it does not call banking tools, modify records, create links, or decide eligibility.
4. Read each status literally and distinguish a completed referral from an application or a friend merely signing up. A bonus is not due merely because someone applied or opened an account.
5. For every rejected referral, use the helper's cap assessment:
   - `confirmed_by_timestamps` supports saying the weekly limit caused the denial.
   - `likely_by_dates` supports saying the records indicate the weekly limit was likely the reason, because the source records lack exact timestamps.
   - `not_shown_by_records` means do not attribute the rejection to the weekly cap; explain only the documented `REJECTED` meaning and that the records should be reviewed.
6. Do not promise that a rejected referral will be restored, and do not retry it. A referral denied because of the cap cannot be reinstated during that seven-day window. Do not offer a referral-link tool in response to a rejected referral.
7. Direct the customer to the mobile app or customer service to monitor status if they want further status updates. No transfer is required solely because a referral is rejected.

## Helper interface

Run `scripts/analyze_referrals.py` with one JSON object on standard input and read one JSON object from standard output.

Input schema:

```json
{
  "referrals": [
    {
      "referral_id": "optional opaque identifier",
      "referred_account_type": "card name",
      "referral_status": "COMPLETE | IN_PROGRESS | NO_PROGRESS | APPLIED | REJECTED | ERROR",
      "date": "YYYY-MM-DD, MM/DD/YYYY, or ISO-8601 timestamp"
    }
  ]
}
```

`referrals` is required and must be an array. Unknown fields are preserved only as input context and are not needed by the helper. A missing or unparseable `date` prevents rolling-window conclusions for that record. ISO timestamps permit an exact cap comparison; date-only records deliberately produce a qualified, date-level conclusion.

Output schema highlights:

```json
{
  "ok": true,
  "status_counts": {"COMPLETE": 0},
  "referrals": [
    {
      "index": 0,
      "status": "COMPLETE",
      "documented_interpretation": "...",
      "card_terms": {"qualification": "..."},
      "cap_assessment": {"finding": "likely_by_dates"}
    }
  ],
  "validation_warnings": []
}
```

For example, provide a JSON object of the schema above as the script's stdin to `scripts/analyze_referrals.py`. A valid result has `ok: true`; before relying on a cap conclusion, confirm there are no date-related warnings and inspect the rejected referral's `cap_assessment`.

## Compose the customer response

Keep the response concise, empathetic, and tied to the retrieved records:

1. State how many referrals are `COMPLETE` and explain that `COMPLETE` has met the applicable bonus criteria.
2. Explain each non-complete referral separately, naming its card only when it is present in the record:
   - **IN_PROGRESS:** the referred person has not yet met the applicable criteria. For Silver, state approval plus at least $750 spent within 60 days of account opening; its bonus normally posts one to two billing cycles after that requirement is met.
   - **REJECTED:** state that the status reflects too many referral processes. If the helper supports the weekly-cap explanation, explain the two-successful-referral rolling seven-day cap applies across cards and caused or likely caused the denial, at the evidence level returned by the helper.
   - **APPLIED, NO_PROGRESS, or ERROR:** use the documented status meaning from the helper and do not invent a bonus date.
3. State Platinum's $1,500-within-90-days requirement only when discussing a Platinum referral that is still capable of qualifying. Do not imply that satisfying spend can overturn a rejected referral.
4. Do not state bonus amounts, annual-limit conclusions, payout dates for undocumented card types, or individual referred customers' private information. The documented terms vary by card.
5. Close by offering the documented status-tracking channels (mobile app or customer service).

If the retrieval is empty, malformed, or belongs to a different customer, say that the available records do not establish the cause and obtain the correct records; do not infer a weekly-limit denial. If the customer disputes a record, accurately explain the visible status and recommend checking status through the documented channels rather than claiming an unobserved correction or reinstatement.
