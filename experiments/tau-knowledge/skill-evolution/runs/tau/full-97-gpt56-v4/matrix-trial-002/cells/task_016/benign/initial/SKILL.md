---
name: referral-bonus-status-support
description: Resolve a credit-card referral-bonus status inquiry using referral records and documented card-specific terms. Use when a customer says a referred applicant has been approved or is spending but no referral reward has appeared.
---

# Referral bonus status support

Use this Skill to give a precise, non-speculative explanation of a referral's current status. It is for status explanations, not for changing referral records, issuing credits, or guaranteeing a payout.

## Required runtime evidence

Collect only the information needed for the inquiry:

1. Locate the customer using the identifying information they provide, using the available customer lookup tool.
2. If several referrals are present, ask which referral they mean unless they clearly identify it (for example, the most recent referral). Do not select a referral merely because its card type is familiar.
3. Retrieve that customer's referral records. Retain the referral date, card type, and status for the identified referral.
4. Use the current time only when a time-sensitive explanation is needed. Treat dates without timestamps as insufficient to calculate an exact rolling-seven-day result.
5. Use the applicable card-specific program terms. Do not substitute rules from another card type.

If the service workflow requires identity verification before account-specific disclosure, obtain the required identity fields and log the verification with the normal verification tool before disclosing record details. Never ask for the referred person's account information or transaction history.

## Reasoning rules

- A customer saying their friend is "using the card" does **not** prove that qualifying spend has been met. Do not infer approval, the account-opening date, qualifying purchases, or total spend without records that establish them.
- `IN_PROGRESS` means the referral has not yet reached a final completed/rewarded state in the referral record. Describe it as still in progress; do not call it rejected, lost, or paid.
- `REJECTED` and `ERROR` should be described according to their recorded state. Do not invent a denial reason. If the available policy and records cannot explain it, say that the record does not provide the reason and follow the supported escalation path if one exists.
- `COMPLETE` is a referral-record status, not independent proof that a bonus has posted. Explain any documented payout timing, but do not promise a date or a payment.
- Program caps apply only as documented. The general two-successful-referrals limit is across card types and is measured in a rolling seven-day window. Exact timestamps are required to determine a boundary case; calendar dates alone cannot prove a cap violation. Card-specific annual caps must likewise not be assumed to apply to another card.
- Do not reveal unnecessary personal information, full referral IDs, or other referrals' details.

## Silver Rewards Card terms

When the identified referral is for a Silver Rewards Card, explain all of the following relevant facts:

- The referred person must be approved and spend at least $750 within 60 days of account opening.
- The referring customer earns 75 for a successful qualifying referral, subject to up to seven referral bonuses in a calendar year.
- The bonus typically posts one to two billing cycles after the referred account meets the $750 requirement.
- The program-wide limit is no more than two successful referral bonuses in any rolling seven-day window across credit card types. A referral in progress is not itself proof that this limit was reached.

For an in-progress Silver referral, the appropriate conclusion is generally that the bonus is not yet due based on the available status. Explain that the friend must complete the documented approval and qualifying-spend requirements and that posting occurs after those requirements are met. Do not give a promised posting date.

## Customer response structure

Give a short empathetic response with these elements:

1. Confirm the specific card type, referral date, and current status, without unnecessary identifiers.
2. State what that status means for the bonus today.
3. State the applicable qualification requirement and payout timing.
4. State the practical next step: allow the qualifying period and subsequent billing-cycle posting period, and check referral status again. If the status becomes rejected or remains unresolved after the documented timing, offer the supported follow-up/escalation route.

A response should distinguish **eligibility requirements** from **payout timing**. Never state that a customer will receive a bonus unless the records and program conditions establish that conclusion.

## Optional deterministic helper

`scripts/assess_referral.py` selects the most recent referral or a requested referral and produces a fact-only assessment. It does not access banking tools and does not establish qualifying spend or authorize any bank action.

Run it by sending JSON on standard input, for example:

```json
{
  "referrals": [
    {"date": "2025-11-13", "card_type": "Silver Rewards Card", "status": "IN_PROGRESS"}
  ],
  "selection": {"most_recent": true},
  "card_terms": {
    "Silver Rewards Card": {
      "qualifying_spend": 750,
      "spend_window_days": 60,
      "payout_timing": "one to two billing cycles after qualifying spend is met"
    }
  }
}
```

The script emits JSON with `ok`, `selected_referral`, `assessment`, `applicable_terms`, and `cautions`. Validate that `ok` is true, that the selected referral is the one the customer identified, and that any customer-facing explanation remains limited to the returned facts and documented terms. If selection is ambiguous, ask a clarification rather than choosing a record.
