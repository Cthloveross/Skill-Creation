---
name: referral-bonus-status-explanation
description: Determine the relevant credit-card referral record, interpret its status, and give a customer-safe explanation of qualification and payout timing. Use when a referrer asks why a referral bonus has not arrived, especially when the referral is described as recent, approved, or in progress.
---

# Referral bonus status explanation

Use this Skill to diagnose the *status* of a referral from the referrer's referral records. It does not create, retry, reinstate, or pay a referral bonus.

## Supported information and rules

- `IN_PROGRESS` means the referred person successfully opened an account and is still working toward the referral-bonus criteria. The documented action is to monitor until the criteria are met.
- For a **Silver Rewards Card** referral, the referred person must be approved and spend at least **$750 within 60 days of account opening**. Once that requirement is met, the bonus typically posts within **one to two billing cycles**.
- Silver Rewards Card referral bonuses are limited to **7 per calendar year**.
- Across all credit-card types, a customer can receive at most **2 successful referral bonuses in a rolling 7-day window**. This is based on exact successful-bonus timestamps, not merely referral record dates. A third or later referral in that window is automatically denied and cannot be reinstated during the same window.
- A `COMPLETE` referral has met the criteria to get the referral bonus. It does not by itself provide a precise posting timestamp.
- `APPLIED` means awaiting an application decision; `NO_PROGRESS` means no application has started; `REJECTED` means too many referral processes are underway; and `ERROR` is a processing error.

Do not invent qualification requirements, reward amounts, or posting times for Bronze, Gold, Platinum, EcoCard, or other card types whose card-specific terms were not supplied.

## Workflow

1. Use referral records already supplied in the conversation or observations. If records are absent, identify the referrer with an available normal lookup tool and retrieve their referrals.
2. Ask which referral the customer means if there is no reliable selector. If they say “most recent,” choose the uniquely latest dated record. Do not guess among tied or undated records.
3. Normalize the relevant records into the JSON schema below and run `scripts/referral_status_advisor.py`. The script deterministically selects a record and returns customer-safe wording and limitations.
4. Explain the result plainly:
   - State the selected card type, record date, and status.
   - For a Silver `IN_PROGRESS` referral, explain the $750/60-day requirement and that the 1–2 billing-cycle posting period begins only after the requirement is met.
   - Do not say the referred person has reached $750, that a bonus is already owed, or that a cap caused the delay unless the supplied record/status explicitly establishes it.
   - Do not calculate a rolling-seven-day result from date-only referral records. Exact successful-bonus timestamps are required.
5. If the selected record is `ERROR`, advise retrying later or internal escalation if it persists. If it is `REJECTED`, do not advise an immediate retry; review existing referral activity. If it is `COMPLETE` but the customer says the relevant Silver payout window has already passed, explain that the record alone cannot establish the actual qualifying-spend date or billing cycles and route through the normal internal follow-up process if one exists.

No account change or bank action is needed for a normal `IN_PROGRESS` explanation. Do not access or disclose the referred person's account or transaction data; the referral status is the authoritative available signal.

## Identity and privacy

Use only the minimum account information needed to answer. A name-based lookup identifies a possible record but is not, by itself, successful identity verification. If the runtime or requested action requires verification, obtain confirmation of two of the four required fields (date of birth, email, phone number, and address), then obtain the current time and call `log_verification` with all required fields. Never log a verification that was not actually completed.

## Script interface

Run from the package root:

```text
python scripts/referral_status_advisor.py < referrals.json
```

Input JSON:

```json
{
  "referrals": [
    {
      "referral_id": "optional record identifier",
      "referred_account_type": "card type",
      "referral_status": "COMPLETE | IN_PROGRESS | NO_PROGRESS | APPLIED | REJECTED | ERROR",
      "date": "MM/DD/YYYY, YYYY-MM-DD, or ISO datetime"
    }
  ],
  "selector": {
    "mode": "most_recent | referral_id",
    "referral_id": "required only when mode is referral_id"
  }
}
```

Output JSON always includes `ok`. On success it includes a minimally scoped `selected_referral`, `customer_response`, and `do_not_claim`. On failure it includes `error` and a `next_step`. The executor should use the returned response as a factual draft, adapt it conversationally, and honor its limitations.

## Validation before responding

- Confirm the selected record is the one the customer described.
- Confirm status is one of the supported values.
- For a Silver `IN_PROGRESS` result, ensure the response says the spend must occur within 60 days **of account opening**, and that payout timing is **after** the spend requirement is met.
- Do not turn a date-only record into a claimed weekly-cap calculation or a claimed payout date.
- If the script reports ambiguity, ask the customer for a card type, application/referral date, or another non-sensitive way to distinguish the referral.
