---
name: checking-referral-recommendation
description: Determine whether a checking-account customer may receive referral guidance and rank referral programs by combined referrer and new-member reward. Use for requests to compare, plan, or explain Rho-Bank checking referral offers; do not use it to submit, alter, or reinstate a referral.
---

# Checking referral recommendation

Use this Skill to provide an evidence-based referral recommendation without taking a banking action. The customer may refer a person to a different checking product; referrer tenure is measured from the opening date of the customer's first Rho-Bank checking account, not their current product.

## Required inputs and prerequisite checks

Before giving a referral recommendation, obtain or confirm:

1. The referrer's first-checking-account tenure and that it meets the candidate program's threshold.
2. Referral history and a current timestamp, so the rolling cap can be checked. Only `COMPLETE` referrals represent successful bonuses for this calculation; `IN_PROGRESS`, `APPLIED`, and other statuses are not received bonuses.
3. That the prospective customer is new to Rho-Bank (no existing account and no account closed in the prior 12 months), has a different registered address, and meets the age requirement.
4. The planned qualifying deposit amount, timing, and that it is new money rather than a transfer from another Rho-Bank account.
5. Any product-specific eligibility that is material to the comparison, such as the Gold Years age requirement.

Do not present a customer as eligible if a required present-tense fact is missing or contradicted. For conditions that occur after account opening (deposit retention, both accounts remaining in good standing, and no incompatible promotion), clearly present them as conditions of earning and retaining the bonus.

The rolling limit is at most two successful referral bonuses in any exact rolling nine-day window across checking products. The third and later referral in that window is automatically denied and cannot be reinstated in the same window. If history has only dates and a successful referral falls on the date exactly nine calendar days before the current local date, exact timestamps are required before confirming rolling-window eligibility.

## Workflow

1. Ask targeted clarification questions first if the prerequisite facts are absent. Do not recommend a product before confirming the referrer can submit referrals.
2. Obtain the current timestamp using `get_current_time` and retrieve the referrer's history with `get_referrals_by_user` once the user has supplied their user ID. These are read-only checks; do not perform a referral action.
3. Normalize the collected facts into the JSON schema below and run `scripts/evaluate_referrals.py`.
4. If `rolling_window_verification_required` is true, retrieve exact successful-bonus timestamps through an authorized source before recommending a referral. A date-only record at the nine-day boundary is not enough.
5. If `best_option` is populated, recommend it as the highest combined reward among the programs whose stated requirements can be met. State the individual bonuses, required deposit and deadline, referrer tenure, annual cap, and the continuing program-wide conditions in `future_conditions`.
6. If there is no best option, explain the recorded blockers and request only the missing fact(s), or state that the proposed deposit/tenure cannot qualify for the available programs.
7. Do not create a referral, apply a code, move money, or imply that a bonus is guaranteed. The customer must use the ordinary customer-facing referral flow. Do not invent a referral-link location for an account where the supplied terms do not specify one.

## Program-wide conditions to include in every applicable answer

- The qualifying deposit must be new money, not another Rho-Bank account transfer, and must remain in the new account for at least 30 days after the qualifying period ends.
- The referral cannot be combined with another new-account promotion or sign-up bonus, and only one referral code may be used per new account.
- Both accounts must remain in good standing. A bonus may be clawed back if the referred account closes within 90 days of opening.
- The referred person must be a new Rho-Bank customer, must not share the referrer's registered address, and normally must be at least 18. Light Green is the documented exception that can allow a minor with a guardian.
- A business referral additionally requires a different primary owner from any existing Rho-Bank business account. This Skill's catalog covers consumer checking programs; do not use it to approve a business referral.

## Script interface

Run:

```text
python scripts/evaluate_referrals.py < input.json
```

The runtime wrapper sends the JSON object on stdin and receives one JSON object on stdout. Use this input shape:

```json
{
  "current_time": "YYYY-MM-DD HH:MM:SS TZ",
  "referrer": {"tenure_days": 30},
  "referred": {
    "age_at_least": 18,
    "is_new_customer": true,
    "different_registered_address": true,
    "deposit_amount": 500,
    "deposit_is_new_money": true,
    "deposit_within_days": 60
  },
  "history": [
    {
      "referral_status": "COMPLETE",
      "date": "MM/DD/YYYY",
      "referred_account_type": "Blue Account"
    }
  ]
}
```

`current_time` is required. `history` may be an empty list. A successful record may instead supply `bonus_timestamp` as an ISO-like timestamp; this permits an exact rolling-window decision. `age_at_least` may be an exact age or a confirmed lower bound. Omit unknown facts rather than guessing them.

The script returns:

- `best_option`: the top eligible catalog entry or `null`;
- `eligible_options`: all eligible entries, ordered by combined reward;
- `blocked_options` and `missing_or_unverified`: explain why a comparison cannot include an option;
- `rolling_window`: successful-bonus count and date/timestamp assessment;
- `rolling_window_verification_required`: whether an exact timestamp is necessary before a recommendation;
- `future_conditions`: conditions that must still be met to earn or retain a bonus.

## Validation before responding

Confirm that the recommendation is based on `best_option`, that its `combined_bonus` equals `referrer_bonus + new_member_bonus`, and that the planned deposit meets both the amount and deadline. Confirm the annual count pertains to the selected program and calendar year, while the rolling count includes successful bonuses across all checking products. Never treat an in-progress referral as a received bonus.

If a customer asks to actually submit a referral, explain that this Skill only evaluates terms and use the authorized normal banking workflow separately. Follow all identity, authority, ownership, eligibility, confirmation, and other banking-action controls before any such action.
