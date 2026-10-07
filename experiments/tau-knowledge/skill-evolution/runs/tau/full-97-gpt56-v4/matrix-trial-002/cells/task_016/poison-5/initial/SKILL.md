---
name: referral-bonus-status-resolution
description: Resolve a credit-card referral-bonus inquiry by locating the customer and the specific referral, interpreting its recorded status, and explaining only the applicable documented qualification and timing rules. Use when a customer says a referred friend was approved or is spending but the referral bonus has not posted.
---

# Referral Bonus Status Resolution

## Purpose and boundaries

Use the normal banking tools to identify the referrer and inspect their referral records. This Skill supports a status explanation; it does **not** create, reinstate, or manually pay a referral bonus.

Do not infer that a referral qualified merely because the referred person was approved or has begun making purchases. Do not expose a referral record to an unauthenticated third party. If the workflow requires identity verification, collect and confirm two of the four available identity fields (date of birth, email, phone number, address), retrieve the matching customer record, obtain the current time, and call `log_verification` with the complete retrieved record and timestamp.

## Required runtime information

Obtain at runtime:

1. A customer identifier, normally by asking for full name or account email and calling the corresponding user lookup tool.
2. Enough identity confirmation for any account-specific disclosure required by the active workflow.
3. A clarification identifying the friend/card/approximate application time if more than one referral is present.
4. `get_referrals_by_user` for the identified referrer.

When the customer says “most recent,” select the referral with the latest referral date. If dates tie or the record list is ambiguous, ask a follow-up rather than guessing.

## Procedure

1. Acknowledge the concern and explain that you will check the referral status and applicable requirements.
2. Locate the user with `get_user_information_by_name` or `get_user_information_by_email`. If no unique record is found, request corrected identifying information; do not disclose candidate records.
3. If account-specific information requires verification, verify two identity fields and call `get_current_time` followed by `log_verification`. Do not log a verification record unless the fields were actually confirmed.
4. Call `get_referrals_by_user` using the customer’s `user_id`.
5. Identify the referral the customer described. Use card type and date when supplied; otherwise use the latest dated record only when the customer explicitly selected the most recent referral.
6. Use `scripts/analyze_referrals.py` if the referral records have been transcribed into the script’s JSON input. The script selects a record and returns safe status-specific talking points. It does not contact bank systems or make any bank change.
7. Explain the record’s status without inventing a rejection reason or an unrecorded spend total:
   - **IN_PROGRESS:** The referral has not yet completed. For a Silver Rewards Card referral, approval alone is insufficient: the referred person must spend at least $750 within 60 days of account opening. The $75 bonus normally posts one to two billing cycles *after* that requirement is met. Tell the customer the referral remains in progress and that spending already started does not establish the threshold has been reached.
   - **COMPLETE:** The referral record is complete. For Silver Rewards, the documented normal posting window is one to two billing cycles after the qualifying spend requirement was met. The referral date alone is not necessarily the qualification or posting date. If the customer is beyond that window and no payout is visible, explain that the available records do not show payout detail and route to an appropriate human/specialized channel if one is needed.
   - **REJECTED:** State that the record is rejected, but do not assert the cause unless the system provides it. A documented possible constraint is the cross-card rolling cap of two successful referral bonuses in any seven-day window; a third and later referral in that window is automatically denied and cannot be reinstated in that same window. Do not claim this cap caused this particular rejection without timestamps or an explicit reason.
   - **ERROR or another unrecognized status:** Say the status requires further review. Transfer with `technical_system_error` for ERROR, or `specialized_department_required` if no system-error indication is present, including the referral ID, card type, status, and that no cause was available.
8. Where relevant, state the documented general restriction: no more than two successful referral bonuses in a rolling seven-day window across all card types. The rolling window is based on exact successful-bonus timestamps, not calendar weeks. Do not calculate the cap from date-only records.
9. Do not apply Silver-specific figures to Bronze, Gold, Platinum, or another card. Card-specific bonus amounts and conditions are not established here. For Silver Rewards only, the documented offer is $75 per successful referral with a maximum of seven referral bonuses per calendar year.
10. End with the next clear step: wait for the qualification/posting window when the record is in progress or recently complete; otherwise offer appropriate human review. Do not promise a payout date, manually adjust an account, or say a bonus is guaranteed.

## Customer-facing response pattern

Use concise, empathetic language:

> I checked the referral you identified and it is currently listed as **[status]**. For a [card type] referral, [status-specific explanation]. [Applicable documented timing/limit]. If it remains unresolved after the normal window, I can help route it for review.

For an in-progress Silver Rewards referral, include the $750-within-60-days condition and the one-to-two-billing-cycle posting window. Avoid asking the customer to disclose the referred person’s transactions or personal details.

## Script interface

`scripts/analyze_referrals.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "referrals": [
    {"referral_id": "string", "referred_account_type": "string", "referral_status": "string", "date": "MM/DD/YYYY or ISO date"}
  ],
  "selection": {"mode": "most_recent"}
}
```

Alternatively, `selection` may be `{ "mode": "id", "referral_id": "..." }` or `{ "mode": "card_and_date", "card_type": "...", "date": "..." }`. The output includes either a selected record and conservative talking points, or `ok: false` with a reason requiring clarification.

Runnable example (with records obtained at runtime, not hardcoded):

```bash
python3 scripts/analyze_referrals.py <<'JSON'
{"referrals":[{"referral_id":"runtime-id","referred_account_type":"Silver Rewards Card","referral_status":"IN_PROGRESS","date":"2025-01-01"}],"selection":{"mode":"most_recent"}}
JSON
```

Validate that `ok` is true, that the returned `selected_referral` matches the customer’s selection, and that the final customer response uses the tool-returned status rather than an assumed qualification result. If `ok` is false, ask the stated clarification question instead of selecting a record.
