---
name: checking-referral-eligibility-and-optimizer
description: Safely determine checking-referral eligibility and recommend a compliant, highest-value account plan for multiple individual and business referrals. Use for questions about referral bonuses, qualification, account selection, annual caps, or the shared rolling nine-day limit.
---

# Checking Referral Eligibility and Optimizer

## Purpose

Use this Skill before providing referral terms or account recommendations. The referral policy requires eligibility to be checked first. The Skill separates verified eligibility from conditional planning so that missing facts are never represented as approval.

## Required runtime checks

1. Obtain the current timestamp with `get_current_time`.
2. Retrieve the referrer's referral history with `get_referrals_by_user`.
3. Retrieve the checking-account history required for tenure:
   - Unlock `get_all_user_accounts_by_user_id_3847` using `unlock_discoverable_agent_tool`.
   - Call it through `call_discoverable_agent_tool` with the user's ID.
   - Find the earliest opening date among checking accounts. Tenure is based on that date, not the currently held product.
   - Confirm the referrer has an active checking relationship if the returned status data supports that conclusion.
4. Count `COMPLETE` referrals by referred account type in the relevant calendar year. Compare each count with that program's annual cap.
5. Count successful bonuses occurring in the preceding rolling nine days across *all* checking products. Use exact bonus timestamps when available. A date-only record at a nine-day boundary is insufficient for an exact rolling-window decision.
6. Verify all referred-party facts before issuing a recommendation:
   - Every referred party is a new Rho-Bank customer with no open, existing, or closed Rho-Bank account during the last 12 months.
   - Each individual is registered at a different address than the referrer.
   - Each business has a primary authorized signer whose SSN is not the primary owner of an existing Rho-Bank business account.
   - Confirm age, deposit ability, business age/enterprise status where applicable, and that no incompatible new-account promotion will be used.

A name search returning no record is not conclusive proof of a future applicant's new-customer status or address. Ask for the required confirmation when authoritative data is unavailable.

If the checking-account tool cannot establish the first checking-account opening date, do **not** provide account-specific referral recommendations or bonus terms. Explain that the tenure prerequisite cannot yet be verified, and direct the user to their account history/support for the opening date. Do not transfer unless the user requests a human or another supported transfer reason applies.

## Selecting an account after eligibility is verified

1. Load `references/referral_program_catalog.json`; it is a normalized catalog of the supplied referral terms.
2. For every candidate, reject programs that fail age, deposit, company-age, enterprise, tenure, annual-cap, or required confirmation conditions.
3. For eligible individual programs, rank by combined referrer and referred-party bonus, unless the user gives another stated account requirement that changes the set of qualifying programs.
4. For business programs during the active 2025-11-01 through 2025-11-30 promotion, selection is constrained by promotion priority: recommend Sky Blue first if it meets every requirement; otherwise Lime Green if it meets every requirement; consider another qualifying business account only if neither does. Never recommend a promotional account that fails a requirement.
5. Enforce the shared maximum of two successful referral bonuses in any rolling nine-day period. This limit applies across all account types and is in addition to annual caps. If more than two planned referrals could qualify together, plan no more than two qualifying bonuses in a batch, then wait until the oldest successful bonus is more than nine days old before the next qualifying bonus. Do not promise an exact availability moment without exact timestamps.
6. State that qualifying deposits must be new money (not transferred from another Rho-Bank account), must arrive in the program's deposit window, and must remain for 30 days after that window ends. Only one referral code and no other new-account/sign-up promotion may be used. Both accounts must remain in good standing; closing the referred account within 90 days can cause a clawback.

Annual caps apply to earned bonuses in a calendar year. Do not reserve a cap merely by sharing a link; use the actual qualification/bonus timing when it is known.

## Deterministic planner

Run:

```text
python scripts/plan_referrals.py < request.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout. It performs no banking action and does not query tools.

### Input schema

```json
{
  "current_time": "ISO-8601 timestamp",
  "referrer": {
    "earliest_checking_opened": "ISO-8601 date or timestamp, or null",
    "has_active_checking": true,
    "good_standing": true
  },
  "referrals": [
    {"referred_account_type": "Catalog account name", "referral_status": "COMPLETE", "date": "ISO-8601 timestamp"}
  ],
  "candidates": [
    {
      "id": "nonempty caller-supplied label",
      "kind": "individual or business",
      "age": 0,
      "available_deposit": 0,
      "new_customer_confirmed": true,
      "different_address_confirmed": true,
      "no_other_new_account_promotion": true,
      "guardian_confirmed": true
    }
  ],
  "programs": ["optional override of catalog programs"],
  "promotion_active": true
}
```

Business candidates use `company_age_years` or `formation_date`, `different_primary_owner_confirmed`, and `enterprise_confirmed` when relevant. Unknown facts should be omitted or set to `null`, never guessed. When `programs` is omitted, the packaged catalog is used.

### Output and validation

The output contains `errors`, shared `eligibility_blockers`, rolling-window capacity, annual usage, and a result for every candidate. A candidate's `eligible_programs` list contains only programs with no blockers; `pending_programs` identifies programs that could qualify if named facts are confirmed; and `disqualified_programs` contains factual failures. `recommended_program` is present only for fully eligible programs. Validate that `errors` is empty and that every recommendation is in `eligible_programs`. Treat `eligibility_blockers`, pending facts, and rolling timing as mandatory follow-up rather than approval.

The executor should turn the validated output into a customer response: explain verified eligibility first, give the recommended account and both bonuses only after the checks pass, list the qualifying deposit and deadline, state remaining cap/rolling timing, and clearly enumerate unresolved confirmations.
