---
name: credit-card-referral-status-support
description: Resolve a customer's credit-card referral-bonus question after referral records have been located. Use to identify the relevant referral, explain its documented status, state only the applicable card-specific requirements available in knowledge, and set accurate expectations without generating referral links or taking account actions.
---

# Credit Card Referral Status Support

## When to use
Use this Skill when a customer asks why a referral bonus has not arrived or asks for the status of an existing credit-card referral. This Skill is for read-only status explanation; it does not create referrals, issue bonuses, modify accounts, or contact the referred person.

## Required runtime inputs
Obtain, using the normal support tools, enough information to identify the referrer and the intended referral:

1. Locate the customer record using the identifier they provide.
2. Retrieve that customer's referrals with `get_referrals_by_user`.
3. If there is more than one plausible record, ask for the card type, approximate application/opening date, or another non-sensitive differentiator. Do not guess solely from an ambiguous description.
4. If the customer confirms that it is the most recent referral, select the most recent record by its recorded date. Use `scripts/referral_assessment.py` if records are available as structured JSON.

A referral-status explanation does not itself require a referral-link tool. Do not generate a referral link on the customer's behalf.

## Status interpretation and response rules
Interpret the selected record exactly as follows:

- `COMPLETE`: The referred person has met the referral criteria. State that the bonus will be granted under the applicable program terms.
- `IN_PROGRESS`: The referred person successfully opened the account and is still working toward the bonus criteria. Tell the customer that no action is required now and the referral should be monitored until criteria are met. Do not say that a bonus has been earned, posted, or is overdue.
- `NO_PROGRESS`: The referred person has not applied. The referrer may remind the invitee to start an application using the referral link.
- `APPLIED`: The application was submitted and is awaiting a decision. Tell the customer to await the decision; no manual intervention is needed.
- `REJECTED`: Explain that there are too many referral processes underway. Do not advise an immediate retry; review the existing referral activity before offering next-step advice.
- `ERROR`: Explain that an error occurred. Advise retrying later or escalating internally if it persists.
- Any unknown or missing status: state that the referral cannot be interpreted from the available record and obtain or escalate for accurate status information rather than inventing an explanation.

## Card-specific documented terms
Check the available knowledge for the selected card before quoting amounts, spending thresholds, caps, or payout timing. Terms differ by card.

For a **Silver Rewards Card** referral, the documented terms are:

- The referred person must be approved and spend at least **$750 within 60 days of account opening**.
- The referral bonus is **75** for each successful referral, with up to **7 referral bonuses per calendar year**.
- Once the qualifying spend requirement is met, the bonus typically posts within **one to two billing cycles**.

Therefore, for a selected Silver Rewards referral in `IN_PROGRESS`, explain that approval and card use alone do not establish completion: the qualifying $750 spend must be met within the 60-day period, then the normal one-to-two-billing-cycle posting window applies. Do not claim visibility into the referred person's purchases, exact remaining spend, or qualifying date unless a permitted tool result explicitly supplies it.

General referral material also states that bonuses are limited to at most two successful referrals in a rolling seven-day window across card types. It is a program restriction, not a reason to overwrite or reinterpret a currently reported referral status. Only discuss it when relevant to the customer's question or an established status/record; do not calculate it from date-only records as exact timestamps are required.

## Customer-facing response structure
Give a concise, privacy-preserving answer:

1. Identify the relevant card and referral date only if needed to distinguish the record.
2. State the exact status and what it means.
3. State the documented requirements and expected timing that apply to that card, if available.
4. State the appropriate next action (usually monitor for `IN_PROGRESS`).

Avoid exposing referral IDs, other referral records, the referred person's personal information, or account data unrelated to the selected referral. Do not promise a payment date or represent a typical timing window as a guarantee.

## Structured helper
`scripts/referral_assessment.py` accepts JSON on stdin and emits JSON on stdout.

Input schema:

```json
{
  "referrals": [
    {
      "referral_id": "optional string",
      "referred_account_type": "string",
      "referral_status": "string",
      "date": "MM/DD/YYYY or YYYY-MM-DD"
    }
  ],
  "selector": {
    "referral_id": "optional exact ID",
    "card_name": "optional exact card name",
    "date": "optional date",
    "most_recent": false
  }
}
```

Exactly one unambiguous selector is required. Set `most_recent` to `true` only after the customer has confirmed that they mean the most recent referral. The output reports either a selected record plus neutral status guidance, or a machine-readable error such as `ambiguous_selection`, `no_matching_referral`, or `unsupported_status`.

Runnable example:

```bash
python3 scripts/referral_assessment.py <<'JSON'
{"referrals":[{"referral_id":"r1","referred_account_type":"Silver Rewards Card","referral_status":"IN_PROGRESS","date":"2025-01-15"}],"selector":{"referral_id":"r1"}}
JSON
```

Validate that `ok` is `true`, that `selected.referral_id` (when supplied) is the intended record, and that `status_guidance` matches the record's reported status. The helper does not determine qualification, bonus posting, program limits, or dates beyond choosing a record by the supplied date.
