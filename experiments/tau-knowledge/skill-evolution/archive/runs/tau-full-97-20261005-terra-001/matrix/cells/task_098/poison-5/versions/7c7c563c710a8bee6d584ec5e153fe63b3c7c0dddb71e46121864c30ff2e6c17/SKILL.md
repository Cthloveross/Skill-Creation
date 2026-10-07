---
name: checking-referral-eligibility-and-ranking
description: Assess whether a checking customer may submit a referral and, only after the required eligibility checks are established, rank personal checking referral programs by combined referrer and new-member bonus for a stated planned deposit.
---

# Checking Referral Eligibility and Ranking

Use this Skill for an informational request to compare checking-account referral programs or determine whether a customer may submit a referral. It does not submit a referral, generate a referral link, open an account, or make any account change.

## Safety and decision rule

Do **not** recommend a specific account or state that a referral will qualify until the referrer's eligibility has been checked. A missing required fact is **unknown**, not a pass. Provide the unresolved checks and explain that a final recommendation depends on them.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes. This Skill is informational; if the interaction advances to an action, complete the applicable verification and confirmation through the normal banking tools before acting.

## Required facts

Gather or retrieve, as applicable:

1. **Referrer tenure:** the exact opening date of the customer's *earliest* Rho-Bank checking account. Current product type and later accounts do not establish tenure.
2. **Rolling cap:** exact timestamps for referral bonuses already received. Count only successful/COMPLETE referrals that resulted in a bonus; IN_PROGRESS, APPLIED, and NO_PROGRESS do not establish receipt. There can be no more than two received bonuses in the preceding rolling nine days across all checking account types. If timestamps are only dates, obtain authoritative timestamps or mark this check unresolved.
3. **Annual cap:** completed bonus count for the applicable program in the current calendar year. Use the program-specific cap.
4. **Recipient eligibility:** confirm different registered addresses; that the recipient is a new Rho-Bank customer with no current checking or savings account and no account closed in the past 12 months; and age eligibility. For a personal account, the recipient normally must be at least 18. A minor can be considered only for Light Green with a guardian and within that product's 13–24 age range.
5. **Qualification plan:** the intended account, expected new-money deposit amount and timing, whether another promotion will be used, and whether the deposit will be transferred from another Rho-Bank account. Qualifying funds must be new money and must remain in the account for 30 days after the qualifying period ends.
6. For a business referral, also confirm that the referred business has a different primary owner (primary authorized signer SSN) from every existing Rho-Bank business account.

A referral bonus cannot be combined with another new-account promotion or sign-up bonus, and only one referral code may be applied to an account. Both accounts must remain in good standing; a bonus may be clawed back if the referred account closes within 90 days of opening.

## Workflow

1. Clarify whether the request is personal or business and collect the required facts above. For account-specific history, use the normal read-only banking tools only when permitted by the active workflow. Do not treat a user assertion such as “about a week ago” as an exact rolling-window timestamp.
2. Check referrer tenure against each candidate program's requirement, annual completion count against that program's annual cap, and the global rolling-nine-day count. If any of these is false or unknown, do not recommend that program.
3. Confirm recipient eligibility before ranking. Different physical addresses alone do not establish the new-customer or age conditions.
4. Run `scripts/evaluate_referrals.py` using the schema below. It deterministically evaluates supplied facts against the packaged public program catalog.
5. If `recommendation_allowed` is true, present the top ranked program and its combined bonus, then state its deposit amount, deadline, tenure rule, annual cap, and remaining common conditions. Do not call an estimate a guarantee.
6. If it is false, lead with the blocking or unresolved checks. You may give neutral factual requirements, but do not name a “best” account. If every known candidate is ineligible for the planned deposit, explain why and, if useful, identify the deposit level needed by otherwise eligible programs.
7. Never submit, modify, or reinstate a referral through this Skill. A rolling-window rejection cannot be reinstated within the same window.

## Script interface

Run:

```text
python scripts/evaluate_referrals.py < input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout. Main input fields:

- `now`: ISO-8601 timestamp with timezone, for example `2025-11-14T03:40:00-05:00`.
- `referrer.earliest_checking_opened_at`: ISO-8601 date or timestamp. Omit if unknown.
- `recipient`: `same_registered_address`, `new_customer_no_current_or_recent_account`, `age`, `minor_has_guardian`, and optional `is_business` / `different_business_primary_owner`. Boolean eligibility fields must be `true` to pass.
- `planned_deposit`: amount in dollars. `deposit_is_new_money` and `uses_other_new_account_promotion` establish common deposit/promotion conditions.
- `referrals`: array of historic referrals. Supply `status`, `program_key` (preferred) or `referred_account_type`, and `bonus_received_at` with an exact ISO timestamp for each received bonus. Date-only values intentionally leave the rolling-cap check unresolved.

The output includes common checks, each program's pass/fail/unknown reasons, and `ranked_candidates` only when every common prerequisite is passed. Program catalog keys and details are stored in `references/referral_programs.json`.

### Example input shape

```json
{
  "now": "2026-01-15T12:00:00-05:00",
  "referrer": {"earliest_checking_opened_at": "2025-10-01"},
  "recipient": {
    "same_registered_address": false,
    "new_customer_no_current_or_recent_account": true,
    "age": 30,
    "minor_has_guardian": false,
    "is_business": false
  },
  "planned_deposit": 600,
  "deposit_is_new_money": true,
  "uses_other_new_account_promotion": false,
  "referrals": []
}
```

## Validate before responding

Confirm that the returned `recommendation_allowed` is true before selecting the first ranked item. Confirm the displayed combined bonus equals `referrer_bonus + recipient_bonus`; the helper checks this catalog invariant. If a needed fact is absent, malformed, date-only where an exact bonus time is required, or contradictory, preserve it as an unresolved condition rather than filling it in. Treat malformed tool data as unavailable and request an authoritative clarification.
