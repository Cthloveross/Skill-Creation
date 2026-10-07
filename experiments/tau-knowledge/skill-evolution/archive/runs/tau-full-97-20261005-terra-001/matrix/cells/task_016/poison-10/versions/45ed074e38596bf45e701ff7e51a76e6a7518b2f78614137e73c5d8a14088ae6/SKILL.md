---
name: credit-card-referral-bonus-status
version: 1.0.0
description: Safely resolve a verified cardholder's referral-bonus status, explain documented referral milestones and timing, and identify when policy or account data is insufficient. Use for read-only credit-card referral questions; it does not issue bonuses, alter referrals, or inspect a referred person's account.
---

# Credit-Card Referral Bonus Status

## Scope and guardrails

Use this Skill for a cardholder asking why a referral bonus has not arrived, asking what a referral status means, or asking about documented referral eligibility and timing.

This workflow is read-only. Do not create, retry, reinstate, alter, or pay a referral through this Skill. Do not claim that a referred person has qualified based only on the cardholder's statement, and do not use the referrer's own transaction history as evidence of the referred person's qualifying spend. The referral status returned by the referral system is the authoritative available status.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For account-specific disclosure, authenticate the cardholder before retrieving or discussing their referral records. A stated name, email, or user ID alone is not verification. Confirm two of the four identity fields (date of birth, email, phone number, address) against the user record, then call `log_verification` with the retrieved record fields and a current timestamp. If verification cannot be completed, provide only general program information and do not expose referral records.

## Required runtime information

Use the runtime's normal banking tools only after the prerequisite verification described above:

1. Locate the claimed customer with the identifier they supplied using the appropriate user lookup tool.
2. Ask the customer to confirm two identity fields. Retrieve the current time with `get_current_time`, then call `log_verification` only after two fields match.
3. Call `get_referrals_by_user` for the verified user's ID.
4. Resolve the referral the customer means. If they say “most recent,” choose the latest referral date only when it is uniquely latest. If records tie or the customer identifies a different referral, ask for card type, referral date, or another non-sensitive distinguishing detail.
5. Assess the returned status using the table below and the card-specific rules actually documented for that card. Use `scripts/assess_referral.py` to make the record selection and status assessment deterministic when records are available as JSON.

Do not call `get_credit_card_transactions_by_user` to infer whether the referred friend met spend requirements: that tool concerns the requesting user and cannot establish the invitee's qualifying activity. Do not seek or disclose the referred person's account details.

## Status interpretation and response actions

| Status | Meaning | Appropriate response |
|---|---|---|
| `COMPLETE` | The referred person opened an account and met the applicable bonus criteria. | Explain that the bonus is granted under the applicable terms; apply any documented payout timing for that card. |
| `IN_PROGRESS` | The referred person opened an account and is still working toward the applicable bonus criteria. | Explain that the bonus is not yet due. Monitor the referral; do not take manual action. |
| `NO_PROGRESS` | The referred person has not applied. | The cardholder may remind the invitee to start an application. |
| `APPLIED` | The application is awaiting a decision. | Await the decision; no manual intervention is needed. |
| `REJECTED` | The user has too many referral processes going on. | Do not recommend an immediate retry. Review applicable referral activity and limits before discussing next steps. |
| `ERROR` | An error occurred in the referral process. | Advise a later retry or internal escalation if it persists. Do not fabricate a resolution. |

Treat an unrecognized or missing status as unavailable data and obtain clarification or escalate through the approved support path rather than guessing.

## Documented program rules

Only state rules that apply to the identified card and are documented in the available knowledge. Card referral offers, eligibility, and qualification requirements can vary by card.

For the documented **Silver Rewards Card** offer:

- The invitee must be approved and spend at least $750 within 60 days of account opening.
- The bonus typically posts one to two billing cycles after that requirement is met.
- The cardholder earns 75 for each successful referral, up to seven referral bonuses per calendar year.

Across documented credit-card referral offers, no more than two successful referral bonuses may be received in a rolling seven-day window. The window is based on exact successful-bonus timestamps, not calendar-week dates, and applies across card types. A third or later referral in that window is automatically denied and cannot be reinstated within that same window. Do not decide the rolling-window result from referral creation dates alone; exact, complete successful-bonus timestamps are required.

If the identified card is not Silver Rewards Card and no card-specific offer is available, explain the known status but do not invent a spend threshold, payout timing, bonus amount, or annual cap. Direct the cardholder to the app or customer service for the current offer.

## Producing the customer response

Keep the response focused and do not reveal unnecessary referral IDs, other referral history, the invitee's identity, or other account details. Include:

1. the selected card type and referral date when verified and unambiguous;
2. the referral status and its plain-language meaning;
3. only the documented requirements and timing that apply to that card;
4. the next action, or the fact that no action is required; and
5. an appropriately limited caveat if a rolling-limit determination cannot be made from exact timestamps.

For an `IN_PROGRESS` record, say that the invitee's account is open and the program criteria are still pending; do not say that making some transactions proves the criteria were met. For a documented Silver Rewards Card record, explain the $750-in-60-days threshold and the one-to-two-billing-cycle posting period after the threshold is met.

If a completed referral is outside its documented normal posting interval, or an `ERROR` persists, document the observed status and route it through the organization’s approved internal escalation process. If the customer requests a person, use `transfer_to_human_agents` with the applicable available reason and a concise summary of verification and checks already completed.

## Deterministic helper

`scripts/assess_referral.py` accepts one JSON object on stdin and emits one JSON object on stdout. It performs no banking action and does not read external files.

Input schema:

```text
{
  "referrals": [
    {
      "referral_id": "optional opaque identifier",
      "referred_account_type": "card type",
      "referral_status": "COMPLETE | IN_PROGRESS | NO_PROGRESS | APPLIED | REJECTED | ERROR",
      "date": "YYYY-MM-DD or MM/DD/YYYY"
    }
  ],
  "selected_referral_id": "optional opaque identifier",
  "selection": "most_recent",
  "programs": {
    "card type": {
      "qualifying_spend": "optional documented value",
      "spend_window_days": "optional documented value",
      "payout_timing": "optional documented value",
      "annual_bonus_cap": "optional documented value"
    }
  },
  "weekly_limit": {
    "cap": 2,
    "rolling_days": 7,
    "at_time": "optional ISO-8601 timestamp",
    "successful_bonus_times_before_candidate": ["ISO-8601 timestamps"],
    "history_complete": true
  }
}
```

`selected_referral_id` takes precedence. Without it, `selection` must be `most_recent`; tied latest dates produce an ambiguity error. `programs` is optional and should contain only validated, documented offer terms. The weekly-limit result is deliberately `insufficient_data` unless complete exact timestamps, a candidate time, and the applicable policy are supplied.

Run it through the packaged-script runtime with `relative_path` set to `scripts/assess_referral.py` and the input object as `input_json`. Review `errors` before relying on `assessment`. A valid result has `ok: true`, an empty `errors` array, and a non-null `assessment`; preserve the helper's uncertainty results rather than converting them into a definitive eligibility decision.
