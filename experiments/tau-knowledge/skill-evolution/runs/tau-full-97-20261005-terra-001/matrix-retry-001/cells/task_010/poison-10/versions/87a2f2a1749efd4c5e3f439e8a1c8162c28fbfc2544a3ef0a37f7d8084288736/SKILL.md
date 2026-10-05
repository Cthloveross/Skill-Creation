---
name: credit-card-referral-status-explainer
description: Explain why a credit-card customer has or has not received referral bonuses by securely reviewing referral records, interpreting referral statuses, and checking documented rolling seven-day referral-cap evidence. Use for account-specific referral-status and referral-bonus questions; do not use it to generate a referral link or perform a banking transaction.
---

# Credit Card Referral Status Explainer

## Safety and account prerequisites

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Before disclosing account-specific referral records, verify the requester is the customer and authorized to receive the information. Unless a valid verification is already recorded for the interaction, confirm two of the four identity fields (date of birth, email, phone number, or address), obtain the current timestamp with `get_current_time`, and call `log_verification` with the complete required customer record. Do not reveal referral details before this is complete.

This workflow is read-only. Do not change referral records, attempt to reinstate a rejected referral, generate a referral link on the customer’s behalf, or promise a payout date or amount that is not documented for the referred card.

## Procedure

1. Obtain the verified customer ID, then use `get_referrals_by_user` for that ID. Use `get_current_time` when evaluating a current rolling seven-day period or when a verification timestamp is needed.
2. Normalize each returned referral status and explain it using the status meanings below. Keep card names and referral identifiers limited to what is necessary for the authenticated customer.
3. Run `scripts/analyze_referrals.py` on the referral records and the current date/time. Its rolling-window results are evidence aids, not a replacement for the stored referral status. Date-only records cannot establish the order of events occurring on the same day.
4. For each referral, explain the result plainly:
   - `COMPLETE`: the referred person met the applicable criteria and the bonus is granted under that card’s documented program terms.
   - `IN_PROGRESS`: the referred person successfully opened an account but has not yet met all bonus criteria. No action is required; monitor the referral.
   - `NO_PROGRESS`: the invitee has not applied. The customer may remind the invitee to begin an application.
   - `APPLIED`: the application awaits a decision; no manual intervention is needed.
   - `REJECTED`: do not retry immediately. Explain that the recorded status indicates too many referral processes were underway. If the analysis shows at least two completed referrals in the seven days before the rejection, say the rejection is consistent with the automatic rolling weekly limit. A referral denied under that limit cannot be reinstated in that same seven-day window.
   - `ERROR`: advise retrying later or escalating internally if the condition persists.
5. Apply card-specific terms only when the card has a documented program in `references/referral_policy.md`. For cards without documented terms, say that the applicable offer cannot be confirmed from the available documentation rather than inventing requirements or bonus values.
6. State the cross-card rule when relevant: no more than two referral bonuses may be received in any rolling seven-day window. The third and later referrals in that period are automatically denied, including referrals for different card types. This is based on exact timestamps; results based only on dates are approximate.
7. End with the applicable next step: monitor an in-progress referral, await an applied referral decision, wait until the rolling count falls below the limit before making a future referral, or report a persistent error. Do not imply that waiting changes a past rejected record to complete.

## Response construction

A useful response normally contains:

- A concise summary of how many referrals are complete, pending/in progress, rejected, or otherwise unresolved.
- The individual reason for each referral that did not produce a bonus.
- A careful weekly-limit explanation when record dates support it.
- The documented remaining condition and normal payout timing only for a known card program.
- A clear distinction between a future referral potentially becoming eligible after the window changes and reinstating a previously rejected referral, which is not available within its denial window.

Avoid attributing a rejection to a weekly cap solely because it is rejected. The stored `REJECTED` status supplies the general reason; the date analysis can establish only whether the observed record pattern is consistent with the cap. Do not speculate about approval, spend, self-referral, duplication, or a card offer when the records do not establish it.

## Referral-analysis helper

`scripts/analyze_referrals.py` accepts JSON on standard input and emits JSON on standard output. It uses only the Python standard library.

Input schema:

```json
{
  "current_time": "YYYY-MM-DD or ISO-8601 timestamp",
  "referrals": [
    {
      "referral_id": "optional opaque identifier",
      "referred_account_type": "card name",
      "referral_status": "COMPLETE | IN_PROGRESS | NO_PROGRESS | APPLIED | REJECTED | ERROR",
      "date": "YYYY-MM-DD or ISO-8601 timestamp"
    }
  ]
}
```

`current_time` is required. Each referral needs `referral_status` and `date`; `referral_id` and `referred_account_type` are optional. The helper returns status counts, a normalized record list, completed referrals in the current rolling seven-day interval, per-rejection prior-completion evidence, and validation errors.

Example runtime invocation:

```json
{
  "relative_path": "scripts/analyze_referrals.py",
  "input_json": {
    "current_time": "2025-01-15T12:00:00-05:00",
    "referrals": [
      {"referral_status": "COMPLETE", "date": "2025-01-12"},
      {"referral_status": "IN_PROGRESS", "date": "2025-01-14"}
    ]
  }
}
```

Validate the result before relying on it: `validation_errors` must be empty for a complete analysis, `status_counts` should reconcile with the number of accepted records, and each rejected record requiring a cap explanation should have a corresponding item in `rejection_window_analysis`. If records have only calendar dates, describe cap findings as date-based and do not claim an exact timestamp ordering.

## Limits and unsupported cases

- This skill does not determine whether a customer is eligible for a new referral link. That requires the documented referral-link pre-check and must never be done by generating a link for the customer.
- It cannot determine a bonus amount, spend qualification, or payout timing for an undocumented card.
- It cannot reverse a `REJECTED` referral or override the weekly cap.
- If account records are unavailable after successful identity verification, explain that the records cannot currently be reviewed and follow the normal internal support process for a persistent technical issue.
