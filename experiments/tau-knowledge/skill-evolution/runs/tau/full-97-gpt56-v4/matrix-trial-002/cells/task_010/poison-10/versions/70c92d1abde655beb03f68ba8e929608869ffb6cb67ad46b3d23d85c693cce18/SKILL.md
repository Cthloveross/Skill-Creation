---
name: credit-card-referral-status-explainer
description: Safely investigate and explain why a credit-card referrer received, is awaiting, or was denied referral bonuses. Use for account-specific referral-status questions when referral records and card-program rules are available.
---

# Credit Card Referral Status Explainer

Use this workflow to handle questions such as “I referred several friends but received fewer bonuses.” It distinguishes completed, pending, and denied referrals without promising an unsupported payment or denial reversal.

## Required controls

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

1. Treat a request for a customer’s referral records as account-specific information. Confirm authority and verify identity by having the customer confirm two of the four stored fields: date of birth, email, phone number, and address.
2. Retrieve the customer record only from an identifier supplied by the customer or a matching lookup. Do not disclose stored identity fields merely to solicit confirmation.
3. After two fields match, obtain the current timestamp and create the required verification audit record with the verified customer details and timestamp.
4. Only after verification, retrieve the customer’s referral records. Confirm that the record belongs to the verified customer before discussing it.
5. This is a read-only inquiry. Do not change referrals, bonuses, accounts, or profile data. No bank action is implied by the analysis script.
6. If identity, authority, or ownership cannot be verified, provide only general program rules and invite the customer to complete verification. Do not reveal account-specific referral statuses.

## Investigation method

1. Obtain referral records using the normal referral lookup tool. Preserve each referral’s ID, referred card type, status, and date/timestamp.
2. Evaluate the rolling weekly cap across **all** card types:
   - At most two successful referral bonuses can be received in any rolling seven-day window.
   - The third and later referral in such a window is automatically denied.
   - The relevant window is timestamp-based, not a calendar week. If only dates are available, say that the assessment is based on the recorded dates and exact timestamps could affect a boundary case.
   - A referral denied by this limit cannot be reinstated during that same rolling window. Do not promise an override.
3. Run `scripts/analyze_referrals.py` with normalized records to identify completed referrals in the seven days before each rejected record. Its output is an evidence aid, not an authorization to alter records.
4. Explain each record conservatively:
   - `COMPLETE`: state that it is recorded as complete; do not invent a bonus amount or payout date unless the card’s specific program terms are available.
   - `IN_PROGRESS`: state that it has not yet completed the program’s qualification process. Give card-specific qualifying requirements only when supported by supplied program terms.
   - `REJECTED`: say the rolling cap is a likely explanation only when the analyzer identifies at least two earlier completed referrals within the preceding seven days. Otherwise say the record does not provide a reason and avoid guessing.
   - Any other or missing status: report it as unavailable/unknown and recommend checking the referral dashboard or customer service.
5. Apply supported card terms precisely:
   - Silver Rewards: the referred person must be approved and spend at least $750 within 60 days of account opening. The $75 bonus generally posts one to two billing cycles after that condition is met, subject to the annual maximum of seven bonuses.
   - Platinum Rewards: the referred person must be approved and spend at least $1,500 within 90 days of account opening. The bonus is $100, subject to up to seven referral bonuses per calendar year; self-referrals and duplicate applications do not qualify, and the referrer’s account must be in good standing.
   - For card types without supplied terms, do not infer amount, eligibility, or payout timing. Say that each card has its own offer and qualification rules.
6. Give a short customer-facing conclusion: acknowledge the concern, identify the two completed records if verified, explain a cap-supported denial, explain any pending qualification, and state what will happen next. For a pending Silver or Platinum referral, use only the relevant spending/deadline rule and never claim that spending or approval occurred unless records establish it.

## Script interface

`scripts/analyze_referrals.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "referrals": [
    {
      "referral_id": "string (optional)",
      "referred_account_type": "string (optional)",
      "referral_status": "COMPLETE | IN_PROGRESS | REJECTED | other",
      "date": "YYYY-MM-DD or ISO-8601 timestamp"
    }
  ]
}
```

Output contains normalized records, per-rejected-referral completed records in the prior rolling seven days, and a `likely_rolling_cap` boolean. Invalid or absent dates are returned as validation errors and are not used to establish a cap. Date-only records use inclusive calendar-date comparison and are marked as approximate.

Example executor call (substitute live retrieved records; do not embed customer data in the Skill):

```sh
python3 scripts/analyze_referrals.py <<'JSON'
{"referrals":[{"referral_id":"...","referral_status":"COMPLETE","date":"2025-01-01"}]}
JSON
```

## Validation before responding

- Confirm identity verification and audit logging occurred before using account-specific results.
- Confirm every analyzed referral belongs to the verified referrer.
- Ensure no `REJECTED` referral is attributed to the weekly cap without two earlier `COMPLETE` records in its prior seven-day window.
- Ensure Silver and Platinum figures, deadlines, annual limits, and payout timing are used only for the matching card type.
- Do not claim a referral is approved, has met spend, will be paid, or can be reinstated unless the available record and supported policy establish that conclusion.
